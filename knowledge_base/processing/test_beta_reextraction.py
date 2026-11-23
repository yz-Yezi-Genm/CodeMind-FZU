"""Read-only raw re-extraction and coordinated derived-file tamper regression."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import asyncio

from knowledge_base.processing import build_beta_policy_review as build
from knowledge_base.processing import reextract_beta_policy_review as raw


class RawReextractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = build.read(build.REVIEW / "source-units.json")

    def test_reextracts_all_originals_exactly_without_writes_or_network(self):
        with patch("socket.create_connection", side_effect=AssertionError("offline check must not connect")), \
             patch.object(Path, "write_text", side_effect=AssertionError("check must not overwrite evidence")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("check must not overwrite evidence")):
            report = raw.verify_reextraction(build.ROOT, self.sources)
        self.assertEqual(report["documents"], 8)
        self.assertEqual(report["source_units"], 501)
        self.assertEqual(report["qinghe_lab_rows"], 24)
        self.assertEqual(report["qinghe_nonempty_cells"], 226)
        self.assertEqual(report["qinghe_wps_links"], 40)

    def test_each_retained_document_change_fails_against_raw_bytes(self):
        documents, qinghe_units, audit = raw.reextract_documents(build.ROOT)
        # Reuse the freshly read raw results in this multi-case comparison only;
        # the previous test exercises the complete unmocked file-reading path.
        with patch.object(raw, "reextract_documents", return_value=(documents, qinghe_units, audit)):
            for key in raw.KEYS:
                with self.subTest(key=key):
                    changed = deepcopy(self.sources)
                    changed["documents"][key][0]["content"] += "FORGED POLICY"
                    with self.assertRaisesRegex(ValueError, f"Raw re-extraction mismatch: {key}"):
                        raw.verify_reextraction(build.ROOT, changed)

    def test_pdf_table_cells_and_scores_are_reextracted_from_pdf(self):
        units = raw.recommendation_units(build.ROOT)
        self.assertEqual(units, self.sources["documents"]["recommendation"])
        # No retained layout transcription or source-unit JSON is an input.
        with patch.object(Path, "read_text", side_effect=AssertionError("must not copy saved JSON")):
            self.assertEqual(raw.recommendation_units(build.ROOT), units)
        changed = deepcopy(self.sources)
        changed["documents"]["recommendation"][4]["cells"][2] = "999"
        with self.assertRaisesRegex(ValueError, "Raw re-extraction mismatch: recommendation"):
            raw.verify_reextraction(build.ROOT, changed)

    def test_xlsx_full_cells_and_rich_links_match_retained_audit(self):
        _, units, audit = raw.reextract_documents(build.ROOT)
        saved_units = build.read(build.REVIEW / "qinghe-units.json")
        saved_audit = build.read(build.REVIEW / "qinghe-conversion-audit.json")
        self.assertEqual(units, saved_units)
        for field, value in audit.items():
            self.assertEqual(value, saved_audit[field], field)
        for cell in audit["cells"]:
            self.assertIn(cell["value"], "\n".join(u["content"] for u in units), cell["cell"])

    def test_xlsx_original_change_with_updated_hash_still_fails_content_comparison(self):
        import openpyxl
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(build.ROOT / build.REVIEW, root / build.REVIEW)
            path = root / build.REVIEW / "qinghe-labs.xlsx"
            workbook = openpyxl.load_workbook(path)
            workbook["Sheet1"]["C3"] = "CHANGED ORIGINAL RESEARCH DIRECTION"
            workbook.save(path)
            workbook.close()
            sources = deepcopy(self.sources)
            sources["inputs"][(build.REVIEW / "qinghe-labs.xlsx").as_posix()] = sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "Raw re-extraction mismatch: qinghe"):
                raw.verify_reextraction(root, sources)

    def test_regenerated_forged_outputs_cannot_mask_unchanged_xlsx_original(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Copy only this batch, the pinned older attachments and the import
            # preview. All regeneration writes below stay inside this temp root.
            for area in [build.REVIEW, build.OLD]:
                shutil.copytree(build.ROOT / area, root / area)
            preview = Path("docs/assignment-02/database-design/knowledge-base/入库预览_44条.json")
            (root / preview).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(build.ROOT / preview, root / preview)
            sources = deepcopy(self.sources)
            sources["documents"]["qinghe"][11]["content"] += "\nFORGED EXTRA ADMISSION CONDITION"
            (root / build.REVIEW / "source-units.json").write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
            # Markdown, DTO, hashes and mappings are now all mutually consistent.
            with patch.object(build, "ROOT", root):
                build.build()
                with self.assertRaisesRegex(ValueError, "Raw re-extraction mismatch: qinghe"):
                    asyncio.run(build.check())

    def test_standalone_qinghe_units_or_cell_audit_tampering_fails(self):
        documents, units, audit = raw.reextract_documents(build.ROOT)
        real_read = Path.read_text
        for name, mutate, label in [
            ("qinghe-units.json", lambda d: d[1].__setitem__("content", "forged"), "qinghe-units.json"),
            ("qinghe-conversion-audit.json", lambda d: d["cells"][12].__setitem__("value", "forged"), "qinghe audit cells"),
            ("qinghe-conversion-audit.json", lambda d: d["wps_rich_text_links"].clear(), "qinghe audit wps_rich_text_links")]:
            def altered_read(path, *args, **kwargs):
                text = real_read(path, *args, **kwargs)
                if path == build.ROOT / build.REVIEW / name:
                    data = json.loads(text)
                    mutate(data)
                    return json.dumps(data, ensure_ascii=False)
                return text
            with self.subTest(file=name, field=label), \
                 patch.object(raw, "reextract_documents", return_value=(documents, units, audit)), \
                 patch.object(Path, "read_text", new=altered_read):
                with self.assertRaisesRegex(ValueError, f"Raw re-extraction mismatch: {label}"):
                    raw.verify_reextraction(build.ROOT, self.sources)


if __name__ == "__main__":
    unittest.main()
