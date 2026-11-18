"""In-memory BM25 over validated DocumentPackage snapshots."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from math import fsum, log1p
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.contracts import (
    ChunkIndexStatus,
    DocumentMetadata,
    DocumentPackage,
    IndexResult,
    IndexingStatus,
    ParsedChunk,
    RetrievalRequest,
    RetrievalStatus,
    RetrievedChunk,
    WarningItem,
)

_HAN = r"\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U000323af"
_TOKEN_RUNS = re.compile(fr"(?P<han>[{_HAN}]+)|(?:(?![{_HAN}])[^\W_])+")
_K1 = 1.2
_B = 0.75


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


def _check_storage_key(key: str) -> None:
    if any(part in {"", ".", ".."} for part in key.split("/")) or any(
        char in key for char in ("\\", ":", "\x00")
    ):
        raise ValueError("storage_key 必须是根目录内使用 / 分隔的相对路径")


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


class LocalBM25Retriever:
    """Index trusted ingestion input and expose only enabled chunk snapshots.

    With file_root configured, check local file availability and declared digests
    before inserting a version. Construct a separate instance for each corpus.
    """

    def __init__(self, *, file_root: Path | None = None) -> None:
        self._file_root = file_root.resolve(strict=True) if file_root is not None else None
        if self._file_root is not None and not self._file_root.is_dir():
            raise ValueError("file_root 必须是目录")
        self._versions: dict[UUID, _IndexedVersion] = {}

    def _file_warnings(self, package: DocumentPackage) -> list[WarningItem]:
        root = self._file_root
        if root is None:
            return []

        warnings = []
        for file in package.files:
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

    async def index_document(self, package: DocumentPackage) -> IndexResult:
        # Revalidate nested DTOs and detach from caller-owned mutable models.
        snapshot = DocumentPackage.model_validate(package.model_dump())
        metadata = snapshot.metadata
        document_id = _local_id("document", metadata.record_code)
        version_id = _local_id("version", str(document_id), metadata.version_no)
        file_ids = {}
        for file in snapshot.files:
            _check_storage_key(file.storage_key)
            file_ids[file.storage_key] = _local_id("file", str(version_id), file.storage_key)

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
        warnings = self._file_warnings(snapshot)
        if warnings:
            # A formerly indexed version must not serve stale evidence after a
            # failed integrity check on its replacement.
            self._versions.pop(version_id, None)
            return IndexResult(
                **result_ids, status=IndexingStatus.FAILED, indexed_count=0, warnings=warnings
            )

        entries = []
        for chunk in snapshot.chunks:
            if chunk.index_status == ChunkIndexStatus.DISABLED:
                continue
            file_id = file_ids[chunk.source_file_key]
            terms = _terms(chunk.content)
            entries.append(_IndexedChunk(
                parsed=chunk,
                file_id=file_id,
                chunk_id=_local_id("chunk", str(file_id), str(chunk.chunk_no)),
                term_counts=Counter(terms),
                length=len(terms),
            ))

        status = IndexingStatus.INDEXED
        if len(entries) != len(snapshot.chunks):
            status = IndexingStatus.PARTIAL
            warnings.append(WarningItem(
                code="DISABLED_CHUNKS_SKIPPED", message="禁用片段未加入索引。"
            ))
        self._versions[version_id] = _IndexedVersion(
            metadata, document_id, version_id, tuple(entries)
        )
        return IndexResult(
            **result_ids, status=status, indexed_count=len(entries), warnings=warnings
        )

    async def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        request = RetrievalRequest.model_validate(request.model_dump())
        query_terms = sorted(set(_terms(request.query)))
        if not query_terms:
            return []

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
            candidates.extend((version, chunk) for chunk in version.chunks if chunk.length)
        if not candidates:
            return []

        # Only eligible chunks contribute to corpus statistics.
        count = len(candidates)
        average_length = sum(chunk.length for _, chunk in candidates) / count
        idf = {}
        for term in query_terms:
            frequency = sum(term in chunk.term_counts for _, chunk in candidates)
            if frequency:
                idf[term] = log1p((count - frequency + 0.5) / (frequency + 0.5))

        ranked = []
        for version, chunk in candidates:
            normalizer = _K1 * (1 - _B + _B * chunk.length / average_length)
            score = fsum(
                weight * (_K1 + 1) * chunk.term_counts[term]
                / (chunk.term_counts[term] + normalizer)
                for term, weight in idf.items()
                if term in chunk.term_counts
            )
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
