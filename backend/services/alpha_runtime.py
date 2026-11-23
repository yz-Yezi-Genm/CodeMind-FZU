"""Assemble the Beta Retriever, AgentWorkflow, Qwen client and conversations."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from time import monotonic
from typing import Callable
from uuid import UUID

from backend.app.config import AppSettings
from backend.contracts.models import (
    AgentRequest,
    AgentResult,
    ConversationTurn,
    IndexResult,
    IndexingStatus,
    LLMRole,
    RetrievedChunk,
)
from backend.contracts.protocols import AgentService, LLMClient, Retriever
from backend.retrieval.alpha_corpus import (
    AlphaCorpusLoadReport,
    load_approved_alpha_retriever,
)
from backend.retrieval.local import LocalBM25Retriever
from backend.services.agent_workflow import create_alpha_workflow
from backend.services.errors import (
    KnowledgeBaseUnavailableError,
    LLMConfigurationError,
    RuntimeUnavailableError,
    ServiceContractError,
    ServiceError,
)
from backend.services.qwen_client import create_qwen_client_from_env


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ClarificationRule = Callable[[AgentRequest], str | None]
EvidenceCheck = Callable[[AgentRequest, RetrievedChunk], bool]


@dataclass
class _ConversationState:
    history: list[ConversationTurn] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = field(default_factory=monotonic)
    active_requests: int = 0


class InMemoryConversationStore:
    """Keep bounded, isolated histories and serialize writes per conversation."""

    def __init__(
        self,
        *,
        max_messages: int = 12,
        max_chars: int = 6000,
        max_conversations: int = 1000,
        idle_seconds: float = 3600,
    ) -> None:
        if max_messages < 2:
            raise ValueError("max_messages 必须大于等于 2。")
        if max_chars < 1:
            raise ValueError("max_chars 必须大于 0。")
        if max_conversations < 1:
            raise ValueError("max_conversations 必须大于 0。")
        if idle_seconds <= 0:
            raise ValueError("idle_seconds 必须大于 0。")
        self._max_messages = max_messages if max_messages % 2 == 0 else max_messages - 1
        self._max_chars = max_chars
        self._max_conversations = max_conversations
        self._idle_seconds = idle_seconds
        self._states: dict[UUID, _ConversationState] = {}
        self._registry_lock = asyncio.Lock()

    @property
    def max_messages(self) -> int:
        """Effective message limit; odd inputs are rounded down to complete turns."""
        return self._max_messages

    @property
    def conversation_count(self) -> int:
        return len(self._states)

    def history(self, conversation_id: UUID) -> list[ConversationTurn]:
        state = self._states.get(conversation_id)
        if state is None:
            return []
        return [turn.model_copy(deep=True) for turn in state.history]

    async def run(
        self,
        conversation_id: UUID,
        request: AgentRequest,
        agent_service: AgentService,
    ) -> AgentResult:
        state = await self._acquire_state(conversation_id)
        try:
            async with state.lock:
                prior_history = [
                    turn.model_copy(deep=True) for turn in state.history
                ]
                agent_request = AgentRequest.model_validate(
                    {
                        **request.model_dump(mode="python"),
                        "history": [
                            turn.model_dump(mode="python")
                            for turn in prior_history
                        ],
                    }
                )
                result = await agent_service.run(agent_request)
                if not isinstance(result, AgentResult):
                    raise ServiceContractError(
                        "Agent 服务返回了不符合公共契约的结果。"
                    )

                now = datetime.now(timezone.utc)
                reply = result.answer or result.clarifying_question
                if not reply and result.warnings:
                    reply = result.warnings[0].message
                updated = [
                    *prior_history,
                    ConversationTurn(
                        role=LLMRole.USER,
                        content=request.query,
                        created_at=now,
                    ),
                ]
                if reply:
                    updated.append(
                        ConversationTurn(
                            role=LLMRole.ASSISTANT,
                            content=reply,
                            created_at=now,
                        )
                    )
                state.history = self._trim(updated)
                return result
        finally:
            await self._release_state(conversation_id, state)

    async def _acquire_state(self, conversation_id: UUID) -> _ConversationState:
        async with self._registry_lock:
            state = self._states.get(conversation_id)
            if state is None:
                self._evict_lru_locked()
                state = _ConversationState()
                self._states[conversation_id] = state
            state.last_used = monotonic()
            state.active_requests += 1
            return state

    async def _release_state(
        self,
        conversation_id: UUID,
        state: _ConversationState,
    ) -> None:
        async with self._registry_lock:
            if self._states.get(conversation_id) is state:
                state.active_requests = max(0, state.active_requests - 1)
                state.last_used = monotonic()

    def _evict_lru_locked(self) -> None:
        if len(self._states) < self._max_conversations:
            return
        inactive = [
            (state.last_used, conversation_id)
            for conversation_id, state in self._states.items()
            if state.active_requests == 0
        ]
        if inactive:
            _, conversation_id = min(inactive)
            self._states.pop(conversation_id, None)

    async def prune_idle(self, *, idle_seconds: float | None = None) -> int:
        """Remove inactive conversations that have exceeded the idle lifetime."""
        threshold = self._idle_seconds if idle_seconds is None else idle_seconds
        if threshold <= 0:
            raise ValueError("idle_seconds 必须大于 0。")
        now = monotonic()
        async with self._registry_lock:
            expired = [
                conversation_id
                for conversation_id, state in self._states.items()
                if state.active_requests == 0
                and now - state.last_used >= threshold
            ]
            for conversation_id in expired:
                self._states.pop(conversation_id, None)
            return len(expired)

    async def clear_all(self) -> int:
        """Drop every inactive conversation; active turns release their state later."""
        async with self._registry_lock:
            inactive = [
                conversation_id
                for conversation_id, state in self._states.items()
                if state.active_requests == 0
            ]
            for conversation_id in inactive:
                self._states.pop(conversation_id, None)
            return len(inactive)

    async def cleanup_loop(self, interval_seconds: float) -> None:
        """Periodically apply global idle cleanup until cancelled."""
        while True:
            await asyncio.sleep(interval_seconds)
            removed = await self.prune_idle()
            if removed:
                logger.info("Pruned %s idle Alpha conversations", removed)

    def _trim(
        self,
        history: list[ConversationTurn],
    ) -> list[ConversationTurn]:
        trimmed = list(history)
        # User and assistant turns are retained as a pair where possible. The
        # current turn remains available even if one unusually long exchange
        # alone exceeds the configured budget.
        while len(trimmed) > 2:
            total_chars = sum(len(turn.content) for turn in trimmed)
            if (
                len(trimmed) <= self._max_messages
                and total_chars <= self._max_chars
            ):
                break
            del trimmed[:2]
        return [
            turn.model_copy(deep=True)
            for turn in trimmed[-self._max_messages :]
        ]


class ConversationAgentService:
    """AgentService wrapper that injects bounded per-conversation history."""

    def __init__(
        self,
        agent_service: AgentService,
        store: InMemoryConversationStore,
    ) -> None:
        self._agent_service = agent_service
        self._store = store

    async def run(self, request: AgentRequest) -> AgentResult:
        return await self._store.run(
            request.conversation_id,
            request,
            self._agent_service,
        )


class UnavailableAgentService:
    """Expose a sanitized runtime assembly failure through AgentService."""

    def __init__(self, error: ServiceError) -> None:
        self._error = error

    async def run(self, _request: AgentRequest) -> AgentResult:
        raise self._error


@dataclass
class AlphaRuntime:
    """Live components owned by one FastAPI application lifespan."""

    agent_service: AgentService
    retriever: Retriever
    llm_client: LLMClient
    session_store: InMemoryConversationStore
    corpus_report: AlphaCorpusLoadReport
    packages: tuple[str, ...]
    index_results: tuple[IndexResult, ...]
    cleanup_task: asyncio.Task[None] | None = None

    async def close(self) -> None:
        if self.cleanup_task is not None:
            self.cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.cleanup_task
        close = getattr(self.llm_client, "aclose", None)
        if callable(close):
            await close()


async def build_alpha_retriever(
    settings: AppSettings,
    *,
    file_root: Path | None = None,
) -> tuple[LocalBM25Retriever, AlphaCorpusLoadReport]:
    """Load the approved corpus through PR #35's manifest and path gate."""
    root = file_root or PROJECT_ROOT
    try:
        retriever, report = await load_approved_alpha_retriever(
            corpus_dir=settings.alpha_package_dir,
            file_root=root,
            allow_missing=False,
        )
    except Exception as exc:
        raise KnowledgeBaseUnavailableError(
            "人工审核政策资料目录或加载流程未通过检查。"
        ) from exc

    if (
        not report.corpus_dir.is_dir()
        or not report.loaded_packages
        or not report.index_results
        or report.total_indexed_chunks <= 0
        or any(
            result.status != IndexingStatus.INDEXED or result.warnings
            for result in report.index_results
        )
    ):
        skipped = "; ".join(reason for _, reason in report.skipped_packages)
        logger.warning(
            "Approved corpus rejected loaded=%s skipped=%s detail=%s",
            len(report.loaded_packages),
            len(report.skipped_packages),
            skipped,
        )
        raise KnowledgeBaseUnavailableError(
            "没有通过人工审核且完整建立索引的正式政策资料包。"
        )
    return retriever, report


def _business_callbacks(
    retriever: Retriever,
    *,
    clarification_rule: ClarificationRule | None,
    evidence_check: EvidenceCheck | None,
) -> tuple[ClarificationRule, EvidenceCheck]:
    if (clarification_rule is None) != (evidence_check is None):
        raise LLMConfigurationError(
            "业务追问规则和证据规则必须同时注入。"
        )
    if clarification_rule is not None and evidence_check is not None:
        if not callable(clarification_rule) or not callable(evidence_check):
            raise LLMConfigurationError("业务规则回调必须是可调用对象。")
        return clarification_rule, evidence_check

    try:
        rules = import_module("backend.services.alpha_business_rules")
        rule = rules.alpha_clarification_rule
        builder = rules.build_from_retriever
        check = builder(retriever)
    except (ImportError, AttributeError) as exc:
        raise LLMConfigurationError(
            "Alpha 业务规则模块或 retriever 绑定入口未就绪。"
        ) from exc
    except Exception as exc:
        raise LLMConfigurationError(
            "Alpha 业务规则无法绑定到当前 Retriever。"
        ) from exc
    if not callable(rule) or not callable(check):
        raise LLMConfigurationError(
            "Alpha 业务规则返回了无效的回调。"
        )
    return rule, check


async def build_alpha_runtime(
    settings: AppSettings | None = None,
    *,
    llm_client: LLMClient | None = None,
    file_root: Path | None = None,
    clarification_rule: ClarificationRule | None = None,
    evidence_check: EvidenceCheck | None = None,
) -> AlphaRuntime:
    """Build the real runtime graph without starting a nested event loop."""

    app_settings = settings or AppSettings.from_env()
    try:
        retriever, report = await build_alpha_retriever(
            app_settings,
            file_root=file_root,
        )
        clarification_rule, evidence_check = _business_callbacks(
            retriever,
            clarification_rule=clarification_rule,
            evidence_check=evidence_check,
        )
        client = llm_client or create_qwen_client_from_env()
        workflow = await create_alpha_workflow(
            retriever=retriever,
            file_root=file_root or PROJECT_ROOT,
            llm_client=client,
            clarification_rule=clarification_rule,
            evidence_check=evidence_check,
        )
    except ServiceError:
        raise
    except Exception as exc:
        logger.exception("Alpha runtime assembly failed")
        raise RuntimeUnavailableError(
            "Alpha 后端运行组件组装失败。"
        ) from exc

    store = InMemoryConversationStore(
        max_messages=app_settings.conversation_max_messages,
        max_chars=app_settings.conversation_history_char_limit,
        max_conversations=app_settings.conversation_max_count,
        idle_seconds=app_settings.conversation_idle_seconds,
    )
    cleanup_task = asyncio.create_task(
        store.cleanup_loop(app_settings.conversation_cleanup_interval_seconds),
        name="alpha-conversation-cleanup",
    )
    return AlphaRuntime(
        agent_service=ConversationAgentService(workflow, store),
        retriever=retriever,
        llm_client=client,
        session_store=store,
        corpus_report=report,
        packages=report.loaded_packages,
        index_results=report.index_results,
        cleanup_task=cleanup_task,
    )


__all__ = [
    "AlphaRuntime",
    "ConversationAgentService",
    "InMemoryConversationStore",
    "PROJECT_ROOT",
    "UnavailableAgentService",
    "build_alpha_retriever",
    "build_alpha_runtime",
]
