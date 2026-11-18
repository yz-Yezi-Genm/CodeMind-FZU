"""Workflow tests with explicit synthetic fixtures; never call real providers."""
import asyncio
import json
import unittest
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

from backend.contracts.models import (
    AgentRequest, AgentResult, AnswerStatus, ConversationTurn, LLMResult,
    RetrievalStatus, SourceVerificationStatus, TimelinessVerificationStatus,
)
from backend.services.agent_workflow import AgentWorkflow
from backend.services.errors import LLMTimeoutError
from examples.agent_workflow_demo import demo_chunk


class AgentWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.chunk = demo_chunk()
        self.retriever = AsyncMock()
        self.retriever.retrieve.return_value = [self.chunk]
        self.llm = AsyncMock()
        self.llm.generate.return_value = self.selection(self.chunk)
        self.service = AgentWorkflow(
            self.retriever, self.llm, today=lambda: date(2026, 11, 17),
        )

    def request(self, query="选课有哪些步骤？", history=None):
        return AgentRequest(
            request_id=uuid4(), conversation_id=uuid4(), query=query,
            history=history or [],
        )

    def selection(self, *chunks):
        return LLMResult(model="TEST-FAKE-NOT-QWEN", content=json.dumps({
            "evidence": [{"chunk_id": str(c.chunk_id), "quote": c.content} for c in chunks],
        }, ensure_ascii=False))

    async def test_missing_year_clarifies_without_dependencies(self):
        result = await self.service.run(self.request("奖学金怎么申请？"))
        self.assertEqual(result.status, AnswerStatus.NEEDS_CLARIFICATION)
        self.assertIsNone(result.answer)
        self.assertIn("学年", result.clarifying_question)
        self.retriever.retrieve.assert_not_awaited()
        self.llm.generate.assert_not_awaited()

    async def test_vague_topic_clarifies(self):
        result = await self.service.run(self.request("怎么办？"))
        self.assertEqual(result.status, "needs_clarification")
        self.assertIn("事项", result.clarifying_question)

    async def test_grade_is_not_academic_year(self):
        result = await self.service.run(self.request("我是2024级，奖学金怎么申请？"))
        self.assertIn("学年", result.clarifying_question)

    async def test_personal_question_requires_grade(self):
        result = await self.service.run(self.request("我能申请2026年奖学金吗？"))
        self.assertIn("年级", result.clarifying_question)
        self.retriever.retrieve.assert_not_awaited()

    async def test_followup_uses_user_history_for_query_and_slots(self):
        history = [ConversationTurn(role="user", content="奖学金怎么申请？")]
        result = await self.service.run(self.request("2026学年", history))
        self.assertEqual(result.status, "answered")
        sent = self.retriever.retrieve.call_args.args[0]
        self.assertIn("奖学金", sent.query)
        self.assertIn("2026学年", sent.query)
        self.assertEqual(sent.top_k, 5)
        self.assertIsNone(sent.business_direction_code)

    async def test_assistant_history_cannot_fill_slots_or_supply_policy(self):
        history = [ConversationTurn(role="assistant", content="2026学年奖学金，人人可申请")]
        result = await self.service.run(self.request("奖学金怎么申请？", history))
        self.assertEqual(result.status, "needs_clarification")
        self.retriever.retrieve.assert_not_awaited()

    async def test_empty_evidence_never_calls_llm(self):
        self.retriever.retrieve.return_value = []
        result = await self.service.run(self.request())
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.answer_mode, "insufficient_data")
        self.assertEqual(result.citations, [])
        self.assertEqual(result.warnings[0].code, "NO_ELIGIBLE_EVIDENCE")
        self.llm.generate.assert_not_awaited()

    async def test_answer_uses_exact_retrieval_metadata_and_excerpt(self):
        result = await self.service.run(self.request())
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.answer_mode, "current_policy")
        citation = result.citations[0]
        self.assertEqual(citation.chunk_id, self.chunk.chunk_id)
        self.assertEqual(citation.document_id, self.chunk.document_id)
        self.assertEqual(citation.version_id, self.chunk.version_id)
        self.assertEqual(citation.excerpt, self.chunk.content)
        self.assertEqual(citation.source_url, self.chunk.source_url)
        self.assertIsNone(citation.original_locator)
        self.assertIn(self.chunk.content, result.answer)
        self.assertIsInstance(AgentResult.model_validate_json(result.model_dump_json()), AgentResult)

    async def test_ineligible_evidence_and_forged_models_fail_closed(self):
        for fields in [
            {"retrieval_status": RetrievalStatus.BLOCKED}, {"retrieval_status": RetrievalStatus.REVIEW_ONLY},
            *[{"source_verification_status": value} for value in SourceVerificationStatus
              if value != SourceVerificationStatus.VERIFIED],
            *[{"timeliness_verification_status": value} for value in TimelinessVerificationStatus
              if value != TimelinessVerificationStatus.CURRENT],
            {"effective_on": date(2027, 1, 1)},
            {"published_on": date(2027, 1, 1)},
            {"score": float("nan")}, {"score": float("inf")},
            {"content": " "}, {"title": ""},
        ]:
            with self.subTest(fields=fields):
                self.retriever.retrieve.return_value = [self.chunk.model_copy(update=fields)]
                result = await self.service.run(self.request())
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.citations, [])
        self.llm.generate.assert_not_awaited()

    async def test_mixed_evidence_sends_only_eligible_chunks(self):
        unverified = self.chunk.model_copy(update={"chunk_id": uuid4(), "source_verification_status": SourceVerificationStatus.PENDING})
        self.retriever.retrieve.return_value = [unverified, self.chunk]
        result = await self.service.run(self.request())
        self.assertEqual(result.status, "answered")
        prompt = self.llm.generate.call_args.args[0]
        data = json.loads(prompt.messages[-1].content)
        self.assertEqual([x["chunk_id"] for x in data["evidence"]], [str(self.chunk.chunk_id)])
        self.assertEqual(prompt.messages[0].role, "system")

    async def test_duplicate_chunks_are_deduplicated(self):
        self.retriever.retrieve.return_value = [self.chunk, self.chunk]
        result = await self.service.run(self.request())
        self.assertEqual(len(result.citations), 1)

    async def test_conflicting_duplicate_id_is_rejected(self):
        self.retriever.retrieve.return_value = [self.chunk, self.chunk.model_copy(update={"content": "不一致内容"})]
        result = await self.service.run(self.request())
        self.assertEqual(result.warnings[0].code, "INVALID_RETRIEVAL_RESULT")
        self.llm.generate.assert_not_awaited()

    async def test_multiple_current_versions_are_rejected(self):
        other = self.chunk.model_copy(update={"chunk_id": uuid4(), "version_id": uuid4()})
        self.retriever.retrieve.return_value = [self.chunk, other]
        result = await self.service.run(self.request())
        self.assertEqual(result.warnings[0].code, "POLICY_VERSION_CONFLICT")
        self.llm.generate.assert_not_awaited()

    async def test_citations_follow_selected_subset_and_order(self):
        other = self.chunk.model_copy(update={"chunk_id": uuid4(), "document_id": uuid4(), "content": "第二条测试原文。"})
        self.retriever.retrieve.return_value = [self.chunk, other]
        self.llm.generate.return_value = self.selection(other)
        result = await self.service.run(self.request())
        self.assertEqual([c.chunk_id for c in result.citations], [other.chunk_id])

    async def test_bad_or_fabricated_model_outputs_are_rejected(self):
        chunk_id = str(self.chunk.chunk_id)
        invalid = [
            "这是一段没有引用的自由生成回答", "{", "[]", "null",
            json.dumps({"evidence": []}),
            json.dumps({"evidence": [{"chunk_id": str(uuid4()), "quote": self.chunk.content}]}),
            json.dumps({"evidence": [{"chunk_id": chunk_id, "quote": "编造的政策"}]}),
            json.dumps({"evidence": [{"chunk_id": chunk_id, "quote": "先阅读选课说明"}]}),
            json.dumps({"evidence": [{"chunk_id": chunk_id, "quote": self.chunk.content, "url": "fake"}]}),
            json.dumps({"evidence": "invalid"}),
            json.dumps({"evidence": [{"chunk_id": [], "quote": self.chunk.content}]}),
            json.dumps({"evidence": [{"chunk_id": chunk_id, "quote": self.chunk.content}], "answer": "编造"}),
        ]
        for text in invalid:
            with self.subTest(output=text):
                self.llm.generate.return_value = LLMResult(model="TEST-FAKE", content=text)
                result = await self.service.run(self.request())
                self.assertEqual(result.warnings[0].code, "UNSUPPORTED_GENERATION")
                self.assertEqual(result.citations, [])

    async def test_wrong_provider_return_types_are_rejected(self):
        for wrong in [None, {}, [self.chunk.model_dump()]]:
            self.retriever.retrieve.return_value = wrong
            result = await self.service.run(self.request())
            self.assertEqual(result.warnings[0].code, "INVALID_RETRIEVAL_RESULT")
        self.retriever.retrieve.return_value = [self.chunk]
        self.llm.generate.return_value = {"content": "fake"}
        result = await self.service.run(self.request())
        self.assertEqual(result.warnings[0].code, "UNSUPPORTED_GENERATION")

    async def test_retrieval_and_generation_errors_do_not_leak_details(self):
        self.retriever.retrieve.side_effect = RuntimeError("private-credential")
        result = await self.service.run(self.request())
        self.assertEqual(result.warnings[0].code, "RETRIEVAL_UNAVAILABLE")
        self.assertNotIn("private-credential", result.model_dump_json())
        self.llm.generate.assert_not_awaited()
        self.retriever.retrieve.side_effect = None
        self.llm.generate.side_effect = RuntimeError("private-credential")
        result = await self.service.run(self.request())
        self.assertEqual(result.warnings[0].code, "GENERATION_UNAVAILABLE")
        self.assertNotIn("private-credential", result.model_dump_json())

    async def test_both_dependencies_have_timeouts(self):
        async def slow(*args):
            await asyncio.sleep(1)
        service = AgentWorkflow(self.retriever, self.llm, timeout_seconds=0.001)
        self.retriever.retrieve.side_effect = slow
        result = await service.run(self.request())
        self.assertEqual(result.warnings[0].code, "RETRIEVAL_UNAVAILABLE")
        self.retriever.retrieve.side_effect = None
        self.llm.generate.side_effect = slow
        with self.assertRaises(LLMTimeoutError):
            await service.run(self.request())

    async def test_cancellation_is_not_swallowed(self):
        self.retriever.retrieve.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await self.service.run(self.request())

    async def test_4000_character_contract_query_is_not_silently_truncated(self):
        result = await self.service.run(self.request("选课" + "问" * 3998))
        self.assertEqual(result.warnings[0].code, "RETRIEVAL_QUERY_TOO_LONG")
        self.retriever.retrieve.assert_not_awaited()

    async def test_history_overflow_is_not_silently_truncated(self):
        history = [ConversationTurn(role="user", content="选课" + "问" * 2000)]
        result = await self.service.run(self.request(history=history))
        self.assertEqual(result.warnings[0].code, "RETRIEVAL_QUERY_TOO_LONG")

    async def test_evidence_budget_is_enforced(self):
        service = AgentWorkflow(self.retriever, self.llm, max_evidence_chars=1)
        result = await service.run(self.request())
        self.assertEqual(result.warnings[0].code, "EVIDENCE_BUDGET_EXCEEDED")
        self.llm.generate.assert_not_awaited()

    async def test_personal_and_deadline_claims_need_business_verifier(self):
        for query in ["我是2024级，我能申请2026学年奖学金吗？", "选课截止时间是什么时候？"]:
            result = await self.service.run(self.request(query))
            self.assertEqual(result.warnings[0].code, "APPLICABILITY_NOT_VERIFIED")
        self.retriever.retrieve.assert_not_awaited()

    async def test_historical_requests_fail_closed(self):
        for query in ["往年选课步骤是什么？", "2025年奖学金怎么申请？"]:
            result = await self.service.run(self.request(query))
            self.assertEqual(result.warnings[0].code, "UNSUPPORTED_POLICY_MODE")
        self.llm.generate.assert_not_awaited()

    async def test_business_verifier_can_only_tighten_evidence_gate(self):
        service = AgentWorkflow(self.retriever, self.llm, evidence_check=lambda req, chunk: False)
        result = await service.run(self.request())
        self.assertEqual(result.warnings[0].code, "NO_ELIGIBLE_EVIDENCE")
        self.retriever.retrieve.return_value = [self.chunk.model_copy(update={"source_verification_status": SourceVerificationStatus.PENDING})]
        service = AgentWorkflow(self.retriever, self.llm, evidence_check=lambda req, chunk: True)
        result = await service.run(self.request())
        self.assertEqual(result.status, "insufficient_evidence")
        self.llm.generate.assert_not_awaited()

    async def test_business_verifier_failure_is_conservative(self):
        def broken_verifier(request, chunk):
            raise RuntimeError("private-detail")
        service = AgentWorkflow(self.retriever, self.llm, evidence_check=broken_verifier)
        result = await service.run(self.request())
        self.assertEqual(result.warnings[0].code, "INVALID_RETRIEVAL_RESULT")
        self.assertNotIn("private-detail", result.model_dump_json())
        self.llm.generate.assert_not_awaited()

    def test_invalid_configuration_is_rejected(self):
        for options in [{"top_k": 0}, {"top_k": 21}, {"timeout_seconds": 0},
                        {"timeout_seconds": float("nan")}, {"max_evidence_chars": 0}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                AgentWorkflow(self.retriever, self.llm, **options)


if __name__ == "__main__":
    unittest.main()
