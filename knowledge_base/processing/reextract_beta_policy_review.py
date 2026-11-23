"""Read-only, offline raw originals -> retained source-unit verification.

No reads of Markdown/packages as extraction inputs, no network and no writes.
Install requirements-beta-review.txt alongside the backend review environment.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from knowledge_base.processing.extract_policy_review import attach_headings, html_units, word_units
from knowledge_base.processing.extract_qinghe_labs import extract as extract_qinghe

REVIEW = Path("knowledge_base/processing/policy-review/2026-11-23")
KEYS = ("competition", "scholarship", "college-scholarship", "xinghuo",
        "recommendation", "innovation", "retest", "qinghe")


def compact(text):
    return re.sub(r"\s+", "", text)


def recommendation_units(root):
    """Re-extract p.1-3 text and p.4 spatial cells; never copy a transcription.

    Coordinates describe ONLY this hash-pinned, already reviewed four-page PDF.
    The legacy representation repeats merged headers, strips whitespace and
    the competition score suffix 分, and normalizes the note's ASCII comma.
    作者条件 is an editorial column label, not a quotation of a PDF header.
    """
    from pypdf import PdfReader
    import pdfplumber
    from pdfplumber.utils import extract_text
    key = (REVIEW / "recommendation-pdf.pdf").as_posix()
    path = root / key
    if sha256(path.read_bytes()).hexdigest() != "39e96e8a22588c1b1b1d8fed10144df40df417b54a64ed1278395c6f85ed8fa7":
        raise ValueError("Recommendation PDF changed; redo spatial/layout review")
    reader = PdfReader(path)
    if len(reader.pages) != 4:
        raise ValueError("Recommendation PDF must have four pages")
    units = [{"locator": f"PDF p.{n}", "content": reader.pages[n-1].extract_text().strip(),
              "method": "pypdf-page-text-layout-reviewed", "original_file_key": key} for n in range(1, 4)]
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[3]
        covered = set()
        def region(x0, top, x1, bottom):
            selected = [(i, c) for i, c in enumerate(page.chars)
                        if x0 <= (c["x0"] + c["x1"]) / 2 < x1
                        and top <= (c["top"] + c["bottom"]) / 2 < bottom]
            covered.update(i for i, _ in selected)
            return compact(extract_text([c for _, c in selected]) or "")
        def add(locator, content, cells=None):
            item = {"locator": f"PDF p.4 {locator}", "content": content,
                    "method": "visual-layout-transcription-pending-human-signoff", "original_file_key": key}
            if cells is not None:
                item["cells"] = cells
            units.append(item)
        add("附件1标题", region(75, 70, 525, 90))
        title = region(75, 100, 525, 120)
        headers = [region(116, 120, 200, 175), region(200, 120, 336, 175)]
        score_header = region(336, 120, 479, 148)
        headers += [score_header + "：" + region(336, 148, 400, 175),
                    score_header + "：" + region(400, 148, 479, 175)]
        for group, bounds in enumerate([(175, 251), (251, 326)]):
            level = region(116, bounds[0], 200, bounds[1])
            starts = [176, 196, 215, 234] if group == 0 else [252, 271, 289, 308]
            ends = [196, 215, 234, 251] if group == 0 else [271, 289, 308, 326]
            for offset, (start, end) in enumerate(zip(starts, ends), 1):
                cells = [level, region(200, start, 336, end),
                         region(336, start, 400, end).removesuffix("分"),
                         region(400, start, 479, end).removesuffix("分")]
                content = title + "\n|" + "|".join(headers) + "|\n|---|---|---|---|\n|" + "|".join(cells) + "|"
                add(f"{title} 第{group * 4 + offset}个数据行", content, cells)
        add("学科竞赛表下注", region(75, 326, 525, 393).replace(",", "，"))
        title = region(75, 400, 525, 420)
        headers = [region(91, 420, 134, 451), region(134, 420, 448, 451), "作者条件", region(448, 420, 505, 451)]
        project = region(91, 451, 134, 643)
        for number, (start, end) in enumerate([(451, 500), (500, 548), (548, 596), (596, 643)], 1):
            cells = [project, region(134, start, 345, end), region(345, start, 448, end), region(448, start, 505, end)]
            content = title + "\n|" + "|".join(headers) + "|\n|---|---|---|---|\n|" + "|".join(cells) + "|"
            add(f"{title} 第{number}个数据行", content)
        add("志愿服务条款（原文边界待释义）", region(75, 650, 525, 698))
        add("参军入伍条款", region(75, 700, 525, 730))
        add("国际组织实习条款（保留原文缺闭合书名号）", region(75, 730, 525, 770))
        missing = [c for i, c in enumerate(page.chars) if i not in covered and c["top"] < 770 and c["text"].strip()]
        if missing:
            raise ValueError("Recommendation p.4 contains text outside reviewed spatial regions")
    return units


def reextract_documents(root):
    """Re-read the actual HTML/DOCX/PDF/XLSX bytes; do not read source-units."""
    from pypdf import PdfReader
    documents, qinghe_audit, qinghe_units = {}, None, None
    for key in KEYS:
        if key == "recommendation":
            documents[key] = recommendation_units(root)
            continue
        if key == "retest":
            original = (REVIEW / "retest.pdf").as_posix()
            reader = PdfReader(root / original)
            if len(reader.pages) != 9:
                raise ValueError("Retest PDF must have nine pages")
            units = []
            for number, page in enumerate(reader.pages, 1):
                text = (page.extract_text() or "").strip()
                if len(text) < 100:
                    raise ValueError(f"Retest PDF p.{number} needs OCR")
                units.append({"content": text, "locator": f"PDF p.{number}", "original_file_key": original,
                              "heading_path": ["2027年接收推免复试；历史批次", f"PDF第{number}页"],
                              "method": "pypdf-complete-page-text; AI-render-comparison; human-review-pending"})
        else:
            original = REVIEW / f"{key}.html"
            units, _ = html_units(root / original)
            attach_headings(units)
            for unit in units:
                unit["original_file_key"] = original.as_posix()
            if key == "competition":
                for number in range(1, 4):
                    original = REVIEW / f"competition-attachment-{number}.docx"
                    rows, _ = word_units(root / original)
                    for unit in rows:
                        unit.update(original_file_key=original.as_posix(), heading_path=[f"竞赛级别认定附件{number}"])
                    units.extend(rows)
            if key == "qinghe":
                original = REVIEW / "qinghe-labs.xlsx"
                qinghe_units, qinghe_audit = extract_qinghe(root / original)
                for unit in qinghe_units:
                    unit["original_file_key"] = original.as_posix()
                units.extend(qinghe_units)
        documents[key] = units
    return documents, qinghe_units, qinghe_audit


def assert_exact(actual, retained, label):
    # Exact JSON values/types; dictionary key order and serialization whitespace
    # are irrelevant. Do not print policy/contact text on mismatch.
    if json.dumps(actual, ensure_ascii=False, sort_keys=True) != json.dumps(retained, ensure_ascii=False, sort_keys=True):
        raise ValueError(f"Raw re-extraction mismatch: {label}")


def verify_reextraction(root, sources):
    documents, qinghe_units, audit = reextract_documents(root)
    if set(documents) != set(sources["documents"]):
        raise ValueError("Raw re-extraction mismatch: document inventory")
    for key, units in documents.items():
        assert_exact(units, sources["documents"][key], key)
    retained_qinghe = json.loads((root / REVIEW / "qinghe-units.json").read_text(encoding="utf-8-sig"))
    assert_exact(qinghe_units, retained_qinghe, "qinghe-units.json")
    saved_audit = json.loads((root / REVIEW / "qinghe-conversion-audit.json").read_text(encoding="utf-8-sig"))
    for field, value in audit.items():
        assert_exact(value, saved_audit.get(field), f"qinghe audit {field}")
    return {"documents": len(documents), "source_units": sum(map(len, documents.values())),
            "by_document": {key: len(units) for key, units in documents.items()},
            "qinghe_lab_rows": audit["lab_count"], "qinghe_nonempty_cells": audit["nonempty_cells"],
            "qinghe_wps_links": sum(map(len, audit["wps_rich_text_links"].values())),
            "recommendation_page4": "re-read spatial PDF characters; all non-footer text covered",
            "method": "offline originals re-extracted in memory; exact unit/field comparison; no writes"}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    sources = json.loads((root / REVIEW / "source-units.json").read_text(encoding="utf-8-sig"))
    print(json.dumps(verify_reextraction(root, sources), ensure_ascii=False, indent=2))
