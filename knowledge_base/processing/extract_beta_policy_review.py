"""Offline Beta evidence extraction; no approval, database or contract changes.

Requires lxml, openpyxl and pypdf in the review tooling environment.
Run fetch_beta_policy_sources and its --attachments mode before this command.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urljoin
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from knowledge_base.processing.extract_policy_review import html_units, word_units, attach_headings
from knowledge_base.processing.extract_qinghe_labs import main as extract_qinghe
from knowledge_base.processing.audit_policy_forms import inspect_xlsx

ROOT = Path(__file__).resolve().parents[2]
REVIEW = Path("knowledge_base/processing/policy-review/2026-11-23")
OLD = Path("knowledge_base/processing/policy-review/2026-11-19")
DATES = {"competition": "2026-03-06", "scholarship": "2026-05-18",
         "college-scholarship": "2026-04-13", "xinghuo": "2026-04-20",
         "recommendation": "2026-09-08", "innovation": "2024-05-30",
         "retest": "2026-09-17", "qinghe": "2026-10-16"}
TITLE_TOKENS = {"competition": "大学生学科竞赛级别认定结果", "scholarship": "本科生奖学金评定管理办法",
                "college-scholarship": "院级奖学金评选", "xinghuo": "星火奖教奖学金",
                "recommendation": "2027年推荐优秀应届本科毕业生免试攻读研究生工作方案",
                "innovation": "创新创业实践与素质拓展学分认定管理实施办法", "retest": "2027年招收直博生、硕士生推免复试方案",
                "qinghe": "青禾计划"}


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def write(path, data):
    (ROOT / path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return sha256((ROOT / path).read_bytes()).hexdigest()


def extract():
    from lxml import html
    from pypdf import PdfReader
    extract_qinghe()
    fetches = {r["name"]: r for r in read(REVIEW / "source-fetch.json")}
    inputs = {}
    for row in fetches.values():
        if not row.get("storage_key"):
            continue
        key = row["storage_key"]
        if digest(Path(key)) != row["sha256"]:
            raise ValueError(f"Downloaded snapshot changed: {key}")
        inputs[key] = row["sha256"]
    old = read(OLD / "source-units.json")
    documents, audit = {}, {}
    for key, date in DATES.items():
        page = REVIEW / f"{key}.html"
        if fetches[page.name].get("fetch_status") != "downloaded":
            raise ValueError(f"Fresh official policy download missing: {key}")
        root = html.fromstring((ROOT / page).read_bytes())
        title = root.xpath('string(//title)').strip()
        date_pattern = r"(?:发布时间|发布日期)[：:\s]*" + re.escape(date)
        if not re.search(date_pattern, root.text_content()):
            raise ValueError(f"Publication date not confirmed on official page: {key}")
        if TITLE_TOKENS[key] not in title:
            raise ValueError(f"Unexpected official policy title: {key}")
        info = {"page": page.as_posix(), "official_url": fetches[page.name]["url"],
                "page_title": title, "published_on": date, "date_verified_from_page": True,
                "human_approved": False}
        # Bind downloads back to this fresh notice; old URLs alone are not
        # proof that a changed notice still designates the same attachment.
        linked = {urljoin(info["official_url"], a.get("href")): a.text_content().strip()
                  for a in root.xpath('//a[@href]')}
        embedded = {urljoin(info["official_url"], value): "embedded PDF"
                    for value in re.findall(r'showVsbpdfIframe\("([^"\n]+\.pdf)"', (ROOT / page).read_text(encoding="utf-8"))}
        linked.update(embedded)
        names = {"competition": [f"competition-attachment-{n}.docx" for n in range(1, 4)],
                 "recommendation": ["recommendation-pdf.pdf"], "retest": ["retest.pdf"],
                 "qinghe": ["qinghe-labs.xlsx", "qinghe-registration.docx"]}.get(key, [])
        attachments = [fetches[name] for name in names]
        archive_name = {"college-scholarship": "college-attachments.zip", "xinghuo": "xinghuo-forms.rar"}.get(key)
        if archive_name:
            attachments.append(next(r for r in read(OLD / "attachment-fetch.json") if r.get("storage_key", "").endswith("/" + archive_name)))
        for item in attachments:
            if item["url"] not in linked:
                raise ValueError(f"Retained attachment no longer linked by notice: {key}")
        info["linked_attachments"] = [{"file": Path(item["storage_key"]).name, "url": item["url"],
                                        "label": linked[item["url"]], "storage_key": item["storage_key"]} for item in attachments]
        if key == "recommendation":
            # Reuse the previously layout-compared four-page extraction only
            # after a fresh download proves that the original PDF is identical.
            if not fetches["recommendation-pdf.pdf"].get("matches_alpha_attachment"):
                raise ValueError("Recommendation PDF changed; redo page-4 layout comparison")
            units = json.loads(json.dumps(old["documents"][key]))
            for unit in units:
                unit["original_file_key"] = (REVIEW / "recommendation-pdf.pdf").as_posix()
            info.update(method="Alpha four-page/table extraction reused after fresh SHA-256 equality",
                        prior_evidence=(OLD / "source-units.json").as_posix(), pdf_pages=4,
                        page4_semantics="既有逐行版式对照保留；未新增人工签核")
        elif key == "retest":
            if digest(REVIEW / "retest.pdf") != "730cc46d2931c7769ca89f153ff3888167f0f08a2aad1e318617a742983bb4b1":
                raise ValueError("Retest PDF changed; redo the dated AI render comparison")
            reader = PdfReader(ROOT / REVIEW / "retest.pdf")
            if len(reader.pages) != 9:
                raise ValueError("Retest PDF page count changed; redo layout review")
            units = []
            for number, pdf_page in enumerate(reader.pages, 1):
                text = (pdf_page.extract_text() or "").strip()
                if len(text) < 100:
                    raise ValueError(f"Retest PDF p.{number} needs OCR; no synthetic body generated")
                units.append({"content": text, "locator": f"PDF p.{number}",
                              "original_file_key": (REVIEW / "retest.pdf").as_posix(),
                              "heading_path": ["2027年接收推免复试；历史批次", f"PDF第{number}页"],
                              "method": "pypdf-complete-page-text; AI-render-comparison; human-review-pending"})
            info.update(pdf_pages=9, extracted_pages=9,
                        layout_review="2026-11-23使用PDFium渲染并AI目视对照9页；第2页招生计划表6行、列顺序及页间续文可见；不等于人工审核",
                        attachment_gap="PDF第9页列出4项复试用表；网页ZIP未转换或纳入正文，不提供填写指导。")
        else:
            units, stats = html_units(ROOT / page)
            attach_headings(units)
            for unit in units:
                unit["original_file_key"] = page.as_posix()
            info["html_extraction"] = stats
            if key == "competition":
                attachment_stats = []
                for number in range(1, 4):
                    name = f"competition-attachment-{number}.docx"
                    if not fetches[name].get("matches_alpha_attachment"):
                        raise ValueError("Competition attachment changed; redo semantic/layout review")
                    rows, counts = word_units(ROOT / REVIEW / name)
                    for unit in rows:
                        unit["original_file_key"] = (REVIEW / name).as_posix()
                        unit["heading_path"] = [f"竞赛级别认定附件{number}"]
                    units.extend(rows)
                    attachment_stats.append({"file": name, **counts})
                info["attachments"] = attachment_stats
                info["notice_check"] = "本次HTTP响应为真实通知正文，已核对校教〔2026〕9号和三附件入口；不使用登录页作证据。网络可达性可能因环境变化。"
            if key == "qinghe":
                units.extend(read(REVIEW / "qinghe-units.json"))
                form_units, form_stats = word_units(ROOT / REVIEW / "qinghe-registration.docx")
                with ZipFile(ROOT / REVIEW / "qinghe-registration.docx") as archive:
                    xml_parts = {name: ET.fromstring(archive.read(name)) for name in archive.namelist() if name.endswith((".xml", ".rels"))}
                    nodes = [n for tree in xml_parts.values() for n in tree.iter()]
                    form_static = {"xml_parts_scanned": len(xml_parts),
                         "all_xml_text_attributes_sha256": sha256(json.dumps([(name, [(n.tag, sorted(n.attrib.items()), n.text or "") for n in tree.iter()]) for name, tree in sorted(xml_parts.items())], ensure_ascii=False).encode()).hexdigest(),
                         "deleted_text_nodes": sum(n.tag.split("}")[-1] == "delText" for n in nodes),
                         "hidden_text_markers": sum(n.tag.split("}")[-1] in {"vanish", "webHidden"} for n in nodes),
                         "comments_or_embedded_binary": [name for name in archive.namelist() if any(s in name.lower() for s in ["comment", "embedding", "vba"])],
                         "office_metadata": "存在原始创建者/最后编辑者及WPS自定义属性；不把编辑者当作申请人，不在摘要复述账号值；原件按官方公开文件保留。"}
                info.update(xlsx_audit=(REVIEW / "qinghe-conversion-audit.json").as_posix(),
                            xlsx_package_static=inspect_xlsx((ROOT / REVIEW / "qinghe-labs.xlsx").read_bytes()),
                            registration_template={"file": "qinghe-registration.docx", "stats": form_stats,
                                                   "static_inspection": form_static,
                                                   "content": [u["content"] for u in form_units],
                                                   "finding": "已提取全部段落及表格检查，为空白报名模板；未发现已填写的申请人记录。保留官方公开联系人；未采集申请数据。",
                                                   "human_review": "pending"})
        info["source_units"] = len(units)
        documents[key], audit[key] = units, info
    # All retained Alpha archive attachments remain pinned to their original
    # hashes and privacy audit. Do not re-download or silently change archives.
    for name in ["college-attachments.zip", "xinghuo-forms.rar"]:
        key = (OLD / name).as_posix()
        inputs[key] = digest(Path(key))
        expected = next(r["sha256"] for r in read(OLD / "attachment-fetch.json") if r.get("storage_key") == key)
        if inputs[key] != expected:
            raise ValueError("Previously privacy-audited archive changed")
    listings = []
    for name in ["college-notices.html", "college-teaching.html", "student-regulations.html"]:
        row = fetches[name]
        root = html.fromstring((ROOT / row["storage_key"]).read_bytes())
        links = []
        for anchor in root.xpath('//a[@href]'):
            label = re.sub(r"\s+", " ", anchor.text_content()).strip()
            if any(word in label for word in ["竞赛", "奖学金", "推免", "青禾", "创新创业", "进实验室"]):
                links.append({"title": label, "url": urljoin(row["url"], anchor.get("href"))})
        listings.append({"source_url": row["url"], "snapshot": row["storage_key"], "sha256": row["sha256"],
                         "matching_links": links,
                         "scope": "仅本次下载的列表页及8份已知正文/关联附件；未遍历分页或全站。未检出替代文件不构成现行有效证明。"})
    write(REVIEW / "source-units.json", {"inputs": inputs, "documents": documents})
    write(REVIEW / "verification-evidence.json", {"checked_on": "2026-11-23", "documents": audit,
          "bounded_version_search": listings, "final_human_review": "pending", "approved_packages": 0})
    print(json.dumps({k: len(v) for k, v in documents.items()}, ensure_ascii=False))


if __name__ == "__main__":
    extract()
