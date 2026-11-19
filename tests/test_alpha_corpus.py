import json
import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from backend.contracts import (
    AgentRequest,
    AnswerStatus,
    DocumentMetadata,
    DocumentPackage,
    FileProcessingStatus,
    LLMGenerateRequest,
    LLMResult,
    ParsedChunk,
    ParsedFile,
    RetrievalRequest,
    RetrievalStatus,
)
from backend.retrieval import (
    DEFAULT_APPROVED_DIR,
    build_approved_alpha_retriever,
    load_approved_alpha_retriever,
)
from backend.services.agent_workflow import AgentWorkflow


class _FirstEvidenceLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMGenerateRequest) -> LLMResult:
        self.calls += 1
        hit = json.loads(request.messages[-1].content)["evidence"][0]
        output = {"evidence": [{"chunk_id": hit["chunk_id"], "quote": hit["content"]}]}
        return LLMResult(content=json.dumps(output), model="offline-test-double")


def _write_approved_package(
    root: Path,
    corpus_dir: Path,
    filename: str,
    *,
    record_code: str,
    content: str = "2026年院级奖学金面向计算机学院全日制本科生，截止时间为2026年12月20日。",
    retrieval_status: str = "enabled",
    temporal_notes: dict | None = None,
    deadline_on: date | None = date(2026, 12, 20),
    applicability_raw: dict | None = None,
    corrupt_hash: bool = False,
) -> Path:
    text_rel = f"texts/{Path(filename).stem}.md"
    text_path = root / text_rel
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_bytes = content.encode("utf-8")
    text_path.write_bytes(text_bytes)
    digest = "0" * 64 if corrupt_hash else sha256(text_bytes).hexdigest()

    meta_kwargs = {
        "title": f"测试政策-{record_code}",
        "document_type": "通知",
        "category_name": "综评与奖学金",
        "business_direction_codes": ["POLICY_AFFAIRS"],
        "record_code": record_code,
        "version_no": "v1",
        "source_url": "https://example.invalid/approved-policy",
        "published_on": date(2026, 11, 1),
        "effective_on": date(2026, 11, 1),
        "deadline_on": deadline_on,
        "applicability_raw": applicability_raw or {"college": "计算机与大数据学院", "degree": "本科生"},
        "temporal_notes": temporal_notes,
        "source_verification_status": "verified",
        "timeliness_verification_status": "current",
        "extraction_status": "extracted",
        "v1_inclusion_status": "included",
        "retrieval_status": retrieval_status,
    }
    package = DocumentPackage(
        metadata=DocumentMetadata(**meta_kwargs),
        files=[
            ParsedFile(
                file_role="extracted",
                storage_key=text_rel,
                original_name=text_path.name,
                sha256=digest,
                processing_status=FileProcessingStatus.EXTRACTED,
            ),
        ],
        chunks=[
            ParsedChunk(
                chunk_no=1,
                content=content,
                locator="第 1 条",
                locator_note='{"heading": "一、评选对象"}',
                source_file_key=text_rel,
            ),
        ],
    )
    pkg_path = corpus_dir / filename
    pkg_path.write_text(package.model_dump_json(indent=2), encoding="utf-8")
    return pkg_path


class AlphaCorpusLoaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_approved_dir_loads_cleanly_when_empty(self):
        retriever, report = await load_approved_alpha_retriever(corpus_dir=DEFAULT_APPROVED_DIR)
        self.assertEqual(report.loaded_packages, ())
        self.assertEqual(report.skipped_packages, ())
        self.assertEqual(report.total_indexed_chunks, 0)
        self.assertEqual(await retriever.retrieve(RetrievalRequest(query="奖学金")), [])

    async def test_missing_dir_returns_empty_by_default_and_raises_when_disallowed(self):
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "not-created-yet"
            retriever, report = await load_approved_alpha_retriever(
                corpus_dir=missing, file_root=Path(tmp)
            )
            self.assertEqual(report.loaded_packages, ())
            self.assertEqual(report.total_indexed_chunks, 0)
            self.assertEqual(await retriever.retrieve(RetrievalRequest(query="奖学金")), [])
            with self.assertRaises(FileNotFoundError):
                await load_approved_alpha_retriever(
                    corpus_dir=missing, file_root=Path(tmp), allow_missing=False
                )

    async def test_directory_loader_skips_unapproved_and_failed_packages(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved_dir = root / "approved"
            approved_dir.mkdir()

            _write_approved_package(root, approved_dir, "ok.json", record_code="OK-1")
            (approved_dir / "summary.json").write_text('{"ignored": true}', encoding="utf-8")
            (approved_dir / "ok.metadata.json").write_text('{"ignored": true}', encoding="utf-8")
            _write_approved_package(
                root, approved_dir, "blocked.json", record_code="BLK-1", retrieval_status="blocked"
            )
            _write_approved_package(
                root, approved_dir, "review.json", record_code="REV-1", retrieval_status="review_only"
            )
            _write_approved_package(
                root, approved_dir, "unreviewed.json", record_code="UNR-1",
                temporal_notes={"human_approved": False},
            )
            _write_approved_package(
                root, approved_dir, "bad_hash.json", record_code="HASH-1", corrupt_hash=True
            )

            retriever, report = await load_approved_alpha_retriever(
                corpus_dir=approved_dir, file_root=root
            )
            self.assertEqual(report.loaded_packages, ("approved/ok.json",))
            self.assertEqual(report.total_indexed_chunks, 1)
            skipped_by_name = dict(report.skipped_packages)
            self.assertEqual(
                set(skipped_by_name),
                {
                    "approved/blocked.json",
                    "approved/review.json",
                    "approved/unreviewed.json",
                    "approved/bad_hash.json",
                },
            )
            hits = await retriever.retrieve(RetrievalRequest(query="院级奖学金"))
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].title, "测试政策-OK-1")
            self.assertEqual(hits[0].retrieval_status, RetrievalStatus.ENABLED)

    async def test_manifest_loader_enforces_human_approved_and_directory_boundary(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved_dir = root / "approved"
            pending_dir = root / "pending-review"
            approved_dir.mkdir()
            pending_dir.mkdir()

            _write_approved_package(root, approved_dir, "a.json", record_code="A-1")
            _write_approved_package(root, approved_dir, "b.json", record_code="B-1")
            _write_approved_package(root, pending_dir, "leak.json", record_code="LEAK-1")

            manifest = {
                "packages": [
                    {"package": "approved/a.json", "human_approved": True},
                    {"package": "approved/b.json", "human_approved": False},
                ]
            }
            (approved_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            retriever, report = await load_approved_alpha_retriever(
                corpus_dir=approved_dir, file_root=root
            )
            self.assertEqual(report.loaded_packages, ("approved/a.json",))
            self.assertEqual(len(report.skipped_packages), 1)
            self.assertIn("human_approved=true", report.skipped_packages[0][1])
            hits = await retriever.retrieve(RetrievalRequest(query="院级奖学金"))
            self.assertEqual([hit.title for hit in hits], ["测试政策-A-1"])

            # Non-boolean truthy strings like "false" must NOT be treated as approved.
            tricky_manifest = {
                "packages": [
                    {"package": "approved/a.json", "human_approved": "false"},
                ]
            }
            (approved_dir / "manifest.json").write_text(json.dumps(tricky_manifest), encoding="utf-8")
            retriever, report = await load_approved_alpha_retriever(
                corpus_dir=approved_dir, file_root=root
            )
            self.assertEqual(report.loaded_packages, ())
            self.assertEqual(len(report.skipped_packages), 1)

            # Duplicate document version across two files must be rejected.
            (approved_dir / "manifest.json").unlink()
            _write_approved_package(root, approved_dir, "dup.json", record_code="A-1")
            with self.assertRaisesRegex(ValueError, "重复文档版本"):
                await load_approved_alpha_retriever(corpus_dir=approved_dir, file_root=root)
            (approved_dir / "dup.json").unlink()

            # Manifest pointing outside approved/ must be rejected.
            bad_manifest = {"packages": [{"package": "pending-review/leak.json", "human_approved": True}]}
            (approved_dir / "manifest.json").write_text(json.dumps(bad_manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "目录外"):
                await load_approved_alpha_retriever(corpus_dir=approved_dir, file_root=root)

    async def test_agent_workflow_evidence_check_reads_applicability_and_deadline(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved_dir = root / "approved"
            approved_dir.mkdir()
            _write_approved_package(
                root,
                approved_dir,
                "college.json",
                record_code="COLLEGE-2026",
                deadline_on=date(2026, 12, 20),
                applicability_raw={"college": "计算机与大数据学院", "degree": "本科生"},
            )

            retriever = await build_approved_alpha_retriever(corpus_dir=approved_dir, file_root=root)
            observed = {}

            def check_evidence(request: AgentRequest, chunk) -> bool:
                meta = retriever.get_document_metadata(chunk.version_id)
                parsed = retriever.get_parsed_chunk(chunk.chunk_id)
                if meta is None or parsed is None:
                    return False
                observed["applicability_raw"] = meta.applicability_raw
                observed["deadline_on"] = meta.deadline_on
                observed["locator_note"] = parsed.locator_note
                return (
                    meta.applicability_raw.get("degree") == "本科生"
                    and meta.deadline_on is not None
                    and meta.deadline_on >= date(2026, 11, 19)
                )

            llm = _FirstEvidenceLLM()
            workflow = AgentWorkflow(
                retriever,
                llm,
                clarification_rule=lambda _: None,
                evidence_check=check_evidence,
                today=lambda: date(2026, 11, 19),
            )
            result = await workflow.run(AgentRequest(
                request_id=uuid4(),
                conversation_id=uuid4(),
                query="2026年计算机学院院级奖学金截止时间是什么时候？",
            ))
            self.assertEqual(result.status, AnswerStatus.ANSWERED)
            self.assertEqual(llm.calls, 1)
            self.assertEqual(observed["deadline_on"], date(2026, 12, 20))
            self.assertEqual(
                observed["applicability_raw"],
                {"college": "计算机与大数据学院", "degree": "本科生"},
            )
            self.assertEqual(observed["locator_note"], '{"heading": "一、评选对象"}')


if __name__ == "__main__":
    unittest.main()
