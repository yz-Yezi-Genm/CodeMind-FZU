"""Read the local index exhaustively for Agent's public-lab batch check."""
from __future__ import annotations

from collections.abc import Iterator

from backend.contracts.models import RetrievalStatus, RetrievedChunk
from backend.contracts.protocols import Retriever
from backend.retrieval.local import LocalBM25Retriever
from backend.services.agent_generation import Evidence


def public_lab_index(retriever: Retriever) -> Iterator[RetrievedChunk] | None:
    """Inventory the live index without relying on BM25's truncated hit list."""
    if type(retriever) is not LocalBM25Retriever:
        return None
    # Retriever's public contract only exposes ranked search and point lookups.
    # This read-only adapter is deliberately limited to the local implementation.
    versions = tuple(retriever._versions.values())
    return (
        RetrievedChunk(
            chunk_id=chunk.chunk_id, document_id=version.document_id, version_id=version.version_id,
            file_id=chunk.file_id, content=chunk.parsed.content, title=version.metadata.title,
            publisher=version.metadata.publisher, source_url=version.metadata.source_url,
            published_on=version.metadata.published_on, effective_on=version.metadata.effective_on,
            locator=chunk.parsed.locator, original_locator=chunk.parsed.original_locator,
            score=0.0, retrieval_method="bm25",
            source_verification_status=version.metadata.source_verification_status,
            timeliness_verification_status=version.metadata.timeliness_verification_status,
            retrieval_status=version.metadata.retrieval_status,
        )
        for version in versions
        if version.metadata.retrieval_status == RetrievalStatus.ENABLED
        and "COLLEGE_RESOURCES" in version.metadata.business_direction_codes
        and version.metadata.category_name in {"实验室与科研团队", "研究方向与公开介绍"}
        for chunk in version.chunks
    )


def public_lab_batch(item: Evidence) -> tuple[str, str] | None:
    if not item.period:
        return None
    declared = {
        str(facts[key]).strip()
        for facts in (item.metadata.temporal_notes or {}, item.metadata.applicability_raw or {})
        for key in ("资料批次", "适用批次", "批次")
        if facts.get(key) and str(facts[key]).strip()
    }
    if len(declared) > 1:
        return None
    if declared:
        return item.period, next(iter(declared))
    # The two views of one official attachment may share its source page.
    return item.period, item.metadata.source_page_url or item.metadata.source_url
