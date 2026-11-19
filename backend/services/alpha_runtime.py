"""Assemble the Alpha Retriever, AgentWorkflow, Qwen client and conversations."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Callable, Protocol
from uuid import UUID

from pydantic import ValidationError

from backend.app.config import AppSettings
from backend.contracts.models import (
    AgentRequest,
    AgentResult,
    ConversationTurn,
    DocumentPackage,
    IndexResult,
    IndexingStatus,
    LLMRole,
    RetrievalStatus,
)
from backend.contracts.protocols import AgentService, LLMClient, Retriever
from backend.retrieval.local import LocalBM25Retriever
from backend.services.agent_workflow import (
    AgentWorkflow,
    default_clarification_rule,
)
from backend.services.errors import (
    KnowledgeBaseUnavailableError,
    RuntimeUnavailableError,
    ServiceContractError,
    ServiceError,
)
from backend.services.qwen_client import create_qwen_client_from_env


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SIDECAR_NAMES = {"manifest.json", "summary.json"}


@dataclass
class _ConversationState:
    history: list[ConversationTurn] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class InMemoryConversationStore:
    """Keep bounded, isolated histories and serialize writes per conversation."""

    def __init__(
        self,
        *,
        max_messages: int = 12,
        max_chars: int = 6000,
    ) -> None:
        if max_messages < 2 or max_messages % 2:
            raise ValueError("max_messages 必须是大于等于 2 的偶数。")
        if max_chars < 1:
            raise ValueError("max_chars 必须大于 0。")
        self._max_messages = max_messages
        self._max_chars = max_chars
        self._states: dict[UUID, _ConversationState] = {}

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
        state = self._states.setdefault(conversation_id, _ConversationState())
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


@dataclass(frozen=True)
class AlphaRuntime:
    """Live Alpha components owned by one FastAPI application lifespan."""

    agent_service: AgentService
    retriever: Retriever
    llm_client: LLMClient
    session_store: InMemoryConversationStore
    packages: tuple[Path, ...]
    index_results: tuple[IndexResult, ...]

    async def close(self) -> None:
        close = getattr(self.llm_client, "aclose", None)
        if callable(close):
            await close()


def _approved_package_paths(directory: Path) -> tuple[Path, ...]:
    if not directory.is_dir():
        raise KnowledgeBaseUnavailableError(
            "未找到人工审核政策资料目录。"
        )
    paths = tuple(
        path
        for path in sorted(directory.rglob("*.json"))
        if path.name not in _SIDECAR_NAMES
        and not path.name.endswith(".metadata.json")
    )
    if not paths:
        raise KnowledgeBaseUnavailableError(
            "人工审核政策资料目录中没有可加载的资料包。"
        )
    return paths


async def build_alpha_retriever(
    settings: AppSettings,
    *,
    file_root: Path | None = None,
) -> tuple[LocalBM25Retriever, tuple[Path, ...], tuple[IndexResult, ...]]:
    """Load only enabled packages from the approved corpus into one BM25 index."""

    package_paths = _approved_package_paths(settings.alpha_package_dir)
    retriever = LocalBM25Retriever(file_root=file_root or PROJECT_ROOT)
    indexed_paths: list[Path] = []
    results: list[IndexResult] = []
    skipped = 0

    for path in package_paths:
        try:
            package = DocumentPackage.model_validate_json(path.read_bytes())
        except (OSError, ValidationError, ValueError) as exc:
            raise KnowledgeBaseUnavailableError(
                "人工审核政策资料包无法通过公共契约校验。"
            ) from exc
        if package.metadata.retrieval_status != RetrievalStatus.ENABLED:
            skipped += 1
            logger.warning(
                "Skipped non-enabled package path=%s status=%s",
                path,
                package.metadata.retrieval_status.value,
            )
            continue

        try:
            indexed = await retriever.index_document(package)
        except Exception as exc:
            raise KnowledgeBaseUnavailableError(
                "人工审核政策资料包建立索引失败。"
            ) from exc
        if indexed.status != IndexingStatus.INDEXED:
            raise KnowledgeBaseUnavailableError(
                "人工审核政策资料未完整通过索引检查。"
            )
        indexed_paths.append(path)
        results.append(indexed)

    if not indexed_paths:
        detail = "；已忽略未开放资料" if skipped else ""
        raise KnowledgeBaseUnavailableError(
            f"没有可进入正式问答的已开放政策资料包{detail}。"
        )
    return retriever, tuple(indexed_paths), tuple(results)


def _business_callbacks() -> tuple[
    Callable[[AgentRequest], str | None],
    Callable[[AgentRequest, object], bool] | None,
]:
    try:
        rules = import_module("backend.services.alpha_business_rules")
        clarification_rule = rules.alpha_clarification_rule
        evidence_check = rules.alpha_evidence_check
    except (ImportError, AttributeError):
        logger.warning(
            "Alpha business rules not delivered; using conservative workflow defaults."
        )
        return default_clarification_rule, None
    return clarification_rule, evidence_check


async def build_alpha_runtime(
    settings: AppSettings | None = None,
    *,
    llm_client: LLMClient | None = None,
    file_root: Path | None = None,
) -> AlphaRuntime:
    """Build the real runtime graph without starting a nested event loop."""

    app_settings = settings or AppSettings.from_env()
    try:
        client = llm_client or create_qwen_client_from_env()
        (
            retriever,
            indexed_paths,
            results,
        ) = await build_alpha_retriever(
            app_settings,
            file_root=file_root,
        )
        clarification_rule, evidence_check = _business_callbacks()
        workflow = AgentWorkflow(
            retriever,
            client,
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
    )
    return AlphaRuntime(
        agent_service=ConversationAgentService(workflow, store),
        retriever=retriever,
        llm_client=client,
        session_store=store,
        packages=indexed_paths,
        index_results=results,
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
