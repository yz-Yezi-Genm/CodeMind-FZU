"""Read the local index exhaustively for Agent's public-lab batch check."""
from __future__ import annotations

import re
from collections.abc import Iterator

from backend.contracts.models import RetrievalStatus, RetrievedChunk
from backend.contracts.protocols import Retriever
from backend.retrieval.local import LocalBM25Retriever
from backend.services.agent_generation import Evidence
from backend.services.agent_policy_context import _LAB_NAME_FIELD, _LAB_SUBJECT, _lab_key, public_lab_batch_number


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
        and version.metadata.category_name.strip() == "研究方向与公开介绍"
        for chunk in version.chunks
    )


def public_lab_batch(item: Evidence) -> tuple[str, str, int | None] | None:
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
    label = next(iter(declared), item.metadata.title)
    source = item.metadata.source_page_url or item.metadata.source_url
    number = public_lab_batch_number(label)
    return item.period, f"{source} {label}" if declared and number is None else source, number


_ROSTER_SEQUENCE = re.compile(
    r"^#{1,6}\s*R4·实验室序号(\d+)·|^序号(?:[（(][^）)\n]+[）)])?[：:][ \t]*\n?[ \t]*(\d+)[ \t]*$", re.M,
)
_ROSTER_NAME = re.compile(r"""[\w \u00a0+·（）()“”「」'"’&,，\-—]{1,150}""")


def public_lab_directory(evidence: list[Evidence]) -> list[tuple[int | None, str, Evidence]]:
    """Keep one public name per original row. Never return the rest of the chunk."""
    rows = {}
    unnumbered = {}
    for item in evidence:
        content = item.chunk.content
        labels = _LAB_NAME_FIELD.findall(content)
        if not labels:
            match = _LAB_SUBJECT.match(content.partition("\n")[0])
            labels = [match["name"]] if match else []
        if len(labels) != 1:
            continue
        name = labels[0].strip()
        if not _ROSTER_NAME.fullmatch(name) or re.search(r"电话|邮箱|报名|招募|接收|名额|截止|\d{7,}", name):
            continue
        sequences = {int(heading or field) for heading, field in _ROSTER_SEQUENCE.findall(content)}
        if len(sequences) > 1:
            continue
        if sequences:
            rows.setdefault(next(iter(sequences)), (name, item))
        else:
            unnumbered.setdefault(_lab_key(name), (name, item))
    numbered_names = {_lab_key(name) for name, _ in rows.values()}
    return [
        (number, name, item) for number, (name, item) in sorted(rows.items())
    ] + [
        (None, name, item) for key, (name, item) in unnumbered.items() if key not in numbered_names
    ]
