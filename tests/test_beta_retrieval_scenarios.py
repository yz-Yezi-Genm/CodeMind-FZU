"""Beta S1-S4 four-domain BM25 retrieval & formal-loading verification tests."""
from __future__ import annotations

from datetime import date
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from backend.contracts import (
    AgentRequest,
    AnswerStatus,
    IndexingStatus,
    LLMGenerateRequest,
    LLMResult,
    RetrievalRequest,
    RetrievalStatus,
)
from backend.retrieval import load_approved_alpha_retriever
from scripts.eval_beta_bm25_comparison import run_comparison
from scripts.eval_beta_retrieval import (
    materialize_synthetic_corpus,
    run_corpus_probe,
    run_evaluation,
)

_OFFICIAL_S4_CATEGORIES = {
    "通知与办事渠道",
    "培养方案与课程",
    "实验室与科研团队",
    "研究方向与公开介绍",
    "科研实践与竞赛",
    "学院公开信息与联系方式",
}


class BetaFourDomainRetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_s1_to_s4_evaluation_metrics_and_filtering(self):
        summary = await run_evaluation()

        self.assertEqual(len(summary["loaded_packages"]), 5)
        self.assertEqual(len(summary["skipped_packages"]), 2)
        self.assertEqual(summary["total_indexed_chunks"], 8)

        # Synthetic baseline must achieve clean Hit@1 / Hit@3 / MRR.
        self.assertEqual(summary["metrics"]["hit_at_1"], 1.0)
        self.assertEqual(summary["metrics"]["hit_at_3"], 1.0)
        self.assertEqual(summary["metrics"]["mrr"], 1.0)

        # Unrelated query and blocked/unapproved decoys must return empty lists.
        self.assertEqual(summary["negative_checks"]["no_match_count"], 0)
        self.assertEqual(summary["negative_checks"]["decoy_blocked_count"], 0)
        self.assertEqual(summary["negative_checks"]["decoy_unapproved_count"], 0)

    async def test_multi_direction_full_corpus_query_avoids_cross_domain_omission(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved_dir = materialize_synthetic_corpus(root)
            retriever, report = await load_approved_alpha_retriever(
                corpus_dir=approved_dir, file_root=root, allow_missing=False
            )
            self.assertTrue(report.corpus_dir.is_dir())
            self.assertTrue(
                all(r.status == IndexingStatus.INDEXED and not r.warnings for r in report.index_results)
            )

            # Without business_direction_code, a cross-domain query retrieves both S1 and S2.
            hits = await retriever.retrieve(
                RetrievalRequest(query="竞赛获奖 综测加分 奖学金申请表", top_k=4)
            )
            record_codes = {
                retriever.get_document_metadata(hit.version_id).record_code
                for hit in hits
            }
            self.assertIn("BETA-SYN-S1-2026", record_codes)
            self.assertIn("BETA-SYN-S2-2026", record_codes)

    async def test_metadata_and_parsed_chunk_fields_match_beta_v21_requirements(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved_dir = materialize_synthetic_corpus(root)
            retriever, _ = await load_approved_alpha_retriever(
                corpus_dir=approved_dir, file_root=root, allow_missing=False
            )

            hits = await retriever.retrieve(
                RetrievalRequest(
                    query="ACM-ICPC 创新创业学分",
                    business_direction_code="COMPETITION_RESEARCH",
                    top_k=1,
                )
            )
            self.assertEqual(len(hits), 1)
            hit = hits[0]

            meta = retriever.get_document_metadata(hit.version_id)
            parsed = retriever.get_parsed_chunk(hit.chunk_id)
            self.assertIsNotNone(meta)
            self.assertIsNotNone(parsed)

            # Verify all V2.1-Final required metadata fields are readable.
            self.assertEqual(meta.record_code, "BETA-SYN-S1-2026")
            self.assertEqual(meta.version_no, "beta-syn-v1")
            self.assertEqual(
                set(meta.applicability_raw.keys()),
                {"适用年级", "适用专业", "适用对象", "学院", "适用届别"},
            )
            self.assertEqual(meta.applicability_raw["学院"], "计算机与大数据学院")
            self.assertEqual(meta.applicability_raw["适用对象"], "本科生")
            self.assertIsNotNone(meta.deadline_on)
            self.assertIs(meta.temporal_notes["human_approved"], True)
            self.assertEqual(meta.source_verification_status.value, "verified")
            self.assertEqual(meta.timeliness_verification_status.value, "current")
            self.assertEqual(meta.retrieval_status, RetrievalStatus.ENABLED)

            # Verify S4 packages align with PR #45 formal RESOURCE_CATEGORY_MAP names.
            try:
                from backend.services.alpha_business_rules import RESOURCE_CATEGORY_MAP
            except ModuleNotFoundError:
                valid_s4_categories = _OFFICIAL_S4_CATEGORIES
            else:
                self.assertEqual(set(RESOURCE_CATEGORY_MAP), _OFFICIAL_S4_CATEGORIES)
                valid_s4_categories = set(RESOURCE_CATEGORY_MAP)
            s4_hits = await retriever.retrieve(
                RetrievalRequest(
                    query="实验室 培养方案",
                    business_direction_code="COLLEGE_RESOURCES",
                    top_k=5,
                )
            )
            self.assertEqual(len(s4_hits), 2)
            for s4_hit in s4_hits:
                s4_meta = retriever.get_document_metadata(s4_hit.version_id)
                self.assertIsNotNone(s4_meta)
                self.assertIn(s4_meta.category_name, valid_s4_categories)

            # Verify all V2.1-Final required ParsedChunk fields are readable & aligned.
            self.assertEqual(parsed.content, hit.content)
            self.assertEqual(parsed.locator, hit.locator)
            self.assertIn("ACM-ICPC", parsed.locator_note)
            self.assertEqual(parsed.original_locator, hit.original_locator)
            self.assertEqual(parsed.source_file_key, "texts/s1-competition-synthetic.md")
            self.assertEqual(parsed.chunk_no, 1)

            # Verify traceability back to the physical source text file on disk.
            source_file = root / parsed.source_file_key
            self.assertTrue(source_file.is_file())
            self.assertIn(parsed.content, source_file.read_text(encoding="utf-8"))

    async def test_english_case_insensitive_top_k_direction_filter_and_probe_mode(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved_dir = materialize_synthetic_corpus(root)
            retriever, _ = await load_approved_alpha_retriever(
                corpus_dir=approved_dir, file_root=root, allow_missing=False
            )

            # Pure English & case-insensitive queries across S1 / S3 / S4.
            for query, expected_code in (
                ("acm-icpc", "BETA-SYN-S1-2026"),
                ("cet-6", "BETA-SYN-S3-2027"),
                ("gpu", "BETA-SYN-S4-R3-2026"),
            ):
                hits = await retriever.retrieve(RetrievalRequest(query=query, top_k=2))
                self.assertTrue(hits, msg=f"expected hit for {query!r}")
                top_meta = retriever.get_document_metadata(hits[0].version_id)
                self.assertEqual(top_meta.record_code, expected_code)

            # Wrong business_direction_code filters out S4; omitting it succeeds.
            self.assertEqual(
                await retriever.retrieve(
                    RetrievalRequest(query="gpu", business_direction_code="POLICY_AFFAIRS")
                ),
                [],
            )

            # Top-K truncation and descending score order.
            top1 = await retriever.retrieve(RetrievalRequest(query="奖学金 申请", top_k=1))
            top3 = await retriever.retrieve(RetrievalRequest(query="奖学金 申请", top_k=3))
            self.assertEqual(len(top1), 1)
            self.assertGreaterEqual(len(top3), 2)
            self.assertEqual(top1[0].chunk_id, top3[0].chunk_id)
            scores = [hit.score for hit in top3]
            self.assertEqual(scores, sorted(scores, reverse=True))

            # Corpus probe mode (used for formal approved/ verification) runs cleanly.
            probe = await run_corpus_probe(approved_dir, file_root=root)
            self.assertEqual(probe["corpus_type"], "approved_directory_probe")
            self.assertEqual(len(probe["loaded_packages"]), 5)
            self.assertEqual(len(probe["skipped_packages"]), 2)
            self.assertEqual(probe["total_indexed_chunks"], 8)

    async def test_retriever_integrates_with_merged_beta_rules_and_agent_workflow(self):
        try:
            from backend.contracts import (
                DocumentMetadata,
                DocumentPackage,
                FileProcessingStatus,
                ParsedChunk,
                ParsedFile,
            )
            from backend.services.agent_workflow import AgentWorkflow
            from backend.services.alpha_business_rules import (
                alpha_clarification_rule,
                build_from_retriever,
            )
        except ModuleNotFoundError:
            self.skipTest("当前精简环境缺少 Agent/Qwen 运行依赖")

        class _OfflineFirstEvidenceLLM:
            def __init__(self) -> None:
                self.calls = 0

            async def generate(self, request: LLMGenerateRequest) -> LLMResult:
                self.calls += 1
                hit = json.loads(request.messages[-1].content)["evidence"][0]
                if "evidence_id" in hit:
                    payload = {"answer": hit["content"], "used_evidence_ids": [hit["evidence_id"]]}
                else:
                    payload = {"evidence": [{"chunk_id": hit["chunk_id"], "quote": hit["content"]}]}
                return LLMResult(content=json.dumps(payload, ensure_ascii=False), model="offline-test-double")

        fixed_today = lambda: date(2026, 9, 10)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved_dir = materialize_synthetic_corpus(root)
            retriever, _ = await load_approved_alpha_retriever(
                corpus_dir=approved_dir, file_root=root, allow_missing=False
            )
            # Also index a synthetic school-level scholarship bylaw matching PR #45 S2 rules.
            bylaw_text = "2026学年优秀学生综合奖学金要求学习成绩GPA排名本专业前10%且无不及格课程。"
            bylaw_path = root / "texts/s2-bylaw-synthetic.md"
            bylaw_path.write_bytes(bylaw_text.encode("utf-8"))
            from hashlib import sha256
            bylaw_pkg = DocumentPackage(
                metadata=DocumentMetadata(
                    title="【合成测试】2026年本科生奖学金评定管理办法",
                    document_type="办法",
                    category_name="综评与奖学金",
                    business_direction_codes=["POLICY_AFFAIRS"],
                    record_code="BETA-SYN-S2-BYLAW-2026",
                    version_no="beta-syn-v1",
                    source_url="https://example.invalid/beta/s2-bylaw-synthetic",
                    published_on=date(2026, 9, 1),
                    effective_on=date(2026, 9, 1),
                    deadline_on=date(2026, 10, 20),
                    applicability_raw={
                        "适用年级": "全日制本科各年级",
                        "适用专业": "全院本科专业",
                        "适用对象": "全日制本科生",
                        "学院": "计算机与大数据学院",
                        "适用届别": None,
                    },
                    temporal_notes={"human_approved": True, "synthetic_fixture": True},
                    source_verification_status="verified",
                    timeliness_verification_status="current",
                    extraction_status="extracted",
                    v1_inclusion_status="included",
                    retrieval_status="enabled",
                ),
                files=[
                    ParsedFile(
                        file_role="extracted",
                        storage_key="texts/s2-bylaw-synthetic.md",
                        original_name="s2-bylaw-synthetic.md",
                        sha256=sha256(bylaw_text.encode("utf-8")).hexdigest(),
                        processing_status=FileProcessingStatus.EXTRACTED,
                    )
                ],
                chunks=[
                    ParsedChunk(
                        chunk_no=1,
                        content=bylaw_text,
                        locator="第 1 节",
                        locator_note='{"heading": "一、优秀学生综合奖学金评选条件"}',
                        original_locator="PDF 第 1 页",
                        source_file_key="texts/s2-bylaw-synthetic.md",
                    )
                ],
            )
            await retriever.index_document(bylaw_pkg)

            llm = _OfflineFirstEvidenceLLM()
            workflow = AgentWorkflow(
                retriever,
                llm,
                clarification_rule=lambda req: alpha_clarification_rule(req, today=fixed_today),
                evidence_check=build_from_retriever(retriever, today=fixed_today),
                today=fixed_today,
            )

            # S2 synthetic bylaw passes retrieval + PR #45 business rules + citation validation.
            s2_res = await workflow.run(AgentRequest(
                request_id=uuid4(),
                conversation_id=uuid4(),
                query="2026学年本科生申请优秀学生综合奖学金有什么GPA和成绩条件？",
            ))
            self.assertEqual(s2_res.status, AnswerStatus.ANSWERED)
            self.assertEqual(llm.calls, 1)
            self.assertEqual(len(s2_res.citations), 1)
            self.assertEqual(s2_res.citations[0].locator, "第 1 节")
            self.assertEqual(s2_res.citations[0].original_locator, "PDF 第 1 页")

            # S4 synthetic package (example.invalid) is retrieved by BM25 but blocked by PR #45
            # official-host gate via retriever.get_document_metadata() -> insufficient_evidence, 0 new LLM calls.
            s4_res = await workflow.run(AgentRequest(
                request_id=uuid4(),
                conversation_id=uuid4(),
                query="人工智能与大数据实验室在哪里，怎么申请GPU算力？",
            ))
            self.assertEqual(s4_res.status, AnswerStatus.INSUFFICIENT_EVIDENCE)
            self.assertEqual(llm.calls, 1)
            self.assertEqual(s4_res.citations, [])

    async def test_title_plus_content_bm25_has_no_degradation_vs_content_only_stress_suite(self):
        comparison = await run_comparison()
        content_only = comparison["content_only"]
        title_plus = comparison["title_and_content"]

        self.assertGreaterEqual(title_plus["chunk_count"], 35)
        self.assertGreaterEqual(title_plus["query_count"], 20)
        self.assertGreaterEqual(title_plus["hit_at_1"], content_only["hit_at_1"])
        self.assertGreaterEqual(title_plus["hit_at_3"], content_only["hit_at_3"])
        self.assertGreaterEqual(title_plus["mrr"], content_only["mrr"])
        self.assertLessEqual(
            title_plus["long_doc_boilerplate_in_top3"],
            content_only["long_doc_boilerplate_in_top3"],
        )
        for cat in ("long_doc", "similar_title", "same_name_lab", "cross_direction"):
            self.assertEqual(title_plus["by_category"][cat]["hit_at_1"], 1.0, msg=cat)


if __name__ == "__main__":
    unittest.main()
