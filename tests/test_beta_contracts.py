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
from datetime import date
from uuid import uuid4

from pydantic import ValidationError

from backend.contracts.models import (
    AgentResult,
    AnswerMode,
    AnswerStatus,
    DocumentMetadata,
    DocumentPackage,
    FileProcessingStatus,
    ParsedChunk,
    ParsedFile,
    RetrievalStatus,
    SourceVerificationStatus,
    TimelinessVerificationStatus,
)
from backend.retrieval.local import LocalBM25Retriever


def _enabled_package(record_code: str = "BETA-TEST-1") -> DocumentPackage:
    """构造一个 human_approved + enabled 的合成测试 DocumentPackage。"""
    metadata = DocumentMetadata(
        title="【测试替身】Beta 契约测试资料",
        document_type="管理办法",
        category_name="综评与奖学金",
        business_direction_codes=["POLICY_AFFAIRS"],
        record_code=record_code,
        version_no="v1",
        publisher="测试替身发布方",
        source_url="https://example.invalid/beta-contract",
        published_on=date(2026, 1, 1),
        effective_on=date(2026, 1, 1),
        deadline_on=date(2026, 12, 31),
        source_verification_status="verified",
        timeliness_verification_status="current",
        extraction_status="extracted",
        v1_inclusion_status="included",
        retrieval_status=RetrievalStatus.ENABLED,
        temporal_notes={"human_approved": True, "备注": "仅测试用"},
        applicability_raw={"适用对象": "本科生", "适用年度": "2026年"},
    )
    return DocumentPackage(
        metadata=metadata,
        files=[
            ParsedFile(
                file_role="extracted", storage_key="policy.md",
                original_name="policy.md",
                processing_status=FileProcessingStatus.EXTRACTED,
            ),
        ],
        chunks=[
            ParsedChunk(
                chunk_no=1,
                content="优秀学生综合奖学金一等奖1500元/学期。",
                source_file_key="policy.md",
                locator="第七条",
                locator_note="第三章 奖学金评定",
                original_locator="第三章/第七条",
            ),
        ],
    )


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


class LocalBM25RetrieverApiTests(unittest.IsolatedAsyncioTestCase):
    """V2.1 §8.1/8.2/8.3 LocalBM25Retriever 三方法实现检查。

    注意：本测试只检查 LocalBM25Retriever 这个**实现类**是否提供三个方法并
    正确工作，不检查公共 Retriever Protocol（backend/contracts/protocols.py
    目前只声明了 retrieve，另外两个方法待王智洋补齐）。公共 Protocol 的三方法
    契约测试，待王智洋完成上游修改后补充，本文件不擅自修改他人负责的公共接口。
    """

    async def asyncSetUp(self):
        self.retriever = LocalBM25Retriever()
        self.package = _enabled_package()
        self.indexed = await self.retriever.index_document(self.package)
        # chunk_id 通过 file_id + chunk_no 确定性生成，从 retrieve 结果拿到
        from backend.contracts.models import RetrievalRequest
        hits = await self.retriever.retrieve(RetrievalRequest(query="优秀学生综合奖学金"))
        self.assertGreater(len(hits), 0)
        self.chunk_id = hits[0].chunk_id

    def test_local_bm25_retriever_has_three_methods(self):
        self.assertTrue(callable(getattr(self.retriever, "retrieve", None)))
        self.assertTrue(callable(getattr(self.retriever, "get_document_metadata", None)))
        self.assertTrue(callable(getattr(self.retriever, "get_parsed_chunk", None)))

    def test_get_document_metadata_returns_correct_metadata(self):
        metadata = self.retriever.get_document_metadata(self.indexed.version_id)
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.record_code, "BETA-TEST-1")
        self.assertEqual(metadata.retrieval_status, RetrievalStatus.ENABLED)
        self.assertEqual(metadata.source_verification_status, "verified")
        # V2.1 §8.2：必须能读取 version_no / applicability_raw / deadline_on / temporal_notes
        self.assertEqual(metadata.version_no, "v1")
        self.assertEqual(metadata.applicability_raw, {"适用对象": "本科生", "适用年度": "2026年"})
        self.assertEqual(metadata.deadline_on, date(2026, 12, 31))
        self.assertEqual(metadata.temporal_notes, {"human_approved": True, "备注": "仅测试用"})

    def test_get_parsed_chunk_returns_correct_chunk(self):
        chunk = self.retriever.get_parsed_chunk(self.chunk_id)
        self.assertIsNotNone(chunk)
        self.assertEqual(chunk.content, "优秀学生综合奖学金一等奖1500元/学期。")
        self.assertEqual(chunk.locator, "第七条")
        # V2.1 §8.3：必须能读取 locator_note / original_locator / source_file_key / chunk_no
        self.assertEqual(chunk.locator_note, "第三章 奖学金评定")
        self.assertEqual(chunk.original_locator, "第三章/第七条")
        self.assertEqual(chunk.source_file_key, "policy.md")
        self.assertEqual(chunk.chunk_no, 1)

    def test_get_document_metadata_returns_deep_copy(self):
        metadata = self.retriever.get_document_metadata(self.indexed.version_id)
        original_record = metadata.record_code
        # 外部修改返回对象（含嵌套字典）不应影响内部索引
        metadata.record_code = "MUTATED"
        metadata.applicability_raw["适用对象"] = "已篡改"
        metadata.temporal_notes["human_approved"] = False
        fresh = self.retriever.get_document_metadata(self.indexed.version_id)
        self.assertEqual(fresh.record_code, original_record)
        self.assertEqual(fresh.applicability_raw, {"适用对象": "本科生", "适用年度": "2026年"})
        self.assertEqual(fresh.temporal_notes["human_approved"], True)

    def test_get_parsed_chunk_returns_deep_copy(self):
        chunk = self.retriever.get_parsed_chunk(self.chunk_id)
        original_content = chunk.content
        chunk.content = "已篡改"
        fresh = self.retriever.get_parsed_chunk(self.chunk_id)
        self.assertEqual(fresh.content, original_content)

    def test_unknown_version_returns_none(self):
        self.assertIsNone(self.retriever.get_document_metadata(uuid4()))

    def test_unknown_chunk_returns_none(self):
        self.assertIsNone(self.retriever.get_parsed_chunk(uuid4()))

    async def test_blocked_version_returns_none_for_metadata(self):
        # 未开放（blocked）资料即使已索引，元数据查询也应返回 None（V2.1 §8.2）
        blocked = _enabled_package(record_code="BETA-BLOCKED-1")
        blocked.metadata.retrieval_status = RetrievalStatus.BLOCKED
        blocked_result = await self.retriever.index_document(blocked)
        self.assertIsNone(
            self.retriever.get_document_metadata(blocked_result.version_id)
        )

    async def test_blocked_version_returns_none_for_chunk(self):
        # V2.1 §8.3：未开放（blocked）资料的片段查询也应返回 None
        blocked = _enabled_package(record_code="BETA-BLOCKED-2")
        blocked.metadata.retrieval_status = RetrievalStatus.BLOCKED
        await self.retriever.index_document(blocked)
        # blocked 资料无法被检索到，其 chunk_id 需按 LocalBM25Retriever 的确定性
        # 生成规则推算（与 index_document 内部一致的 UUID5 规则）
        from backend.retrieval.local import _local_id, _document_and_version_ids
        _document_id, version_id = _document_and_version_ids("BETA-BLOCKED-2", "v1")
        file_id = _local_id("file", str(version_id), "policy.md")
        chunk_id = _local_id("chunk", str(file_id), "1")
        self.assertIsNone(self.retriever.get_parsed_chunk(chunk_id))


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
