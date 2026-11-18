"""接口规范契约测试（颜俊宇 · 测试与质量保障）。

覆盖 CodeMind-FZU Alpha 接口规范 V1.0 中定义的公共数据模型与状态机约束。
依据文件：
  - docs/assignment-03/interface-contract-v1.md
  - backend/contracts/models.py
  - backend/contracts/protocols.py

运行方式（在仓库根目录）：
  python -m unittest discover -s tests -v
或：
  python -m pytest tests/test_interface_contracts.py -v

设计原则：本文件只验证「契约本身」，不依赖数据库、LLM、检索器或任何外部服务。
每个公共模型至少覆盖一个「正常（合法）用例」和一个「异常（非法）用例」。
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from backend.contracts.models import (
    AgentRequest,
    AgentResult,
    AnswerMode,
    AnswerStatus,
    ApiErrorDetail,
    ApiErrorResponse,
    AskRequest,
    AskResponse,
    Citation,
    ConversationTurn,
    DocumentListResponse,
    DocumentMetadata,
    DocumentPackage,
    DocumentSummary,
    DocumentUploadResponse,
    IndexingStatus,
    IndexResult,
    InclusionStatus,
    LLMGenerateRequest,
    LLMMessage,
    LLMResult,
    LLMRole,
    ParsedChunk,
    ParsedFile,
    ReindexResponse,
    RetrievalRequest,
    RetrievalStatus,
    RetrievedChunk,
    SourceVerificationStatus,
    TimelinessVerificationStatus,
    WarningItem,
)


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _valid_citation() -> Citation:
    return Citation(
        document_id=_uuid(),
        version_id=_uuid(),
        chunk_id=_uuid(),
        title="示例政策文件",
        publisher="福州大学",
        source_url="https://example.edu.cn/policy",
        published_on=date(2026, 6, 1),
        effective_on=date(2026, 9, 1),
        locator="第三条",
        original_locator="PDF 第 2 页",
        excerpt="与本次回答直接相关的原文摘录。",
        source_verification_status=SourceVerificationStatus.VERIFIED,
        timeliness_verification_status=TimelinessVerificationStatus.CURRENT,
        retrieval_status=RetrievalStatus.ENABLED,
    )


def _valid_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=_uuid(),
        document_id=_uuid(),
        version_id=_uuid(),
        file_id=_uuid(),
        content="示例正文内容。",
        title="示例文件",
        publisher="福州大学",
        source_url="https://example.edu.cn/policy",
        score=0.82,
        retrieval_method="vector",
        source_verification_status=SourceVerificationStatus.VERIFIED,
        timeliness_verification_status=TimelinessVerificationStatus.CURRENT,
        retrieval_status=RetrievalStatus.ENABLED,
    )


def _valid_metadata() -> DocumentMetadata:
    return DocumentMetadata(
        title="示例文件",
        document_type="办法",
        category_name="综评与奖学金",
        record_code="TEST-001",
        version_no="import-1",
        source_url="https://example.edu.cn/policy",
    )


# ---------------------------------------------------------------------------
# 1. 学生端 HTTP API 契约：AskRequest / AskResponse / Citation / WarningItem
# ---------------------------------------------------------------------------
class AskRequestTests(unittest.TestCase):
    def test_query_required_non_empty(self):
        req = AskRequest(query="申请国家奖学金需要满足什么条件？")
        self.assertEqual(req.conversation_id, None)

    def test_query_rejects_blank(self):
        with self.assertRaises(ValidationError):
            AskRequest(query="   ")

    def test_query_rejects_over_4000_chars(self):
        with self.assertRaises(ValidationError):
            AskRequest(query="字" * 4001)

    def test_conversation_id_must_be_uuid(self):
        with self.assertRaises(ValidationError):
            AskRequest(query="问题", conversation_id="not-a-uuid")


class AskResponseTests(unittest.TestCase):
    def test_answered_requires_non_empty_answer(self):
        with self.assertRaises(ValidationError):
            AskResponse(
                request_id=_uuid(),
                conversation_id=_uuid(),
                status=AnswerStatus.ANSWERED,
                answer=None,
                answer_mode=AnswerMode.CURRENT_POLICY,
                citations=[],
                warnings=[],
                created_at=_now(),
            )

    def test_needs_clarification_requires_question_and_null_answer(self):
        # 正常：有 clarifying_question，answer 为 null
        ok = AskResponse(
            request_id=_uuid(),
            conversation_id=_uuid(),
            status=AnswerStatus.NEEDS_CLARIFICATION,
            answer=None,
            answer_mode=None,
            clarifying_question="请问你咨询的是哪一学年的奖学金评定？",
            citations=[],
            warnings=[],
            created_at=_now(),
        )
        self.assertEqual(ok.status, AnswerStatus.NEEDS_CLARIFICATION)

        # 异常：缺 clarifying_question
        with self.assertRaises(ValidationError):
            AskResponse(
                request_id=_uuid(),
                conversation_id=_uuid(),
                status=AnswerStatus.NEEDS_CLARIFICATION,
                answer=None,
                answer_mode=None,
                clarifying_question=None,
                citations=[],
                warnings=[],
                created_at=_now(),
            )

        # 异常：answer 不应有值
        with self.assertRaises(ValidationError):
            AskResponse(
                request_id=_uuid(),
                conversation_id=_uuid(),
                status=AnswerStatus.NEEDS_CLARIFICATION,
                answer="不该有答案",
                answer_mode=None,
                clarifying_question="追问",
                citations=[],
                warnings=[],
                created_at=_now(),
            )

    def test_insufficient_evidence_requires_matching_mode(self):
        with self.assertRaises(ValidationError):
            AskResponse(
                request_id=_uuid(),
                conversation_id=_uuid(),
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                answer="没有证据",
                answer_mode=AnswerMode.CURRENT_POLICY,  # 必须是 insufficient_data
                citations=[],
                warnings=[],
                created_at=_now(),
            )

    def test_citations_default_to_empty_list(self):
        resp = AskResponse(
            request_id=_uuid(),
            conversation_id=_uuid(),
            status=AnswerStatus.ANSWERED,
            answer="答案",
            answer_mode=AnswerMode.CURRENT_POLICY,
            created_at=_now(),
        )
        self.assertEqual(resp.citations, [])
        self.assertEqual(resp.warnings, [])

    def test_rejects_unknown_field(self):
        with self.assertRaises(ValidationError):
            AskRequest(query="问题", unexpected_field=True)


class CitationTests(unittest.TestCase):
    def test_valid_citation(self):
        c = _valid_citation()
        self.assertEqual(c.retrieval_status, RetrievalStatus.ENABLED)

    def test_title_must_not_be_blank(self):
        with self.assertRaises(ValidationError):
            Citation(
                document_id=_uuid(),
                version_id=_uuid(),
                chunk_id=_uuid(),
                title="",
                source_url="https://example.edu.cn/policy",
                excerpt="摘录",
                source_verification_status=SourceVerificationStatus.VERIFIED,
                timeliness_verification_status=TimelinessVerificationStatus.CURRENT,
                retrieval_status=RetrievalStatus.ENABLED,
            )


class WarningItemTests(unittest.TestCase):
    def test_code_and_message(self):
        w = WarningItem(code="NO_ELIGIBLE_EVIDENCE", message="未找到允许用于正式回答的证据。")
        self.assertEqual(w.code, "NO_ELIGIBLE_EVIDENCE")


# ---------------------------------------------------------------------------
# 2. 统一错误格式：ApiErrorResponse / ApiErrorDetail
# ---------------------------------------------------------------------------
class ApiErrorTests(unittest.TestCase):
    def test_error_envelope(self):
        resp = ApiErrorResponse(
            request_id=_uuid(),
            error=ApiErrorDetail(code="MODEL_TIMEOUT", message="模型服务暂时不可用，请稍后重试。", retryable=True),
        )
        self.assertTrue(resp.error.retryable)

    def test_retryable_defaults_false(self):
        detail = ApiErrorDetail(code="INVALID_REQUEST", message="参数错误")
        self.assertFalse(detail.retryable)


# ---------------------------------------------------------------------------
# 3. Agent 契约：AgentRequest / AgentResult / ConversationTurn
# ---------------------------------------------------------------------------
class AgentRequestTests(unittest.TestCase):
    def test_history_defaults_empty(self):
        req = AgentRequest(request_id=_uuid(), conversation_id=_uuid(), query="问题")
        self.assertEqual(req.history, [])

    def test_history_accepts_turns(self):
        req = AgentRequest(
            request_id=_uuid(),
            conversation_id=_uuid(),
            query="问题",
            history=[ConversationTurn(role=LLMRole.USER, content="上一句")],
        )
        self.assertEqual(len(req.history), 1)

    def test_invalid_role_rejected(self):
        with self.assertRaises(ValidationError):
            ConversationTurn(role="human", content="x")


class AgentResultTests(unittest.TestCase):
    def test_answered_requires_answer(self):
        with self.assertRaises(ValidationError):
            AgentResult(status=AnswerStatus.ANSWERED, answer=None)

    def test_answered_valid(self):
        r = AgentResult(
            status=AnswerStatus.ANSWERED,
            answer="答案",
            answer_mode=AnswerMode.CURRENT_POLICY,
            citations=[_valid_citation()],
        )
        self.assertEqual(r.status, AnswerStatus.ANSWERED)

    def test_needs_clarification_rules(self):
        with self.assertRaises(ValidationError):
            AgentResult(status=AnswerStatus.NEEDS_CLARIFICATION, clarifying_question=None)

    def test_insufficient_evidence_mode(self):
        with self.assertRaises(ValidationError):
            AgentResult(
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                answer="x",
                answer_mode=AnswerMode.CURRENT_POLICY,
            )


# ---------------------------------------------------------------------------
# 4. 检索契约：RetrievalRequest / RetrievedChunk
# ---------------------------------------------------------------------------
class RetrievalRequestTests(unittest.TestCase):
    def test_top_k_default_5(self):
        req = RetrievalRequest(query="奖学金")
        self.assertEqual(req.top_k, 5)

    def test_top_k_range(self):
        with self.assertRaises(ValidationError):
            RetrievalRequest(query="x", top_k=0)
        with self.assertRaises(ValidationError):
            RetrievalRequest(query="x", top_k=21)

    def test_optional_filters_none_by_default(self):
        req = RetrievalRequest(query="x")
        self.assertIsNone(req.business_direction_code)
        self.assertIsNone(req.category_name)


class RetrievedChunkTests(unittest.TestCase):
    def test_valid_enabled_chunk(self):
        self.assertEqual(_valid_chunk().retrieval_status, RetrievalStatus.ENABLED)

    def test_blocked_chunk_rejected(self):
        with self.assertRaises(ValidationError):
            RetrievedChunk(
                chunk_id=_uuid(),
                document_id=_uuid(),
                version_id=_uuid(),
                file_id=_uuid(),
                content="正文",
                title="标题",
                source_url="https://example.edu.cn/policy",
                score=0.5,
                source_verification_status=SourceVerificationStatus.VERIFIED,
                timeliness_verification_status=TimelinessVerificationStatus.CURRENT,
                retrieval_status=RetrievalStatus.BLOCKED,
            )

    def test_score_is_float(self):
        c = _valid_chunk()
        self.assertIsInstance(c.score, float)


# ---------------------------------------------------------------------------
# 5. 文档解析与索引：DocumentMetadata / DocumentPackage / IndexResult
# ---------------------------------------------------------------------------
class DocumentMetadataTests(unittest.TestCase):
    def test_defaults_to_blocked(self):
        self.assertEqual(_valid_metadata().retrieval_status, RetrievalStatus.BLOCKED)

    def test_enabled_requires_all_prerequisites(self):
        with self.assertRaises(ValidationError):
            DocumentMetadata(
                title="示例文件",
                document_type="办法",
                category_name="综评与奖学金",
                record_code="TEST-002",
                version_no="import-1",
                source_url="https://example.edu.cn/policy",
                retrieval_status=RetrievalStatus.ENABLED,
            )

    def test_enabled_accepts_verified_metadata(self):
        m = DocumentMetadata(
            title="示例文件",
            document_type="办法",
            category_name="综评与奖学金",
            record_code="TEST-003",
            version_no="v1",
            source_url="https://example.edu.cn/policy",
            v1_inclusion_status=InclusionStatus.INCLUDED,
            source_verification_status=SourceVerificationStatus.VERIFIED,
            extraction_status="extracted",
            timeliness_verification_status=TimelinessVerificationStatus.CURRENT,
            retrieval_status=RetrievalStatus.ENABLED,
        )
        self.assertEqual(m.retrieval_status, RetrievalStatus.ENABLED)


class DocumentPackageTests(unittest.TestCase):
    def test_rejects_duplicate_storage_key(self):
        with self.assertRaises(ValidationError):
            DocumentPackage(
                metadata=_valid_metadata(),
                files=[
                    ParsedFile(file_role="original", storage_key="a.pdf", original_name="a.pdf"),
                    ParsedFile(file_role="original", storage_key="a.pdf", original_name="b.pdf"),
                ],
                chunks=[],
            )

    def test_rejects_unknown_chunk_file(self):
        with self.assertRaises(ValidationError):
            DocumentPackage(
                metadata=_valid_metadata(),
                files=[ParsedFile(file_role="original", storage_key="official/test.pdf", original_name="test.pdf")],
                chunks=[ParsedChunk(chunk_no=1, content="正文", source_file_key="missing/test.pdf")],
            )

    def test_valid_package(self):
        pkg = DocumentPackage(
            metadata=_valid_metadata(),
            files=[ParsedFile(file_role="original", storage_key="official/test.pdf", original_name="test.pdf")],
            chunks=[ParsedChunk(chunk_no=1, content="正文", source_file_key="official/test.pdf")],
        )
        self.assertEqual(len(pkg.chunks), 1)


class IndexResultTests(unittest.TestCase):
    def test_indexed_requires_all_indexed(self):
        with self.assertRaises(ValidationError):
            IndexResult(
                document_id=_uuid(),
                version_id=_uuid(),
                status=IndexingStatus.INDEXED,
                chunk_count=3,
                indexed_count=2,
            )

    def test_failed_requires_zero_indexed(self):
        with self.assertRaises(ValidationError):
            IndexResult(
                document_id=_uuid(),
                version_id=_uuid(),
                status=IndexingStatus.FAILED,
                chunk_count=3,
                indexed_count=1,
            )

    def test_partial_allowed(self):
        r = IndexResult(
            document_id=_uuid(),
            version_id=_uuid(),
            status=IndexingStatus.PARTIAL,
            chunk_count=3,
            indexed_count=2,
        )
        self.assertEqual(r.status, IndexingStatus.PARTIAL)


# ---------------------------------------------------------------------------
# 6. LLM 契约：LLMGenerateRequest / LLMMessage / LLMResult
# ---------------------------------------------------------------------------
class LLMContractTests(unittest.TestCase):
    def test_messages_required_non_empty(self):
        with self.assertRaises(ValidationError):
            LLMGenerateRequest(messages=[])

    def test_temperature_range(self):
        with self.assertRaises(ValidationError):
            LLMGenerateRequest(messages=[LLMMessage(role=LLMRole.USER, content="hi")], temperature=2.5)

    def test_valid_result(self):
        r = LLMResult(content="回答", model="qwen-max", usage={"prompt_tokens": 10, "completion_tokens": 5})
        self.assertEqual(r.model, "qwen-max")


# ---------------------------------------------------------------------------
# 7. 后台管理契约：DocumentSummary / DocumentListResponse / Upload / Reindex
# ---------------------------------------------------------------------------
class AdminContractTests(unittest.TestCase):
    def test_list_response_pagination(self):
        resp = DocumentListResponse(items=[], total=0, page=1, page_size=20)
        self.assertEqual(resp.page, 1)

    def test_page_size_max_100(self):
        with self.assertRaises(ValidationError):
            DocumentListResponse(items=[], total=0, page=1, page_size=101)

    def test_upload_response(self):
        r = DocumentUploadResponse(
            document_id=_uuid(),
            version_id=_uuid(),
            status="processing",
            message="已接收，正在解析",
        )
        self.assertEqual(r.status, "processing")

    def test_reindex_response(self):
        r = ReindexResponse(
            document_id=_uuid(),
            version_id=_uuid(),
            status=IndexingStatus.INDEXED,
            chunk_count=2,
            indexed_count=2,
            message="重建完成",
        )
        self.assertEqual(r.status, IndexingStatus.INDEXED)


if __name__ == "__main__":
    unittest.main()
