"""Build/check B8: two unapproved S4 packages, 24 original rows each.

python -m knowledge_base.processing.build_qinghe_b8 [--check]
Uses existing contracts/parser; never writes approved/ or changes the 8-package
review baseline. Source preflight runs before any output is overwritten.
"""
from __future__ import annotations

import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path

from backend.contracts import DocumentMetadata, DocumentPackage, RetrievalRequest
from backend.document_processing import TextDocumentParser
from backend.retrieval.local import LocalBM25Retriever
from knowledge_base.processing import build_beta_policy_review as baseline
from knowledge_base.processing.extract_policy_review import html_units
from knowledge_base.processing.extract_qinghe_labs import extract

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path("knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23")
MAPPING = baseline.REVIEW / "qinghe-b8-source-map.json"
VERSION = "beta-b8-2026-11-23-1"
MAX_CHARS = 16384  # one lab per section; fail rather than silently split a row
CATEGORIES = {"R3": "实验室与科研团队", "R4": "研究方向与公开介绍"}
COLUMNS = {"R3": "ABDEFGH", "R4": "ABCI"}
FIVE_KEYS = ("适用年级", "适用专业", "适用对象", "学院", "适用届别")


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def dump(path, value):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def file_digest(path):
    return sha256((ROOT / path).read_bytes()).hexdigest()


def prepare():
    # Includes independent raw re-extraction, original/file inventory hashes and
    # blocked gates of the retained candidate baseline; no generation writes.
    asyncio.run(baseline.check())
    parent = DocumentPackage.model_validate(read(baseline.OUTPUT / "qinghe.json"))
    _, audit = extract(ROOT / baseline.REVIEW / "qinghe-labs.xlsx")
    notice, _ = html_units(ROOT / baseline.REVIEW / "qinghe.html")
    cells = {c["cell"]: c for c in audit["cells"]}
    headers = {letter: cells[f"{letter}2"]["value"].replace("\n", " ") for letter in "ABCDEFGHI"}
    result = {}
    for category in CATEGORIES:
        meta = parent.metadata.model_dump(mode="json")
        meta.update(title=f"2026—2027学年青禾计划·{CATEGORIES[category]}", category_name=CATEGORIES[category],
                    record_code=parent.metadata.record_code + "-" + category, version_no=VERSION,
                    document_type="年度实验室招募资料" if category == "R3" else "历史公开资源介绍",
                    business_direction_codes=["COLLEGE_RESOURCES"],
                    deadline_on="2026-10-31" if category == "R3" else None,
                    timeliness_verification_status="expired" if category == "R3" else "historical",
                    applicability_raw={"适用年级": "全体本科生；具体实验室另有接收条件",
                        "适用专业": None, "适用对象": "计算机与大数据学院（软件学院）本科生；具体实验室按原行条件",
                        "学院": "福州大学计算机与大数据学院（软件学院）", "适用届别": None},
                    policy_status="2026—2027学年当期报名已截止；待人工审核" if category == "R3" else "2026-10发布的历史公开介绍；不证明当前方向或招募状态",
                    verification_note="B8按原序号拆分；本包仅" + CATEGORIES[category] + "。原文‘无’按缺失处理；未提供专业/届别不推断。待组长最终人工核验。",
                    retrieval_status="blocked")
        meta["temporal_notes"] = {
            "human_approved": False, "checked_on": "2026-11-23", "beta_domains": ["S4"],
            "resource_category": category, "source_academic_year": "2026—2027学年",
            "source_record_code": parent.metadata.record_code, "source_version_no": parent.metadata.version_no,
            "source_package": (baseline.OUTPUT / "qinghe.json").as_posix(),
            "split_contract": "B8: R3/R4 two independent packages, 24 chunks each; preserve row IDs",
            "scope_notes": "适用专业/届别原文未明确，不推断不限；全体本科生只指本院，仍看每行接收条件。",
            "deadline_meaning": "通知10月31日前报名，未给具体时刻；2026批次已过期" if category == "R3" else "本包不承担报名流程/资格判断；不得继承招募时效为现行介绍",
            "missing_value_policy": "空白或仅‘无’标为未提供；原始值及坐标保留在原件/审计映射中",
        }
        metadata = DocumentMetadata.model_validate(meta)
        units = []
        for number in range(1, 25):
            row = number + 2
            name = cells[f"B{row}"]["value"].strip()
            context = ("2026—2027学年青禾计划当期记录；学院本科生，仍须符合本行接收条件。2026年10月31日前报名已截止，接收人数是当时计划，不是实时余量；联系渠道未核实当前可达。"
                       if category == "R3" else
                       "以下为2026年10月官方附件中的历史公开介绍，仅供了解当时研究内容和成果；不证明目前招募、资格、名额或联系方式。成果/去向是原表介绍，不保证个人结果。")
            fields, missing, references = [], [], []
            for letter in COLUMNS[category]:
                coordinate = f"{letter}{row}"
                cell = cells.get(coordinate)
                value = cell["value"] if cell else None
                absent = value is None or not value.strip() or value.strip() == "无"
                shown = "未提供（原表为‘无’或空白；不能推断）" if absent else value
                fields.append(f"{headers[letter]}（{coordinate}）：\n{shown}")
                if absent:
                    missing.append(coordinate)
                links = list(dict.fromkeys(([cell["hyperlink"]] if cell and cell["hyperlink"] else []) + audit["wps_rich_text_links"].get(coordinate, [])))
                if not absent:
                    fields.extend(f"原单元格链接（{coordinate}；未访问或验证）：{url}" for url in links)
                references.append({"cell": coordinate, "raw_value": value, "missing": absent,
                                   "hyperlinks": links, "raw_value_sha256": sha256((value or "").encode()).hexdigest()})
            if category == "R3":
                # Keep the verified notice verbatim, including the deadline and
                # initial screening/interview steps; the row never invents them.
                fields.append("本批报名及选拔流程（官方通知原文，历史流程）：\n" + "\n".join(u["content"] for u in notice[:7]))
            units.append({"lab_no": number, "heading": f"{category}·实验室序号{number:02d}·{name}",
                          "content": context + "\n\n" + "\n\n".join(fields), "cells": references,
                          "missing_cells": missing, "source_range": f"Sheet1!A{row}:I{row}",
                          "notice_locators": [u["locator"] for u in notice[:7]] if category == "R3" else []})
        text, intervals = "", []
        for unit in units:
            start = len(text)
            text += f"## {unit['heading']}\n\n{unit['content']}\n\n"
            intervals.append((start, len(text), unit))
        result[category] = {"metadata": metadata, "units": units, "text": text, "intervals": intervals,
                            "originals": [f.model_copy(deep=True) for f in parent.files if f.storage_key != parent.chunks[0].source_file_key]}
    return result


def package_for(category, data):
    path = OUTPUT / "texts" / f"qinghe-{category.lower()}.md"
    if (ROOT / path).read_text(encoding="utf-8") != data["text"]:
        raise ValueError("B8 Markdown differs from freshly extracted raw fields")
    package = TextDocumentParser(ROOT, max_chunk_chars=MAX_CHARS, file_role="curated").parse_document(path, data["metadata"])
    if len(package.chunks) != 24:
        raise ValueError("B8 requires exactly one complete chunk for each of the 24 labs")
    package.files.extend(data["originals"])
    mappings = []
    original_key = (baseline.REVIEW / "qinghe-labs.xlsx").as_posix()
    notice_key = (baseline.REVIEW / "qinghe.html").as_posix()
    for chunk, (start, end, unit) in zip(package.chunks, data["intervals"]):
        note = json.loads(chunk.locator_note)
        if chunk.chunk_no != unit["lab_no"] or not start <= note["char_start"] < note["char_end"] <= end:
            raise ValueError("B8 lab row or interval mismatch")
        chunk.original_file_key, chunk.original_locator = original_key, unit["source_range"]
        mappings.append({"package": f"qinghe-{category.lower()}.json", "category": category,
            "lab_no": unit["lab_no"], "chunk_no": chunk.chunk_no, "source_file_key": chunk.source_file_key,
            "original_file_key": original_key, "original_sha256": file_digest(Path(original_key)),
            "original_locator": chunk.original_locator, "locator_note": note, "fields": unit["cells"],
            "missing_cells": unit["missing_cells"], "selected_columns": COLUMNS[category],
            "notice": {"original_file_key": notice_key, "sha256": file_digest(Path(notice_key)), "locators": unit["notice_locators"]} if category == "R3" else None})
    return DocumentPackage.model_validate(package.model_dump(mode="json")), mappings


def manifest_for(packages):
    return {"stage": "pending-review", "package_format": "backend.contracts.DocumentPackage", "checked_on": "2026-11-23",
        "human_approved_packages": 0, "enabled_packages": 0, "total_chunks": 48,
        "supersedes_for_s4": (baseline.OUTPUT / "qinghe.json").as_posix(),
        "notice": "旧35片段混合包仅核验基线；A4交接使用本R3/R4两包。未获人工签核，不得进入approved。",
        "packages": [{"package": (OUTPUT / f"qinghe-{c.lower()}.json").as_posix(),
            "record_code": p.metadata.record_code, "category_name": p.metadata.category_name,
            "business_direction_codes": ["COLLEGE_RESOURCES"], "chunk_count": 24,
            "retrieval_status": "blocked", "human_approved": False} for c, p in packages.items()]}


def build():
    prepared = prepare()  # all raw/metadata/source preflight happens before writes
    packages, mapping = {}, []
    for category, data in prepared.items():
        path = ROOT / OUTPUT / "texts" / f"qinghe-{category.lower()}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data["text"], encoding="utf-8", newline="\n")
        package, rows = package_for(category, data)
        packages[category] = package
        mapping.extend(rows)
        dump(OUTPUT / f"qinghe-{category.lower()}.json", package.model_dump(mode="json"))
    dump(MAPPING, mapping)
    dump(OUTPUT / "manifest.json", manifest_for(packages))


def check():
    prepared = prepare()
    packages, mapping = {}, []
    for category, data in prepared.items():
        expected, rows = package_for(category, data)
        path = OUTPUT / f"qinghe-{category.lower()}.json"
        actual = DocumentPackage.model_validate(read(path))
        if actual.metadata.retrieval_status.value != "blocked" or (actual.metadata.temporal_notes or {}).get("human_approved") is not False:
            raise ValueError("B8 candidates must remain blocked with human_approved=false")
        if actual.model_dump(mode="json") != expected.model_dump(mode="json"):
            raise ValueError(f"B8 {category} package differs from raw-derived candidate")
        for file in actual.files:
            if file.sha256 != file_digest(Path(file.storage_key)):
                raise ValueError("B8 package file SHA mismatch")
        packages[category] = actual
        mapping.extend(rows)
    if read(MAPPING) != mapping:
        raise ValueError("B8 raw row/cell mapping mismatch")
    manifest = read(OUTPUT / "manifest.json")
    if (json.dumps(manifest, sort_keys=True) != json.dumps(manifest_for(packages), sort_keys=True)):
        raise ValueError("B8 pending-review manifest mismatch")
    async def isolation():
        store = LocalBM25Retriever(file_root=ROOT)
        counts = []
        for category, package in packages.items():
            result = await store.index_document(package)
            if result.status.value != "indexed" or result.indexed_count != 24 or result.warnings:
                raise ValueError("B8 candidate technical indexing failed")
            ids = [identity for identity, (version, _) in store._chunk_index.items() if version == result.version_id]
            if len(ids) != 24 or store.get_document_metadata(result.version_id) is not None or any(store.get_parsed_chunk(i) is not None for i in ids):
                raise ValueError("B8 blocked metadata/chunk gate failed")
            counts.append({"category": category, "indexed_chunks": 24, "metadata_hidden": True, "chunk_lookups_hidden": 24})
        if await store.retrieve(RetrievalRequest(query="青禾 实验室 报名 方向", business_direction_code="COLLEGE_RESOURCES")):
            raise ValueError("B8 candidates leaked into formal retrieval")
        return counts
    counts = asyncio.run(isolation())
    return {"packages": 2, "chunks": 48, "enabled_packages": 0, "human_approved_packages": 0,
            "raw_labs": 24, "original_sha256": file_digest(baseline.REVIEW / "qinghe-labs.xlsx"), "index_checks": counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        build()
    report = check()
    dump(baseline.DOCS / "qinghe-b8-validation-report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
