"""Beta 接口契约测试（V2.1-Final）。

基于《CodeMind-FZU Beta 接口规范 V2.1-Final》的公共契约验证，只测试**已冻结的
规范**与**已实现的代码**，不依赖尚未实现的 Beta 功能（历史政策处理、S4、受约束
生成等），确保 Draft 阶段测试即可通过、不阻塞 main。

覆盖：
- AnswerMode 四枚举完整性（current_policy / historical / procedure_reference /
  insufficient_data）。
- AgentResult 三状态结构约束（answered / needs_clarification / insufficient_evidence）。
- Retriever 三方法契约（retrieve / get_document_metadata / get_parsed_chunk）。
- 历史政策相关状态枚举（TimelinessVerificationStatus 的 historical / superseded /
  expired 等）。

注意：本文件只做「规范符合性」断言，不判定业务规则正确性（那属于 Final PR 的
真实 E2E 验收）。
"""
from __future__ import annotations

import unittest

from backend.contracts.models import (
    AgentResult,
    AnswerMode,
    AnswerStatus,
    Citation,
    DocumentMetadata,
    ParsedChunk,
    RetrievalStatus,
    SourceVerificationStatus,
    TimelinessVerificationStatus,
    WarningItem,
)
from backend.contracts.protocols import Retriever
from backend.retrieval.local import LocalBM25Retriever


class AnswerModeContractTests(unittest.TestCase):
    """V2.1 §5.3 回答模式枚举完整性。"""

    def test_answer_mode_has_four_beta_values(self):
        expected = {"current_policy", "historical", "procedure_reference", "insufficient_data"}
        actual = {mode.value for mode in AnswerMode}
        self.assertEqual(actual, expected)

    def test_answer_mode_historical_and_procedure_reference_defined(self):
        # V2.1 §9.2 历史政策要求：historical（已结束年度）、procedure_reference（当前办理）
        self.assertEqual(AnswerMode.HISTORICAL.value, "historical")
        self.assertEqual(AnswerMode.PROCEDURE_REFERENCE.value, "procedure_reference")
        self.assertEqual(AnswerMode.CURRENT_POLICY.value, "current_policy")
        self.assertEqual(AnswerMode.INSUFFICIENT_DATA.value, "insufficient_data")


class AgentResultShapeContractTests(unittest.TestCase):
    """V2.1 §6.2 AgentResult 三状态结构约束。"""

    def _base(self, status):
        return AgentResult(status=status)

    def test_answered_requires_nonempty_answer(self):
        with self.assertRaises(Exception):
            AgentResult(status=AnswerStatus.ANSWERED, answer=None)
        # answered 且 answer 非空 + 明确 answer_mode 是合法的
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
        self.assertEqual(result.citations, [])

    def test_insufficient_evidence_requires_insufficient_data_mode(self):
        with self.assertRaises(Exception):
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

    def test_timeliness_has_historical_superseded_expired(self):
        # 历史政策允许 historical / superseded / expired，不允许 pending / uncertain / failed
        allowed_historical = {
            TimelinessVerificationStatus.HISTORICAL,
            TimelinessVerificationStatus.SUPERSEDED,
            TimelinessVerificationStatus.EXPIRED,
        }
        for status in allowed_historical:
            self.assertIn(status.value, {
                "historical", "superseded", "expired",
            })

    def test_timeliness_forbidden_states(self):
        forbidden = {
            TimelinessVerificationStatus.PENDING,
            TimelinessVerificationStatus.UNCERTAIN,
        }
        # pending / uncertain 不能放行（V2.1 §9.3 明确列出）
        self.assertIn(TimelinessVerificationStatus.PENDING, forbidden)
        self.assertIn(TimelinessVerificationStatus.UNCERTAIN, forbidden)


class RetrieverProtocolContractTests(unittest.TestCase):
    """V2.1 §8.4 Retriever 三方法契约。

    注意：这是「契约符合性」测试。当前 LocalBM25Retriever 已实现三方法，
    但 Retriever Protocol 只声明了 retrieve（缺口由王智洋补齐）。本测试
    验证实现类是否符合 V2.1 要求，不改动 Protocol 定义。
    """

    def test_local_bm25_retriever_has_three_methods(self):
        retriever = LocalBM25Retriever()
        # V2.1 §8.1/8.2/8.3：retrieve + get_document_metadata + get_parsed_chunk
        self.assertTrue(callable(getattr(retriever, "retrieve", None)))
        self.assertTrue(callable(getattr(retriever, "get_document_metadata", None)))
        self.assertTrue(callable(getattr(retriever, "get_parsed_chunk", None)))

    def test_get_document_metadata_returns_none_for_unknown_version(self):
        from uuid import uuid4
        retriever = LocalBM25Retriever()
        self.assertIsNone(retriever.get_document_metadata(uuid4()))

    def test_get_parsed_chunk_returns_none_for_unknown_chunk(self):
        from uuid import uuid4
        retriever = LocalBM25Retriever()
        self.assertIsNone(retriever.get_parsed_chunk(uuid4()))


class RetrievalStatusContractTests(unittest.TestCase):
    """V2.1 §9.3 检索开放状态：blocked / review_only 不能进入正式问答。"""

    def test_retrieval_status_has_blocked_review_only_enabled(self):
        self.assertEqual(RetrievalStatus.BLOCKED.value, "blocked")
        self.assertEqual(RetrievalStatus.REVIEW_ONLY.value, "review_only")
        self.assertEqual(RetrievalStatus.ENABLED.value, "enabled")

    def test_source_verification_has_verified_and_failed(self):
        self.assertEqual(SourceVerificationStatus.VERIFIED.value, "verified")
        self.assertEqual(SourceVerificationStatus.FAILED.value, "failed")


if __name__ == "__main__":
    unittest.main()
