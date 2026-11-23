"""Build/check four-domain Beta candidates, ALWAYS blocked, using public DTOs.

Offline: python -m knowledge_base.processing.build_beta_policy_review [--check]
Requires the existing backend environment. Never writes approved/ or an index.
"""
from __future__ import annotations

import argparse
import asyncio
from hashlib import sha256
import json
import mimetypes
from pathlib import Path

from backend.contracts import DocumentMetadata, DocumentPackage, ParsedFile, RetrievalRequest
from backend.document_processing import TextDocumentParser
from backend.retrieval.local import LocalBM25Retriever
from knowledge_base.processing.build_policy_review import metadata_for as alpha_metadata, RECORDS as ALPHA_RECORDS

ROOT = Path(__file__).resolve().parents[2]
REVIEW = Path("knowledge_base/processing/policy-review/2026-11-23")
OLD = Path("knowledge_base/processing/policy-review/2026-11-19")
OUTPUT = Path("knowledge_base/processed/alpha/pending-review/beta-2026-11-23")
VERSION = "beta-review-2026-11-23-1"
RECORDS = {**ALPHA_RECORDS, "innovation": "福大-2024-创新创业学分认定",
           "retest": "计算机学院-2026-推免复试参考", "qinghe": "计算机学院-2026-青禾计划"}
DOMAINS = {"competition": ["S1"], "innovation": ["S1"], "scholarship": ["S2"],
           "college-scholarship": ["S2"], "xinghuo": ["S2"], "recommendation": ["S3"],
           "retest": ["S3"], "qinghe": ["S4", "S1"]}
NOTES = {
    "competition": "2026-11-23真实通知正文、校教〔2026〕9号及三份附件入口已核对；本网络可读取，无需账号。三份DOCX与Alpha原件SHA-256相同，逐行保留合并标记及脚注。竞赛级别认定用于规定的学分/绩效用途，不能直接换成综测加分或奖学金等级。205数据行未获逐项人工签核；后续版本非全站穷尽核验。",
    "scholarship": "2026办法第1—15条已重新提取，金额、比例、排除条件原文保留。第十四条公布施行并废止2024〔37〕号；学工部当前规章制度列表仍有2026办法。有限检索未构成官方现行性证明；待人工确认。校级通则不能替代院级/专项细则。",
    "college-scholarship": "发布2026-04-13但正文及四份表头写2025年度；统计区间含2025.03—2026.02和2024—2025学年，不擅自改成2026评奖。奖项别称和适用本科/研究生条件需分别确认。ZIP沿用Alpha隐私检查且哈希固定；仍待学院确认及最终审核。",
    "xinghuo": "通知发布2026-04-20，2026沿用2025细则，2026-04-26前报送，申请期已过。学生30人/4000元等条款与教师16人/5000元分开；正文保留章节上下文，学生问答不得用教师条件。RAR沿用全量隐私审计；旧DOC未新增为正式政策正文，填写指导及人工审核待办。",
    "recommendation": "2027届本科推荐资格方案；2026-09-09 21:00截止，已过期。新下载4页PDF与Alpha原件同哈希，沿用第4页按行保留表头/个人集体列的版式对照。不得当作下一届现行方案；志愿服务30/60小时重叠边界仍待官方解释及人工签核。",
    "innovation": "校教〔2024〕7号，正文第27条明确2024-09-01执行，2022〔1〕号废止，2016〔66〕号有2020级毕业后的过渡安排。正文第1—28条及表格按HTML合并标记保留；项目原始分、创新学分与综合素质测评分值不得混用。需结合入学年级、培养方案和认定目录；现行性待人工核实。",
    "retest": "这是接收2027年硕士推免生/直博生复试方案，不是取得本科推荐资格的办法。官方嵌入PDF9页已提取，逐页渲染AI对照，第2页6行计划表保留；2026-09-19 11:00首批预报名导出及9月22日首批复试均已过。后续批次以另行公告为准，不宣称现在可报名。未转换复试用表ZIP，完整填写指导不可用；人工审核待办。",
    "qinghe": "2026—2027学年学院本科生青禾计划；2026-10-31前发送报名表电子版至各实验室邮箱，之后材料初选/面试或笔试。XLSX24条记录、226非空单元格全量转换；2空工作表登记，标题合并不填充为行属性。研究方向、条件、人数和官方公开联系渠道保留原值，人数非实时空缺、联系方式未测可达；报名已过期，不推广到下一批。空白报名表仅作原件关联，不采集学生申请资料。",
}


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def write(path, value):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return sha256((ROOT / path).read_bytes()).hexdigest()


def verify_inputs(sources):
    for key, expected in sources["inputs"].items():
        if digest(Path(key)) != expected:
            raise ValueError(f"Original hash changed; redo extraction/review: {key}")


def metadata_for(key, preview):
    version = next(r for r in preview["document_versions"] if r["record_code"] == RECORDS[key])
    if key in ALPHA_RECORDS:
        data = alpha_metadata(key, preview).model_dump(mode="json")
    else:
        doc = next(r for r in preview["knowledge_documents"] if r["id"] == version["document_id"])
        directions = {r["id"]: r["code"] for r in preview["business_directions"]}
        data = {k: v for k, v in version.items() if k in DocumentMetadata.model_fields}
        data.update(title=doc["title"], document_type=doc["document_type"],
                    category_name=next(r["name"] for r in preview["knowledge_categories"] if r["id"] == doc["category_id"]),
                    business_direction_codes=[directions[r["direction_id"]] for r in preview["document_business_directions"] if r["document_id"] == doc["id"]])
    expired = key in {"xinghuo", "recommendation", "retest", "qinghe"}
    data.update(version_no=VERSION, source_verification_status="verified", extraction_status="extracted",
                retrieval_status="blocked", timeliness_verification_status="expired" if expired else "uncertain",
                policy_status="本批次截止/首批安排已过，仅历史参考；待最终审核" if expired else "官方正文已核对；现行性/适用性待最终审核",
                verification_note=NOTES[key], source_page_url=data["source_url"],
                temporal_notes={"checked_on": "2026-11-23", "check_method": "official snapshot/hash/structure comparison; AI review, not human signoff",
                                "human_approved": False, "baseline_version": version["version_no"],
                                "beta_domains": DOMAINS[key], "scope_limitations": NOTES[key],
                                "version_search_evidence": (REVIEW / "verification-evidence.json").as_posix()})
    if key in {"qinghe", "retest"}:
        data["effective_on"] = None  # publication is not an independently specified effective date
        data["deadline_on"] = "2026-10-31" if key == "qinghe" else "2026-09-19"
        data["temporal_notes"]["deadline_meaning"] = "原文10月31日前；未给时刻" if key == "qinghe" else "首批预报名数据导出截止2026-09-19 11:00；不代表后续批次统一截止"
        data["applicability_raw"] = ({"对象": "计算机与大数据学院（软件学院）全体本科生；另看各实验室接收条件", "批次": "2026—2027学年青禾计划；报名期已过", "资源状态": "发布时计划与联系渠道，非实时招生名额"}
                                     if key == "qinghe" else {"对象": "已取得所在学校推免资格的校内外优秀应届本科毕业生；申请硕士/直博另看细则", "年度": "2027年接收推免；2026年9月实施", "限制": "不是本科推荐资格办法；不适用于下一届或当前开放判断"})
    if key == "recommendation":
        data["temporal_notes"]["deadline_exact_local"] = "2026-09-09T21:00:00+08:00"
    if key == "innovation":
        data["effective_on"] = "2024-09-01"
        data["applicability_raw"] = {**data["applicability_raw"], "过渡说明": "第27条：2016办法待2020级毕业后自动废止，2022办法废止；具体年级和培养方案待人工确认"}
    if key == "college-scholarship":
        data["policy_status"] = "发布2026年/评奖2025年等区间存在歧义；不得推定现行"
    return DocumentMetadata.model_validate(data)


def build():
    sources = read(REVIEW / "source-units.json")
    verify_inputs(sources)
    preview = read(Path("docs/assignment-02/database-design/knowledge-base/入库预览_44条.json"))
    fetches = {r["storage_key"]: r for path in [REVIEW / "source-fetch.json", OLD / "attachment-fetch.json"]
               for r in read(path) if r.get("storage_key")}
    labels = {a["storage_key"]: a["label"].removeprefix("附件1：").removeprefix("附件2：").removeprefix("附件3：")
              for document in read(REVIEW / "verification-evidence.json")["documents"].values()
              for a in document["linked_attachments"] if a["label"] != "embedded PDF"}
    mappings, summaries = [], []
    for key, units in sources["documents"].items():
        metadata = metadata_for(key, preview)
        md_key = OUTPUT / "texts" / f"{key}.md"
        text, intervals = "", []
        for number, unit in enumerate(units, 1):
            start = len(text)
            scope = " / ".join(unit.get("heading_path", []))
            text += f"## {metadata.title} | {scope} | 来源单元{number:04d}\n\n{unit['content']}\n\n"
            intervals.append((start, len(text), number, unit))
        (ROOT / md_key).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / md_key).write_text(text, encoding="utf-8", newline="\n")
        package = TextDocumentParser(ROOT, max_chunk_chars=2400, file_role="curated" if key == "recommendation" else "extracted").parse_document(md_key, metadata)
        originals = {u["original_file_key"] for u in units} | {(REVIEW / f"{key}.html").as_posix()}
        if key in {"college-scholarship", "xinghuo"}:
            originals.add((OLD / ("college-attachments.zip" if key == "college-scholarship" else "xinghuo-forms.rar")).as_posix())
        if key == "qinghe":
            originals.add((REVIEW / "qinghe-registration.docx").as_posix())
        for file_key in sorted(originals):
            item = fetches[file_key]
            package.files.append(ParsedFile(file_role="original" if file_key.endswith(".html") else "attachment",
                 storage_key=file_key, original_name=item.get("original_name", labels.get(file_key, Path(file_key).name)),
                 media_type=mimetypes.guess_type(file_key)[0] or "application/octet-stream", sha256=digest(Path(file_key)),
                 source_url=item["url"], processing_status="saved"))
        for chunk in package.chunks:
            note = json.loads(chunk.locator_note)
            start, end, number, unit = next(i for i in intervals if i[0] <= note["char_start"] < i[1])
            if note["char_end"] > end:
                raise ValueError("Chunk crosses original source units")
            chunk.original_file_key, chunk.original_locator = unit["original_file_key"], unit["locator"]
            mappings.append({"package": f"{key}.json", "chunk_no": chunk.chunk_no, "source_unit": number,
                "source_file_key": chunk.source_file_key, "original_file_key": chunk.original_file_key,
                "original_sha256": sources["inputs"][chunk.original_file_key], "original_locator": chunk.original_locator,
                "locator_note": note, "source_unit_sha256": sha256(unit["content"].encode()).hexdigest(), "transformation": unit["method"]})
        package = DocumentPackage.model_validate(package.model_dump(mode="json"))
        write(OUTPUT / f"{key}.json", package.model_dump(mode="json"))
        summaries.append({"key": key, "domains": DOMAINS[key], "record_code": metadata.record_code,
            "package": (OUTPUT / f"{key}.json").as_posix(), "chunk_count": len(package.chunks), "source_units": len(units),
            "source_verification_status": metadata.source_verification_status.value,
            "timeliness_verification_status": metadata.timeliness_verification_status.value,
            "retrieval_status": "blocked", "human_approved": False})
    write(REVIEW / "chunk-source-map.json", mappings)
    write(OUTPUT / "manifest.json", {"checked_on": "2026-11-23", "package_format": "backend.contracts.DocumentPackage",
          "storage_root": "repository root", "stage": "pending-review", "enabled_packages": 0, "human_approved_packages": 0,
          "packages": summaries})
    return summaries


async def check():
    sources = read(REVIEW / "source-units.json")
    verify_inputs(sources)
    manifest = read(OUTPUT / "manifest.json")
    mapping = read(REVIEW / "chunk-source-map.json")
    lookup = {(r["package"], r["chunk_no"]): r for r in mapping}
    if len(lookup) != len(mapping):
        raise ValueError("Duplicate source mappings")
    retriever = LocalBM25Retriever(file_root=ROOT)
    count = 0
    for row in manifest["packages"]:
        package = DocumentPackage.model_validate(read(Path(row["package"])))
        if package.metadata.retrieval_status.value != "blocked" or package.metadata.temporal_notes.get("human_approved") is not False:
            raise ValueError("Beta candidates cannot approve/enable policies")
        if package.metadata.version_no != VERSION or len(package.chunks) != row["chunk_count"]:
            raise ValueError("Package manifest inconsistent")
        for file in package.files:
            if digest(Path(file.storage_key)) != file.sha256:
                raise ValueError("Package file hash mismatch")
        for chunk in package.chunks:
            evidence = lookup[(Path(row["package"]).name, chunk.chunk_no)]
            note = json.loads(chunk.locator_note)
            text = (ROOT / chunk.source_file_key).read_text(encoding="utf-8")
            if text[note["char_start"]:note["char_end"]] != chunk.content:
                raise ValueError("Chunk text interval differs from conversion")
            unit = sources["documents"][row["key"]][evidence["source_unit"] - 1]
            if evidence["source_unit_sha256"] != sha256(unit["content"].encode()).hexdigest():
                raise ValueError("Source unit hash mismatch")
            if (evidence["original_file_key"], evidence["original_locator"], evidence["original_sha256"]) != (chunk.original_file_key, chunk.original_locator, digest(Path(chunk.original_file_key))):
                raise ValueError("Original mapping mismatch")
        await retriever.index_document(package)
        count += len(package.chunks)
    hits = {}
    for code, query in [("COMPETITION_RESEARCH", "大学生学科竞赛认定创新学分"), ("POLICY_AFFAIRS", "本科生奖学金申请条件"),
                        ("EDUCATION_CAREER", "2027推免复试资格"), ("COLLEGE_RESOURCES", "青禾计划实验室研究方向报名")]:
        hits[code] = len(await retriever.retrieve(RetrievalRequest(query=query, business_direction_code=code)))
    if any(hits.values()):
        raise ValueError("Blocked candidate leaked into formal retrieval")
    if len(mapping) != count:
        raise ValueError("Incomplete chunk mapping")
    return {"packages": len(manifest["packages"]), "chunks": count, "original_mappings": len(mapping),
            "enabled_packages": 0, "human_approved_packages": 0, "formal_hits_for_blocked_candidates": hits}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        build()
    result = asyncio.run(check())
    write(REVIEW / "validation-report.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
