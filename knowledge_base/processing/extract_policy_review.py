"""Rebuild source units from retained official snapshots, without network writes.

Review tooling only: requires lxml and pypdf (available in the desktop bundled
Python). The production Markdown/TXT parser and public contracts are unchanged.
Run from repository root: python -m knowledge_base.processing.extract_policy_review
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "knowledge_base/processing/policy-review/2026-11-19"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(value):
    return re.sub(r"\s+", " ", value).strip()


def html_units(path):
    from lxml import html
    root = html.fromstring(path.read_bytes())
    nodes = root.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," v_news_content ")]')
    if len(nodes) != 1:
        raise ValueError(f"Expected one official content container: {path.name}")
    body = nodes[0]
    for node in body.xpath('.//style|.//script'):
        node.drop_tree()
    units = []
    # Tables stay in original HTML order. Span attributes are explicit rather
    # than silently expanded into invented category values.
    for node in body.xpath('.//p[not(ancestor::table)]|.//table|.//h1|.//h2|.//h3|.//h4'):
        if node.tag == "table":
            rows = []
            for row_no, row in enumerate(node.xpath('.//tr'), 1):
                cells = []
                for cell_no, cell in enumerate(row.xpath('./td|./th'), 1):
                    cells.append({"cell": cell_no, "text": clean(cell.text_content()),
                                  "rowspan": int(cell.get("rowspan", 1)),
                                  "colspan": int(cell.get("colspan", 1))})
                rows.append({"row": row_no, "cells": cells})
            content = "\n".join(
                f"第{r['row']}行：" + "；".join(
                    f"单元格{c['cell']}[rowspan={c['rowspan']},colspan={c['colspan']}]：{c['text']}"
                    for c in r["cells"]) for r in rows)
            units.append({"locator": root.getroottree().getpath(node), "content": content,
                          "method": "html-table-with-explicit-spans", "rows": rows})
        else:
            content = clean(node.text_content())
            if content:
                units.append({"locator": root.getroottree().getpath(node),
                              "content": content, "method": "html-paragraph-whitespace-normalized"})
    # Fail closed if extraction drops visible text outside supported blocks.
    expected = clean(body.text_content()).replace(" ", "")
    covered = "".join(clean(u["content"]).replace(" ", "") for u in units)
    text_nodes = [clean(t).replace(" ", "") for t in body.xpath('.//text()[not(ancestor::style or ancestor::script)]') if clean(t)]
    missing = [t for t in text_nodes if t not in covered]
    if missing:
        raise ValueError(f"Uncovered HTML text in {path.name}: {missing[:3]}")
    return units, {"body_visible_chars": len(expected), "units": len(units), "uncovered_text_nodes": 0}


def word_units(path):
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
        body = root.find(W + "body")
        units, table_stats = [], []
        table_no = para_no = 0
        for child in body:
            if child.tag == W + "p":
                para_no += 1
                content = "".join(n.text or "" for n in child.iter(W + "t"))
                if clean(content):
                    units.append({"locator": f"word/document.xml body/p[{para_no}]", "content": clean(content), "method": "ooxml-paragraph"})
            elif child.tag == W + "tbl":
                table_no += 1
                rows = child.findall(W + "tr")
                stats = {"table": table_no, "rows_including_header": len(rows), "gridSpan": 0, "vMerge": 0}
                header = None
                for row_no, row in enumerate(rows, 1):
                    cells = []
                    for cell in row.findall(W + "tc"):
                        cells.append(clean("\n".join("".join(n.text or "" for n in p.iter(W + "t")) for p in cell.findall(W + "p"))))
                    if header is None:
                        header = cells
                    spans = [{"tag": n.tag.split("}")[-1], "value": n.get(W + "val", "continue")} for n in row.iter() if n.tag in {W + "gridSpan", W + "vMerge"}]
                    stats["gridSpan"] += sum(n["tag"] == "gridSpan" for n in spans)
                    stats["vMerge"] += sum(n["tag"] == "vMerge" for n in spans)
                    content = "表头：" + "；".join(header) + "\n本行：" + "；".join(cells)
                    if spans:
                        content += "\n原合并标记：" + json.dumps(spans, ensure_ascii=False)
                    units.append({"locator": f"word/document.xml table[{table_no}]/row[{row_no}]", "content": content,
                                  "cells": cells, "header": header, "spans": spans, "method": "ooxml-row-with-header"})
                table_stats.append(stats)
        notes = []
        for name in ["word/footnotes.xml", "word/endnotes.xml"]:
            if name not in archive.namelist():
                continue
            for note in ET.fromstring(archive.read(name)):
                if int(note.get(W + "id", "-1")) <= 0:
                    continue  # separator markers are not policy notes
                content = clean("".join(n.text or "" for n in note.iter(W + "t")))
                if content:
                    notes.append({"locator": f"{name} id={note.get(W + 'id')}", "content": content, "method": "ooxml-note"})
        units.extend(notes)
        return units, {"tables": table_stats, "footnotes_and_endnotes": len(notes), "units": len(units)}


def attach_headings(units):
    """Carry verbatim headings, especially teacher vs student 星火 sections."""
    title, section = "", ""
    for unit in units:
        value = unit["content"]
        if len(value) < 70 and (value.endswith("评选细则") or value.endswith("评定管理办法")):
            title, section = value, ""
        elif len(value) < 70 and re.match(r"^(第[一二三四五六七八九十]+章|[一二三四五六七八九十]+、)", value):
            section = value
        unit["heading_path"] = [s for s in [title, section] if s]


def extract():
    from pypdf import PdfReader
    all_units, stats, inputs = {}, {}, {}
    snapshots = {k: REVIEW / f"{k}.html" for k in ["scholarship", "college-scholarship", "xinghuo"]}
    snapshots["competition"] = ROOT / "knowledge_base/政策资料/原始资料/学校/福州大学_2026_大学生学科竞赛级别认定结果.html"
    for key, path in snapshots.items():
        units, stats[key] = html_units(path)
        attach_headings(units)
        for unit in units:
            unit["original_file_key"] = path.relative_to(ROOT).as_posix()
        all_units[key] = units
        inputs[path.relative_to(ROOT).as_posix()] = digest(path)
    for i in range(1, 4):
        path = REVIEW / f"competition-attachment-{i}.docx"
        units, stats[f"competition-attachment-{i}"] = word_units(path)
        for unit in units:
            unit["original_file_key"] = path.relative_to(ROOT).as_posix()
        all_units["competition"].extend(units)
        inputs[path.relative_to(ROOT).as_posix()] = digest(path)
    path = REVIEW / "recommendation-pdf.pdf"
    pdf = PdfReader(path)
    if len(pdf.pages) != 4:
        raise ValueError("Recommendation PDF page count changed; requires fresh layout review")
    units = []
    for page_no, page in enumerate(pdf.pages, 1):
        content = page.extract_text()
        (REVIEW / f"recommendation-page-{page_no}.txt").write_text(content + "\n", encoding="utf-8")
        if page_no < 4:
            units.append({"locator": f"PDF p.{page_no}", "content": content.strip(), "method": "pypdf-page-text-layout-reviewed",
                          "original_file_key": path.relative_to(ROOT).as_posix()})
    # Explicit layout transcription from the retained p.4 image. Never produced
    # by guessing from a flattened table; changes require a new visual review.
    layout = json.loads((REVIEW / "recommendation-page-4-layout.json").read_text(encoding="utf-8"))
    if layout["pdf_sha256"] != digest(path):
        raise ValueError("PDF changed since layout transcription")
    for item in layout["units"]:
        units.append({**item, "method": "visual-layout-transcription-pending-human-signoff",
                      "original_file_key": path.relative_to(ROOT).as_posix()})
    all_units["recommendation"] = units
    inputs[path.relative_to(ROOT).as_posix()] = digest(path)
    inputs[(REVIEW / "recommendation-page-4-layout.json").relative_to(ROOT).as_posix()] = digest(REVIEW / "recommendation-page-4-layout.json")
    for page_no in range(1, 5):
        image = REVIEW / f"recommendation-page-{page_no}.png"
        inputs[image.relative_to(ROOT).as_posix()] = digest(image)
    stats["recommendation"] = {"pages": 4, "layout_reviewed_pages": [1, 2, 3, 4], "human_signoff": False}
    # Inventory ZIP without extracting paths supplied by the archive.
    with zipfile.ZipFile(REVIEW / "college-attachments.zip") as z:
        stats["college-attachment-inventory"] = [{"name": i.filename if i.flag_bits & 0x800 else i.filename.encode("cp437").decode("gbk"), "bytes": i.file_size,
                                                  "parsed": False} for i in z.infolist() if not i.is_dir()]
    dump(REVIEW / "source-units.json", {"inputs": inputs, "documents": all_units})
    dump(REVIEW / "extraction-audit.json", stats)
    print(json.dumps({k: len(v) for k, v in all_units.items()}, ensure_ascii=False))


if __name__ == "__main__":
    extract()
