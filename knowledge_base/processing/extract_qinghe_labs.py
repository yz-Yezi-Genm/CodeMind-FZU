"""Convert this Qinghe attachment only; not a DocumentParser XLSX extension.

Offline extraction requires openpyxl. Preserve original values and coordinates;
fail if this known table layout changes instead of silently losing content.
"""
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "knowledge_base/processing/policy-review/2026-11-23"
HEADERS = ["序号", "实验室名称", "实验室简介（100字左右）", "实验室地点", "联系人", "联系电话或邮箱",
           "计划接收人数\n接收条件", "考核方式", "科研成果与学生典型事迹\n（可附上网页链接）"]


def extract(path):
    import openpyxl
    # WPS stores multiple links within a single cell in customXml, beyond
    # openpyxl's one-hyperlink-per-cell view. Preserve these too; never visit.
    rich_links = {}
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("customXml/") or not name.endswith(".xml"):
                continue
            for node in ET.fromstring(archive.read(name)).iter():
                if node.tag.split("}")[-1] != "hyperlink" or not node.get("ref"):
                    continue
                for child in node:
                    address = child.get("address")
                    if address:
                        rich_links.setdefault(node.get("ref"), []).append(address)
    workbook = openpyxl.load_workbook(path, data_only=False, read_only=False)
    try:
        if workbook.sheetnames != ["Sheet1", "Sheet2", "Sheet3"]:
            raise ValueError("Qinghe workbook sheets changed; inspect source before conversion")
        sheet = workbook["Sheet1"]
        allowed_coordinates = {sheet.cell(row, col).coordinate for row in range(3, 27) for col in range(1, 10)}
        if set(rich_links) - allowed_coordinates:
            raise ValueError("WPS links outside known Qinghe data rows; conversion stopped")
        headers = [str(sheet.cell(2, c).value or "") for c in range(1, 10)]
        if headers != HEADERS:
            raise ValueError("Qinghe columns changed; inspect source before conversion")
        all_cells, units, reviewed_cells = [], [], set()
        for table in workbook:
            for row in table:
                for cell in row:
                    if cell.value is None:
                        continue
                    if cell.data_type == "f":
                        raise ValueError("Formula found; resolve formula/display semantics before conversion")
                    all_cells.append({"sheet": table.title, "cell": cell.coordinate, "value": str(cell.value),
                                      "hyperlink": cell.hyperlink.target if cell.hyperlink else None})
                    if table.title != "Sheet1" or cell.column > 9 or cell.row > 26:
                        raise ValueError("Nonempty content outside known Qinghe table; conversion stopped")
        title = str(sheet["A1"].value)
        title_unit = {"content": title + "\n\n原表字段：" + "；".join(headers), "locator": "Sheet1!A1:I2",
                      "method": "xlsx-title-and-headers", "heading_path": ["原表标题与字段"]}
        units.append(title_unit)
        reviewed_cells.update(("Sheet1", c["cell"]) for c in all_cells if int(''.join(filter(str.isdigit, c['cell']))) <= 2)
        labs = []
        for row in range(3, 27):
            number = sheet.cell(row, 1).value
            name = str(sheet.cell(row, 2).value or "")
            if number != row - 2 or not name.strip():
                raise ValueError("Qinghe lab sequence/name changed; conversion stopped")
            fields = []
            for col, header in enumerate(headers, 1):
                cell = sheet.cell(row, col)
                value = str(cell.value) if cell.value is not None else "（原表空白，未推断）"
                fields.append(f"{header.replace(chr(10), ' ')}（{cell.coordinate}）：\n{value}")
                if cell.hyperlink and cell.hyperlink.target:
                    fields.append(f"原单元格超链接（{cell.coordinate}）：{cell.hyperlink.target}")
                for address in dict.fromkeys(rich_links.get(cell.coordinate, [])):
                    fields.append(f"原WPS富文本超链接（{cell.coordinate}）：{address}")
                if cell.value is not None:
                    reviewed_cells.add(("Sheet1", cell.coordinate))
            # The original publication deadline applies to every resource row.
            context = "适用批次：2026—2027学年青禾计划；学院本科生，另须符合本行接收条件。通知要求2026年10月31日前报名，已过期；表中人数为当时计划，非实时空缺。联系方式为该官方附件发布时的联系渠道，未验证目前可达。报名流程须结合通知，不凭本表推断。"
            units.append({"content": context + "\n\n" + "\n\n".join(fields),
                          "locator": f"Sheet1!A{row}:I{row}", "method": "xlsx-complete-row-with-coordinate-labels",
                          "heading_path": [f"实验室{number:02d}：{name.strip()}"], "lab_no": number})
            labs.append({"lab_no": number, "lab_name": name, "source_range": f"Sheet1!A{row}:I{row}",
                         "missing_cells": [sheet.cell(row, c).coordinate for c in range(1, 10) if sheet.cell(row, c).value is None]})
        if reviewed_cells != {(c["sheet"], c["cell"]) for c in all_cells}:
            raise ValueError("Qinghe nonempty cells lost during conversion")
        return units, {"original_sha256": sha256(path.read_bytes()).hexdigest(), "workbook_sheets": workbook.sheetnames,
                       "empty_sheets": [s.title for s in workbook if not any(c.value is not None for row in s for c in row)],
                       "merged_ranges": {s.title: [str(r) for r in s.merged_cells.ranges] for s in workbook},
                       "hidden_sheets": [s.title for s in workbook if s.sheet_state != "visible"],
                       "hidden_rows": {s.title: [i for i, r in s.row_dimensions.items() if r.hidden] for s in workbook},
                       "hidden_columns": {s.title: [i for i, c in s.column_dimensions.items() if c.hidden] for s in workbook},
                       "nonempty_cells": len(all_cells), "converted_nonempty_cells": len(reviewed_cells),
                       "uncovered_nonempty_cells": 0, "lab_count": len(labs), "labs": labs,
                       "cells": all_cells, "policy_approval": False, "human_approved": False,
                       "wps_rich_text_links": rich_links,
                       "contact_scope": "仅官方公开资源对接联系方式；无申请学生填报数据。原值用于逐单元格转换核对，未另行收集个人资料。"}
    finally:
        workbook.close()


def main():
    path = REVIEW / "qinghe-labs.xlsx"
    units, audit = extract(path)
    fetches = json.loads((REVIEW / "source-fetch.json").read_text(encoding="utf-8"))
    item = next(r for r in fetches if r["name"] == path.name)
    if audit["original_sha256"] != item["sha256"]:
        raise ValueError("Downloaded XLSX hash differs from conversion source")
    audit.update(original_file_key=path.relative_to(ROOT).as_posix(), original_name=item["original_name"],
                 source_url=item["url"], source_page_url=item["parent_url"], published_on="2026-10-16",
                 checked_on="2026-11-23", conversion="全表非空单元格逐项保留；空值显式标记；合并标题不填充为各行属性；额外两空表登记；无公式计算或推断补值")
    for unit in units:
        unit["original_file_key"] = audit["original_file_key"]
    for name, data in [("qinghe-units.json", units), ("qinghe-conversion-audit.json", audit)]:
        (REVIEW / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ("lab_count", "nonempty_cells", "converted_nonempty_cells", "uncovered_nonempty_cells", "empty_sheets")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
