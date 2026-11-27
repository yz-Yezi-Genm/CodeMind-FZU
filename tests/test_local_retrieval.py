import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

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

    async def test_two_retriever_instances_isolate_independent_withdrawal(self):
        package = sample("ISO-2026")
        store_a = LocalBM25Retriever()
        store_b = LocalBM25Retriever()

        res_a = await store_a.index_document(package)
        res_b = await store_b.index_document(package)
        hits_a = await store_a.retrieve(RetrievalRequest(query="奖学金申请"))
        hits_b = await store_b.retrieve(RetrievalRequest(query="奖学金申请"))
        self.assertTrue(hits_a)
        self.assertTrue(hits_b)
        self.assertEqual(res_a.version_id, res_b.version_id)
        self.assertEqual(hits_a[0].chunk_id, hits_b[0].chunk_id)

        # Withdraw from store_a only; store_b must remain completely unaffected.
        revoked = package.model_copy(deep=True)
        revoked.metadata.retrieval_status = RetrievalStatus.BLOCKED
        await store_a.index_document(revoked)

        self.assertEqual(await store_a.retrieve(RetrievalRequest(query="奖学金申请")), [])
        self.assertIsNone(store_a.get_document_metadata(res_a.version_id))
        self.assertIsNone(store_a.get_parsed_chunk(hits_a[0].chunk_id))

        self.assertTrue(await store_b.retrieve(RetrievalRequest(query="奖学金申请")))
        self.assertIsNotNone(store_b.get_document_metadata(res_b.version_id))
        self.assertIsNotNone(store_b.get_parsed_chunk(hits_b[0].chunk_id))

    async def test_title_and_content_terms_both_contribute_to_bm25_retrieval(self):
        package = sample(
            "TITLE-2026",
            title="2026年星火科创奖学金评选通知",
        )
        package.chunks.append(
            ParsedChunk(
                chunk_no=3,
                content="——。！？",
                source_file_key="text.md",
            )
        )
        result = await self.indexer.index_document(package)
        # A tokenless chunk must still be skipped even when metadata.title has terms.
        self.assertEqual(result.status, IndexingStatus.PARTIAL)
        self.assertEqual(result.indexed_count, 2)
        self.assertTrue(any(w.code == "TOKENLESS_CHUNKS_SKIPPED" for w in result.warnings))

        # Pure title-only query must match indexed chunks of that document.
        title_only_hits = await self.retriever.retrieve(
            RetrievalRequest(query="星火科创", top_k=5)
        )
        self.assertEqual(len(title_only_hits), 2)

        # Query matching title ("星火科创") + specific chunk content ("申请表") ranks that chunk first.
        hits = await self.retriever.retrieve(
            RetrievalRequest(query="星火科创 申请表", top_k=2)
        )
        self.assertEqual(len(hits), 2)
        self.assertIn("申请表", hits[0].content)
        self.assertGreater(hits[0].score, hits[1].score)

    async def test_list_document_metadata_gates_filters_sort_and_detachment(self):
        # Approved enabled documents with varied dates and record_codes.
        pkg_2025 = sample(
            "S4-QINGHE-2025",
            title="2025年青禾计划实验室招募通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2025, 9, 10),
            temporal_notes={"human_approved": True},
        )
        pkg_2025.chunks = [
            ParsedChunk(
                chunk_no=1,
                content="EDA实验室（序号14）联系人：张老师。",
                source_file_key="text.md",
                locator="第 14 项",
            ),
            ParsedChunk(
                chunk_no=2,
                content="智能感知实验室联系人：陈老师。",
                source_file_key="text.md",
                locator="第 18 项",
            ),
        ]

        pkg_2026_b = sample(
            "S4-QINGHE-2026-B",
            title="2026年青禾计划实验室招募通知（补充批）",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 9, 12),
            temporal_notes={"human_approved": True},
        )
        pkg_2026_b.chunks = [
            ParsedChunk(
                chunk_no=1,
                content="ROIS团队招新说明，联系人：李老师。",
                source_file_key="text.md",
                locator="第 1 项",
            ),
        ]

        pkg_2026_a = sample(
            "S4-QINGHE-2026-A",
            title="2026年青禾计划实验室招募通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 9, 12),
            temporal_notes={"human_approved": True},
        )
        pkg_2026_a.chunks = [
            ParsedChunk(
                chunk_no=1,
                content="EDA实验室（序号15）联系人：王老师。",
                source_file_key="text.md",
                locator="第 15 项",
            ),
        ]

        pkg_undated = sample(
            "S4-QINGHE-UNDATED",
            title="青禾计划历史归档说明",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=None,
            temporal_notes={"human_approved": True},
        )

        # Gate exclusions: unapproved, non-boolean approval, blocked with human_approved=True,
        # review_only with human_approved=True, and 0-chunk partial package.
        pkg_unapproved = sample(
            "S4-UNAPPROVED",
            title="2026年青禾计划未签核通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 10, 1),
            temporal_notes={"human_approved": False},
        )
        pkg_string_approved = sample(
            "S4-STR-APPROVED",
            title="2026年青禾计划字符串签核通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 10, 2),
            temporal_notes={"human_approved": "true"},
        )
        pkg_no_notes = sample(
            "S4-NO-NOTES",
            title="2026年青禾计划无签核字段通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 10, 3),
        )
        pkg_blocked = sample(
            "S4-BLOCKED",
            title="2026年青禾计划阻断通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 10, 4),
            retrieval_status=RetrievalStatus.BLOCKED,
            temporal_notes={"human_approved": True},
        )
        pkg_review_only = sample(
            "S4-REVIEW-ONLY",
            title="2026年青禾计划仅审核通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 10, 5),
            retrieval_status=RetrievalStatus.REVIEW_ONLY,
            temporal_notes={"human_approved": True},
        )
        pkg_empty_chunks = sample(
            "S4-EMPTY-CHUNKS",
            title="2026年青禾计划无可用片段通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 10, 6),
            temporal_notes={"human_approved": True},
        )
        pkg_empty_chunks.chunks = [
            ParsedChunk(
                chunk_no=1,
                content="禁用片段。",
                source_file_key="text.md",
                index_status=ChunkIndexStatus.DISABLED,
            ),
        ]

        # Another business direction / category for filter checks.
        pkg_other_dir = sample(
            "S1-SCHOLAR-2026",
            title="2026年本科生奖学金评定通知",
            category_name="综评与奖学金",
            business_direction_codes=["POLICY_AFFAIRS"],
            published_on=date(2026, 5, 1),
            temporal_notes={"human_approved": True},
        )

        for pkg in (
            pkg_2025, pkg_2026_b, pkg_2026_a, pkg_undated,
            pkg_unapproved, pkg_string_approved, pkg_no_notes,
            pkg_blocked, pkg_review_only, pkg_empty_chunks, pkg_other_dir,
        ):
            await self.indexer.index_document(pkg)
        # Re-indexing same version_id must remain deduplicated.
        await self.indexer.index_document(pkg_2026_a)

        # Full list: only 5 approved+enabled+non-empty versions, sorted by published_on DESC then record_code ASC.
        all_metas = self.store.list_document_metadata()
        self.assertEqual(
            [m.record_code for m in all_metas],
            [
                "S4-QINGHE-2026-A",
                "S4-QINGHE-2026-B",
                "S1-SCHOLAR-2026",
                "S4-QINGHE-2025",
                "S4-QINGHE-UNDATED",
            ],
        )

        # Subject matching title ("青禾计划") + direction/category filters.
        qinghe = self.store.list_document_metadata(
            subject="青禾计划",
            business_direction_code="COLLEGE_RESOURCES",
            category_name="实验室与科研团队",
        )
        self.assertEqual(
            [m.record_code for m in qinghe],
            ["S4-QINGHE-2026-A", "S4-QINGHE-2026-B", "S4-QINGHE-2025", "S4-QINGHE-UNDATED"],
        )

        # Subject matching chunk content only (case-insensitive NFKC substring, no alias).
        eda = self.store.list_document_metadata(subject="eda实验室")
        self.assertEqual([m.record_code for m in eda], ["S4-QINGHE-2026-A", "S4-QINGHE-2025"])

        # Single-batch subject vs zero-match vs blank subject.
        self.assertEqual(
            [m.record_code for m in self.store.list_document_metadata(subject="智能感知实验室")],
            ["S4-QINGHE-2025"],
        )
        self.assertEqual(self.store.list_document_metadata(subject="不存在的实验室"), [])
        self.assertEqual(self.store.list_document_metadata(subject="   "), [])

        # Detachment: mutating returned metadata must not affect stored snapshot.
        eda[0].title = "被篡改标题"
        self.assertEqual(
            self.store.list_document_metadata(subject="EDA实验室")[0].title,
            "2026年青禾计划实验室招募通知",
        )

        # Withdrawal immediately hides version from list_document_metadata and list_parsed_chunks.
        revoked = pkg_2026_a.model_copy(deep=True)
        revoked.metadata.retrieval_status = RetrievalStatus.BLOCKED
        await self.indexer.index_document(revoked)
        self.assertEqual(
            [m.record_code for m in self.store.list_document_metadata(subject="EDA实验室")],
            ["S4-QINGHE-2025"],
        )
        self.assertEqual(
            self.store.list_parsed_chunks(
                record_code=pkg_2026_a.metadata.record_code,
                version_no=pkg_2026_a.metadata.version_no,
            ),
            [],
        )

    async def test_list_parsed_chunks_by_version_id_and_record_key(self):
        pkg_2025 = sample(
            "S4-EDA-2025",
            title="2025年青禾计划实验室招募通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2025, 9, 10),
            temporal_notes={"human_approved": True},
        )
        pkg_2025.chunks = [
            ParsedChunk(
                chunk_no=2,
                content="EDA实验室（序号14）联系人：张老师（2025）。",
                source_file_key="text.md",
                locator="第 14 项",
            ),
            ParsedChunk(
                chunk_no=1,
                content="2025年青禾计划总说明。",
                source_file_key="text.md",
                locator="总则",
            ),
            ParsedChunk(
                chunk_no=3,
                content="禁用片段不应返回。",
                source_file_key="text.md",
                index_status=ChunkIndexStatus.DISABLED,
            ),
        ]

        pkg_2026 = sample(
            "S4-EDA-2026",
            title="2026年青禾计划实验室招募通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 9, 10),
            temporal_notes={"human_approved": True},
        )
        pkg_2026.chunks = [
            ParsedChunk(
                chunk_no=1,
                content="EDA实验室（序号15）联系人：王老师（2026）。",
                source_file_key="text.md",
                locator="第 15 项",
            ),
        ]

        pkg_unapproved = sample(
            "S4-UNAPPROVED-CHUNKS",
            title="2026年未签核招募",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            temporal_notes={"human_approved": False},
        )

        res_2025 = await self.indexer.index_document(pkg_2025)
        await self.indexer.index_document(pkg_2026)
        res_unapproved = await self.indexer.index_document(pkg_unapproved)

        # Lookup by version_id returns indexed chunks sorted by (source_file_key, chunk_no), excluding DISABLED.
        chunks_by_id = self.store.list_parsed_chunks(res_2025.version_id)
        self.assertEqual([c.chunk_no for c in chunks_by_id], [1, 2])
        self.assertTrue(all(c.index_status != ChunkIndexStatus.DISABLED for c in chunks_by_id))

        # S4-01/02 flow: even if retrieve(top_k=1) only returns one batch, list_document_metadata
        # enumerates all batches and list_parsed_chunks(record_code=..., version_no=...) fetches
        # each batch's chunks for cross-year contact comparison.
        top1 = await self.retriever.retrieve(RetrievalRequest(query="EDA实验室", top_k=1))
        self.assertEqual(len(top1), 1)

        batches = self.store.list_document_metadata(
            subject="EDA实验室",
            business_direction_code="COLLEGE_RESOURCES",
            category_name="实验室与科研团队",
        )
        self.assertEqual([m.record_code for m in batches], ["S4-EDA-2026", "S4-EDA-2025"])

        contacts_by_batch = {
            meta.record_code: [
                c.content
                for c in self.store.list_parsed_chunks(
                    record_code=meta.record_code,
                    version_no=meta.version_no,
                )
                if "EDA实验室" in c.content
            ]
            for meta in batches
        }
        self.assertIn("王老师（2026）", contacts_by_batch["S4-EDA-2026"][0])
        self.assertIn("张老师（2025）", contacts_by_batch["S4-EDA-2025"][0])

        # Detachment check on returned chunks.
        chunks_by_id[0].content = "被篡改内容"
        self.assertEqual(
            self.store.list_parsed_chunks(res_2025.version_id)[0].content,
            "2025年青禾计划总说明。",
        )

        # Unknown / unapproved versions return [].
        self.assertEqual(self.store.list_parsed_chunks(uuid4()), [])
        self.assertEqual(self.store.list_parsed_chunks(res_unapproved.version_id), [])
        self.assertEqual(
            self.store.list_parsed_chunks(record_code="UNKNOWN", version_no="v1"),
            [],
        )

        # Invalid argument combinations raise ValueError.
        with self.assertRaises(ValueError):
            self.store.list_parsed_chunks()
        with self.assertRaises(ValueError):
            self.store.list_parsed_chunks(
                res_2025.version_id, record_code="S4-EDA-2025", version_no="v1"
            )
        with self.assertRaises(ValueError):
            self.store.list_parsed_chunks(record_code="S4-EDA-2025")

    async def test_list_document_metadata_version_vs_record_granularity(self):
        # Same record_code with two version_no values must both be returned at
        # version granularity, while business callers can collapse by record_code.
        pkg_v1 = sample(
            "S4-QINGHE-R3-2025",
            version_no="v1",
            title="2025年青禾计划实验室招募通知（初版）",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2025, 9, 10),
            temporal_notes={"human_approved": True},
        )
        pkg_v1.chunks = [
            ParsedChunk(chunk_no=1, content="v1 正文：联系人张老师。", source_file_key="text.md")
        ]

        pkg_v2 = sample(
            "S4-QINGHE-R3-2025",
            version_no="v2",
            title="2025年青禾计划实验室招募通知（修订版）",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2025, 9, 10),
            temporal_notes={"human_approved": True},
        )
        pkg_v2.chunks = [
            ParsedChunk(chunk_no=1, content="v2 正文：联系人更新为李老师。", source_file_key="text.md")
        ]

        # Same year split across R4 package is also a separate record_code.
        pkg_r4 = sample(
            "S4-QINGHE-R4-2025",
            version_no="v1",
            title="2025年青禾计划实验室研究方向介绍",
            category_name="研究方向与公开介绍",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2025, 9, 10),
            temporal_notes={"human_approved": True},
        )

        for pkg in (pkg_v2, pkg_v1, pkg_r4):
            await self.indexer.index_document(pkg)

        r3_versions = self.store.list_document_metadata(
            business_direction_code="COLLEGE_RESOURCES",
            category_name="实验室与科研团队",
        )
        # Interface returns version-level entries sorted by version_no on ties.
        self.assertEqual(
            [(m.record_code, m.version_no) for m in r3_versions],
            [("S4-QINGHE-R3-2025", "v1"), ("S4-QINGHE-R3-2025", "v2")],
        )
        # Collapsing by record_code yields 1 logical record, not 2 historical batches.
        self.assertEqual({m.record_code for m in r3_versions}, {"S4-QINGHE-R3-2025"})

        # list_parsed_chunks distinguishes v1 vs v2 under the same record_code.
        v1_chunks = self.store.list_parsed_chunks(record_code="S4-QINGHE-R3-2025", version_no="v1")
        v2_chunks = self.store.list_parsed_chunks(record_code="S4-QINGHE-R3-2025", version_no="v2")
        self.assertIn("张老师", v1_chunks[0].content)
        self.assertIn("李老师", v2_chunks[0].content)

    async def test_list_document_metadata_full_enumeration_without_subject(self):
        pkg_r3_2025 = sample(
            "S4-LAB-R3-2025",
            title="2025年实验室招募",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2025, 9, 1),
            temporal_notes={"human_approved": True},
        )
        pkg_r3_2026 = sample(
            "S4-LAB-R3-2026",
            title="2026年实验室招募",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 9, 1),
            temporal_notes={"human_approved": True},
        )
        pkg_r4_2026 = sample(
            "S4-LAB-R4-2026",
            title="2026年研究方向介绍",
            category_name="研究方向与公开介绍",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 9, 2),
            temporal_notes={"human_approved": True},
        )
        pkg_blocked = sample(
            "S4-LAB-R3-BLOCKED",
            title="2026年未放行实验室招募",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 9, 3),
            retrieval_status=RetrievalStatus.BLOCKED,
            temporal_notes={"human_approved": True},
        )
        pkg_other_dir = sample(
            "S1-POLICY-2026",
            title="2026年本科奖学金",
            category_name="综评与奖学金",
            business_direction_codes=["POLICY_AFFAIRS"],
            published_on=date(2026, 9, 4),
            temporal_notes={"human_approved": True},
        )
        for pkg in (pkg_r3_2025, pkg_r3_2026, pkg_r4_2026, pkg_blocked, pkg_other_dir):
            await self.indexer.index_document(pkg)

        # Enumerate all COLLEGE_RESOURCES without subject or category_name.
        all_college = self.store.list_document_metadata(
            business_direction_code="COLLEGE_RESOURCES",
        )
        self.assertEqual(
            [m.record_code for m in all_college],
            ["S4-LAB-R4-2026", "S4-LAB-R3-2026", "S4-LAB-R3-2025"],
        )

        # Enumerate COLLEGE_RESOURCES + R3 category only, without subject.
        r3_only = self.store.list_document_metadata(
            business_direction_code="COLLEGE_RESOURCES",
            category_name="实验室与科研团队",
        )
        self.assertEqual(
            [m.record_code for m in r3_only],
            ["S4-LAB-R3-2026", "S4-LAB-R3-2025"],
        )

        # Empty list vs missing optional extension semantics.
        self.assertEqual(
            self.store.list_document_metadata(
                business_direction_code="COLLEGE_RESOURCES",
                category_name="不存在的类别",
            ),
            [],
        )
        self.assertIsNotNone(getattr(self.store, "list_document_metadata", None))
        self.assertIsNone(getattr(object(), "list_document_metadata", None))

    async def test_list_document_metadata_subject_normalization_and_no_alias_boundary(self):
        pkg_space = sample(
            "S4-ROIS-2025",
            title="2025年 ROIS 团队招募通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2025, 9, 5),
            temporal_notes={"human_approved": True},
        )
        pkg_fullwidth = sample(
            "S4-ROIS-2026",
            title="2026年ＲＯＩＳ团队招募通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 9, 5),
            temporal_notes={"human_approved": True},
        )
        pkg_ideographic_space = sample(
            "S4-EDA-SPACE-2026",
            title="2026年青禾计划招募",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2026, 9, 6),
            temporal_notes={"human_approved": True},
        )
        pkg_ideographic_space.chunks = [
            ParsedChunk(
                chunk_no=1,
                content="序号15：ＥＤＡ　实验室招收本科生。",
                source_file_key="text.md",
            )
        ]
        pkg_alias_name = sample(
            "S4-ALIAS-2025",
            title="2025年信息安全研究组招募通知",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            published_on=date(2025, 9, 1),
            temporal_notes={"human_approved": True},
        )
        for pkg in (pkg_space, pkg_fullwidth, pkg_ideographic_space, pkg_alias_name):
            await self.indexer.index_document(pkg)

        # Whitespace, full-width/half-width, and case differences must not miss batches.
        for query in ("ROIS团队", "rois 团队", "ROIS  团队", "ＲＯＩＳ　团队"):
            with self.subTest(subject=query):
                matched = self.store.list_document_metadata(subject=query)
                self.assertEqual(
                    [m.record_code for m in matched],
                    ["S4-ROIS-2026", "S4-ROIS-2025"],
                )

        # Full-width + ideographic space in chunk content matches compact ASCII query.
        self.assertEqual(
            [m.record_code for m in self.store.list_document_metadata(subject="eda实验室")],
            ["S4-EDA-SPACE-2026"],
        )

        # No alias expansion in retrieval layer: "ROIS团队" does not match "信息安全研究组";
        # callers needing alias matching must enumerate without subject.
        self.assertNotIn(
            "S4-ALIAS-2025",
            [m.record_code for m in self.store.list_document_metadata(subject="ROIS团队")],
        )
        self.assertIn(
            "S4-ALIAS-2025",
            [
                m.record_code
                for m in self.store.list_document_metadata(
                    business_direction_code="COLLEGE_RESOURCES",
                    category_name="实验室与科研团队",
                )
            ],
        )
