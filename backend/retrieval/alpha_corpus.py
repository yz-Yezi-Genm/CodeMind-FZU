"""Unified loader for human-approved Alpha policy packages."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from backend.contracts import (
    DocumentPackage,
    IndexResult,
    IndexingStatus,
    RetrievalStatus,
)
from .local import LocalBM25Retriever

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_APPROVED_DIR = PROJECT_ROOT / "knowledge_base" / "processed" / "alpha" / "approved"


@dataclass(frozen=True)
class AlphaCorpusLoadReport:
    """Observable summary of loading approved Alpha DocumentPackages."""

    corpus_dir: Path
    loaded_packages: tuple[str, ...]
    skipped_packages: tuple[tuple[str, str], ...]
    index_results: tuple[IndexResult, ...]

    @property
    def total_indexed_chunks(self) -> int:
        return sum(result.indexed_count for result in self.index_results)


def _resolve_within(root: Path, rel_path: str) -> Path:
    if (
        not isinstance(rel_path, str)
        or not rel_path
        or any(part in {"", ".", ".."} for part in rel_path.split("/"))
        or any(char in rel_path for char in ("\\", ":", "\x00"))
    ):
        raise ValueError(f"非法相对路径：{rel_path!r}")
    resolved = (root / rel_path).resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"路径超出允许目录或不是文件：{rel_path}")
    return resolved


def _display_path(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            pass
    return path.name


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction and isjunction(path))


def _check_corpus_dir_security(corpus_dir: Path, *, resolved_root: Path | None) -> None:
    """Reject symlinks/junctions on corpus_dir or its path components under file_root."""
    raw_dir = Path(os.path.abspath(corpus_dir))
    if _is_link(corpus_dir) or _is_link(raw_dir):
        raise ValueError(f"approved 资料目录不能是符号链接：{corpus_dir}")

    if resolved_root is not None:
        raw_root = Path(os.path.abspath(resolved_root))
        try:
            rel_parts = raw_dir.relative_to(raw_root).parts
        except ValueError:
            rel_parts = ()
        current = raw_root
        for part in rel_parts:
            current = current / part
            if _is_link(current):
                raise ValueError(f"approved 资料目录路径包含符号链接：{current}")


def _discover_entries(
    corpus_dir: Path,
    *,
    file_root: Path | None,
    allow_missing: bool = True,
) -> tuple[Path, list[tuple[str, Path]], list[tuple[str, str]]]:
    """Discover candidate JSON packages under corpus_dir.

    Supports either a manifest.json (same layout as pending-review/manifest.json)
    or direct *.json DocumentPackage files inside corpus_dir.
    """
    resolved_root = file_root.resolve(strict=True) if file_root is not None else None
    _check_corpus_dir_security(corpus_dir, resolved_root=resolved_root)

    if not corpus_dir.exists():
        if allow_missing:
            return corpus_dir.resolve(strict=False), [], []
        raise FileNotFoundError(f"approved 资料目录不存在：{corpus_dir}")
    resolved_corpus = corpus_dir.resolve(strict=True)
    if not resolved_corpus.is_dir():
        raise ValueError(f"approved 资料目录无效：{corpus_dir}")
    if resolved_root is not None and not resolved_corpus.is_relative_to(resolved_root):
        raise ValueError(f"approved 资料目录超出允许根目录：{corpus_dir}")

    manifest_path = resolved_corpus / "manifest.json"
    candidates: list[tuple[str, Path]] = []
    skipped: list[tuple[str, str]] = []

    if manifest_path.is_file():
        if _is_link(manifest_path):
            raise ValueError("manifest.json 不能是符号链接")
        resolved_manifest = manifest_path.resolve(strict=True)
        if not resolved_manifest.is_relative_to(resolved_corpus):
            raise ValueError("manifest.json 必须位于 approved 目录内")
        manifest: dict[str, Any] = json.loads(resolved_manifest.read_bytes())
        entries = manifest.get("packages")
        if not isinstance(entries, list):
            raise ValueError("manifest.json 缺少有效的 packages 列表")
        base_root = resolved_root if resolved_root is not None else resolved_corpus
        seen_paths: set[Path] = set()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("package"), str):
                raise ValueError("manifest.json 中存在格式错误的 package 条目")
            raw_key = entry["package"]
            if entry.get("human_approved") is not True:
                skipped.append((raw_key, "manifest 未标记 human_approved=true，跳过加载"))
                continue
            resolved_pkg = _resolve_within(base_root, raw_key)
            if not resolved_pkg.is_relative_to(resolved_corpus):
                raise ValueError(f"approved manifest 不允许引用目录外资料包：{raw_key}")
            if resolved_pkg in seen_paths:
                raise ValueError(f"manifest.json 中存在重复资料包：{raw_key}")
            seen_paths.add(resolved_pkg)
            candidates.append((raw_key, resolved_pkg))
        return resolved_corpus, candidates, skipped

    for path in sorted(resolved_corpus.glob("*.json")):
        if path.name in {"manifest.json", "summary.json"} or path.name.endswith(".metadata.json"):
            continue
        if _is_link(path):
            raise ValueError(f"approved 目录不允许包含符号链接资料包：{path.name}")
        resolved_pkg = path.resolve(strict=True)
        if not resolved_pkg.is_relative_to(resolved_corpus) or not resolved_pkg.is_file():
            raise ValueError(f"approved 目录不允许引用目录外资料包：{path.name}")
        candidates.append((_display_path(resolved_pkg, resolved_root), resolved_pkg))
    return resolved_corpus, candidates, skipped


async def load_approved_alpha_retriever(
    *,
    corpus_dir: Path = DEFAULT_APPROVED_DIR,
    file_root: Path | None = PROJECT_ROOT,
    allow_missing: bool = True,
) -> tuple[LocalBM25Retriever, AlphaCorpusLoadReport]:
    """Load human-approved enabled DocumentPackages into a LocalBM25Retriever.

    Only packages with ``retrieval_status=enabled`` and explicit boolean
    ``temporal_notes["human_approved"] is True`` (plus ``human_approved=True``
    in ``manifest.json`` when a manifest is present) are indexed into the
    returned retriever. Missing or non-True approval flags are always skipped.

    Return semantics for formal runtime assembly:
    - When ``allow_missing=True`` (default) and ``corpus_dir`` does not exist, an
      empty retriever and an empty report are returned rather than raising. Because
      a missing directory and an existing empty directory both yield empty
      ``index_results``, no ``IndexResult.warnings``, and ``total_indexed_chunks == 0``,
      formal backend assembly cannot rely on those fields alone to verify corpus
      health; pass ``allow_missing=False`` or explicitly check
      ``report.corpus_dir.is_dir()``.
    - ``report.loaded_packages`` records every package whose indexing result is not
      ``IndexingStatus.FAILED`` — including ``IndexingStatus.PARTIAL`` packages
      (for example when unready/``needs_ocr`` source files leave ``indexed_count == 0``).
      Unready chunks are never exposed to retrieval, so ``loaded_packages`` alone does
      not imply a package is fully ready for formal QA.
    - Formal backend/Agent assembly should inspect ``report.corpus_dir.is_dir()``
      (or pass ``allow_missing=False``), ``report.index_results`` (requiring
      ``IndexingStatus.INDEXED`` under conservative Alpha policy and checking each
      ``IndexResult.warnings``), and ``report.total_indexed_chunks`` to distinguish
      a missing/unready corpus from a normal zero-hit query.
    """
    resolved_root = file_root.resolve(strict=True) if file_root is not None else None
    retriever = LocalBM25Retriever(file_root=resolved_root)
    resolved_corpus, candidates, skipped = _discover_entries(
        corpus_dir, file_root=resolved_root, allow_missing=allow_missing
    )

    loaded: list[str] = []
    results: list[IndexResult] = []
    seen_versions: set[tuple[str, str]] = set()
    for label, path in candidates:
        package = DocumentPackage.model_validate_json(path.read_bytes())
        metadata = package.metadata
        version_key = (metadata.record_code, metadata.version_no)
        if version_key in seen_versions:
            raise ValueError(
                f"approved 目录存在重复文档版本：{metadata.record_code} ({metadata.version_no})"
            )
        seen_versions.add(version_key)
        if metadata.retrieval_status != RetrievalStatus.ENABLED:
            skipped.append((
                label,
                f"retrieval_status={metadata.retrieval_status.value}，仅允许加载 enabled 资料",
            ))
            continue
        if not (
            isinstance(metadata.temporal_notes, dict)
            and metadata.temporal_notes.get("human_approved") is True
        ):
            skipped.append((label, "temporal_notes 未标记 human_approved=true，未通过人工审核"))
            continue

        result = await retriever.index_document(package)
        results.append(result)
        if result.status == IndexingStatus.FAILED:
            reason = "; ".join(w.message for w in result.warnings) or "索引失败"
            skipped.append((label, f"索引失败：{reason}"))
            continue
        loaded.append(label)

    report = AlphaCorpusLoadReport(
        corpus_dir=resolved_corpus,
        loaded_packages=tuple(loaded),
        skipped_packages=tuple(skipped),
        index_results=tuple(results),
    )
    return retriever, report


async def build_approved_alpha_retriever(
    *,
    corpus_dir: Path = DEFAULT_APPROVED_DIR,
    file_root: Path | None = PROJECT_ROOT,
    allow_missing: bool = True,
) -> LocalBM25Retriever:
    """Convenience entry point returning a Retriever without the load report.

    Because this wrapper discards ``AlphaCorpusLoadReport``, formal backend assembly
    should prefer ``load_approved_alpha_retriever()`` so it can verify
    ``index_results``, ``warnings``, and ``total_indexed_chunks``.
    """
    retriever, _ = await load_approved_alpha_retriever(
        corpus_dir=corpus_dir,
        file_root=file_root,
        allow_missing=allow_missing,
    )
    return retriever
