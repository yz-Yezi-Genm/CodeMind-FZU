import unittest
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from backend.contracts import (
    ChunkIndexStatus, DocumentMetadata, DocumentPackage, FileProcessingStatus,
    IndexingStatus, KnowledgeIndexer, ParsedChunk, ParsedFile, RetrievalRequest,
    RetrievalStatus, Retriever,
)
from backend.retrieval.local import LocalBM25Retriever


def sample(record_code="TEST-1", **metadata_updates):
    metadata = {
        "title": "合成资料",
        "document_type": "测试",
        "category_name": "综评与奖学金",
        "business_direction_codes": ["POLICY_AFFAIRS"],
        "record_code": record_code,
        "version_no": "v1",
        "source_url": "https://example.invalid/policy",
        "source_verification_status": "verified",
        "timeliness_verification_status": "current",
        "extraction_status": "extracted",
        "v1_inclusion_status": "included",
        "retrieval_status": "enabled",
    }
    return DocumentPackage(
        metadata=DocumentMetadata(**(metadata | metadata_updates)),
        files=[
            ParsedFile(
                file_role="extracted", storage_key="text.md", original_name="text.md",
                processing_status=FileProcessingStatus.EXTRACTED,
            ),
            ParsedFile(file_role="original", storage_key="policy.pdf", original_name="policy.pdf"),
        ],
        chunks=[
            ParsedChunk(
                chunk_no=1, content="奖学金申请需要提交申请表。",
                source_file_key="text.md", original_file_key="policy.pdf",
                locator="第 2 行", original_locator="第 3 页",
            ),
            ParsedChunk(chunk_no=2, content="奖学金名单公示。", source_file_key="text.md"),
        ],
    )


class LocalRetrievalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = LocalBM25Retriever()
        self.indexer: KnowledgeIndexer = self.store
        self.retriever: Retriever = self.store

    async def search(self, query="奖学金申请", **filters):
        return await self.retriever.retrieve(RetrievalRequest(query=query, **filters))

    async def test_rank_and_trace_matching_chunks(self):
        package = sample()
        indexed = await self.indexer.index_document(package)
        hits = await self.search()
        self.assertEqual(indexed.status, IndexingStatus.INDEXED)
        self.assertEqual(indexed.indexed_count, 2)
        self.assertEqual(len(hits), 2)
        self.assertGreater(hits[0].score, hits[1].score)
        self.assertGreater(hits[1].score, 0)
        self.assertEqual(await self.search(top_k=1), hits[:1])
        best = hits[0]
        self.assertEqual((best.document_id, best.version_id), (indexed.document_id, indexed.version_id))
        self.assertEqual(best.content, package.chunks[0].content)
        self.assertEqual(best.title, package.metadata.title)
        self.assertEqual(best.source_url, package.metadata.source_url)
        self.assertEqual(best.locator, "第 2 行")
        self.assertEqual(best.original_locator, "第 3 页")
        self.assertIsNone(hits[1].original_locator)
        self.assertEqual(best.retrieval_status, RetrievalStatus.ENABLED)
        self.assertNotEqual(best.chunk_id, hits[1].chunk_id)
        self.assertEqual(best.file_id, hits[1].file_id)

    async def test_request_filters_and_no_match(self):
        self.assertEqual(await self.search(), [])
        await self.indexer.index_document(sample())
        self.assertEqual(await self.search("量子纠缠"), [])
        self.assertEqual(await self.search("？！"), [])
        self.assertEqual(await self.search(category_name="培养方案与学位要求"), [])
        self.assertEqual(await self.search(business_direction_code="CAREER"), [])
        self.assertTrue(await self.search(
            category_name="综评与奖学金", business_direction_code="POLICY_AFFAIRS"
        ))

    async def test_unopened_packages_do_not_affect_results_or_scores(self):
        await self.indexer.index_document(sample())
        initial = await self.search()
        for status in ("blocked", "review_only"):
            package = sample(status, retrieval_status=status)
            result = await self.indexer.index_document(package)
            self.assertEqual(result.indexed_count, 2)
            self.assertEqual(package.metadata.retrieval_status, status)
        self.assertEqual(await self.search(), initial)

    async def test_reindex_replaces_version_and_revokes_access(self):
        package = sample()
        first = await self.indexer.index_document(package)
        hits = await self.search()
        self.assertEqual(await self.indexer.index_document(package), first)
        self.assertEqual(await self.search(), hits)
        package.chunks.pop()
        await self.indexer.index_document(package)
        self.assertEqual([hit.chunk_id for hit in await self.search()], [hits[0].chunk_id])
        package.metadata.retrieval_status = RetrievalStatus.BLOCKED
        await self.indexer.index_document(package)
        self.assertEqual(await self.search(), [])

    async def test_invalid_revocation_still_removes_only_its_version(self):
        other = await self.indexer.index_document(sample(version_no="v2"))
        for status in (RetrievalStatus.BLOCKED, RetrievalStatus.REVIEW_ONLY):
            with self.subTest(status=status):
                package = sample()
                await self.indexer.index_document(package)
                self.assertEqual(len(await self.search()), 4)
                package.metadata.retrieval_status = status
                package.chunks[0].source_file_key = "missing.md"
                with self.assertRaises(ValidationError):
                    await self.indexer.index_document(package)
                self.assertEqual(
                    {hit.version_id for hit in await self.search()}, {other.version_id}
                )

    async def test_unvalidated_mutations_cannot_open_a_package(self):
        package = sample(source_verification_status="pending", retrieval_status="blocked")
        package.metadata.retrieval_status = RetrievalStatus.ENABLED
        with self.assertRaises(ValidationError):
            await self.indexer.index_document(package)
        self.assertEqual(await self.search(), [])

    async def test_mutating_package_or_results_does_not_change_index(self):
        package = sample(retrieval_status="review_only")
        await self.indexer.index_document(package)
        package.metadata.retrieval_status = RetrievalStatus.ENABLED
        self.assertEqual(await self.search(), [])
        await self.indexer.index_document(package)
        hits = await self.search()
        exposed = await self.search()
        exposed[0].content = "已修改"
        package.chunks[0].content = "也被修改"
        self.assertEqual(await self.search(), hits)

    async def test_bad_chunk_references_and_duplicate_numbers_are_rejected(self):
        package = sample()
        package.chunks[0].original_file_key = "unknown.pdf"
        with self.assertRaises(ValidationError):
            await self.indexer.index_document(package)
        package.chunks[0].original_file_key = None
        package.chunks[1].chunk_no = 1
        with self.assertRaisesRegex(ValueError, "chunk_no"):
            await self.indexer.index_document(package)
        self.assertEqual(await self.search(), [])

    async def test_chunk_numbers_are_scoped_to_their_source_file(self):
        package = sample()
        package.files.append(ParsedFile(
            file_role="extracted", storage_key="attachment.md", original_name="attachment.md",
            processing_status=FileProcessingStatus.EXTRACTED,
        ))
        package.chunks.append(ParsedChunk(
            chunk_no=1,
            source_file_key="attachment.md",
            content="奖学金实践证明示例。",
        ))
        result = await self.indexer.index_document(package)
        self.assertEqual(result.indexed_count, 3)
        hits = await self.search("奖学金")
        self.assertEqual(len({hit.file_id for hit in hits}), 2)
        self.assertEqual(len({hit.chunk_id for hit in hits}), 3)

    async def test_disabled_chunks_stay_unsearchable(self):
        package = sample()
        package.chunks[0].index_status = ChunkIndexStatus.DISABLED
        result = await self.indexer.index_document(package)
        self.assertEqual(result.status, IndexingStatus.PARTIAL)
        self.assertEqual(result.indexed_count, 1)
        self.assertEqual(await self.search("提交申请"), [])
        self.assertEqual(len(await self.search("奖学金")), 1)

    async def test_unprocessed_source_files_are_skipped_in_mixed_package(self):
        for status in (
            FileProcessingStatus.FAILED, FileProcessingStatus.NEEDS_OCR,
            FileProcessingStatus.SAVED,
        ):
            with self.subTest(status=status):
                package = sample()
                package.files.append(ParsedFile(
                    file_role="extracted", storage_key="unready.md", original_name="unready.md",
                    processing_status=status,
                ))
                package.chunks[0].source_file_key = "unready.md"

                result = await self.indexer.index_document(package)
                self.assertEqual(result.status, IndexingStatus.PARTIAL)
                self.assertEqual((result.chunk_count, result.indexed_count), (2, 1))
                self.assertEqual([item.code for item in result.warnings], [
                    "SOURCE_FILE_NOT_READY",
                ])
                self.assertIn("unready.md", result.warnings[0].message)
                self.assertIn(status.value, result.warnings[0].message)
                self.assertEqual(await self.search("提交申请"), [])
                hits = await self.search("奖学金")
                self.assertEqual([hit.content for hit in hits], [package.chunks[1].content])

    async def test_reindex_clears_old_hits_when_all_source_chunks_are_skipped(self):
        package = sample()
        await self.indexer.index_document(package)
        self.assertTrue(await self.search())
        package.files[0].processing_status = FileProcessingStatus.NEEDS_OCR

        result = await self.indexer.index_document(package)
        self.assertEqual(result.status, IndexingStatus.PARTIAL)
        self.assertEqual((result.chunk_count, result.indexed_count), (2, 0))
        self.assertEqual([item.code for item in result.warnings], ["SOURCE_FILE_NOT_READY"])
        self.assertIn("2 个片段", result.warnings[0].message)
        self.assertEqual(await self.search(), [])

    async def test_reviewed_source_remains_searchable(self):
        package = sample()
        package.files[0].processing_status = FileProcessingStatus.REVIEWED
        result = await self.indexer.index_document(package)
        self.assertEqual(result.status, IndexingStatus.INDEXED)
        self.assertEqual(result.indexed_count, 2)
        self.assertEqual(result.warnings, [])
        self.assertEqual(len(await self.search()), 2)

    async def test_chunks_without_searchable_terms_are_not_counted(self):
        package = sample()
        package.chunks[0].content = "……？！"
        result = await self.indexer.index_document(package)
        self.assertEqual(result.status, IndexingStatus.PARTIAL)
        self.assertEqual((result.chunk_count, result.indexed_count), (2, 1))
        self.assertEqual([item.code for item in result.warnings], ["TOKENLESS_CHUNKS_SKIPPED"])
        self.assertIn("1 个片段", result.warnings[0].message)
        self.assertEqual([hit.content for hit in await self.search()], [package.chunks[1].content])

        package.chunks[1].content = "。"
        result = await self.indexer.index_document(package)
        self.assertEqual(result.status, IndexingStatus.PARTIAL)
        self.assertEqual(result.indexed_count, 0)
        self.assertEqual(await self.search(), [])

    async def test_rejects_invalid_storage_location(self):
        for key in ("../outside.md", "/rooted.md", "C:/outside.md", "sub/../text.md"):
            with self.subTest(key=key):
                package = sample()
                package.files[1].storage_key = key
                package.chunks[0].original_file_key = key
                with self.assertRaisesRegex(ValueError, "storage_key"):
                    await self.indexer.index_document(package)

    async def test_local_files_are_checked_before_indexing(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            store = LocalBM25Retriever(file_root=root)
            package = sample()
            (root / "policy.pdf").write_bytes(b"synthetic original")
            (root / "text.md").write_bytes(b"synthetic text")
            package.files[0].sha256 = sha256(b"synthetic text").hexdigest()
            result = await store.index_document(package)
            self.assertEqual(result.status, IndexingStatus.INDEXED)

            (root / "text.md").write_bytes(b"changed")
            (root / "policy.pdf").unlink()
            result = await store.index_document(package)
            self.assertEqual(result.status, IndexingStatus.FAILED)
            self.assertEqual(result.indexed_count, 0)
            self.assertEqual({item.code for item in result.warnings}, {
                "FILE_HASH_MISMATCH", "FILE_UNAVAILABLE",
            })
            self.assertEqual(await store.retrieve(RetrievalRequest(query="奖学金")), [])

    async def test_missing_unready_source_is_ignored_only_when_unused(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            store = LocalBM25Retriever(file_root=root)
            (root / "text.md").write_text("synthetic text", encoding="utf-8")
            package = sample()
            package.files[1].processing_status = FileProcessingStatus.FAILED
            package.chunks[0].source_file_key = "policy.pdf"
            request = RetrievalRequest(query="奖学金")

            result = await store.index_document(package)
            self.assertEqual(result.status, IndexingStatus.PARTIAL)
            self.assertEqual((result.chunk_count, result.indexed_count), (2, 1))
            self.assertEqual([item.code for item in result.warnings], ["SOURCE_FILE_NOT_READY"])
            self.assertEqual(
                [hit.content for hit in await store.retrieve(request)], [package.chunks[1].content]
            )

            package.chunks[0].index_status = ChunkIndexStatus.DISABLED
            result = await store.index_document(package)
            self.assertEqual(result.status, IndexingStatus.PARTIAL)
            self.assertEqual(result.indexed_count, 1)

            # The same missing file must pass integrity checks if a retained
            # chunk now relies on it for provenance.
            package.chunks[1].original_file_key = "policy.pdf"
            result = await store.index_document(package)
            self.assertEqual(result.status, IndexingStatus.FAILED)
            self.assertEqual(result.indexed_count, 0)
            self.assertIn("FILE_UNAVAILABLE", {item.code for item in result.warnings})
            self.assertEqual(await store.retrieve(request), [])

    async def test_real_parser_handoff_indexes_without_exposing_policies(self):
        root = Path(__file__).resolve().parents[1]
        store = LocalBM25Retriever(file_root=root)
        cases = (
            ("competition-recognition-2026", 13, "竞赛认定"),
            ("scholarship-2026", 4, "奖学金"),
            ("recommendation-eligibility-2027", 6, "推免"),
        )
        for stem, count, query in cases:
            with self.subTest(package=stem):
                path = root / "knowledge_base/processed/alpha" / (stem + ".json")
                package = DocumentPackage.model_validate_json(path.read_bytes())
                result = await store.index_document(package)
                self.assertEqual(result.status, IndexingStatus.INDEXED, result.warnings)
                self.assertEqual(result.indexed_count, count)
                self.assertEqual(package.metadata.retrieval_status, RetrievalStatus.BLOCKED)
                self.assertEqual(await store.retrieve(RetrievalRequest(query=query)), [])

    async def test_metadata_and_chunk_lookups_expose_enabled_snapshots_only(self):
        from datetime import date
        from uuid import uuid4

        package = sample(
            deadline_on=date(2026, 4, 26),
            applicability_raw={"audience": "计算机学院本科生", "grade": "2024级"},
            temporal_notes={"deadline_exact_local": "2026-04-26T17:00:00+08:00"},
        )
        package.chunks[0].locator_note = '{"heading": "二、学生评选条件"}'
        indexed = await self.indexer.index_document(package)
        hits = await self.search()
        self.assertTrue(hits)

        meta = self.store.get_document_metadata(hits[0].version_id)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.deadline_on, date(2026, 4, 26))
        self.assertEqual(meta.applicability_raw, {"audience": "计算机学院本科生", "grade": "2024级"})
        self.assertEqual(meta.temporal_notes, {"deadline_exact_local": "2026-04-26T17:00:00+08:00"})

        parsed = self.store.get_parsed_chunk(hits[0].chunk_id)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.locator_note, '{"heading": "二、学生评选条件"}')
        self.assertEqual(parsed.original_file_key, "policy.pdf")

        # Returned snapshots must be detached copies.
        meta.applicability_raw["audience"] = "已篡改"
        parsed.locator_note = "已篡改"
        self.assertEqual(
            self.store.get_document_metadata(hits[0].version_id).applicability_raw["audience"],
            "计算机学院本科生",
        )
        self.assertEqual(
            self.store.get_parsed_chunk(hits[0].chunk_id).locator_note,
            '{"heading": "二、学生评选条件"}',
        )

        # Unknown IDs and unopened versions must return None.
        self.assertIsNone(self.store.get_document_metadata(uuid4()))
        self.assertIsNone(self.store.get_parsed_chunk(uuid4()))
        for status in ("blocked", "review_only"):
            unopened = sample(f"UNOPENED-{status}", retrieval_status=status)
            unopened_res = await self.indexer.index_document(unopened)
            self.assertIsNone(self.store.get_document_metadata(unopened_res.version_id))

        # Reindexing with fewer chunks must evict removed chunk IDs.
        removed_chunk_id = hits[1].chunk_id
        self.assertIsNotNone(self.store.get_parsed_chunk(removed_chunk_id))
        package.chunks.pop()
        await self.indexer.index_document(package)
        self.assertIsNone(self.store.get_parsed_chunk(removed_chunk_id))
        self.assertIsNotNone(self.store.get_parsed_chunk(hits[0].chunk_id))

        # Separate retriever instances must not share metadata or chunk lookups.
        other_store = LocalBM25Retriever()
        self.assertIsNone(other_store.get_document_metadata(hits[0].version_id))
        self.assertIsNone(other_store.get_parsed_chunk(hits[0].chunk_id))

        # Withdrawal (review_only or blocked) clears both version metadata and chunk lookup immediately.
        for status in (RetrievalStatus.REVIEW_ONLY, RetrievalStatus.BLOCKED):
            package.metadata.retrieval_status = RetrievalStatus.ENABLED
            await self.indexer.index_document(package)
            self.assertIsNotNone(self.store.get_document_metadata(indexed.version_id))
            self.assertIsNotNone(self.store.get_parsed_chunk(hits[0].chunk_id))
            package.metadata.retrieval_status = status
            await self.indexer.index_document(package)
            self.assertIsNone(self.store.get_document_metadata(indexed.version_id))
            self.assertIsNone(self.store.get_parsed_chunk(hits[0].chunk_id))

    def test_local_retriever_conforms_to_retriever_protocol_signatures(self):
        import inspect
        from typing import get_type_hints

        for name in ("retrieve", "get_document_metadata", "get_parsed_chunk"):
            protocol_method = getattr(Retriever, name)
            impl_method = getattr(LocalBM25Retriever, name)
            self.assertEqual(
                inspect.iscoroutinefunction(impl_method),
                inspect.iscoroutinefunction(protocol_method),
                msg=f"{name} async/sync mismatch",
            )
            self.assertEqual(
                list(inspect.signature(impl_method).parameters),
                list(inspect.signature(protocol_method).parameters),
                msg=f"{name} parameter mismatch",
            )
            self.assertEqual(
                get_type_hints(impl_method),
                get_type_hints(protocol_method),
                msg=f"{name} type hint mismatch",
            )
