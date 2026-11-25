"""Shared Pydantic v2 contracts for CodeMind-FZU.

These models define module boundaries only. They do not connect to a database,
vector store, LLM provider, or external service.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    """Base class: reject undeclared fields to catch contract drift early."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AnswerStatus(str, Enum):
    ANSWERED = "answered"
    NEEDS_CLARIFICATION = "needs_clarification"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class AnswerMode(str, Enum):
    CURRENT_POLICY = "current_policy"
    HISTORICAL = "historical"
    PROCEDURE_REFERENCE = "procedure_reference"
    INSUFFICIENT_DATA = "insufficient_data"


class SourceVerificationStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    VERIFIED = "verified"
    FAILED = "failed"


class TimelinessVerificationStatus(str, Enum):
    PENDING = "pending"
    CURRENT = "current"
    HISTORICAL = "historical"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    UNCERTAIN = "uncertain"


class ExtractionStatus(str, Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    NEEDS_OCR = "needs_ocr"
    FAILED = "failed"


class RetrievalStatus(str, Enum):
    BLOCKED = "blocked"
    REVIEW_ONLY = "review_only"
    ENABLED = "enabled"


class InclusionStatus(str, Enum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    PENDING = "pending"


class FileRole(str, Enum):
    ORIGINAL = "original"
    ATTACHMENT = "attachment"
    EXTRACTED = "extracted"
    CURATED = "curated"


class FileProcessingStatus(str, Enum):
    SAVED = "saved"
    EXTRACTED = "extracted"
    NEEDS_OCR = "needs_ocr"
    REVIEWED = "reviewed"
    FAILED = "failed"


class ChunkIndexStatus(str, Enum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"
    DISABLED = "disabled"


class IndexingStatus(str, Enum):
    INDEXED = "indexed"
    PARTIAL = "partial"
    FAILED = "failed"


class LLMRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class HealthResponse(ContractModel):
    status: str = "ok"
    service: str = "codemind-fzu-api"
    version: str = "0.1.0"
    timestamp: datetime


class AskRequest(ContractModel):
    query: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None


class Citation(ContractModel):
    document_id: UUID
    version_id: UUID
    chunk_id: UUID
    title: str = Field(min_length=1, max_length=512)
    publisher: str | None = None
    source_url: str = Field(min_length=1)
    published_on: date | None = None
    effective_on: date | None = None
    locator: str | None = None
    original_locator: str | None = None
    excerpt: str = Field(min_length=1)
    source_verification_status: SourceVerificationStatus
    timeliness_verification_status: TimelinessVerificationStatus
    retrieval_status: RetrievalStatus


class WarningItem(ContractModel):
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=1000)


def _validate_response_shape(
    *,
    status: AnswerStatus,
    answer: str | None,
    answer_mode: AnswerMode | None,
    clarifying_question: str | None,
    citations: list[Citation],
    warnings: list[WarningItem],
) -> None:
    """Enforce the shared V2.1 response shape, not factual correctness."""
    if status == AnswerStatus.ANSWERED:
        if not answer or not answer.strip():
            raise ValueError("answered 状态必须提供非空 answer")
        if answer_mode is None:
            raise ValueError("answered 状态必须明确 answer_mode")
    elif status == AnswerStatus.NEEDS_CLARIFICATION:
        if not clarifying_question or not clarifying_question.strip():
            raise ValueError("needs_clarification 状态必须提供非空 clarifying_question")
        if answer is not None:
            raise ValueError("needs_clarification 状态下 answer 必须为 null")
        if answer_mode is not None:
            raise ValueError("needs_clarification 状态下 answer_mode 必须为 null")
        if citations:
            raise ValueError("needs_clarification 状态下 citations 必须为空")
    elif status == AnswerStatus.INSUFFICIENT_EVIDENCE:
        if answer_mode != AnswerMode.INSUFFICIENT_DATA:
            raise ValueError("insufficient_evidence 必须使用 insufficient_data answer_mode")
        if citations:
            raise ValueError("insufficient_evidence 状态下 citations 必须为空")
        if not (answer and answer.strip()) and not any(
            warning.message.strip() for warning in warnings
        ):
            raise ValueError("insufficient_evidence 必须说明证据不足原因")


class AskResponse(ContractModel):
    request_id: UUID
    conversation_id: UUID
    status: AnswerStatus
    answer: str | None = None
    answer_mode: AnswerMode | None = None
    clarifying_question: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def validate_result_shape(self) -> "AskResponse":
        _validate_response_shape(
            status=self.status,
            answer=self.answer,
            answer_mode=self.answer_mode,
            clarifying_question=self.clarifying_question,
            citations=self.citations,
            warnings=self.warnings,
        )
        return self


class ApiErrorDetail(ContractModel):
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool = False


class ApiErrorResponse(ContractModel):
    request_id: UUID | None = None
    error: ApiErrorDetail


class ConversationTurn(ContractModel):
    role: LLMRole
    content: str
    created_at: datetime | None = None


class AgentRequest(ContractModel):
    request_id: UUID
    conversation_id: UUID
    query: str = Field(min_length=1, max_length=4000)
    history: list[ConversationTurn] = Field(default_factory=list)


class AgentResult(ContractModel):
    status: AnswerStatus
    answer: str | None = None
    answer_mode: AnswerMode | None = None
    clarifying_question: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result_shape(self) -> "AgentResult":
        _validate_response_shape(
            status=self.status,
            answer=self.answer,
            answer_mode=self.answer_mode,
            clarifying_question=self.clarifying_question,
            citations=self.citations,
            warnings=self.warnings,
        )
        return self


class RetrievalRequest(ContractModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    business_direction_code: str | None = None
    category_name: str | None = None


class RetrievedChunk(ContractModel):
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    file_id: UUID
    content: str = Field(min_length=1)
    title: str
    publisher: str | None = None
    source_url: str = Field(min_length=1)
    published_on: date | None = None
    effective_on: date | None = None
    locator: str | None = None
    original_locator: str | None = None
    score: float
    retrieval_method: str | None = None
    source_verification_status: SourceVerificationStatus
    timeliness_verification_status: TimelinessVerificationStatus
    retrieval_status: RetrievalStatus

    @model_validator(mode="after")
    def require_enabled_for_answer_retrieval(self) -> "RetrievedChunk":
        if self.retrieval_status != RetrievalStatus.ENABLED:
            raise ValueError("正式问答检索结果只能包含 retrieval_status=enabled 的片段")
        return self


class DocumentMetadata(ContractModel):
    """Ingestion metadata; field meanings follow the existing DB design."""

    title: str = Field(min_length=1, max_length=512)
    document_type: str = Field(min_length=1, max_length=64)
    category_name: str = Field(min_length=1, max_length=64)
    business_direction_codes: list[str] = Field(default_factory=list)
    record_code: str = Field(min_length=1, max_length=128)
    version_no: str = Field(min_length=1, max_length=64)
    publisher: str | None = None
    responsible_department: str | None = None
    document_number: str | None = None
    source_url: str = Field(min_length=1)
    source_page_url: str | None = None
    published_on: date | None = None
    issued_on: date | None = None
    effective_on: date | None = None
    deadline_on: date | None = None
    document_written_on: date | None = None
    applicability_raw: dict[str, Any] | None = None
    policy_status: str = "待核验"
    source_verification_status: SourceVerificationStatus = SourceVerificationStatus.PENDING
    timeliness_verification_status: TimelinessVerificationStatus = (
        TimelinessVerificationStatus.PENDING
    )
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    v1_inclusion_status: InclusionStatus = InclusionStatus.PENDING
    retrieval_status: RetrievalStatus = RetrievalStatus.BLOCKED
    inclusion_reason: str | None = None
    verification_note: str | None = None
    import_snapshot: dict[str, Any] | None = None
    temporal_notes: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_retrieval_gate(self) -> "DocumentMetadata":
        if self.retrieval_status == RetrievalStatus.ENABLED:
            eligible_timeliness = {
                TimelinessVerificationStatus.CURRENT,
                TimelinessVerificationStatus.HISTORICAL,
                TimelinessVerificationStatus.SUPERSEDED,
                TimelinessVerificationStatus.EXPIRED,
            }
            if self.v1_inclusion_status != InclusionStatus.INCLUDED:
                raise ValueError("开放检索前必须确认 v1_inclusion_status=included")
            if self.source_verification_status != SourceVerificationStatus.VERIFIED:
                raise ValueError("开放检索前必须通过来源核验")
            if self.extraction_status != ExtractionStatus.EXTRACTED:
                raise ValueError("开放检索前必须完成正文提取")
            if self.timeliness_verification_status not in eligible_timeliness:
                raise ValueError("开放检索前必须明确政策时效状态")
        return self


class ParsedFile(ContractModel):
    file_role: FileRole
    storage_key: str = Field(min_length=1, max_length=1024)
    original_name: str = Field(min_length=1, max_length=512)
    media_type: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_url: str | None = None
    processing_status: FileProcessingStatus = FileProcessingStatus.SAVED


class ParsedChunk(ContractModel):
    chunk_no: int = Field(ge=1)
    content: str = Field(min_length=1)
    locator: str | None = None
    locator_note: str | None = None
    source_file_key: str = Field(min_length=1)
    original_file_key: str | None = None
    original_locator: str | None = None
    index_status: ChunkIndexStatus = ChunkIndexStatus.PENDING


class DocumentPackage(ContractModel):
    metadata: DocumentMetadata
    files: list[ParsedFile] = Field(min_length=1)
    chunks: list[ParsedChunk] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_file_references(self) -> "DocumentPackage":
        keys = [item.storage_key for item in self.files]
        if len(keys) != len(set(keys)):
            raise ValueError("DocumentPackage 中 storage_key 不得重复")
        known_keys = set(keys)
        for chunk in self.chunks:
            if chunk.source_file_key not in known_keys:
                raise ValueError(f"知识片段引用了不存在的 source_file_key: {chunk.source_file_key}")
            if chunk.original_file_key and chunk.original_file_key not in known_keys:
                raise ValueError(f"知识片段引用了不存在的 original_file_key: {chunk.original_file_key}")
        return self


class IndexResult(ContractModel):
    document_id: UUID
    version_id: UUID
    status: IndexingStatus
    chunk_count: int = Field(ge=0)
    indexed_count: int = Field(ge=0)
    warnings: list[WarningItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_counts(self) -> "IndexResult":
        if self.indexed_count > self.chunk_count:
            raise ValueError("indexed_count 不能大于 chunk_count")
        if self.status == IndexingStatus.INDEXED and self.indexed_count != self.chunk_count:
            raise ValueError("indexed 状态要求所有片段均已建立索引")
        if self.status == IndexingStatus.FAILED and self.indexed_count != 0:
            raise ValueError("failed 状态下 indexed_count 必须为 0")
        return self


class LLMMessage(ContractModel):
    role: LLMRole
    content: str = Field(min_length=1)


class LLMGenerateRequest(ContractModel):
    messages: list[LLMMessage] = Field(min_length=1)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=8192)


class LLMResult(ContractModel):
    content: str = Field(min_length=1)
    model: str = Field(min_length=1)
    usage: dict[str, int] | None = None


class DocumentSummary(ContractModel):
    document_id: UUID
    title: str
    document_type: str
    category_name: str
    record_code: str
    version_no: str
    source_verification_status: SourceVerificationStatus
    timeliness_verification_status: TimelinessVerificationStatus
    extraction_status: ExtractionStatus
    retrieval_status: RetrievalStatus
    updated_at: datetime | None = None


class DocumentListResponse(ContractModel):
    items: list[DocumentSummary]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class DocumentUploadResponse(ContractModel):
    document_id: UUID
    version_id: UUID
    status: str
    message: str


class ReindexResponse(ContractModel):
    document_id: UUID
    version_id: UUID
    status: IndexingStatus
    chunk_count: int = Field(ge=0)
    indexed_count: int = Field(ge=0)
    message: str
