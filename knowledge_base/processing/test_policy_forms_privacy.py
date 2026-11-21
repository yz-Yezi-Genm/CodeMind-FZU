"""Privacy inspection must include hidden/later rows and avoid publishing values."""
from io import BytesIO
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import zipfile

from knowledge_base.processing import audit_policy_forms as audit


def workbook():
    ns = audit.NS["s"]
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" state="veryHidden" r:id="r1"/></sheets><definedNames><definedName name="private">PRIVATE_DEFINED_VALUE</definedName></definedNames></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{ns}"><cols><col min="2" max="3" hidden="1"/></cols><sheetData><row r="2"><c r="A2" t="inlineStr"><is><t>姓名</t></is></c></row><row r="99" hidden="1"><c r="B99" t="s"><v>0</v></c><c r="C99"><f>PRIVATE_FORMULA</f><v>12345678901</v></c></row></sheetData></worksheet>')
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{ns}"><si><t>PRIVATE_NAME</t></si><si><t>UNUSED_PRIVATE_NAME</t></si></sst>')
        z.writestr("xl/comments1.xml", '<comments><comment>PRIVATE_COMMENT</comment></comments>')
        z.writestr("docProps/core.xml", '<properties><creator>PRIVATE_CREATOR</creator></properties>')
        z.writestr("xl/media/image1.png", b"binary-privacy-evidence")
    return stream.getvalue()


class FormPrivacyTests(unittest.TestCase):
    def test_all_cells_hidden_rows_columns_and_sheets_are_scanned(self):
        obj = audit.inspect_xlsx(workbook())
        sheet = obj["sheets"][0]
        self.assertEqual(sheet["state"], "veryHidden")
        self.assertEqual(sheet["hidden_rows"], ["99"])
        self.assertEqual(sheet["hidden_column_ranges"], [{"min": "2", "max": "3"}])
        self.assertEqual(sheet["populated_rows"][-1]["cells"], ["B99", "C99"])
        self.assertEqual(sheet["formula_cells"], 1)

    def test_unused_strings_comments_properties_and_binaries_are_not_ignored(self):
        obj = audit.inspect_xlsx(workbook())
        self.assertEqual(obj["unused_shared_strings"], 1)
        self.assertEqual(obj["comment_parts"], 1)
        self.assertEqual(obj["office_properties_present"], ["docProps/core.xml"])
        self.assertEqual(obj["binary_parts"][0]["part"], "xl/media/image1.png")

    def test_report_never_contains_sensitive_cell_or_property_values(self):
        serialized = json.dumps(audit.inspect_xlsx(workbook()))
        for secret in ("PRIVATE_NAME", "12345678901", "PRIVATE_CREATOR", "PRIVATE_COMMENT", "PRIVATE_FORMULA", "PRIVATE_DEFINED_VALUE"):
            self.assertNotIn(secret, serialized)

    def test_changed_or_extra_member_requires_new_review(self):
        old = {"archive": "a.zip", "member": "form.xlsx", "member_sha256": "a", "inspection": {}, "content_assessment": {}}
        for current in ({**old, "member_sha256": "b"}, {**old, "member": "extra.xlsx"}):
            with self.assertRaises(ValueError):
                audit.validate_against_baseline([current], {"records": [old]})
        with self.assertRaises(ValueError):
            audit.validate_against_baseline([], {"records": [old]})

    def test_doc_converter_includes_hidden_removed_text_and_rejects_warnings(self):
        result = subprocess.CompletedProcess([], 0, b"blank template", b"")
        with patch.object(audit.subprocess, "run", return_value=result) as run:
            audit.convert_doc_text(Path("input.doc"), "antiword", None)
            self.assertTrue({"-r", "-s", "-t"}.issubset(set(run.call_args.args[0])))
        result.stderr = b"private conversion warning"
        with patch.object(audit.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "privacy review incomplete") as error:
                audit.convert_doc_text(Path("input.doc"), "antiword", None)
            self.assertNotIn("private conversion warning", str(error.exception))

    def test_current_archives_match_full_reviewed_baseline(self):
        baseline = json.loads((audit.REVIEW / "form-privacy-baseline.json").read_text(encoding="utf-8"))
        records = []
        for item in baseline["archives"]:
            path = audit.ROOT / item["file"]
            self.assertEqual(audit.digest(path.read_bytes()), item["sha256"])
            for name, data in audit.archive_members(path):
                previous = next(r for r in baseline["records"] if r["archive"] == path.name and r["member"] == name)
                inspection = audit.inspect_xlsx(data) if name.endswith(".xlsx") else previous["inspection"]
                records.append({"archive": path.name, "member": name, "member_sha256": audit.digest(data), "inspection": inspection})
        audit.validate_against_baseline(records, baseline)
        self.assertEqual(len(records), 8)
        self.assertTrue(all(not r["content_assessment"]["real_applicant_records_found"] for r in records))
        # DOC conversion is separately run with actual optional tools, not mocked
        # or claimed as re-executed by this stdlib-only baseline integrity test.


if __name__ == "__main__":
    unittest.main()
