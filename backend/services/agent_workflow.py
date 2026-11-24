"""Compose the Retriever, business rules and LLMClient for campus Q&A."""
from __future__ import annotations

import asyncio
import logging
import math
import re
from collections.abc import Callable, Iterable
from datetime import date
from functools import partial
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError

from backend.contracts.models import (
    AgentRequest, AgentResult, AnswerMode, AnswerStatus, DocumentMetadata, DocumentPackage,
    ChunkIndexStatus, IndexingStatus, LLMResult, LLMRole, ParsedChunk, RetrievalRequest,
    RetrievedChunk, RetrievalStatus, SourceVerificationStatus,
    TimelinessVerificationStatus, WarningItem,
)
from backend.contracts.protocols import LLMClient, Retriever
from backend.services.agent_generation import Evidence, generation_request, requested_facts, verify_answer
from backend.services.agent_policy_context import PolicyScope, contextual_request, is_live_quota_question, separate_live_lab_quota
from backend.services.errors import LLMTimeoutError, LLMUnavailableError, ServiceError

logger = logging.getLogger(__name__)
ClarificationRule = Callable[[AgentRequest], str | None]
EvidenceCheck = Callable[[AgentRequest, RetrievedChunk], bool]


def _human_approved(metadata: DocumentMetadata) -> bool:
    return (isinstance(metadata.temporal_notes, dict)
            and metadata.temporal_notes.get("human_approved") is True)


_TOPIC = re.compile(r"奖学金|综评|综合素质|学分|推免|保研|转专业|辅修|选课|重修|学位|毕业|学生证|学籍|课程|英语|竞赛|创新创业|实验室|学院资源|培养方案|办事渠道|青禾计划")
_YEAR = re.compile(r"20\d{2}(?!\s*级)|本学年|本学期|今年|这学期|当前学年|去年|前年|上学年")
_GRADE = re.compile(r"20\d{2}\s*级|大[一二三四五]|[一二三四五]年级")
_PERSONAL = re.compile(r"我|本人|能否|有没有资格|是否符合|能不能")


def _user_context(request: AgentRequest) -> str:
    """Only user turns can supply missing slots; assistant prose is not evidence."""
    previous = [turn.content for turn in request.history if turn.role == LLMRole.USER]
    return "\n".join([*previous, request.query])


def default_clarification_rule(request: AgentRequest) -> str | None:
    """Default for direct callers. The runtime injects the business rules."""
    context = _user_context(request)
    if not _TOPIC.search(context):
        return "请问你具体咨询哪项学校政策或办理事项？"
    if re.search(r"奖学金|综评|综合素质", context) and not _YEAR.search(context):
        return "请问你咨询的是哪一学年的评定？"
    if _PERSONAL.search(context) and not _GRADE.search(context):
        return "请问你是哪个入学年级的学生？"
    return None


def _insufficient(code: str, message: str) -> AgentResult:
    return AgentResult(
        status=AnswerStatus.INSUFFICIENT_EVIDENCE,
        answer=message,
        answer_mode=AnswerMode.INSUFFICIENT_DATA,
        warnings=[WarningItem(code=code, message=message)],
    )


class AgentWorkflow:
    """Apply the source and time gates before consulting the injected business rules."""

    def __init__(
        self,
        retriever: Retriever,
        llm_client: LLMClient,
        *,
        clarification_rule: ClarificationRule = default_clarification_rule,
        evidence_check: EvidenceCheck | None = None,
        top_k: int = 5,
        timeout_seconds: float = 30.0,
        max_evidence_chars: int = 24000,
        today: Callable[[], date] = date.today,
    ) -> None:
        # Reuse the contract for top_k validation; do not duplicate its bounds.
        RetrievalRequest(query="configuration", top_k=top_k)
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive and finite")
        if max_evidence_chars < 1:
            raise ValueError("max_evidence_chars must be positive")
        if not callable(clarification_rule):
            raise ValueError("clarification_rule must be callable")
        if evidence_check is not None and not callable(evidence_check):
            raise ValueError("evidence_check must be callable")
        self.retriever = retriever
        self.llm_client = llm_client
        self.clarification_rule = clarification_rule
        self.evidence_check = evidence_check
        self.top_k = top_k
        self.timeout_seconds = timeout_seconds
        self.max_evidence_chars = max_evidence_chars
        self.today = today

    async def run(self, request: AgentRequest) -> AgentResult:
        request = contextual_request(request)
        remaining_query = separate_live_lab_quota(request)
        if remaining_query is None:
            return await self._run(request)

        code = "LIVE_LAB_QUOTA_UNVERIFIED"
        message = "暂无经过核验的实时剩余名额，请以实验室或学院当前通知为准。"
        if not remaining_query:
            return _insufficient(code, message)

        result = await self._run(request.model_copy(update={
            "query": remaining_query,
            "history": [turn for turn in request.history if not is_live_quota_question(turn.content)],
        }))
        return result.model_copy(update={
            "answer": f"{result.answer}\n\n{message}" if result.answer else None,
            "warnings": [*result.warnings, WarningItem(code=code, message=message)],
        })

    async def _run(self, request: AgentRequest) -> AgentResult:
        try:
            question = self.clarification_rule(request.model_copy(deep=True))
            if question is not None and (not isinstance(question, str) or not question.strip()):
                raise ValueError("Clarification rule must return a nonblank question or None")
        except Exception:
            logger.warning("Clarification rule failed; request_id=%s", request.request_id)
            return _insufficient("CLARIFICATION_RULE_FAILED", "必要信息检查暂时不可用，本次不生成政策答案。")
        scope = PolicyScope.from_request(request, self.today())
        if not question and scope.historical and not scope.periods and not scope.current:
            question = "请问你想查哪一年或哪一学年的历史资料？"
        if question:
            return AgentResult(
                status=AnswerStatus.NEEDS_CLARIFICATION,
                clarifying_question=question.strip(),
            )

        context = _user_context(request)
        if self.evidence_check is None and (scope.historical or scope.asks_deadline or scope.needs_window
                                            or _PERSONAL.search(context) or re.search(r"冲突|矛盾", context)):
            return _insufficient("APPLICABILITY_NOT_VERIFIED", "本次无法核验资料的适用范围、历史版本或办理期限。")

        try:
            retrieval_request = RetrievalRequest(query=context, top_k=self.top_k)
        except ValidationError:
            return _insufficient("RETRIEVAL_QUERY_TOO_LONG", "问题与用户历史合计超过检索接口的 2000 字符限制，请缩短问题或开启新会话。")

        try:
            raw_chunks = await asyncio.wait_for(
                self.retriever.retrieve(retrieval_request), self.timeout_seconds,
            )
        except Exception:
            logger.warning("Retriever failed; request_id=%s", request.request_id)
            return _insufficient("RETRIEVAL_UNAVAILABLE", "检索服务暂时不可用，无法取得可靠证据，请稍后重试。")

        try:
            if not isinstance(raw_chunks, list):
                raise ValueError("Retriever must return list[RetrievedChunk]")
            evidence: list[Evidence] = []
            closed_notices: list[Evidence] = []
            seen: dict[UUID, RetrievedChunk] = {}
            versions: dict[UUID, UUID] = {}
            version_documents: dict[UUID, UUID] = {}
            documents: dict[UUID, str] = {}
            records: dict[str, UUID] = {}
            evidence_chars = 0
            for raw in raw_chunks:
                # model_copy/model_construct can bypass validators. Revalidate a
                # snapshot and apply gates again even if an adapter returns models.
                if not isinstance(raw, RetrievedChunk):
                    raise ValueError("Unexpected retrieval item type")
                snapshot = raw.model_dump()
                # Validate the public base contract even for a typed extension,
                # then retain that extension for the business owner's callback.
                RetrievedChunk.model_validate({
                    key: value for key, value in snapshot.items()
                    if key in RetrievedChunk.model_fields
                })
                chunk = type(raw).model_validate(snapshot)
                if chunk.chunk_id in seen:
                    if chunk != seen[chunk.chunk_id]:
                        raise ValueError("Conflicting duplicate chunk identity")
                    continue
                seen[chunk.chunk_id] = chunk
                eligible = self._eligible(request, chunk, scope)
                if eligible is None:
                    continue
                if eligible.recruitment_closed:
                    if len(chunk.content) <= self.max_evidence_chars:
                        closed_notices.append(eligible)
                    continue
                record_code = eligible.metadata.record_code
                if (documents.get(chunk.document_id, record_code) != record_code
                        or records.get(record_code, chunk.document_id) != chunk.document_id
                        or version_documents.get(chunk.version_id, chunk.document_id) != chunk.document_id):
                    raise ValueError("Conflicting document identity")
                if chunk.document_id in versions and versions[chunk.document_id] != chunk.version_id:
                    return _insufficient("POLICY_VERSION_CONFLICT", "同一文档有多个符合时间范围的版本，需核对版本关系后才能回答。")
                versions[chunk.document_id] = chunk.version_id
                version_documents[chunk.version_id] = chunk.document_id
                documents[chunk.document_id] = record_code
                records[record_code] = chunk.document_id
                evidence_chars += len(chunk.content)
                if evidence_chars > self.max_evidence_chars or len(evidence) >= self.top_k:
                    return _insufficient("EVIDENCE_BUDGET_EXCEEDED", "检索结果超出工作流证据预算，请缩小问题范围后重试。")
                evidence.append(eligible)
        except Exception:
            logger.warning("Evidence validation failed; request_id=%s", request.request_id)
            return _insufficient("INVALID_RETRIEVAL_RESULT", "检索结果不符合公共契约或存在片段冲突，本次不生成政策答案。")

        if not evidence:
            if closed_notices:
                return self._answer_closed_recruitment(request, closed_notices)
            return _insufficient("NO_ELIGIBLE_EVIDENCE", "未找到通过审核且符合本次问题适用范围和时间的资料，无法给出确定结论。")
        facts = requested_facts(scope.fact_question)
        if facts and not any(fact.search(item.chunk.content) for fact in facts for item in evidence):
            return _insufficient("REQUESTED_FACT_NOT_FOUND", "通过审核的资料未载明所询问的金额或截止时间，暂无法确认。")

        # A fresh namespace per invocation rejects IDs copied from another turn,
        # even when the request UUID or the retrieved chunks are the same.
        namespace = uuid4().hex
        evidence_by_id = {f"E{index}-{namespace}": item for index, item in enumerate(evidence, 1)}
        prompt = generation_request(request.query, [turn.content for turn in request.history], evidence_by_id)
        try:
            generated = await asyncio.wait_for(
                self.llm_client.generate(prompt), self.timeout_seconds,
            )
        except ServiceError:
            # Preserve the backend adapter's sanitized error code and HTTP status.
            raise
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise LLMTimeoutError() from exc
        except Exception as exc:
            logger.warning("LLM failed; request_id=%s", request.request_id)
            raise LLMUnavailableError() from exc

        try:
            if not isinstance(generated, LLMResult):
                raise ValueError("LLMClient must return LLMResult")
            generated = LLMResult.model_validate(generated.model_dump())
            answer, selected, partial = verify_answer(generated.content, evidence_by_id, facts)
            citations = [item.citation() for item in selected]
        except (ValueError, TypeError, RecursionError):
            return _insufficient("UNSUPPORTED_GENERATION", "模型未返回能由本次资料核对的答案和有效引用，暂时无法确认。")

        # Recheck the same index and rule after the await. A review can be
        # withdrawn or a notice can close while the model is running.
        if not self._evidence_unchanged(request, selected):
            return _insufficient("EVIDENCE_APPROVAL_CHANGED", "引用资料或适用状态已改变，本次不生成政策答案。")

        mode = AnswerMode.CURRENT_POLICY
        warnings = []
        if any(item.mode == AnswerMode.HISTORICAL for item in selected):
            if any(item.mode != AnswerMode.HISTORICAL for item in selected):
                return _insufficient("POLICY_PERIOD_CONFLICT", "资料涉及不同的政策时效，请分别查询历史和现行政策。")
            mode = AnswerMode.HISTORICAL
            periods = "、".join(dict.fromkeys(item.period for item in selected if item.period))
            replaced = any(item.metadata.timeliness_verification_status == TimelinessVerificationStatus.SUPERSEDED
                           for item in selected)
            note = "其中有政策版本已被替代。" if replaced else "相关通知已结束或仅保留历史效力。"
            message = f"以下为{periods}历史资料。{note}请勿用于当前办理。"
            answer = f"{message}\n\n{answer}"
            warnings.append(WarningItem(code="HISTORICAL_POLICY", message=message))
        elif any(item.mode == AnswerMode.PROCEDURE_REFERENCE for item in selected):
            mode = AnswerMode.PROCEDURE_REFERENCE
        if partial:
            warnings.append(WarningItem(code="PARTIAL_EVIDENCE", message="可核验资料仅覆盖部分问题。"))
        return AgentResult(
            status=AnswerStatus.ANSWERED,
            answer=answer,
            answer_mode=mode,
            citations=citations,
            warnings=warnings,
        )

    def _evidence_unchanged(self, request: AgentRequest, selected: list[Evidence]) -> bool:
        fresh_scope = PolicyScope.from_request(request, self.today())
        try:
            return all(self._eligible(request, item.chunk, fresh_scope) == item for item in selected)
        except Exception:
            return False

    def _answer_closed_recruitment(self, request: AgentRequest, notices: list[Evidence]) -> AgentResult:
        notice = max(notices, key=lambda item: item.metadata.deadline_on or date.min)
        if not self._evidence_unchanged(request, [notice]):
            return _insufficient("EVIDENCE_APPROVAL_CHANGED", "引用资料或适用状态已改变，本次不生成政策答案。")
        deadline = notice.metadata.deadline_on
        if deadline is None:
            return _insufficient("NO_ELIGIBLE_EVIDENCE", "无法核验该年度招募的截止日期。")
        message = "目前是否有新一轮招募，暂无法确认。"
        return AgentResult(
            status=AnswerStatus.ANSWERED,
            answer=f"{notice.period}度报名已于{deadline.year}年{deadline.month}月{deadline.day}日截止。{message}",
            answer_mode=AnswerMode.HISTORICAL,
            citations=[notice.citation()],
            warnings=[WarningItem(code="HISTORICAL_POLICY", message=message)],
        )

    def _eligible(self, request: AgentRequest, chunk: RetrievedChunk, scope: PolicyScope) -> Evidence | None:
        basic = (
            chunk.retrieval_status == RetrievalStatus.ENABLED
            and chunk.source_verification_status == SourceVerificationStatus.VERIFIED
            and (chunk.effective_on is None or chunk.effective_on <= scope.today)
            and (chunk.published_on is None or chunk.published_on <= scope.today)
            and math.isfinite(chunk.score)
            and bool(chunk.title.strip() and chunk.content.strip() and chunk.source_url.strip())
        )
        if not basic:
            return None
        metadata_lookup = getattr(self.retriever, "get_document_metadata", None)
        parsed_lookup = getattr(self.retriever, "get_parsed_chunk", None)
        if not callable(metadata_lookup) or not callable(parsed_lookup):
            return None
        try:
            metadata = metadata_lookup(chunk.version_id)
            parsed = parsed_lookup(chunk.chunk_id)
            if not isinstance(metadata, DocumentMetadata) or not isinstance(parsed, ParsedChunk):
                return None
            metadata = DocumentMetadata.model_validate(metadata.model_dump())
            parsed = ParsedChunk.model_validate(parsed.model_dump())
            matches_metadata = all(
                getattr(metadata, field) == getattr(chunk, field)
                for field in ("title", "source_url", "publisher", "published_on", "effective_on",
                              "retrieval_status", "source_verification_status", "timeliness_verification_status")
            )
            matches_chunk = all(getattr(parsed, field) == getattr(chunk, field)
                                for field in ("content", "locator", "original_locator"))
            if (not matches_metadata or not matches_chunk or not _human_approved(metadata)
                    or parsed.index_status in {ChunkIndexStatus.DISABLED, ChunkIndexStatus.FAILED}
                    or not parsed.source_file_key.strip()):
                return None
            scope_result = scope.evidence_mode(metadata)
            closed_period = None
            if scope_result is None and self.evidence_check is not None:
                closed_period = scope.closed_recruitment_period(metadata, chunk.content)
                if closed_period:
                    scope_result = AnswerMode.HISTORICAL, closed_period
        except Exception:
            return None
        if scope_result is None or (metadata.applicability_raw is None and self.evidence_check is None):
            return None
        if self.evidence_check is not None:
            applicable = self.evidence_check(request.model_copy(deep=True), chunk.model_copy(deep=True))
            if not isinstance(applicable, bool):
                raise ValueError("Evidence rule must return bool")
            if not applicable:
                return None
        return Evidence(chunk, metadata, *scope_result, parsed=parsed, recruitment_closed=bool(closed_period))


async def create_alpha_workflow(
    packages: Iterable[DocumentPackage] | None = None,
    *,
    file_root: Path,
    retriever: Retriever | None = None,
    corpus_dir: Path | None = None,
    llm_client: LLMClient | None = None,
    clarification_rule: ClarificationRule | None = None,
    evidence_check: EvidenceCheck | None = None,
    top_k: int = 5,
    timeout_seconds: float = 30.0,
    max_evidence_chars: int = 24000,
    today: Callable[[], date] = date.today,
) -> AgentWorkflow:
    """Assemble the real local retriever, business callbacks and Qwen adapter.

    The default rule module is owned by the business team. A missing module is
    a configuration error, never a silent fallback to the legacy demo rules.
    Explicit callbacks/client support owner handoff and labelled offline tests.
    With no explicit source, use PR #35's approved loader and check its report.
    Direct packages must also carry human_approved is True; indexing is not approval.
    Injected retrievers must expose approved metadata for every accepted version.
    Inject the result with create_app(agent_service=workflow,
    llm_client=workflow.llm_client). The caller loads its approved package list.
    """
    from importlib import import_module

    from backend.retrieval.local import LocalBM25Retriever
    from backend.services.errors import LLMConfigurationError
    from backend.services.qwen_client import create_qwen_client_from_env

    if sum(source is not None for source in (packages, retriever, corpus_dir)) > 1:
        raise ValueError("Provide only one of packages, retriever or corpus_dir")
    if (clarification_rule is None) != (evidence_check is None):
        raise ValueError("Provide both business callbacks or neither")
    if packages is not None:
        # Validate the entire input before indexing anything or creating a model
        # client. Never turn an enabled flag into an implicit human approval.
        packages = [DocumentPackage.model_validate(package.model_dump()) for package in packages]
        if any(not _human_approved(package.metadata) for package in packages):
            raise ServiceError("政策资料缺少明确的人工审核通过标记。",
                               code="SERVICE_NOT_CONFIGURED", http_status=503)
        retriever = LocalBM25Retriever(file_root=file_root)
    elif retriever is None:
        try:
            loader = import_module("backend.retrieval.alpha_corpus")
            retriever, report = await loader.load_approved_alpha_retriever(
                corpus_dir=corpus_dir if corpus_dir is not None else file_root / "knowledge_base/processed/alpha/approved",
                file_root=file_root, allow_missing=False,
            )
            if (not report.corpus_dir.is_dir() or not report.loaded_packages
                    or not report.index_results or report.total_indexed_chunks <= 0
                    or any(result.status != IndexingStatus.INDEXED or result.warnings
                           for result in report.index_results)):
                raise ValueError("Approved corpus is not fully indexed")
        except Exception as exc:
            raise ServiceError("正式审核资料目录或加载报告未通过完整性检查。",
                               code="SERVICE_NOT_CONFIGURED", http_status=503) from exc
    for package in packages if packages is not None else ():
        indexed = await retriever.index_document(package)
        if indexed.status != IndexingStatus.INDEXED:
            raise ServiceError(
                "政策资料未完整通过索引检查，不能启用正式工作流。",
                code="SERVICE_NOT_CONFIGURED", http_status=503,
            )
    if clarification_rule is None:
        try:
            rules = import_module("backend.services.alpha_business_rules")
            clarification_rule = partial(rules.alpha_clarification_rule, today=today)
            evidence_check = rules.build_from_retriever(retriever, today=today)
        except (ImportError, AttributeError) as exc:
            raise LLMConfigurationError("Alpha 业务规则模块未就绪，不能启用正式工作流。") from exc
    return AgentWorkflow(
        retriever, llm_client if llm_client is not None else create_qwen_client_from_env(),
        clarification_rule=clarification_rule, evidence_check=evidence_check,
        top_k=top_k, timeout_seconds=timeout_seconds,
        max_evidence_chars=max_evidence_chars, today=today,
    )
