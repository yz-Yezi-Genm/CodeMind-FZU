"""Reproduce Alpha sample packages from existing repository materials, offline.

Run from the repository root: python -m scripts.parse_alpha_documents
This writes JSON examples and a comparison report, never a database or index.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import mimetypes
from pathlib import Path

from backend.contracts.models import DocumentMetadata, DocumentPackage, ParsedFile
from backend.document_processing import TextDocumentParser

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("knowledge_base/processing/alpha-manifest.json")
OUTPUT = Path("knowledge_base/processed/alpha")
REPORT = Path("docs/assignment-03/alpha/document-processing-comparison.md")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_samples(root: Path = ROOT) -> list[DocumentPackage]:
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    preview_path = root / manifest["preview_path"]
    preview = json.loads(preview_path.read_text(encoding="utf-8-sig"))
    docs = {x["id"]: x for x in preview["knowledge_documents"]}
    versions = {x["record_code"]: x for x in preview["document_versions"]}
    categories = {x["id"]: x["name"] for x in preview["knowledge_categories"]}
    directions = {x["id"]: x["code"] for x in preview["business_directions"]}
    packages, summaries = [], []
    report = [
        "# Alpha 文档解析前后对比", "",
        "本文件由 `python -m scripts.parse_alpha_documents` 离线生成。输入是已有正文提取稿；"
        "输出是公共 `DocumentPackage`。未执行官网核验、数据库写入、索引或正式检索开放。", "",
        "字符统计和行号均基于 UTF-8 解码、移除 BOM、统一 LF 换行后的文本；哈希针对原始文件字节。", "",
        "| 场景 | 输入字符数（含元数据头） | 切片字符数（去边缘空白） | 片段数 | 解析后状态 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    details = []
    for sample in manifest["samples"]:
        version = versions[sample["record_code"]]
        document = docs[version["document_id"]]
        # Select only declared contract fields. Do not copy database IDs into DTOs.
        data = {key: value for key, value in version.items() if key in DocumentMetadata.model_fields}
        data.update(
            title=document["title"], document_type=document["document_type"],
            category_name=categories[document["category_id"]],
            business_direction_codes=[directions[x["direction_id"]] for x in preview["document_business_directions"]
                                      if x["document_id"] == document["id"]],
            retrieval_status="blocked",
        )
        # An imported archive label is not a present-day timeliness conclusion.
        # Keep its original value in import_snapshot and leave the preview intact.
        if data.get("timeliness_verification_status") == "pending" and data.get("policy_status") == "当前有效":
            data["policy_status"] = "时效待核验（原归档标签：当前有效）"
        notes = [version.get("verification_note"), version.get("legacy_verification_text"), sample["limitation"]]
        data["verification_note"] = "\n".join(x for x in notes if x)
        metadata = DocumentMetadata.model_validate(data)
        input_path = root / sample["file_path"]
        original_bytes = input_path.read_bytes()
        registered = {row["storage_key"]: row for row in preview["document_files"]
                      if row["version_id"] == version["id"]}
        # Supply the business role before parsing; do not patch the result later.
        parser = TextDocumentParser(
            root, max_chunk_chars=manifest["max_chunk_chars"],
            file_role=registered[sample["file_path"]]["file_role"],
        )
        package = parser.parse_document(input_path, metadata)
        files = list(package.files)
        missing_keys = []
        for row in preview["document_files"]:
            if row["version_id"] != version["id"] or row["storage_key"] == sample["file_path"]:
                continue
            key = row["storage_key"]
            candidate = (root / key).resolve()
            if not candidate.is_relative_to(root.resolve()):
                raise ValueError("离线预览包含越界文件键")
            if not candidate.is_file():
                missing_keys.append(key)
                continue
            files.append(ParsedFile(
                file_role=row["file_role"], storage_key=key, original_name=candidate.name,
                media_type=mimetypes.guess_type(candidate.name)[0] or "application/octet-stream",
                sha256=sha256(candidate.read_bytes()).hexdigest(), processing_status="saved",
                source_url=version["source_url"] if row["file_role"] == "original" else None,
            ))
        # Retain originals without inventing which page/attachment produced a chunk.
        package = DocumentPackage(metadata=package.metadata, files=files, chunks=package.chunks)
        write_json(root / OUTPUT / f'{sample["key"]}.json', package.model_dump(mode="json"))
        write_json(root / OUTPUT / f'{sample["key"]}.metadata.json', metadata.model_dump(mode="json"))
        text = original_bytes.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        assert input_path.read_bytes() == original_bytes, "解析不得改动输入文件"
        for chunk in package.chunks:
            location = json.loads(chunk.locator_note)
            assert chunk.content == text[location["char_start"]:location["char_end"]]
        summary = {
            "key": sample["key"], "scenario": sample["scenario"], "record_code": metadata.record_code,
            "input_key": sample["file_path"], "input_sha256": sha256(original_bytes).hexdigest(),
            "input_chars": len(text), "chunk_chars": sum(len(x.content) for x in package.chunks),
            "chunk_count": len(package.chunks), "file_count": len(package.files),
            "missing_registered_files": missing_keys,
            "source_verification_status": package.metadata.source_verification_status.value,
            "timeliness_verification_status": package.metadata.timeliness_verification_status.value,
            "retrieval_status": package.metadata.retrieval_status.value,
            "limitation": sample["limitation"],
        }
        summaries.append(summary)
        packages.append(package)
        report.append(f'| {sample["scenario"]} | {len(text)} | {summary["chunk_chars"]} | {len(package.chunks)} | extracted / blocked |')
        details.extend([
            "", f'## {sample["scenario"]}：{metadata.title}', "",
            f'- 资料编号：`{metadata.record_code}`；版本：`{metadata.version_no}`（离线导入版本，非官方版次）。',
            f'- 官方登记链接：[{metadata.publisher or "来源"}]({metadata.source_url})；登记发布日期：{metadata.published_on}。',
            f'- 输入：[已有正文提取稿](../../../{sample["file_path"]})。',
            f'- 输出：[DocumentPackage](../../../{OUTPUT.as_posix()}/{sample["key"]}.json)。',
            f'- 资料限制：{sample["limitation"]}',
            f'- 核验状态：来源 {summary["source_verification_status"]}、时效 {summary["timeliness_verification_status"]}；正式检索 blocked。',
            '- 原始文件仅作留档；片段到官方原件的逐段对应未核实，original_file_key/original_locator 均为 null。',
            f'- 已登记但当前仓库缺失的关联文件：{len(missing_keys)}；缺失文件不伪造 ParsedFile/哈希。',
            "", "输入片段（保留原有标题和文字）：", "", "```markdown",
            package.chunks[0].content[:260], "```", "",
            "解析后的片段定位：", "",
            "| chunk_no | 字符数 | source_file_key | locator |",
            "| ---: | ---: | --- | --- |",
        ])
        for chunk in package.chunks:
            details.append(f'| {chunk.chunk_no} | {len(chunk.content)} | `{chunk.source_file_key}` | {chunk.locator.replace("|", " / ")} |')
        details.extend(["", "首个 ParsedChunk（正文截取，其余字段真实保留）：", "", "```json",
                        json.dumps({**package.chunks[0].model_dump(mode="json"),
                                    "content": package.chunks[0].content[:260]}, ensure_ascii=False, indent=2), "```"])
    write_json(root / OUTPUT / "summary.json", {
        "metadata_source": manifest["preview_path"], "metadata_source_sha256": sha256(preview_path.read_bytes()).hexdigest(),
        "max_chunk_chars": manifest["max_chunk_chars"], "sample_count": len(summaries), "samples": summaries,
    })
    report.extend(details)
    (root / REPORT).parent.mkdir(parents=True, exist_ok=True)
    (root / REPORT).write_text("\n".join(report) + "\n", encoding="utf-8")
    return packages


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    for package in build_samples():
        print(f'{package.metadata.record_code}: chunks={len(package.chunks)}, retrieval_status=blocked')


if __name__ == "__main__":
    main()
