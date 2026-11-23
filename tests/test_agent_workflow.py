"""Workflow tests with explicit synthetic fixtures; never call real providers."""
import asyncio
import json
import unittest
from datetime import date
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from backend.contracts.models import (
    AgentRequest, AgentResult, AnswerStatus, ChunkIndexStatus, ConversationTurn, LLMResult,
    RetrievedChunk, RetrievalStatus, SourceVerificationStatus, TimelinessVerificationStatus,
)
from backend.services.agent_workflow import AgentWorkflow
from backend.services.errors import LLMTimeoutError, LLMUnavailableError
from examples.agent_workflow_demo import demo_chunk, demo_metadata, demo_parsed_chunk


class AgentWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.chunk = demo_chunk()
        self.retriever = AsyncMock()
        self.retriever.retrieve.return_value = [self.chunk]
        self.retriever.get_document_metadata = Mock(side_effect=lambda version_id: demo_metadata(next(
            chunk for chunk in reversed(self.retriever.retrieve.return_value) if chunk.version_id == version_id)))
        self.retriever.get_parsed_chunk = Mock(side_effect=lambda chunk_id: demo_parsed_chunk(next(
            chunk for chunk in self.retriever.retrieve.return_value if chunk.chunk_id == chunk_id)))
        self.llm = AsyncMock()
        self.llm.generate.side_effect = self.answer_from_prompt
        self.service = AgentWorkflow(
            self.retriever, self.llm, today=lambda: date(2026, 11, 17),
        )

    def request(self, query="选课有哪些步骤？", history=None):
        return AgentRequest(
            request_id=uuid4(), conversation_id=uuid4(), query=query,
            history=history or [],
        )

    @staticmethod
    def evidence_for(prompt):
        return json.loads(prompt.messages[-1].content)["evidence"]

    @staticmethod
    def selection(answer, ids):
        return LLMResult(model="TEST-FAKE-NOT-QWEN", content=json.dumps({
            "answer": answer, "used_evidence_ids": ids,
        }, ensure_ascii=False))

    async def answer_from_prompt(self, prompt):
        first = self.evidence_for(prompt)[0]
        return self.selection(first["content"], [first["evidence_id"]])

    async def test_missing_year_clarifies_without_dependencies(self):
        result = await self.service.run(self.request("奖学金怎么申请？"))
        self.assertEqual(result.status, AnswerStatus.NEEDS_CLARIFICATION)
        self.assertIsNone(result.answer)
        self.assertIsNone(result.answer_mode)
        self.assertEqual(result.citations, [])
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

    async def test_enabled_evidence_requires_explicit_human_approval(self):
        for notes in [None, {}, {"human_approved": False}, {"human_approved": "true"},
                      {"human_approved": 1}, {"human_approved": None}]:
            with self.subTest(notes=notes):
                metadata = demo_metadata(self.chunk)
                metadata.temporal_notes = notes
                self.retriever.get_document_metadata.side_effect = None
                self.retriever.get_document_metadata.return_value = metadata
                result = await self.service.run(self.request())
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.citations, [])
        self.llm.generate.assert_not_awaited()

    async def test_metadata_unavailable_or_mismatched_cannot_be_approved_by_business_rule(self):
        for value in [None, {}, demo_metadata(self.chunk).model_copy(update={"title": "另一个版本"})]:
            with self.subTest(value=value):
                self.retriever.get_document_metadata = Mock(return_value=value)
                result = await AgentWorkflow(self.retriever, self.llm,
                    evidence_check=lambda *_: True).run(self.request())
                self.assertEqual(result.status, "insufficient_evidence")
        self.retriever.get_document_metadata = Mock(side_effect=RuntimeError("private-review-error"))
        result = await self.service.run(self.request())
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertNotIn("private-review-error", result.model_dump_json())
        self.retriever.get_document_metadata = None
        result = await self.service.run(self.request())
        self.assertEqual(result.status, "insufficient_evidence")
        self.llm.generate.assert_not_awaited()

    async def test_approval_withdrawn_during_model_call_discards_answer(self):
        metadata = demo_metadata(self.chunk)
        self.retriever.get_document_metadata = Mock(side_effect=lambda _: metadata.model_copy(deep=True))

        async def generate(request):
            metadata.temporal_notes = {"human_approved": False}
            return await self.answer_from_prompt(request)

        self.llm.generate.side_effect = generate
        result = await self.service.run(self.request())
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.warnings[0].code, "EVIDENCE_APPROVAL_CHANGED")
        self.assertEqual(result.citations, [])

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
        self.assertEqual([x["content"] for x in data["evidence"]], [self.chunk.content])
        self.assertNotIn(str(self.chunk.chunk_id), prompt.messages[-1].content)
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
        other = self.chunk.model_copy(update={"chunk_id": uuid4(), "document_id": uuid4(),
                                             "version_id": uuid4(), "content": "第二条测试原文。"})
        self.retriever.retrieve.return_value = [self.chunk, other]
        async def answer(prompt):
            first, second = self.evidence_for(prompt)
            return self.selection(f'根据已核验资料，{second["content"]}\n{first["content"]}',
                                  [second["evidence_id"], first["evidence_id"]])
        self.llm.generate.side_effect = answer
        result = await self.service.run(self.request())
        self.assertEqual([c.chunk_id for c in result.citations], [other.chunk_id, self.chunk.chunk_id])

    async def test_bad_or_fabricated_model_outputs_are_rejected(self):
        valid = lambda evidence_id: {"answer": self.chunk.content, "used_evidence_ids": [evidence_id]}
        invalid = {
            "free text": lambda _: "这是一段没有引用的自由生成回答",
            "invalid JSON": lambda _: "{",
            "array": lambda _: "[]",
            "missing answer": lambda key: json.dumps({"used_evidence_ids": [key]}),
            "empty answer": lambda key: json.dumps({**valid(key), "answer": " "}),
            "no IDs": lambda key: json.dumps({**valid(key), "used_evidence_ids": []}),
            "unknown ID": lambda _: json.dumps(valid("E99")),
            "inactive ID": lambda key: json.dumps({**valid(key), "used_evidence_ids": [key, "E99"]}),
            "wrong ID type": lambda key: json.dumps({**valid(key), "used_evidence_ids": [[]]}),
            "duplicate key": lambda key: '{"answer":"fake",' + json.dumps(valid(key))[1:],
            "source field": lambda key: json.dumps({**valid(key), "source_url": "https://example.invalid/fake"}),
            "code fence": lambda key: '```json\n' + json.dumps(valid(key)) + '\n```',
        }
        for label, response in invalid.items():
            with self.subTest(label=label):
                async def answer(prompt):
                    key = self.evidence_for(prompt)[0]["evidence_id"]
                    return LLMResult(model="TEST-FAKE", content=response(key))
                self.llm.generate.side_effect = answer
                result = await self.service.run(self.request())
                self.assertEqual(result.warnings[0].code, "UNSUPPORTED_GENERATION")
                self.assertEqual(result.citations, [])

    async def test_wrong_provider_return_types_are_rejected(self):
        for wrong in [None, {}, [self.chunk.model_dump()]]:
            self.retriever.retrieve.return_value = wrong
            result = await self.service.run(self.request())
            self.assertEqual(result.warnings[0].code, "INVALID_RETRIEVAL_RESULT")
        self.retriever.retrieve.return_value = [self.chunk]
        self.llm.generate.side_effect = None
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
        with self.assertRaises(LLMUnavailableError) as raised:
            await self.service.run(self.request())
        self.assertNotIn("private-credential", str(raised.exception))

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

    async def test_model_cancellation_is_not_swallowed(self):
        self.llm.generate.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await self.service.run(self.request())

    async def test_model_cannot_select_filtered_or_previous_round_evidence(self):
        rejected = self.chunk.model_copy(update={"chunk_id": uuid4(), "document_id": uuid4(), "version_id": uuid4()})
        self.retriever.retrieve.return_value = [self.chunk, rejected]
        service = AgentWorkflow(
            self.retriever, self.llm,
            evidence_check=lambda req, chunk: chunk.chunk_id != rejected.chunk_id,
        )
        request = self.request()
        self.assertEqual((await service.run(request)).status, "answered")
        entries = self.evidence_for(self.llm.generate.call_args.args[0])
        self.assertEqual(len(entries), 1)
        for key in (str(rejected.chunk_id), entries[0]["evidence_id"]):
            self.llm.generate.side_effect = None
            self.llm.generate.return_value = self.selection(self.chunk.content, [key])
            result = await service.run(request)
            self.assertEqual(result.status, "insufficient_evidence")
            self.assertEqual(result.citations, [])

    async def test_4000_character_contract_query_is_not_silently_truncated(self):
        result = await self.service.run(self.request("选课" + "问" * 3998))
        self.assertEqual(result.warnings[0].code, "RETRIEVAL_QUERY_TOO_LONG")
        self.retriever.retrieve.assert_not_awaited()

    async def test_history_overflow_is_not_silently_truncated(self):
        history = [ConversationTurn(role="user", content="选课" + "问" * 2000)]
        result = await self.service.run(self.request("那具体怎么做？", history))
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

    def annual_fixture(self, *, year="2025年", status="expired", deadline=date(2025, 10, 3)):
        self.chunk = self.chunk.model_copy(update={
            "title": "合成院级奖学金评选通知",
            "content": "全日制本科生可申请，金额为3000元，截止日期为2025年10月3日。",
            "published_on": date(2025, 9, 1),
            "timeliness_verification_status": TimelinessVerificationStatus(status),
        })
        self.retriever.retrieve.return_value = [self.chunk]
        metadata = demo_metadata(self.chunk).model_copy(update={
            "applicability_raw": {"适用年度": year, "适用对象": "全日制本科生"},
            "deadline_on": deadline,
        })
        self.retriever.get_document_metadata = Mock(return_value=metadata)
        return AgentWorkflow(self.retriever, self.llm, evidence_check=lambda *_: True,
                             today=lambda: date(2026, 11, 17))

    async def test_historical_notice_answers_only_the_matching_period(self):
        for status in ("historical", "expired", "superseded", "current"):
            with self.subTest(status=status):
                service = self.annual_fixture(status=status)
                result = await service.run(self.request("2025年院级奖学金申请条件、金额和截止日期？"))
                self.assertEqual(result.answer_mode, "historical")
                self.assertIn("2025年历史资料", result.answer)
                self.assertIn("3000元", result.answer)
                self.assertIn("2025年10月3日", result.answer)
                self.assertEqual(result.citations[0].excerpt, self.chunk.content)
                if status == "superseded":
                    self.assertIn("已被替代", result.answer)

    async def test_no_matching_historical_or_current_evidence_does_not_call_model(self):
        service = self.annual_fixture()
        for query in ("2024年奖学金申请条件？", "今年奖学金还能报名吗？", "2027年奖学金申请条件？",
                      "2025年奖学金通知现在还能用吗？"):
            with self.subTest(query=query):
                result = await service.run(self.request(query))
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.citations, [])
        self.llm.generate.assert_not_awaited()

    async def test_ambiguous_history_clarifies_before_retrieval(self):
        service = self.annual_fixture()
        result = await service.run(self.request("往年院级奖学金有哪些条件？"))
        self.assertEqual(result.status, "needs_clarification")
        self.assertIn("学年", result.clarifying_question)
        self.retriever.retrieve.assert_not_awaited()
        self.llm.generate.assert_not_awaited()

    async def test_bare_year_answers_the_pending_historical_question(self):
        service = self.annual_fixture()
        history = [ConversationTurn(role="user", content="往年院级奖学金截止日期是什么？")]
        result = await service.run(self.request("2025", history))
        self.assertEqual(result.answer_mode, "historical")
        self.assertIn("2025年10月3日", result.answer)

    async def test_current_annual_notice_is_a_procedure_reference(self):
        service = self.annual_fixture(year="2026年", status="current", deadline=date(2026, 12, 3))
        self.chunk = self.chunk.model_copy(update={"content": "本科生提交申请表，截止日期为2026年12月3日。"})
        self.retriever.retrieve.return_value = [self.chunk]
        result = await service.run(self.request("2026年院级奖学金申请流程是什么？"))
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.answer_mode, "procedure_reference")

    async def test_short_availability_followups_keep_the_active_topic(self):
        for topic, query in (
            ("2026年院级奖学金怎么申请？", "还能申请吗？"),
            ("2026年EDA实验室怎么报名？", "还能报名吗"),
            ("2026年EDA实验室怎么报名？", "请问还可以报名吗？"),
        ):
            with self.subTest(query=query):
                service = self.annual_fixture(year="2026年", status="current", deadline=date(2026, 12, 3))
                self.chunk = self.chunk.model_copy(update={"content": "提交申请表，截止日期为2026年12月3日。"})
                self.retriever.retrieve.return_value = [self.chunk]
                history = [ConversationTurn(role="user", content=topic)]
                result = await service.run(self.request(query, history))
                self.assertEqual(result.answer_mode, "procedure_reference")
                retrieval_query = self.retriever.retrieve.call_args.args[0].query
                self.assertEqual(retrieval_query, f"{topic}\n{query}")

    async def test_short_availability_followup_cannot_use_an_expired_notice(self):
        workflow = self.annual_fixture()
        result = await workflow.run(self.request("还能申请吗？", [
            ConversationTurn(role="user", content="2025年院级奖学金有哪些条件？"),
        ]))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.citations, [])
        self.retriever.retrieve.assert_awaited_once()
        self.llm.generate.assert_not_awaited()

    async def test_short_availability_question_with_no_topic_clarifies(self):
        result = await self.service.run(self.request("还能报名吗？"))
        self.assertEqual(result.status, "needs_clarification")
        self.retriever.retrieve.assert_not_awaited()
        self.llm.generate.assert_not_awaited()

    async def test_academic_year_range_is_resolved_from_metadata(self):
        service = self.annual_fixture(year="2025—2026学年")
        for query_range in ("2025-2026学年", "2025—2026学年", "2025 至 2026 学年"):
            with self.subTest(query_range=query_range):
                result = await service.run(self.request(f"{query_range}奖学金申请条件？"))
                self.assertEqual(result.answer_mode, "historical")
                self.assertIn("2025—2026学年", result.answer)

    async def test_missing_or_mismatched_parsed_chunk_blocks_before_model(self):
        parsed = demo_parsed_chunk(self.chunk)
        for value in (None, parsed.model_copy(update={"content": "伪造原文"}),
                      parsed.model_copy(update={"locator": "另一个章节"}),
                      parsed.model_copy(update={"index_status": ChunkIndexStatus.DISABLED})):
            self.retriever.get_parsed_chunk = Mock(return_value=value)
            result = await self.service.run(self.request())
            self.assertEqual(result.status, "insufficient_evidence")
            self.assertEqual(result.citations, [])
        self.llm.generate.assert_not_awaited()

    async def test_four_scenarios_use_the_same_injected_rules_and_full_retrieval(self):
        queries = ("竞赛认定怎么查？", "校级奖学金条件是什么？", "推免资格是什么？",
                   "学院实验室研究方向是什么？")
        for query in queries:
            with self.subTest(query=query):
                clarification = Mock(return_value=None)
                evidence = Mock(return_value=True)
                self.chunk = self.chunk.model_copy(update={"content": f"合成测试资料：{query}"})
                self.retriever.retrieve.return_value = [self.chunk]
                workflow = AgentWorkflow(self.retriever, self.llm, clarification_rule=clarification,
                                         evidence_check=evidence)
                result = await workflow.run(self.request(query))
                self.assertEqual(result.status, "answered")
                self.assertEqual(clarification.call_args.args[0].query, query)
                self.assertEqual(evidence.call_args.args[0].query, query)
                self.assertIsNone(self.retriever.retrieve.call_args.args[0].business_direction_code)

    async def test_resource_request_does_not_use_past_recruitment_as_current(self):
        service = self.annual_fixture()
        for query in ("实验室现在还在招募吗？", "学院实验室研究方向是什么？"):
            result = await service.run(self.request(query))
            self.assertEqual(result.status, "insufficient_evidence")
        self.llm.generate.assert_not_awaited()

    async def test_explicit_current_period_and_grade_override_history(self):
        history = [
            ConversationTurn(role="user", content="我是2022级，想查2025年奖学金的条件。"),
            ConversationTurn(role="assistant", content="凭空给出的政策金额 99999 元"),
        ]
        service = AgentWorkflow(self.retriever, self.llm, evidence_check=lambda *_: True)
        await service.run(self.request("那我是2024级，查2026年呢？", history))
        text = self.retriever.retrieve.call_args.args[0].query
        self.assertIn("奖学金", text)
        self.assertIn("2026年", text)
        self.assertIn("2024级", text)
        for stale in ("2022级", "2025年", "99999"):
            self.assertNotIn(stale, text)
        self.assertNotIn("99999", self.llm.generate.call_args.args[0].messages[-1].content)

    async def test_topic_change_and_new_conversation_do_not_inherit_old_details(self):
        history = [ConversationTurn(role="user", content="2025年奖学金申请条件？")]
        await self.service.run(self.request("那学院实验室研究方向是什么？", history))
        self.assertEqual(self.retriever.retrieve.call_args.args[0].query, "那学院实验室研究方向是什么？")
        self.retriever.retrieve.reset_mock()
        result = await self.service.run(self.request("2025年呢？"))
        self.assertEqual(result.status, "needs_clarification")
        self.retriever.retrieve.assert_not_awaited()

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

    async def test_clarification_rule_errors_and_wrong_types_stop_dependencies(self):
        def broken(request):
            raise RuntimeError("private-rule-detail")
        for rule in [broken, lambda _: False, lambda _: " ", lambda _: []]:
            with self.subTest(rule=rule):
                service = AgentWorkflow(self.retriever, self.llm, clarification_rule=rule)
                result = await service.run(self.request())
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.warnings[0].code, "CLARIFICATION_RULE_FAILED")
                self.assertNotIn("private-rule-detail", result.model_dump_json())
        self.retriever.retrieve.assert_not_awaited()
        self.llm.generate.assert_not_awaited()

    async def test_evidence_rule_requires_boolean_not_truthy_unknown(self):
        for unknown in [None, "unknown", "false", 1, {"applicable": True}]:
            with self.subTest(unknown=unknown):
                service = AgentWorkflow(
                    self.retriever, self.llm, evidence_check=lambda *_: unknown,
                )
                result = await service.run(self.request())
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.warnings[0].code, "INVALID_RETRIEVAL_RESULT")
        self.llm.generate.assert_not_awaited()

    async def test_rules_cannot_mutate_request_or_verified_source(self):
        original = self.chunk.model_dump()
        request = self.request()

        def clarification(candidate):
            candidate.query = "被回调替换的问题"
            return None

        def evidence(candidate, chunk):
            candidate.query = "被回调替换的问题"
            chunk.content = "被回调替换的政策条件"
            chunk.source_url = "https://example.invalid/replaced"
            return True

        service = AgentWorkflow(
            self.retriever, self.llm, clarification_rule=clarification,
            evidence_check=evidence,
        )
        result = await service.run(request)
        self.assertEqual(result.status, "answered")
        self.assertEqual(request.query, "选课有哪些步骤？")
        self.assertEqual(self.chunk.model_dump(), original)
        self.assertEqual(result.citations[0].excerpt, self.chunk.content)
        self.assertEqual(result.citations[0].source_url, self.chunk.source_url)
        self.assertEqual(self.retriever.retrieve.call_args.args[0].query, request.query)

    async def test_extended_chunk_metadata_reaches_rules_only(self):
        # Provisional test-only fields: this does not change the shared contract
        # or claim agreement with retrieval/business owners.
        class ExtendedChunk(RetrievedChunk):
            applicability_raw: dict[str, str]
            deadline_on: date | None
            policy_year: int | None

        extended = ExtendedChunk(
            **self.chunk.model_dump(), applicability_raw={"scope": "test-only"},
            deadline_on=date(2026, 12, 31), policy_year=2026,
        )
        self.retriever.retrieve.return_value = [extended]
        observed = []

        def evidence(request, chunk):
            observed.append(chunk)
            return chunk.applicability_raw == {"scope": "test-only"}

        service = AgentWorkflow(self.retriever, self.llm, evidence_check=evidence)
        result = await service.run(self.request())
        self.assertEqual(result.status, "answered")
        self.assertEqual(observed, [extended, extended])
        sent = json.loads(self.llm.generate.call_args.args[0].messages[-1].content)["evidence"][0]
        self.assertEqual(set(sent), {"content", "evidence_id", "answer_mode"})
        self.assertNotIn("policy_year", result.citations[0].model_dump())
        self.assertEqual(result.citations[0].excerpt, extended.content)

    async def test_year_scope_mismatch_and_unknown_fail_before_model(self):
        class ScopedChunk(RetrievedChunk):
            policy_year: int | None
            scope: str | None

        # This is a callback contract test, not the owner's business rules.
        def fixture_evidence(request, chunk):
            return chunk.policy_year == 2026 and chunk.scope == "undergraduate"

        for year, scope in [(2025, "undergraduate"), (2026, "graduate"), (None, None)]:
            with self.subTest(year=year, scope=scope):
                self.retriever.retrieve.return_value = [ScopedChunk(
                    **self.chunk.model_dump(), policy_year=year, scope=scope,
                )]
                service = AgentWorkflow(self.retriever, self.llm, evidence_check=fixture_evidence)
                result = await service.run(self.request("2026年校级奖学金申请条件是什么？"))
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.citations, [])
        self.llm.generate.assert_not_awaited()

    async def test_valid_id_cannot_attach_fabricated_policy_claims(self):
        service = self.annual_fixture()
        for answer in (
            self.chunk.content.replace("3000", "9000"),
            self.chunk.content.replace("本科生", "研究生"),
            self.chunk.content.replace("可申请", "无需条件，一律可申请"),
            self.chunk.content.replace("10月3日", "10月30日"),
            self.chunk.content + " 该政策目前仍有效。",
            self.chunk.content + "\n来源：https://example.invalid/forged",
        ):
            with self.subTest(answer=answer):
                async def respond(prompt):
                    key = self.evidence_for(prompt)[0]["evidence_id"]
                    return self.selection(answer, [key])
                self.llm.generate.side_effect = respond
                result = await service.run(self.request("2025年奖学金申请条件？"))
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.citations, [])

    async def test_duplicate_ids_and_unused_citations_are_rejected(self):
        other = self.chunk.model_copy(update={"chunk_id": uuid4(), "content": "第二条内容"})
        self.retriever.retrieve.return_value = [self.chunk, other]
        for repeated in (True, False):
            async def answer(prompt):
                first, second = self.evidence_for(prompt)
                key = first["evidence_id"]
                return self.selection(first["content"], [key, key if repeated else second["evidence_id"]])
            self.llm.generate.side_effect = answer
            result = await self.service.run(self.request())
            self.assertEqual(result.status, "insufficient_evidence")

    async def test_partial_answer_warns_and_cites_only_the_used_source(self):
        async def answer(prompt):
            first = self.evidence_for(prompt)[0]
            return self.selection(first["content"] + "\n其余问题缺少可核验的资料，暂无法确认。",
                                  [first["evidence_id"]])
        self.llm.generate.side_effect = answer
        result = await self.service.run(self.request("选课有哪些步骤，能查到手续费吗？"))
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.warnings[0].code, "PARTIAL_EVIDENCE")
        self.assertEqual([citation.chunk_id for citation in result.citations], [self.chunk.chunk_id])

    async def test_known_amount_without_a_deadline_only_supports_partial_answer(self):
        service = self.annual_fixture(year="2025年")
        self.chunk = self.chunk.model_copy(update={"content": "全日制本科生可申请，金额为3000元。"})
        self.retriever.retrieve.return_value = [self.chunk]
        request = self.request("2025年奖学金金额和截止时间是什么？")
        result = await service.run(request)
        self.assertEqual(result.status, "insufficient_evidence")

        async def answer(prompt):
            first = self.evidence_for(prompt)[0]
            return self.selection("全日制本科生可以申请，金额是3000元。\n其余问题缺少可核验的资料，暂无法确认。",
                                  [first["evidence_id"]])

        self.llm.generate.side_effect = answer
        result = await service.run(request)
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.warnings[-1].code, "PARTIAL_EVIDENCE")
        self.assertIn("金额是3000元", result.answer)
        self.assertEqual(result.citations[0].excerpt, self.chunk.content)

    async def test_one_fragment_can_cover_both_requested_facts(self):
        workflow = self.annual_fixture()
        result = await workflow.run(self.request("2025年奖学金的金额和截止日期是什么？"))
        self.assertEqual(result.status, "answered")
        self.assertIn("3000元", result.answer)
        self.assertIn("2025年10月3日", result.answer)
        self.assertEqual([item.chunk_id for item in result.citations], [self.chunk.chunk_id])

    async def test_multiple_amount_fragments_do_not_cover_a_missing_deadline(self):
        workflow = self.annual_fixture()
        amount = self.chunk.model_copy(update={"content": "奖学金金额为3000元。"})
        repeated = self.chunk.model_copy(update={"chunk_id": uuid4(), "content": "每名获奖学生发放3000元。"})
        deadline = self.chunk.model_copy(update={"chunk_id": uuid4(), "content": "申请截止日期为2025年10月3日。"})
        self.retriever.retrieve.return_value = [amount, repeated, deadline]

        async def answer(prompt):
            first, second, _ = self.evidence_for(prompt)
            return self.selection(
                f'{first["content"]}\n{second["content"]}',
                [first["evidence_id"], second["evidence_id"]],
            )

        self.llm.generate.side_effect = answer
        result = await workflow.run(self.request("2025年奖学金的金额和截止日期是什么？"))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.warnings[0].code, "UNSUPPORTED_GENERATION")
        self.assertEqual(result.citations, [])

    async def test_requested_amount_without_support_stops_before_generation(self):
        result = await self.service.run(self.request("2026年校级奖学金金额是多少？"))
        self.assertEqual(result.warnings[0].code, "REQUESTED_FACT_NOT_FOUND")
        self.assertEqual(result.citations, [])
        self.llm.generate.assert_not_awaited()

    def test_invalid_configuration_is_rejected(self):
        for options in [{"top_k": 0}, {"top_k": 21}, {"timeout_seconds": 0},
                        {"timeout_seconds": float("nan")}, {"max_evidence_chars": 0},
                        {"clarification_rule": None}, {"evidence_check": "not-callable"}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                AgentWorkflow(self.retriever, self.llm, **options)


if __name__ == "__main__":
    unittest.main()
