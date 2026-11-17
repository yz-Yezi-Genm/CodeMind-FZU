"""Markdown/TXT implementation of contracts.protocols.DocumentParser.

No network, LLM, database or index writes. Parsing never grants retrieval access.
Offsets refer to decoded text with BOM removed and newlines normalized to LF.
"""
from __future__ import annotations

from bisect import bisect_right
from hashlib import sha256
import json
import mimetypes
from pathlib import Path
import re
from typing import Iterator

from backend.contracts.models import (
    ChunkIndexStatus,
    DocumentMetadata,
    DocumentPackage,
    ExtractionStatus,
    FileProcessingStatus,
    FileRole,
    ParsedChunk,
    ParsedFile,
    RetrievalStatus,
)

_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")


class DocumentProcessingError(ValueError):
    """Local parser error, to be translated by the caller's API error handler."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class TextDocumentParser:
    """Structural implementation of DocumentParser, without changing the Protocol.

    Relative file paths resolve against storage_root. The output contains relative
    POSIX storage keys only. The caller supplies trusted, reviewed-as-appropriate
    metadata; a file's YAML header cannot override it or enable retrieval.
    """

    def __init__(
        self,
        storage_root: Path,
        *,
        max_chunk_chars: int = 1200,
        encoding: str = "utf-8-sig",
        max_file_bytes: int = 10 * 1024 * 1024,
    ):
        self.storage_root = Path(storage_root).resolve(strict=True)
        if not self.storage_root.is_dir():
            raise ValueError("storage_root 必须为目录")
        if max_chunk_chars < 1 or max_file_bytes < 1:
            raise ValueError("片段长度和文件大小限制必须为正整数")
        self.max_chunk_chars = max_chunk_chars
        self.encoding = encoding
        self.max_file_bytes = max_file_bytes

    def parse_document(
        self, file_path: Path, metadata: DocumentMetadata,
    ) -> DocumentPackage:
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = self.storage_root / candidate
        path = candidate.resolve()
        try:
            storage_key = path.relative_to(self.storage_root).as_posix()
        except ValueError:
            raise DocumentProcessingError("OUTSIDE_STORAGE_ROOT", "文件必须位于配置的资料根目录内") from None
        if not path.is_file():
            raise DocumentProcessingError("DOCUMENT_NOT_FOUND", "待解析文件不存在或不是普通文件")
        try:
            # Bound both allocation and hashing, including files growing after stat().
            with path.open("rb") as stream:
                raw = stream.read(self.max_file_bytes + 1)
        except OSError:
            raise DocumentProcessingError("FILE_READ_FAILED", "无法读取待解析文件") from None
        if len(raw) > self.max_file_bytes:
            raise DocumentProcessingError("FILE_TOO_LARGE", "文件超过本次解析的大小限制")

        suffix = path.suffix.lower()
        supported = suffix in {".md", ".markdown", ".txt"}
        file = ParsedFile(
            file_role=(FileRole.CURATED if suffix in {".md", ".markdown"}
                       else FileRole.EXTRACTED if suffix == ".txt" else FileRole.ORIGINAL),
            storage_key=storage_key,
            original_name=path.name,
            media_type={".md": "text/markdown", ".markdown": "text/markdown", ".txt": "text/plain"}.get(
                suffix, mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            ),
            sha256=sha256(raw).hexdigest(),
            source_url=metadata.source_url,
        )

        # An OCR marker is a workflow gate, even if a text placeholder was supplied.
        needs_ocr = metadata.extraction_status == ExtractionStatus.NEEDS_OCR
        if not supported or needs_ocr:
            status = ExtractionStatus.NEEDS_OCR if needs_ocr else ExtractionStatus.PENDING
            note = ("该资料标记为待 OCR；本次仅登记文件，不生成正文或片段。" if needs_ocr
                    else "本周仅支持 Markdown/TXT；该格式待可靠解析，扫描件需 OCR 后人工复核。")
            file.processing_status = (FileProcessingStatus.NEEDS_OCR if needs_ocr
                                      else FileProcessingStatus.SAVED)
            return DocumentPackage(metadata=self._metadata(metadata, status, note), files=[file], chunks=[])

        try:
            text = raw.decode(self.encoding).removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        except (UnicodeError, LookupError):
            raise DocumentProcessingError("TEXT_DECODE_FAILED", "正文解码失败；请核对编码，不能忽略乱码继续解析") from None
        if any(ord(char) < 32 and char not in "\n\t\f" for char in text):
            raise DocumentProcessingError("BINARY_TEXT", "文本包含二进制控制字符，需人工检查文件格式或编码")

        markdown = suffix != ".txt"
        start = self._body_start(text) if markdown else 0
        line_starts = [0] + [i + 1 for i, char in enumerate(text) if char == "\n"]
        chunks: list[ParsedChunk] = []
        for section_start, section_end, heading_path in self._sections(text, start, markdown):
            for a, b in self._split(text, section_start, section_end):
                line_start, line_end = bisect_right(line_starts, a), bisect_right(line_starts, b - 1)
                headings = [{"level": level, "title": title} for level, title in heading_path]
                title_path = " > ".join(title for _, title in heading_path)
                chunks.append(ParsedChunk(
                    chunk_no=len(chunks) + 1,
                    content=text[a:b],
                    locator=f"L{line_start}-L{line_end}" + (f" | {title_path}" if title_path else ""),
                    locator_note=json.dumps({
                        "coordinate_system": "decoded_text_lf_bom_removed",
                        "line_start": line_start, "line_end": line_end,
                        "char_start": a, "char_end": b,
                        "heading_path": headings,
                        "note": "本输入文件定位；不是官方原件页码。字符区间左闭右开，行号从1开始。",
                    }, ensure_ascii=False),
                    source_file_key=storage_key,
                    original_file_key=None,
                    original_locator=None,
                    index_status=ChunkIndexStatus.PENDING,
                ))
        if not chunks:
            raise DocumentProcessingError("EMPTY_DOCUMENT", "文档正文为空，未生成解析包")
        file.processing_status = FileProcessingStatus.EXTRACTED
        return DocumentPackage(
            metadata=self._metadata(metadata, ExtractionStatus.EXTRACTED),
            files=[file], chunks=chunks,
        )

    @staticmethod
    def _metadata(
        metadata: DocumentMetadata, extraction_status: ExtractionStatus, note: str | None = None,
    ) -> DocumentMetadata:
        data = metadata.model_dump()
        data.update(extraction_status=extraction_status, retrieval_status=RetrievalStatus.BLOCKED)
        if note and note not in (data.get("verification_note") or ""):
            data["verification_note"] = "\n".join(filter(None, [data.get("verification_note"), note]))
        # Revalidate rather than model_copy(update=...), which skips validation.
        return DocumentMetadata.model_validate(data)

    @staticmethod
    def _body_start(text: str) -> int:
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].strip() != "---":
            return 0
        offset = len(lines[0])
        for line in lines[1:]:
            offset += len(line)
            if line.strip() in {"---", "..."}:
                return offset
        raise DocumentProcessingError("INVALID_FRONT_MATTER", "Markdown 元数据头未闭合；请修正后重新解析")

    @staticmethod
    def _sections(text: str, start: int, markdown: bool) -> Iterator[tuple[int, int, tuple]]:
        if not markdown:
            yield start, len(text), ()
            return
        lines = text[start:].splitlines(keepends=True)
        offsets, offset = [], start
        for line in lines:
            offsets.append(offset)
            offset += len(line)
        headings = []
        fence_char, fence_size = "", 0
        for i, line in enumerate(lines):
            value = line.rstrip("\n")
            fence = _FENCE.match(value)
            if fence:
                marker, rest = fence.groups()
                if not fence_char:
                    fence_char, fence_size = marker[0], len(marker)
                elif marker[0] == fence_char and len(marker) >= fence_size and not rest.strip():
                    fence_char, fence_size = "", 0
                continue
            if fence_char:
                continue
            match = _HEADING.match(value)
            if match:
                title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2) or "").strip()
                if title:
                    headings.append((offsets[i], len(match.group(1)), title))
            elif i and _SETEXT.match(value):
                previous = lines[i-1].strip()
                if previous and not re.match(r"[#>|*`~\-]", previous):
                    headings.append((offsets[i-1], 1 if value.lstrip().startswith("=") else 2, previous))
        stack = []
        previous_start = start
        for position, level, title in headings:
            if position > previous_start:
                yield previous_start, position, tuple(stack)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            previous_start = position
        yield previous_start, len(text), tuple(stack)

    def _split(self, text: str, start: int, end: int) -> Iterator[tuple[int, int]]:
        while start < end:
            while start < end and text[start].isspace():
                start += 1
            if start == end:
                return
            limit = min(start + self.max_chunk_chars, end)
            cut = limit
            if limit < end:
                # Prefer paragraphs, then lines, then sentences; otherwise hard-cut.
                half = start + self.max_chunk_chars // 2
                for separator in ("\n\n", "\n", "。", "！", "？", ". ", "; ", "；", " "):
                    pos = text.rfind(separator, half, limit)
                    if pos >= half:
                        cut = pos + len(separator)
                        break
            trimmed_end = cut
            while trimmed_end > start and text[trimmed_end-1].isspace():
                trimmed_end -= 1
            if trimmed_end > start:
                yield start, trimmed_end
            start = cut
