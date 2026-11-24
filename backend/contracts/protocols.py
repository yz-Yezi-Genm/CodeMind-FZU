"""Typed service boundaries used by CodeMind-FZU modules."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol
from uuid import UUID

from .models import (
    AgentRequest,
    AgentResult,
    DocumentListResponse,
    DocumentMetadata,
    DocumentPackage,
    DocumentSummary,
    IndexResult,
    LLMGenerateRequest,
    LLMResult,
    ParsedChunk,
    RetrievalRequest,
    RetrievedChunk,
)


class AgentService(Protocol):
    """Implemented by the Agent workflow owner (吴诗莹)."""

    async def run(self, request: AgentRequest) -> AgentResult:
        ...


class Retriever(Protocol):
    """Implemented by the retrieval owner (王智洋)."""

    async def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        ...

    def get_document_metadata(self, version_id: UUID) -> DocumentMetadata | None:
        ...

    def get_parsed_chunk(self, chunk_id: UUID) -> ParsedChunk | None:
        ...


class DocumentParser(Protocol):
    """Implemented by the document-processing owner (丁晓炜)."""

    def parse_document(
        self,
        file_path: Path,
        metadata: DocumentMetadata,
    ) -> DocumentPackage:
        ...


class KnowledgeIndexer(Protocol):
    """Implemented by the indexing/data-access owner (王智洋)."""

    async def index_document(self, package: DocumentPackage) -> IndexResult:
        ...


class LLMClient(Protocol):
    """Implemented by the model-adapter owner (赵紫龙)."""

    async def generate(self, request: LLMGenerateRequest) -> LLMResult:
        ...


class DocumentAdminService(Protocol):
    """Service boundary for the admin UI (林彦翔); auth is a separate prerequisite."""

    async def list_documents(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> DocumentListResponse:
        ...

    async def get_document(self, document_id: UUID) -> DocumentSummary:
        ...

    async def ingest_document(
        self,
        file_path: Path,
        metadata: DocumentMetadata,
    ) -> DocumentSummary:
        ...

    async def reindex_document(self, document_id: UUID) -> IndexResult:
        ...
