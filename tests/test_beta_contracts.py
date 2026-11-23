"""Beta 接口契约测试（V2.1-Final）。

基于《CodeMind-FZU Beta 接口规范 V2.1-Final》的公共契约验证，只测试**已冻结的
规范**与**已实现的代码**，不依赖尚未实现的 Beta 功能（历史政策处理、S4、受约束
生成等），确保第一阶段测试即可通过、不阻塞 main。

覆盖：
- AnswerMode 四枚举完整性（current_policy / historical / procedure_reference /
  insufficient_data）。
- AgentResult 三状态结构约束（answered / needs_clarification / insufficient_evidence）。
- Retriever 三方法契约（retrieve / get_document_metadata / get_parsed_chunk）。
- 历史政策相关状态枚举（TimelinessVerificationStatus 的 historical / superseded /
  expired 等）。

注意：本文件只做「规范符合性」断言，不判定业务规则正确性（那属于后续阶段的
真实 E2E 验收）。
"""
from __future__ import annotations

import unittest
from uuid import uuid4

from pydantic import ValidationError

from backend.contracts.models import (
    AgentResult,
    AnswerMode,
    AnswerStatus,
    RetrievalStatus,
    SourceVerificationStatus,
    TimelinessVerificationStatus,
)
from backend.retrieval.local import LocalBM25Retriever


class AnswerModeContractTests(unittest.TestCase):
    """V2.1 §5.3 回答模式枚举完整性。"""

    def test_answer_mode_has_exactly_four_beta_values(self):
        expected = {"current_policy", "historical", "procedure_reference", "insufficient_data"}
        actual = {mode.value for mode in AnswerMode}
        self.assertEqual(actual, expected)

    def test_historical_and_procedure_reference_values(self):
        # V2.1 §9.2：historical（已结束年度）、procedure_reference（当前办理）
        self.assertEqual(AnswerMode.HISTORICAL.value, "historical")
        self.assertEqual(AnswerMode.PROCEDURE_REFERENCE.value, "procedure_reference")


class AgentResultShapeContractTests(unittest.TestCase):
    """V2.1 §6.2 AgentResult 三状态结构约束。"""

    def test_answered_requires_nonempty_answer(self):
        with self.assertRaises(ValidationError):
            AgentResult(status=AnswerStatus.ANSWERED, answer=None)
        result = AgentResult(
            status=AnswerStatus.ANSWERED,
            answer="根据已核验资料……",
            answer_mode=AnswerMode.CURRENT_POLICY,
        )
        self.assertEqual(result.status, AnswerStatus.ANSWERED)

    def test_needs_clarification_shape(self):
        result = AgentResult(
            status=AnswerStatus.NEEDS_CLARIFICATION,
            clarifying_question="请问你咨询的是哪一类奖学金？",
        )
        self.assertIsNone(result.answer)
        self.assertIsNone(result.answer_mode)
        self.assertIsNotNone(result.clarifying_question)
        self.assertEqual(result.citations, [])

    def test_insufficient_evidence_requires_insufficient_data_mode(self):
        with self.assertRaises(ValidationError):
            AgentResult(
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                answer="证据不足",
                answer_mode=AnswerMode.CURRENT_POLICY,  # 非法：应为 insufficient_data
            )
        result = AgentResult(
            status=AnswerStatus.INSUFFICIENT_EVIDENCE,
            answer="证据不足",
            answer_mode=AnswerMode.INSUFFICIENT_DATA,
        )
        self.assertEqual(result.answer_mode, AnswerMode.INSUFFICIENT_DATA)


class TimelinessEnumContractTests(unittest.TestCase):
    """V2.1 §9.3 证据门禁涉及的时效状态。"""

    def test_historical_modes_are_defined(self):
        # 历史政策允许的三种时效状态必须在枚举中定义（V2.1 §9.2/9.3）
        defined = {s.value for s in TimelinessVerificationStatus}
        for value in ("historical", "superseded", "expired"):
            self.assertIn(value, defined)

    def test_forbidden_states_are_defined_and_distinct(self):
        # pending / uncertain 是「不能放行」的状态（V2.1 §9.3），且不同于当前/历史状态
        self.assertEqual(TimelinessVerificationStatus.PENDING.value, "pending")
        self.assertEqual(TimelinessVerificationStatus.UNCERTAIN.value, "uncertain")
        self.assertNotEqual(
            TimelinessVerificationStatus.PENDING,
            TimelinessVerificationStatus.CURRENT,
        )
        self.assertNotEqual(
            TimelinessVerificationStatus.UNCERTAIN,
            TimelinessVerificationStatus.HISTORICAL,
        )


class LocalBM25RetrieverApiTests(unittest.TestCase):
    """V2.1 §8.1/8.2/8.3 LocalBM25Retriever 三方法实现检查。

    注意：本测试只检查 LocalBM25Retriever 这个**实现类**是否提供三个方法，
    不检查公共 Retriever Protocol（backend/contracts/protocols.py 目前只声明了
    retrieve，另外两个方法待王智洋补齐）。公共 Protocol 的三方法契约测试，
    待王智洋完成上游修改后补充，本文件不擅自修改他人负责的公共接口。
    """

    def test_local_bm25_retriever_has_three_methods(self):
        retriever = LocalBM25Retriever()
        self.assertTrue(callable(getattr(retriever, "retrieve", None)))
        self.assertTrue(callable(getattr(retriever, "get_document_metadata", None)))
        self.assertTrue(callable(getattr(retriever, "get_parsed_chunk", None)))

    def test_get_document_metadata_returns_none_for_unknown_version(self):
        self.assertIsNone(LocalBM25Retriever().get_document_metadata(uuid4()))

    def test_get_parsed_chunk_returns_none_for_unknown_chunk(self):
        self.assertIsNone(LocalBM25Retriever().get_parsed_chunk(uuid4()))


class RetrievalStatusContractTests(unittest.TestCase):
    """V2.1 §9.3 检索开放状态：blocked / review_only 不能进入正式问答。"""

    def test_retrieval_status_values(self):
        self.assertEqual(RetrievalStatus.BLOCKED.value, "blocked")
        self.assertEqual(RetrievalStatus.REVIEW_ONLY.value, "review_only")
        self.assertEqual(RetrievalStatus.ENABLED.value, "enabled")

    def test_source_verification_values(self):
        self.assertEqual(SourceVerificationStatus.VERIFIED.value, "verified")
        self.assertEqual(SourceVerificationStatus.FAILED.value, "failed")


if __name__ == "__main__":
    unittest.main()
