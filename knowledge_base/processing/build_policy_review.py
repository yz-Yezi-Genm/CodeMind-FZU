"""Build review-only/blocked handoff packages using the existing contracts.

python -m knowledge_base.processing.build_policy_review
python -m knowledge_base.processing.build_policy_review --check
Never enables a document, writes a production database or modifies old samples.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from hashlib import sha256
import json
import mimetypes
from pathlib import Path
import re

from backend.contracts import DocumentMetadata, DocumentPackage, ParsedFile, RetrievalRequest
from backend.document_processing import TextDocumentParser
from backend.retrieval.local import LocalBM25Retriever

ROOT = Path(__file__).resolve().parents[2]
REVIEW = Path("knowledge_base/processing/policy-review/2026-11-19")
OUTPUT = Path("knowledge_base/processed/alpha/pending-review")
DOCS = Path("docs/assignment-03/alpha")
RECORDS = {
    "competition": "福大-2026-竞赛项目级别认定",
    "scholarship": "福大-2026-本科奖学金",
    "college-scholarship": "计算机学院-2026-院级奖学金",
    "xinghuo": "计算机学院-2026-星火奖学金",
    "recommendation": "计算机学院-2027-推免资格推荐",
}
NOTES = {
    "competition": "2026-11-19通知页跳转统一身份认证；仅用旧HTML正文作归档对照，不将HTTP 200登录页视为核验成功。三份官方DOCX已重新下载且与归档哈希一致；205条数据行完成结构及既有正文对照，未逐条人工语义签核。竞赛级别/学分认定不能代替学院综评分值或奖学金等级。",
    "scholarship": "已重新获取官方通知并提取第1—15条，金额、比例及排除条件保留原文。第十四条规定公布施行、2024〔37〕号同步废止；未完成截至核验日所有后续修订的排查，现行性保留uncertain，待人工确认。学校级通则不直接替代学院社会专项规则。",
    "college-scholarship": "2026-04-13发布，但首段为做好2025年度；适用考核年度存在歧义，不能自行改成2026年度。保留奖项名称、四类别合并单元格与金额/名额；表中爱国者之星与后文爱国者的称谓差异未擅自统一。已取得四份XLSX汇总表ZIP，仅登记，未解析表格内容。年度及专项规则未人工确认前blocked。",
    "xinghuo": "官方2026-04-20通知明确2026沿用2025细则；申请报送为2026-04-26前，已过期，不能宣称当前开放。学生细则为30人、每人4000元、综测本专业40%以内含40%、连续三年一次。全文含教师奖教金，教师条件不能用作学生奖学金条件。RAR仅保存并检查成员清单，内含旧DOC/XLSX未可靠解析，不提供表内填写指导。",
    "recommendation": "官方PDF共4页；已渲染逐页对照，第4页竞赛/论文表按行保留合并表头及个人/集体列。申请截止2026-09-09 21:00已过，仅适用2027届推荐资格历史参考；不得当下一届现行方案。志愿服务30/60小时原文边界重叠，保留待释义，不实现自动计分。AI对照不等同人工审核通过。",
}


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def write(path, value):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return sha256((ROOT / path).read_bytes()).hexdigest()


def verify_inputs(units):
    inputs = dict(units["inputs"])
    # Include snapshots not used as正文 (e.g. the PDF landing page and ZIP/RAR).
    for manifest in ("source-fetch.json", "attachment-fetch.json"):
        for item in read(REVIEW / manifest):
            if item.get("storage_key"):
                inputs[item["storage_key"]] = item["sha256"]
    for key, expected in inputs.items():
        if digest(key) != expected:
            raise ValueError(f"原件哈希改变，停止生成并重新核验：{key}")
    return inputs


def metadata_for(key, preview):
    version = next(r for r in preview["document_versions"] if r["record_code"] == RECORDS[key])
    doc = next(r for r in preview["knowledge_documents"] if r["id"] == version["document_id"])
    category = next(r["name"] for r in preview["knowledge_categories"] if r["id"] == doc["category_id"])
    directions = {r["id"]: r["code"] for r in preview["business_directions"]}
    data = {k: v for k, v in version.items() if k in DocumentMetadata.model_fields}
    data.update(title=doc["title"], document_type=doc["document_type"], category_name=category,
                business_direction_codes=[directions[r["direction_id"]] for r in preview["document_business_directions"] if r["document_id"] == doc["id"]],
                version_no="review-2026-11-19-1", source_verification_status="partial" if key == "competition" else "verified",
                timeliness_verification_status="expired" if key in {"xinghuo", "recommendation"} else "pending" if key == "competition" else "uncertain",
                retrieval_status="blocked" if key in {"competition", "college-scholarship"} else "review_only",
                extraction_status="extracted", verification_note=NOTES[key])
    data["policy_status"] = {"competition": "2026版；通知页联网核验受阻", "scholarship": "公布施行；后续修订排查及人工复核待完成",
                             "college-scholarship": "发布年度与正文考核年度存在歧义，待学院确认", "xinghuo": "2026年度申请期已过，仅历史参考",
                             "recommendation": "2027届申请期已过，仅本届历史参考"}[key]
    # Never overwrite the imported record or pretend a date-only DTO has an hour.
    data["temporal_notes"] = {"reviewed_on": "2026-11-19", "review_method": "AI source/layout comparison; human signoff pending",
                              "human_approved": False, "baseline_version": version["version_no"],
                              "baseline_verification_note": version.get("verification_note"), "use_limitations": NOTES[key]}
    if key == "recommendation":
        data["deadline_on"] = "2026-09-09"
        data["temporal_notes"]["deadline_exact_local"] = "2026-09-09T21:00:00+08:00"
        data["applicability_raw"] = {**(data.get("applicability_raw") or {}), "目标届别": "2027届", "使用限制": "不适用于下一届；不可回答当前报名开放"}
    elif key == "xinghuo":
        data["effective_on"] = None  # publication is not an independently stated effective date
        data["deadline_on"] = "2026-04-26"
        data["temporal_notes"]["deadline_original"] = "2026年4月26日前；原文未给具体时刻，不擅自补23:59"
        data["applicability_raw"] = {"学院": "福州大学计算机与大数据学院", "学生对象": "正式学籍、在读全日制本科生和研究生",
                                     "教师条款": "全文为完整性保留，学生问答不得引用教师资格、名额或金额", "年度": "2026年沿用2025细则，申请期已过"}
    elif key == "college-scholarship":
        data["effective_on"] = None
        data["applicability_raw"] = {"学院": "福州大学计算机与大数据学院", "对象": "正式学籍、在读全日制本科生和研究生，各专项另有限制",
                                     "年度歧义": "网页发布2026-04-13；首段2025年度；待学院确认，不自行纠正", "学业类": "原文10名本科生"}
    return DocumentMetadata.model_validate(data)


def build():
    sources = read(REVIEW / "source-units.json")
    inputs = verify_inputs(sources)
    preview = read(Path("docs/assignment-02/database-design/knowledge-base/入库预览_44条.json"))
    fetches = {x["storage_key"]: x for f in ["source-fetch.json", "attachment-fetch.json"] for x in read(REVIEW / f) if x.get("storage_key")}
    mappings, summaries = [], []
    for key, source_units in sources["documents"].items():
        metadata = metadata_for(key, preview)
        md_key = OUTPUT / "texts" / f"{key}.md"
        text, intervals = "", []
        for number, unit in enumerate(source_units, 1):
            start = len(text)
            scope = " / ".join(unit.get("heading_path", []))
            heading = " | ".join(s for s in [metadata.title, scope, f"来源单元{number:04d}"] if s)
            text += f"## {heading}\n\n{unit['content']}\n\n"
            intervals.append((start, len(text), number, unit))
        (ROOT / md_key).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / md_key).write_text(text, encoding="utf-8", newline="\n")
        parser = TextDocumentParser(ROOT, max_chunk_chars=2400, file_role="curated" if key == "recommendation" else "extracted")
        package = parser.parse_document(md_key, metadata)
        original_keys = set(u["original_file_key"] for u in source_units)
        if key == "recommendation":
            original_keys.add((REVIEW / "recommendation.html").as_posix())
        if key == "college-scholarship":
            original_keys.add((REVIEW / "college-attachments.zip").as_posix())
        if key == "xinghuo":
            original_keys.add((REVIEW / "xinghuo-forms.rar").as_posix())
        for file_key in sorted(original_keys):
            item = fetches.get(file_key)
            package.files.append(ParsedFile(file_role="original" if file_key.endswith(".html") else "attachment", storage_key=file_key,
                                             original_name=Path(file_key).name, media_type=mimetypes.guess_type(file_key)[0] or "application/octet-stream",
                                             sha256=digest(Path(file_key)), source_url=item["url"] if item else metadata.source_url,
                                             processing_status="saved"))
        for chunk in package.chunks:
            offset = json.loads(chunk.locator_note)["char_start"]
            start, end, number, unit = next(v for v in intervals if v[0] <= offset < v[1])
            if json.loads(chunk.locator_note)["char_end"] > end:
                raise ValueError("Chunk crosses original source units")
            chunk.original_file_key = unit["original_file_key"]
            chunk.original_locator = unit["locator"]
            mappings.append({"package": f"{key}.json", "chunk_no": chunk.chunk_no, "source_unit": number,
                             "source_file_key": chunk.source_file_key, "original_file_key": chunk.original_file_key,
                             "original_sha256": inputs[chunk.original_file_key], "original_locator": chunk.original_locator,
                             "locator": chunk.locator, "locator_note": json.loads(chunk.locator_note),
                             "transformation": unit["method"], "source_unit_sha256": sha256(unit["content"].encode()).hexdigest()})
        # The parser itself ALWAYS blocks. Only this separately documented review
        # export assigns review_only; there is no approval or enabled code path.
        payload = package.model_dump(mode="json")
        payload["metadata"] = metadata.model_dump(mode="json")
        package = DocumentPackage.model_validate(payload)
        write(OUTPUT / f"{key}.json", package.model_dump(mode="json"))
        summaries.append({"key": key, "record_code": metadata.record_code, "package": (OUTPUT / f"{key}.json").as_posix(),
                          "chunk_count": len(package.chunks), "source_units": len(source_units), "files": len(package.files),
                          "source_verification_status": metadata.source_verification_status.value,
                          "timeliness_verification_status": metadata.timeliness_verification_status.value,
                          "retrieval_status": metadata.retrieval_status.value, "human_approved": False})
    write(REVIEW / "chunk-source-map.json", mappings)
    write(OUTPUT / "manifest.json", {"reviewed_on": "2026-11-19", "package_format": "backend.contracts.DocumentPackage",
                                    "storage_root": "repository root", "human_approved_packages": 0,
                                    "enabled_packages": 0, "packages": summaries})
    return summaries


async def check():
    sources = read(REVIEW / "source-units.json")
    inputs = verify_inputs(sources)
    mapping = read(REVIEW / "chunk-source-map.json")
    lookup = {(r["package"], r["chunk_no"]): r for r in mapping}
    if len(lookup) != len(mapping):
        raise ValueError("Duplicate chunk mappings")
    retriever = LocalBM25Retriever(file_root=ROOT)
    results = []
    expected_metadata = read(OUTPUT / "manifest.json")
    for item in expected_metadata["packages"]:
        path = Path(item["package"])
        package = DocumentPackage.model_validate(read(path))
        if package.metadata.retrieval_status.value not in {"blocked", "review_only"}:
            raise ValueError("Review tooling cannot approve or enable policies")
        for file in package.files:
            if digest(Path(file.storage_key)) != file.sha256:
                raise ValueError("Package file hash mismatch")
        for chunk in package.chunks:
            row = lookup[(path.name, chunk.chunk_no)]
            note = json.loads(chunk.locator_note)
            text = (ROOT / chunk.source_file_key).read_text(encoding="utf-8")
            if text[note["char_start"]:note["char_end"]] != chunk.content:
                raise ValueError("Chunk differs from normalized source substring")
            unit = sources["documents"][item["key"]][row["source_unit"] - 1]
            if row["source_unit_sha256"] != sha256(unit["content"].encode()).hexdigest() or chunk.original_locator != unit["locator"] or chunk.original_file_key != unit["original_file_key"]:
                raise ValueError("Original unit mapping changed")
        result = await retriever.index_document(package)
        if result.indexed_count != len(package.chunks):
            raise ValueError(f"Downstream indexing failed: {result}")
        results.append({"key": item["key"], "index_result": result.model_dump(mode="json")})
    queries = ["蓝桥杯竞赛认定", "奖学金", "推免", "星火4000"]
    hits = {query: len(await retriever.retrieve(RetrievalRequest(query=query))) for query in queries}
    if any(hits.values()):
        raise ValueError("Review-only/blocked document leaked into formal retrieval")
    # Every nonempty OOXML cell, including headers and trailing notes, is checked
    # against the previous extraction. This is textual coverage, not policy approval.
    baseline = (ROOT / "knowledge_base/政策资料/正文资料/学校/福州大学_2026_大学生学科竞赛级别认定结果.md").read_text(encoding="utf-8-sig")
    normal = lambda text: re.sub(r"\s+", "", text)
    cells = [cell for unit in sources["documents"]["competition"] for cell in unit.get("cells", []) if cell]
    if any(normal(cell) not in normal(baseline) for cell in cells):
        raise ValueError("DOCX cell absent from archived extraction")
    report = {"command": "python -m knowledge_base.processing.build_policy_review --check", "verified_input_files": len(inputs),
              "package_count": len(results), "mapped_chunks": len(mapping), "ooxml_cells_checked_against_archive": len(cells),
              "retrieval_status_counts": dict(Counter(x["retrieval_status"] for x in expected_metadata["packages"])),
              "index_results": results, "formal_retrieval_hit_counts": hits, "passed": True,
              "limitations": "真实本地BM25离线对接；无生产数据库写入、人工签核或enabled资料；不是正式问答效果验收。"}
    write(DOCS / "evidence/policy-review-check.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(check()) if args.check else build()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
