"""Known-workbook extraction regression; requires openpyxl in review tools only."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import openpyxl
from knowledge_base.processing.extract_qinghe_labs import REVIEW, extract


class QingheWorkbookTests(unittest.TestCase):
    def test_complete_workbook_merges_and_empty_sheets(self):
        units, audit = extract(REVIEW / "qinghe-labs.xlsx")
        self.assertEqual(len(units), 25)
        self.assertEqual(audit["lab_count"], 24)
        self.assertEqual(audit["merged_ranges"]["Sheet1"], ["A1:I1"])
        self.assertEqual(audit["nonempty_cells"], audit["converted_nonempty_cells"])
        self.assertEqual(audit["empty_sheets"], ["Sheet2", "Sheet3"])

    def altered_workbook(self, mutate, expected_error):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "altered.xlsx"
            wb = openpyxl.load_workbook(REVIEW / "qinghe-labs.xlsx")
            mutate(wb)
            wb.save(path)
            wb.close()
            with self.assertRaisesRegex(ValueError, expected_error):
                extract(path)

    def test_changed_headers_fail(self):
        self.altered_workbook(lambda w: setattr(w["Sheet1"]["B2"], "value", "新字段"), "columns changed")

    def test_hidden_extra_content_is_not_silently_omitted(self):
        def mutate(wb):
            wb["Sheet2"]["A1"] = "additional policy content"
            wb["Sheet2"].sheet_state = "hidden"
        self.altered_workbook(mutate, "outside known")

    def test_formulas_require_review_instead_of_inferred_value(self):
        self.altered_workbook(lambda w: setattr(w["Sheet1"]["G3"], "value", "=1+2"), "Formula found")

    def test_missing_field_explicitly_marked(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.xlsx"
            wb = openpyxl.load_workbook(REVIEW / "qinghe-labs.xlsx")
            wb["Sheet1"]["F3"] = None
            wb.save(path)
            wb.close()
            units, audit = extract(path)
            self.assertIn("F3", audit["labs"][0]["missing_cells"])
            self.assertIn("原表空白，未推断", units[1]["content"])


if __name__ == "__main__":
    unittest.main()
