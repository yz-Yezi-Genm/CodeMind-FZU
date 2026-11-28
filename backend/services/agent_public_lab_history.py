"""Read the local index exhaustively for Agent's public-lab batch check."""
from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from inspect import iscoroutinefunction

from backend.contracts.models import DocumentMetadata, ParsedChunk, RetrievedChunk
from backend.contracts.protocols import Retriever
from backend.retrieval.local import local_index_chunk_ids
from backend.services.agent_generation import Evidence
from backend.services.agent_policy_context import _LAB_NAME_FIELD, _LAB_SUBJECT, _lab_key, public_lab_batch_number


def public_lab_index(retriever: Retriever) -> Iterator[RetrievedChunk] | None:
    """Inventory the live index without relying on BM25's truncated hit list."""
    list_metadata = getattr(retriever, "list_document_metadata", None)
    list_chunks = getattr(retriever, "list_parsed_chunks", None)
    if any(not callable(method) or iscoroutinefunction(method) for method in (list_metadata, list_chunks)):
        return None
    return _enumerate_public_lab_index(retriever, list_metadata, list_chunks)


def _enumerate_public_lab_index(
    retriever: Retriever,
    list_metadata: Callable[..., list[DocumentMetadata]],
    list_chunks: Callable[..., list[ParsedChunk]],
) -> Iterator[RetrievedChunk]:
    versions = list_metadata(business_direction_code="COLLEGE_RESOURCES", category_name="研究方向与公开介绍")
    for metadata in versions:
        chunks = list_chunks(record_code=metadata.record_code, version_no=metadata.version_no)
        if not chunks:
            raise ValueError("The enumerated version is no longer available")
        for parsed in chunks:
            document_id, version_id, file_id, chunk_id = local_index_chunk_ids(metadata, parsed)
            # The optional enumeration returns DTOs without UUIDs. Confirm the
            # local IDs against point lookups before using them in citations.
            if retriever.get_document_metadata(version_id) != metadata or retriever.get_parsed_chunk(chunk_id) != parsed:
                raise ValueError("The enumerated index is inconsistent with its point lookups")
            yield RetrievedChunk(
                chunk_id=chunk_id, document_id=document_id, version_id=version_id,
                file_id=file_id, content=parsed.content, title=metadata.title,
                publisher=metadata.publisher, source_url=metadata.source_url,
                published_on=metadata.published_on, effective_on=metadata.effective_on,
                locator=parsed.locator, original_locator=parsed.original_locator,
                score=0.0, retrieval_method="bm25",
                source_verification_status=metadata.source_verification_status,
                timeliness_verification_status=metadata.timeliness_verification_status,
                retrieval_status=metadata.retrieval_status,
            )


@dataclass(frozen=True)
class PublicLabBatch:
    period: str
    record_code: str
    source: str
    number: int | None


def public_lab_batch(item: Evidence) -> PublicLabBatch | None:
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
    return PublicLabBatch(
        period=item.period,
        record_code=item.metadata.record_code,
        source=item.metadata.source_page_url or item.metadata.source_url,
        number=public_lab_batch_number(next(iter(declared), item.metadata.title)),
    )


class PublicLabVersionConflict(ValueError):
    """Eligible versions of one record disagree on the requested public information."""


def coalesce_public_lab_versions(versions: list[list[Evidence]]) -> list[Evidence]:
    """Keep one version only after checking the relevant evidence agrees."""
    reference = versions[0]
    if any(not version for version in versions):
        raise PublicLabVersionConflict("The requested lab is missing from another eligible version")
    if len(versions) == 1:
        return reference

    def signature(items: list[Evidence]) -> set[tuple[str, str | None]]:
        return {(item.chunk.content, item.chunk.original_locator) for item in items}

    first = reference[0]
    expected = signature(reference)
    for version in versions[1:]:
        if (
            public_lab_batch(first) != public_lab_batch(version[0])
            or first.mode != version[0].mode
            or first.metadata.source_url != version[0].metadata.source_url
            or first.metadata.applicability_raw != version[0].metadata.applicability_raw
            or signature(version) != expected
        ):
            raise PublicLabVersionConflict("Eligible versions of the same lab record disagree")
    return reference


_ROSTER_SEQUENCE = re.compile(
    r"^#{1,6}\s*R4·实验室序号(\d+)·|^序号(?:[（(][^）)\n]+[）)])?[：:][ \t]*\n?[ \t]*(\d+)[ \t]*$", re.M,
)
_ROSTER_NAME = re.compile(r"""[\w \u00a0+·（）()“”「」'"’&,，\-—]{1,150}""")


class PublicLabDirectoryConflict(ValueError):
    """The original row identity does not agree across directory excerpts."""


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
        sequences = {int(heading or field) for heading, field in _ROSTER_SEQUENCE.findall(content)}
        if len(sequences) > 1:
            raise PublicLabDirectoryConflict("An excerpt has conflicting original row numbers")
        if sequences:
            sequence = next(iter(sequences))
            previous_name, _ = rows.setdefault(sequence, (name, item))
            if _lab_key(previous_name) != _lab_key(name):
                raise PublicLabDirectoryConflict("The same original row has different lab names")
        else:
            unnumbered.setdefault(_lab_key(name), (name, item))
    numbered_names = {_lab_key(name) for name, _ in rows.values()}
    entries = [
        (number, name, item) for number, (name, item) in sorted(rows.items())
    ] + [
        (None, name, item) for key, (name, item) in unnumbered.items() if key not in numbered_names
    ]
    return [
        (number, name, item) for number, name, item in entries
        if _ROSTER_NAME.fullmatch(name) and not re.search(r"电话|邮箱|报名|招募|接收|名额|截止|\d{7,}", name)
    ]
