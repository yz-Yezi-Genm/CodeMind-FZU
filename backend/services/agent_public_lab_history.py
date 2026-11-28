"""Read the local index exhaustively for Agent's public-lab batch check."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from inspect import iscoroutinefunction

from backend.contracts.models import DocumentMetadata, ParsedChunk, RetrievedChunk
from backend.contracts.protocols import Retriever
from backend.retrieval.local import local_index_chunk_ids
from backend.services.agent_generation import Evidence
from backend.services.agent_policy_context import (
    _LAB_NAME_FIELD, _LAB_SUBJECT, _LIST_HEADING, _PUBLIC_BATCH, _R4_CATEGORY, _batch_name, _lab_key,
)


def public_lab_index(retriever: Retriever, category: str = _R4_CATEGORY) -> Iterator[RetrievedChunk] | None:
    """Inventory the live index without relying on BM25's truncated hit list."""
    list_metadata = getattr(retriever, "list_document_metadata", None)
    list_chunks = getattr(retriever, "list_parsed_chunks", None)
    if any(not callable(method) or iscoroutinefunction(method) for method in (list_metadata, list_chunks)):
        return None
    return _enumerate_public_lab_index(retriever, list_metadata, list_chunks, category)


def _enumerate_public_lab_index(
    retriever: Retriever,
    list_metadata: Callable[..., list[DocumentMetadata]],
    list_chunks: Callable[..., list[ParsedChunk]],
    category: str,
) -> Iterator[RetrievedChunk]:
    versions = list_metadata(business_direction_code="COLLEGE_RESOURCES", category_name=category)
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
    year: int | None
    name: str | None

    def label(self, evidence: list[Evidence]) -> str:
        period = max((item.period or "" for item in evidence), key=len)
        return period + (self.name or "")


_BATCH_FIELD = re.compile(r"^(?:资料批次|适用批次|报名批次|招募批次|批次)\s*[:：]\s*([^\n；;]+)", re.M)
_SOURCE_HEADING = re.compile(r"^#{1,6}[ \t]+([^\n]+)", re.M)
_PACKAGING_HEADING = re.compile(r"^R[34]·实验室序号")
_SOURCE_BATCH_LINE = re.compile(r"^(?:20\d{2}(?:\s*年(?:度)?|[-—]20\d{2}学年)\s*)?(?:第|春季|夏季|秋季|冬季|春招|秋招)")


def public_lab_batch(item: Evidence) -> PublicLabBatch:
    content = item.chunk.content
    headings = [line for line in _SOURCE_HEADING.findall(content) if not _PACKAGING_HEADING.match(line)]
    first_line = content.lstrip().partition("\n")[0]
    if _SOURCE_BATCH_LINE.match(first_line):
        headings.append(first_line)
    labels = {
        _batch_name(match)
        for text in (item.metadata.title, *headings, *_BATCH_FIELD.findall(content))
        for match in _PUBLIC_BATCH.finditer(unicodedata.normalize("NFKC", text))
    }
    if len(labels) > 1:
        raise PublicLabVersionConflict("The same lab excerpt declares conflicting batches")
    return PublicLabBatch(int(item.period[:4]) if item.period else None, next(iter(labels), None))


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
            {public_lab_batch(item) for item in reference} != {public_lab_batch(item) for item in version}
            or first.period != version[0].period
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


def has_lab_directory(evidence: list[Evidence]) -> bool:
    """Recognize a directory source or multiple numbered rows from the same table."""
    return any(
        _LIST_HEADING.search(item.metadata.title) or _LIST_HEADING.search(item.chunk.content.partition("\n")[0])
        for item in evidence
    ) or len({
        int(heading or field)
        for item in evidence for heading, field in _ROSTER_SEQUENCE.findall(item.chunk.content)
    }) > 1


_CONTACT_SECTION = re.compile(
    r"^(?:[-*][ \t]+)?(联系人|联络人|负责人|联系电话或邮箱|联系方式|联系电话|手机|电话|电子邮箱|邮箱)"
    r"(?:[（(][^）)\n]+[）)])?[ \t]*[：:][ \t]*(?:\n)?([^\n]+(?:\n(?=[^\s#\n])[^\n]+)*)",
    re.M,
)
_INLINE_CONTACT = re.compile(r"(?P<label>联系人|联络人|负责人|联系电话|电话|电子邮箱|邮箱)[：:][ \t]*(?P<value>[^\n，,。；;]+)")
_PHONE = re.compile(r"(?<!\d)(?:1[3-9]\d{9}|0\d{2,3}[- ]?\d{7,8})(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_CONTACT_NAME = re.compile(r"[\w·]{2,36}(?:[、/／，,\s]+[\w·]{2,36})*")


def lab_contact_values(content: str, fields: frozenset[str]) -> frozenset[tuple[str, str]]:
    """Project contact fields from the R3 excerpt, retaining source text for citations."""
    values: set[tuple[str, str]] = set()
    entries = [(match["label"], match["value"]) for match in _INLINE_CONTACT.finditer(content)]
    entries.extend(_CONTACT_SECTION.findall(content))
    for label, raw in entries:
        # Structured cells can run onto adjacent layout lines. Only read the
        # contact cell, and keep phone/email values in their original form.
        raw = re.split(r"\n(?=[^\n]+[：:])", raw, maxsplit=1)[0]
        if label in {"联系人", "联络人", "负责人"} and "联系人" in fields:
            for name in re.split(r"[\n、/／，,]+", raw):
                name = re.split(r"[（(：:]|\s+(?=\d)", name.strip(), maxsplit=1)[0].strip()
                if _CONTACT_NAME.fullmatch(name) and not re.search(r"\d|暂无|未公开|电话|邮箱|招募|报名", name):
                    values.add(("联系人", name))
        if "电话" in fields and label not in {"电子邮箱", "邮箱"}:
            values.update(("电话", phone) for phone in _PHONE.findall(raw))
        if "邮箱" in fields and label not in {"手机", "联系电话", "电话"}:
            values.update(("邮箱", address) for address in _EMAIL.findall(raw))
    return frozenset(values)


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
