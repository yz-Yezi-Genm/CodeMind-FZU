"""In-memory BM25 over validated DocumentPackage snapshots."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from math import fsum, log1p
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.contracts import (
    ChunkIndexStatus,
    DocumentMetadata,
    DocumentPackage,
    FileProcessingStatus,
    IndexResult,
    IndexingStatus,
    ParsedChunk,
    ParsedFile,
    RetrievalRequest,
    RetrievalStatus,
    RetrievedChunk,
    WarningItem,
)

_HAN = r"\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U000323af"
_TOKEN_RUNS = re.compile(fr"(?P<han>[{_HAN}]+)|(?:(?![{_HAN}])[^\W_])+")
_K1 = 1.2
_B = 0.75
_TITLE_WEIGHT = 0.1
_INDEXABLE_FILE_STATUSES = {FileProcessingStatus.EXTRACTED, FileProcessingStatus.REVIEWED}


def _terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    terms = []
    for match in _TOKEN_RUNS.finditer(normalized):
        run = match.group()
        if match.lastgroup == "han" and len(run) > 1:
            terms.extend(run[i : i + 2] for i in range(len(run) - 1))
        else:
            terms.append(run)
    return terms


def _local_id(kind: str, *parts: str) -> UUID:
    return uuid5(NAMESPACE_URL, json.dumps(["codemind-fzu/alpha", kind, *parts]))


def _document_and_version_ids(record_code: str, version_no: str) -> tuple[UUID, UUID]:
    document_id = _local_id("document", record_code)
    return document_id, _local_id("version", str(document_id), version_no)


def _check_storage_key(key: str) -> None:
    if any(part in {"", ".", ".."} for part in key.split("/")) or any(
        char in key for char in ("\\", ":", "\x00")
    ):
        raise ValueError("storage_key 必须是根目录内使用 / 分隔的相对路径")


def _is_human_approved(metadata: DocumentMetadata) -> bool:
    return (
        isinstance(metadata.temporal_notes, dict)
        and metadata.temporal_notes.get("human_approved") is True
    )


def _normalize_substring(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).casefold())


def _metadata_sort_key(version: _IndexedVersion) -> tuple[int, int, str, str]:
    published_on = version.metadata.published_on
    if published_on is None:
        return (1, 0, version.metadata.record_code, version.metadata.version_no)
    return (0, -published_on.toordinal(), version.metadata.record_code, version.metadata.version_no)


@dataclass(frozen=True)
class _IndexedChunk:
    parsed: ParsedChunk
    file_id: UUID
    chunk_id: UUID
    term_counts: Counter[str]
    length: int


@dataclass(frozen=True)
class _IndexedVersion:
    metadata: DocumentMetadata
    document_id: UUID
    version_id: UUID
    chunks: tuple[_IndexedChunk, ...]
    title_term_counts: Counter[str]
    title_length: int


class LocalBM25Retriever:
    """Index trusted ingestion input and expose only enabled chunk snapshots.

    With file_root configured, check local file availability and declared digests
    before inserting a version. Construct a separate instance for each corpus.
    """

    _title_weight: float = _TITLE_WEIGHT

    def __init__(self, *, file_root: Path | None = None) -> None:
        self._file_root = file_root.resolve(strict=True) if file_root is not None else None
        if self._file_root is not None and not self._file_root.is_dir():
            raise ValueError("file_root 必须是目录")
        self._versions: dict[UUID, _IndexedVersion] = {}
        self._chunk_index: dict[UUID, tuple[UUID, _IndexedChunk]] = {}

    def _remove_version(self, version_id: UUID) -> None:
        removed = self._versions.pop(version_id, None)
        if removed is not None:
            for chunk in removed.chunks:
                self._chunk_index.pop(chunk.chunk_id, None)

    def _put_version(self, indexed: _IndexedVersion) -> None:
        self._remove_version(indexed.version_id)
        self._versions[indexed.version_id] = indexed
        for chunk in indexed.chunks:
            self._chunk_index[chunk.chunk_id] = (indexed.version_id, chunk)

    def get_document_metadata(self, version_id: UUID) -> DocumentMetadata | None:
        """Return a detached DocumentMetadata copy for an enabled indexed version.

        Intended for downstream evidence_check callers (e.g. reading
        applicability_raw, deadline_on, temporal_notes) without modifying the
        shared RetrievedChunk contract.
        """
        version = self._versions.get(version_id)
        if version is None or version.metadata.retrieval_status != RetrievalStatus.ENABLED:
            return None
        return version.metadata.model_copy(deep=True)

    def get_parsed_chunk(self, chunk_id: UUID) -> ParsedChunk | None:
        """Return a detached ParsedChunk copy for an enabled indexed chunk."""
        entry = self._chunk_index.get(chunk_id)
        if entry is None:
            return None
        version_id, chunk = entry
        version = self._versions.get(version_id)
        if version is None or version.metadata.retrieval_status != RetrievalStatus.ENABLED:
            return None
        return chunk.parsed.model_copy(deep=True)

    def list_document_metadata(
        self,
        subject: str | None = None,
        business_direction_code: str | None = None,
        category_name: str | None = None,
    ) -> list[DocumentMetadata]:
        """List detached metadata for enabled, human-approved indexed versions.

        Granularity & caller boundary:
        - Deduplication is at the ``version_id`` level (``(record_code, version_no)``),
          NOT the business historical-batch level. Multiple ``version_no`` under the
          same ``record_code``, or same-year splits across multiple packages (e.g.
          R3 + R4), are returned as separate entries; callers determining batch
          counts must aggregate by ``record_code`` / distinct period in business logic.
        - ``subject`` performs NFKC, case, and whitespace-normalized substring
          matching across the document title and indexed chunk contents without
          alias expansion. Callers that need exhaustive cross-year or alias checks
          should omit ``subject`` and enumerate by ``business_direction_code`` and
          ``category_name`` instead of relying on a single substring hit.
        - Ordering is deterministic: ``published_on`` descending (undated last),
          then ``record_code`` and ``version_no`` ascending.
        """
        needle: str | None = None
        if subject is not None:
            needle = _normalize_substring(subject)
            if not needle:
                return []

        matched: list[_IndexedVersion] = []
        for version in self._versions.values():
            metadata = version.metadata
            if metadata.retrieval_status != RetrievalStatus.ENABLED:
                continue
            if not _is_human_approved(metadata):
                continue
            if not version.chunks:
                continue
            if category_name is not None and category_name != metadata.category_name:
                continue
            if (
                business_direction_code is not None
                and business_direction_code not in metadata.business_direction_codes
            ):
                continue
            if needle is not None:
                title_hit = needle in _normalize_substring(metadata.title)
                if not title_hit and not any(
                    needle in _normalize_substring(chunk.parsed.content)
                    for chunk in version.chunks
                ):
                    continue
            matched.append(version)

        matched.sort(key=_metadata_sort_key)
        return [version.metadata.model_copy(deep=True) for version in matched]

    def list_parsed_chunks(
        self,
        version_id: UUID | None = None,
        *,
        record_code: str | None = None,
        version_no: str | None = None,
    ) -> list[ParsedChunk]:
        """List detached indexed ParsedChunk copies for an enabled, human-approved version.

        Callers may identify the version either by ``version_id`` (e.g. from a
        ``RetrievedChunk``) or by ``record_code`` + ``version_no`` (e.g. from a
        ``DocumentMetadata`` returned by ``list_document_metadata``).
        """
        if version_id is not None:
            if record_code is not None or version_no is not None:
                raise ValueError("version_id 与 record_code/version_no 不能同时传入")
            target_version_id = version_id
        else:
            if (
                not isinstance(record_code, str)
                or not record_code.strip()
                or not isinstance(version_no, str)
                or not version_no.strip()
            ):
                raise ValueError("必须提供 version_id，或同时提供非空的 record_code 和 version_no")
            _, target_version_id = _document_and_version_ids(
                record_code.strip(), version_no.strip()
            )

        version = self._versions.get(target_version_id)
        if (
            version is None
            or version.metadata.retrieval_status != RetrievalStatus.ENABLED
            or not _is_human_approved(version.metadata)
        ):
            return []
        ordered = sorted(
            version.chunks,
            key=lambda item: (item.parsed.source_file_key, item.parsed.chunk_no),
        )
        return [chunk.parsed.model_copy(deep=True) for chunk in ordered]

    def _file_warnings(self, files: Iterable[ParsedFile]) -> list[WarningItem]:
        root = self._file_root
        if root is None:
            return []

        warnings = []
        for file in files:
            try:
                path = (root / file.storage_key).resolve(strict=True)
                if not path.is_relative_to(root) or not path.is_file():
                    raise OSError("not a file within the configured root")
                with path.open("rb") as stream:
                    if file.sha256 is None:
                        continue
                    digest = hashlib.sha256()
                    for block in iter(lambda: stream.read(128 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest() != file.sha256:
                    warnings.append(WarningItem(
                        code="FILE_HASH_MISMATCH",
                        message=f"文件 SHA-256 不符：{file.storage_key[:880]}",
                    ))
            except (OSError, RuntimeError):
                warnings.append(WarningItem(
                    code="FILE_UNAVAILABLE",
                    message=f"文件不可读或不在资料根目录内：{file.storage_key[:880]}",
                ))
        return warnings

    def _withdraw_if_requested(self, metadata: object) -> None:
        if not isinstance(metadata, dict) or metadata.get("retrieval_status") not in (
            RetrievalStatus.BLOCKED, RetrievalStatus.REVIEW_ONLY,
        ):
            return
        record_code = metadata.get("record_code")
        version_no = metadata.get("version_no")
        if not isinstance(record_code, str) or not isinstance(version_no, str):
            return
        # A withdrawal from trusted ingestion must take effect even if the rest
        # of the package is malformed. The version still cannot be re-indexed
        # until the complete package passes validation.
        _, version_id = _document_and_version_ids(record_code.strip(), version_no.strip())
        self._remove_version(version_id)

    async def index_document(self, package: DocumentPackage) -> IndexResult:
        # Revalidate nested DTOs and detach from caller-owned mutable models.
        payload = package.model_dump()
        self._withdraw_if_requested(payload.get("metadata"))
        snapshot = DocumentPackage.model_validate(payload)
        metadata = snapshot.metadata
        document_id, version_id = _document_and_version_ids(metadata.record_code, metadata.version_no)
        source_files = {}
        for file in snapshot.files:
            _check_storage_key(file.storage_key)
            source_files[file.storage_key] = (
                _local_id("file", str(version_id), file.storage_key), file.processing_status
            )

        seen = set()
        for chunk in snapshot.chunks:
            key = (chunk.source_file_key, chunk.chunk_no)
            if key in seen:
                raise ValueError("同一来源文件内的 chunk_no 不得重复")
            seen.add(key)

        result_ids = {
            "document_id": document_id,
            "version_id": version_id,
            "chunk_count": len(snapshot.chunks),
        }
        entries = []
        referenced_files: set[str] = set()
        skipped_sources: Counter[str] = Counter()
        skipped_disabled = False
        skipped_tokenless = 0
        title_terms = _terms(metadata.title)
        for chunk in snapshot.chunks:
            file_id, processing_status = source_files[chunk.source_file_key]
            if processing_status not in _INDEXABLE_FILE_STATUSES:
                skipped_sources[chunk.source_file_key] += 1
                continue
            if chunk.index_status == ChunkIndexStatus.DISABLED:
                skipped_disabled = True
                continue
            content_terms = _terms(chunk.content)
            if not content_terms:
                skipped_tokenless += 1
                continue
            referenced_files.add(chunk.source_file_key)
            if chunk.original_file_key:
                referenced_files.add(chunk.original_file_key)
            entries.append(_IndexedChunk(
                parsed=chunk,
                file_id=file_id,
                chunk_id=_local_id("chunk", str(file_id), str(chunk.chunk_no)),
                term_counts=Counter(content_terms),
                length=len(content_terms),
            ))

        # Only unready sources with no retained citation can skip integrity
        # checks. A retained chunk may still cite one as its original file.
        ignored_files = skipped_sources.keys() - referenced_files
        integrity_warnings = self._file_warnings(
            file for file in snapshot.files if file.storage_key not in ignored_files
        )
        warnings = list(integrity_warnings)
        if skipped_disabled:
            warnings.append(WarningItem(
                code="DISABLED_CHUNKS_SKIPPED", message="禁用片段未加入索引。"
            ))
        if skipped_tokenless:
            warnings.append(WarningItem(
                code="TOKENLESS_CHUNKS_SKIPPED",
                message=f"跳过 {skipped_tokenless} 个片段，原因是没有可检索词。",
            ))
        for storage_key, count in skipped_sources.items():
            _, processing_status = source_files[storage_key]
            warnings.append(WarningItem(
                code="SOURCE_FILE_NOT_READY",
                message=(
                    f"来源文件 processing_status={processing_status.value}，"
                    f"跳过 {count} 个片段：{storage_key[:880]}"
                ),
            ))
        if integrity_warnings:
            # A failed integrity check on the replacement invalidates the old
            # snapshot as well.
            self._remove_version(version_id)
            return IndexResult(
                **result_ids, status=IndexingStatus.FAILED, indexed_count=0, warnings=warnings
            )
        status = IndexingStatus.PARTIAL if warnings else IndexingStatus.INDEXED
        self._put_version(_IndexedVersion(
            metadata,
            document_id,
            version_id,
            tuple(entries),
            Counter(title_terms),
            len(title_terms),
        ))
        return IndexResult(
            **result_ids, status=status, indexed_count=len(entries), warnings=warnings
        )

    async def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        request = RetrievalRequest.model_validate(request.model_dump())
        query_terms = sorted(set(_terms(request.query)))
        if not query_terms:
            return []

        eligible_versions = []
        candidates = []
        for version in self._versions.values():
            metadata = version.metadata
            if metadata.retrieval_status != RetrievalStatus.ENABLED:
                continue
            if request.category_name is not None and request.category_name != metadata.category_name:
                continue
            if (
                request.business_direction_code is not None
                and request.business_direction_code not in metadata.business_direction_codes
            ):
                continue
            if version.chunks:
                eligible_versions.append(version)
                candidates.extend((version, chunk) for chunk in version.chunks)
        if not candidates:
            return []

        # Only eligible chunks contribute to content corpus statistics.
        count = len(candidates)
        average_length = sum(chunk.length for _, chunk in candidates) / count
        idf = {}
        for term in query_terms:
            frequency = sum(term in chunk.term_counts for _, chunk in candidates)
            if frequency:
                idf[term] = log1p((count - frequency + 0.5) / (frequency + 0.5))

        # Compute lightweight document-level title BM25 separately so a long
        # matching title cannot crowd out relevant chunks from other documents.
        title_scores: dict[UUID, float] = {}
        if self._title_weight > 0:
            titled_versions = [v for v in eligible_versions if v.title_length > 0]
            if titled_versions:
                v_count = len(titled_versions)
                avg_title_len = sum(v.title_length for v in titled_versions) / v_count
                title_idf = {}
                for term in query_terms:
                    freq = sum(term in v.title_term_counts for v in titled_versions)
                    if freq:
                        title_idf[term] = log1p((v_count - freq + 0.5) / (freq + 0.5))
                for version in titled_versions:
                    t_norm = _K1 * (1 - _B + _B * version.title_length / avg_title_len)
                    t_score = fsum(
                        weight * (_K1 + 1) * version.title_term_counts[term]
                        / (version.title_term_counts[term] + t_norm)
                        for term, weight in title_idf.items()
                        if term in version.title_term_counts
                    )
                    if t_score > 0:
                        title_scores[version.version_id] = t_score

        ranked = []
        for version, chunk in candidates:
            normalizer = _K1 * (1 - _B + _B * chunk.length / average_length)
            content_score = fsum(
                weight * (_K1 + 1) * chunk.term_counts[term]
                / (chunk.term_counts[term] + normalizer)
                for term, weight in idf.items()
                if term in chunk.term_counts
            )
            title_score = title_scores.get(version.version_id, 0.0)
            score = content_score + self._title_weight * title_score
            if score > 0:
                ranked.append((score, version, chunk))
        ranked.sort(key=lambda hit: (-hit[0], hit[2].chunk_id))

        hits = []
        for score, version, chunk in ranked[:request.top_k]:
            metadata = version.metadata
            hits.append(RetrievedChunk(
                chunk_id=chunk.chunk_id,
                document_id=version.document_id,
                version_id=version.version_id,
                file_id=chunk.file_id,
                content=chunk.parsed.content,
                title=metadata.title,
                publisher=metadata.publisher,
                source_url=metadata.source_url,
                published_on=metadata.published_on,
                effective_on=metadata.effective_on,
                locator=chunk.parsed.locator,
                original_locator=chunk.parsed.original_locator,
                score=score,
                retrieval_method="bm25",
                source_verification_status=metadata.source_verification_status,
                timeliness_verification_status=metadata.timeliness_verification_status,
                retrieval_status=metadata.retrieval_status,
            ))
        return hits
