"""Read scholarship form headers/merges without editing official workbooks.

Uses bundled openpyxl for read-only analysis; tar.exe reads individual RAR
members to memory. Old binary DOC is identified, never decoded as plain text.
python -m knowledge_base.processing.inspect_policy_forms
"""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "knowledge_base/processing/policy-review/2026-11-19"


def inspect_workbook(data, header_rows=3):
    import openpyxl
    wb = openpyxl.load_workbook(BytesIO(data), data_only=False, read_only=False)
    try:
        return [{"sheet": sheet.title, "declared_max_row": sheet.max_row,
                 "declared_max_column": sheet.max_column,
                 "merged_ranges": sorted(str(r) for r in sheet.merged_cells.ranges),
                 "headers": [{"cell": c.coordinate, "value": str(c.value)}
                             for row in sheet.iter_rows(min_row=1, max_row=header_rows, max_col=min(sheet.max_column, 40))
                             for c in row if c.value is not None],
                 "inspection_scope": f"前{header_rows}行表头及合并区域；未把示例姓名/电话当成真实申请数据；未计算公式或批准政策"}
                for sheet in wb]
    finally:
        wb.close()


def inspect():
    records = []
    archive = REVIEW / "college-attachments.zip"
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            if member.is_dir():
                continue
            name = member.filename if member.flag_bits & 0x800 else member.filename.encode("cp437").decode("gbk")
            data = z.read(member)
            records.append({"archive": archive.relative_to(ROOT).as_posix(), "member": name,
                            "member_sha256": sha256(data).hexdigest(), "bytes": len(data),
                            "status": "headers_and_merges_extracted", "sheets": inspect_workbook(data)})
    archive = REVIEW / "xinghuo-forms.rar"
    listing = subprocess.run(["tar", "-tf", str(archive)], capture_output=True, check=True)
    # The Windows bsdtar process uses the system Chinese code page for names.
    try:
        names = listing.stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        names = listing.stdout.decode("gb18030").splitlines()
    for name in names:
        if not name.lower().endswith((".doc", ".xlsx")):
            continue
        # stdout-only extraction; untrusted member names never become disk paths.
        result = subprocess.run(["tar", "-xOf", str(archive), "--", name], capture_output=True, check=True)
        data = result.stdout
        record = {"archive": archive.relative_to(ROOT).as_posix(), "member": name,
                  "member_sha256": sha256(data).hexdigest(), "bytes": len(data)}
        if name.lower().endswith(".xlsx"):
            record.update(status="headers_and_merges_extracted", sheets=inspect_workbook(data, header_rows=2))
        else:
            record.update(status="legacy_doc_requires_reliable_conversion",
                          ole_compound_signature_matches=data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")),
                          reason="本机未安装可用的Word/LibreOffice/antiword转换器；不从二进制猜正文，待有转换工具的人工导出可选中文本或DOCX后核对")
        records.append(record)
    value = {"checked_on": "2026-11-19", "original_archives_unchanged": True,
             "workbook_headers_extracted": sum(r["status"] == "headers_and_merges_extracted" for r in records),
             "legacy_doc_pending": sum(r["status"] == "legacy_doc_requires_reliable_conversion" for r in records),
             "policy_approval": False, "records": records}
    (REVIEW / "form-attachment-audit.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in value.items() if k != "records"}, ensure_ascii=False))


if __name__ == "__main__":
    inspect()
