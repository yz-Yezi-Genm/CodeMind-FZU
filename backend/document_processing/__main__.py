"""Single-file CLI, using the existing DocumentMetadata JSON contract."""
import argparse
from pathlib import Path
import sys

from pydantic import ValidationError

from backend.contracts.models import DocumentMetadata
from .parser import DocumentProcessingError, TextDocumentParser


def main() -> int:
    parser = argparse.ArgumentParser(description="解析 Markdown/TXT，输出 blocked 的 DocumentPackage JSON")
    parser.add_argument("file_path", type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--storage-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-chunk-chars", type=int, default=1200)
    parser.add_argument("--encoding", default="utf-8-sig")
    args = parser.parse_args()
    try:
        metadata = DocumentMetadata.model_validate_json(args.metadata.read_text(encoding="utf-8-sig"))
        package = TextDocumentParser(
            args.storage_root, max_chunk_chars=args.max_chunk_chars, encoding=args.encoding,
        ).parse_document(args.file_path, metadata)
        # Do not overwrite an input file when a caller mistakes --output for a directory.
        source = args.file_path if args.file_path.is_absolute() else args.storage_root / args.file_path
        if args.output.resolve() in {source.resolve(), args.metadata.resolve()}:
            parser.error("输出文件不能覆盖正文或元数据输入文件")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(package.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"chunks={len(package.chunks)} retrieval_status={package.metadata.retrieval_status.value}")
        return 0
    except DocumentProcessingError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
    except (OSError, ValidationError, ValueError):
        print("DOCUMENT_PROCESSING_FAILED: 请检查输入元数据、文件权限及解析参数。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
