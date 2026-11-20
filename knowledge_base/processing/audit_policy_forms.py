"""Snapshot-specific privacy evidence; never approves a policy or enables retrieval.

Reads every archive member, worksheet cell and OOXML text part. Binary DOC needs
antiword (-r/-s includes removed/hidden text), olefile and oletools. Nothing runs
Office, formulas, hyperlinks or VBA. Reports contain counts/locations/digests,
never cell values, extracted DOC text or author identifiers.

The checked-in baseline binds the recorded AI review to exact member bytes.
It is NOT a generic PII detector: any changed/extra member requires a new review.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from importlib.metadata import version
import os
from pathlib import Path
import posixpath
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "knowledge_base/processing/policy-review/2026-11-19"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def digest(data):
    return sha256(data).hexdigest()


def decode_listing(data):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gb18030")


def archive_members(path):
    """Read members to memory, never use member names as filesystem paths."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                if not item.is_dir():
                    name = item.filename if item.flag_bits & 0x800 else item.filename.encode("cp437").decode("gbk")
                    yield name, archive.read(item)
    else:
        listing = subprocess.run(["tar", "-tf", str(path)], capture_output=True, check=True)
        names = decode_listing(listing.stdout).splitlines()
        for name in names:
            # bsdtar can list a RAR directory without a trailing slash.
            is_directory = name.endswith("/") or any(n.startswith(name + "/") for n in names)
            if not is_directory:
                result = subprocess.run(["tar", "-xOf", str(path), "--", name], capture_output=True, check=True)
                yield name, result.stdout


def inspect_xlsx(data):
    with zipfile.ZipFile(BytesIO(data)) as z:
        parts = {n: ET.fromstring(z.read(n)) for n in z.namelist() if n.endswith((".xml", ".rels"))}
        strings = ["".join(t.text or "" for t in si.iterfind(".//s:t", NS))
                   for si in parts.get("xl/sharedStrings.xml", [])]
        relations = {e.attrib["Id"]: e.attrib["Target"] for e in parts["xl/_rels/workbook.xml.rels"]}
        used_strings, sheets = set(), []
        for sheet in parts["xl/workbook.xml"].findall("s:sheets/s:sheet", NS):
            target = relations[sheet.attrib[REL]]
            target = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            xml = parts[target]
            rows, hidden, formulas = [], [], 0
            for row in xml.findall("s:sheetData/s:row", NS):
                populated = []
                if row.get("hidden") == "1":
                    hidden.append(row.attrib["r"])
                for cell in row.findall("s:c", NS):
                    value = cell.findtext("s:v", default="", namespaces=NS)
                    if cell.get("t") == "s" and value:
                        index = int(value)
                        used_strings.add(index)
                        value = strings[index]
                    elif cell.get("t") == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iterfind(".//s:t", NS))
                    formula = cell.findtext("s:f", default="", namespaces=NS)
                    formulas += cell.find("s:f", NS) is not None
                    if value or formula:
                        populated.append((cell.attrib["r"], value, formula))
                if populated:
                    rows.append({"row": int(row.attrib["r"]), "cells": [v[0] for v in populated],
                                 "content_sha256": digest(json.dumps(populated, ensure_ascii=False).encode())})
            sheets.append({"sheet": sheet.attrib["name"], "state": sheet.get("state", "visible"),
                           "populated_rows": rows, "nonempty_cells": sum(len(r["cells"]) for r in rows),
                           "hidden_rows": hidden,
                           "hidden_column_ranges": [{"min": c.get("min"), "max": c.get("max")}
                                                    for c in xml.findall("s:cols/s:col", NS) if c.get("hidden") == "1"],
                           "formula_cells": formulas,
                           "merged_ranges": [c.attrib["ref"] for c in xml.findall("s:mergeCells/s:mergeCell", NS)]})
        # Include unused shared strings, comments, footers, defined names,
        # metadata and external relationship targets, even when not visible.
        all_text = [(n, [(e.tag, sorted(e.attrib.items()), e.text or "") for e in xml.iter()])
                    for n, xml in sorted(parts.items())]
        binary_parts = [n for n in z.namelist() if not n.endswith((".xml", ".rels", "/"))]
        return {"kind": "xlsx", "sheets": sheets, "xml_parts_scanned": len(parts),
                "all_xml_text_and_attributes_sha256": digest(json.dumps(all_text, ensure_ascii=False).encode()),
                "shared_string_entries": len(strings), "unused_shared_strings": len(set(range(len(strings))) - used_strings),
                "comment_parts": sum("comment" in n.lower() for n in parts),
                "external_relationships": sum(e.get("TargetMode") == "External" for xml in parts.values() for e in xml.iter()),
                "binary_parts": [{"part": n, "sha256": digest(z.read(n))} for n in binary_parts],
                "office_properties_present": sorted(n for n in parts if n.startswith("docProps/"))}


def convert_doc_text(source, antiword, antiword_home):
    """Fail closed on conversion errors/warnings, without echoing private text."""
    env = os.environ.copy()
    if antiword_home:
        env["ANTIWORDHOME"] = str(antiword_home)
    command = [str(antiword), "-t", "-r", "-s", "-m", "UTF-8.txt", str(source)]
    converted = subprocess.run(command, capture_output=True, env=env, timeout=60)
    if converted.returncode or converted.stderr or not converted.stdout.strip():
        raise ValueError("DOC conversion failed or emitted a warning; privacy review incomplete")
    converted.stdout.decode("utf-8", errors="strict")
    return converted.stdout


def inspect_doc(data, antiword, antiword_home):
    import olefile
    from oletools.olevba import VBA_Parser

    with tempfile.TemporaryDirectory(prefix="codemind-form-") as tmp:
        source = Path(tmp) / "input.doc"
        source.write_bytes(data)
        # -r shows removed text; -s shows hidden Word text. Use no Office COM.
        converted = convert_doc_text(source, antiword, antiword_home)
        text = converted.decode("utf-8", errors="strict")
        with olefile.OleFileIO(BytesIO(data)) as ole:
            streams = [{"stream": "/".join(n), "sha256": digest(ole.openstream(n).read())} for n in ole.listdir()]
            meta = ole.get_metadata()
            properties = {key: bool(getattr(meta, key, None)) for key in
                          ("author", "last_saved_by", "title", "subject", "keywords", "comments")}
        parser = VBA_Parser(str(source))
        try:
            macros = []
            for _, _, name, code in parser.extract_macros():
                if name == "VBA_P-code.txt":
                    # pcodedmp prepends the temporary input filename. Normalize
                    # that generated header only; preserve all actual code.
                    header, separator, body = code.partition("\n")
                    if not header.startswith("' Processing file: ") or not separator:
                        raise ValueError("Unexpected P-code report header; review required")
                    code = "' Processing file: <INPUT_DOC>\n" + body
                raw = code.encode("utf-8") if isinstance(code, str) else code
                macros.append({"module": name, "sha256": digest(raw), "bytes": len(raw)})
        finally:
            parser.close()
    return {"kind": "legacy_doc", "text_sha256": digest(converted), "text_characters": len(text),
            "nonempty_text_lines": sum(bool(s.strip()) for s in text.splitlines()),
            "removed_and_hidden_text_included": True, "ole_streams": streams,
            "office_property_presence": properties, "static_vba_and_pcode": macros,
            "office_or_macros_executed": False}


def validate_against_baseline(records, baseline):
    expected = {(r["archive"], r["member"]): r for r in baseline["records"]}
    actual = {(r["archive"], r["member"]): r for r in records}
    if len(actual) != len(records) or actual.keys() != expected.keys():
        raise ValueError("Archive member set changed; full privacy review required")
    for key, record in actual.items():
        old = expected[key]
        if record["member_sha256"] != old["member_sha256"]:
            raise ValueError("Archive member bytes changed; full privacy review required")
        if record["inspection"] != old["inspection"]:
            raise ValueError("Inspection evidence differs; review tool/output change before accepting")
        record["content_assessment"] = old["content_assessment"]


def run(antiword, antiword_home, baseline_path, output):
    records, archives = [], []
    for name in ("college-attachments.zip", "xinghuo-forms.rar"):
        archive = REVIEW / name
        archives.append({"file": archive.relative_to(ROOT).as_posix(), "sha256": digest(archive.read_bytes())})
        for member, data in archive_members(archive):
            suffix = Path(member).suffix.lower()
            if suffix not in {".xlsx", ".doc"}:
                raise ValueError("Unexpected archive member; full privacy review required")
            inspection = inspect_xlsx(data) if suffix == ".xlsx" else inspect_doc(data, antiword, antiword_home)
            records.append({"archive": name, "member": member, "member_sha256": digest(data),
                            "bytes": len(data), "inspection": inspection})
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if archives != baseline["archives"]:
        raise ValueError("Archive bytes changed; download/privacy evidence must be reviewed")
    validate_against_baseline(records, baseline)
    kinds = Counter(r["inspection"]["kind"] for r in records)
    toolchain = dict(baseline["toolchain"])
    executable = shutil.which(str(antiword))
    if not executable:
        raise ValueError("antiword executable not found")
    toolchain.update(antiword="UTF-8 -t -r -s; exact executable digest below",
                     antiword_sha256=digest(Path(executable).read_bytes()),
                     olefile=version("olefile"), oletools=version("oletools"))
    value = {"checked_on": "2026-11-20", "review_method": "full-content tool extraction and AI comparison; team re-review pending",
             "policy_approval": False, "human_approved": False, "retrieval_status_changed": False,
             "conclusion": "本快照未发现真实申请人/教师的已填写个人记录；只有空白模板及占位示例。仅为附件隐私复审材料，不代表政策人工放行。",
             "toolchain": toolchain,
             "archives": archives, "workbooks": kinds["xlsx"],
             "worksheets": sum(len(r["inspection"].get("sheets", [])) for r in records),
             "legacy_docs": kinds["legacy_doc"], "records": records}
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in value.items() if k not in {"records", "archives"}}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--antiword", default="antiword")
    parser.add_argument("--antiword-home", type=Path)
    parser.add_argument("--baseline", type=Path, default=REVIEW / "form-privacy-baseline.json")
    parser.add_argument("--output", type=Path, default=REVIEW / "form-privacy-audit.json")
    args = parser.parse_args()
    run(args.antiword, args.antiword_home, args.baseline, args.output)


if __name__ == "__main__":
    main()
