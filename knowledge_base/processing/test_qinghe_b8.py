"""B8 true-source split, metadata/routing and unapproved evidence regression."""
from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from knowledge_base.processing import build_qinghe_b8 as b8
from knowledge_base.processing import build_beta_policy_review as baseline


class QingheB8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared = b8.prepare()  # real original re-extraction, not saved units

    def check_tamper(self, path, mutate, error):
        original_read = b8.read
        def changed(candidate):
            value = original_read(candidate)
            if candidate == path:
                mutate(value)
            return value
        with patch.object(b8, "read", side_effect=changed), patch.object(b8, "prepare", return_value=self.prepared):
            with self.assertRaisesRegex(ValueError, error):
                b8.check()

    def test_two_packages_24_chunks_each_real_index_and_blocked_gates(self):
        result = b8.check()
        self.assertEqual((result["packages"], result["chunks"]), (2, 48))
        self.assertEqual((result["enabled_packages"], result["human_approved_packages"]), (0, 0))
        self.assertTrue(all(r["indexed_chunks"] == 24 and r["chunk_lookups_hidden"] == 24 for r in result["index_checks"]))

    def test_distinct_record_identities_exact_categories_and_only_s4(self):
        identities = set()
        for category in ["R3", "R4"]:
            metadata = b8.read(b8.OUTPUT / f"qinghe-{category.lower()}.json")["metadata"]
            identities.add((metadata["record_code"], metadata["version_no"]))
            self.assertEqual(metadata["category_name"], b8.CATEGORIES[category])
            self.assertEqual(metadata["business_direction_codes"], ["COLLEGE_RESOURCES"])
            self.assertEqual(metadata["temporal_notes"]["beta_domains"], ["S4"])
            self.assertFalse(metadata["temporal_notes"]["human_approved"])
        self.assertEqual(len(identities), 2)

    def test_r3_deadline_five_keys_and_r4_historical_intro_limits(self):
        r3 = self.prepared["R3"]["metadata"]
        r4 = self.prepared["R4"]["metadata"]
        self.assertEqual(r3.deadline_on.isoformat(), "2026-10-31")
        self.assertEqual(r3.timeliness_verification_status.value, "expired")
        self.assertEqual(set(r3.applicability_raw), set(b8.FIVE_KEYS))
        self.assertIn("全体本科生", r3.applicability_raw["适用年级"])
        self.assertIsNone(r3.applicability_raw["适用届别"])
        self.assertIsNone(r3.applicability_raw["适用专业"])
        self.assertEqual(r4.timeliness_verification_status.value, "historical")
        self.assertIsNone(r4.deadline_on)

    def test_all_24_row_ids_duplicates_and_cell_column_routing(self):
        mapping = b8.read(b8.MAPPING)
        self.assertEqual(len(mapping), 48)
        for category in ["R3", "R4"]:
            rows = [row for row in mapping if row["category"] == category]
            self.assertEqual([row["lab_no"] for row in rows], list(range(1, 25)))
            for row in rows:
                n = row["lab_no"] + 2
                self.assertEqual(row["original_locator"], f"Sheet1!A{n}:I{n}")
                self.assertEqual([field["cell"] for field in row["fields"]], [f"{c}{n}" for c in b8.COLUMNS[category]])
        # Repeated EDA names are three independent original rows; never dedup.
        for category in ["R3", "R4"]:
            for number in [14, 15, 24]:
                self.assertIn("EDA", self.prepared[category]["units"][number-1]["heading"])

    def test_r3_process_and_r4_intro_come_from_original_notice_and_cells(self):
        mapping = b8.read(b8.MAPPING)
        for category, data in self.prepared.items():
            for unit in data["units"]:
                for cell in unit["cells"]:
                    if not cell["missing"]:
                        self.assertIn(cell["raw_value"], unit["content"], cell["cell"])
                        for url in cell["hyperlinks"]:
                            self.assertIn(url, unit["content"])
                if category == "R3":
                    self.assertIn("10月31日前", unit["content"])
                    self.assertIn("初选", unit["content"])
                    self.assertIn("面试或笔试", unit["content"])
                    self.assertIn("不是实时余量", unit["content"])
                else:
                    self.assertNotIn("报名及选拔流程（", unit["content"])
                    self.assertIn("历史公开介绍", unit["content"])
        self.assertTrue(all(row["notice"] is not None for row in mapping if row["category"] == "R3"))
        self.assertTrue(all(row["notice"] is None for row in mapping if row["category"] == "R4"))

    def test_raw_wu_is_explicit_missing_and_not_a_confirmed_negative(self):
        last = self.prepared["R3"]["units"][-1]
        self.assertEqual(last["missing_cells"], ["D26", "H26"])
        self.assertIn("未提供（原表为‘无’或空白；不能推断）", last["content"])
        for c in last["cells"]:
            if c["cell"] in {"D26", "H26"}:
                self.assertEqual(c["raw_value"], "无")
                self.assertTrue(c["missing"])

    def test_changed_category_deadline_or_s1_mapping_is_rejected(self):
        for field, value in [("category_name", b8.CATEGORIES["R4"]), ("deadline_on", None),
                             ("business_direction_codes", ["COLLEGE_RESOURCES", "COMPETITION_RESEARCH"])]:
            with self.subTest(field=field):
                self.check_tamper(b8.OUTPUT / "qinghe-r3.json",
                    lambda data: data["metadata"].__setitem__(field, value), "differs from raw-derived")

    def test_premature_human_approval_or_manifest_release_is_rejected(self):
        for value in [True, 0, "false"]:
            with self.subTest(value=value):
                self.check_tamper(b8.OUTPUT / "qinghe-r3.json",
                    lambda data: data["metadata"]["temporal_notes"].__setitem__("human_approved", value), "must remain blocked")
        self.check_tamper(b8.OUTPUT / "manifest.json",
            lambda data: data["packages"][0].__setitem__("human_approved", True), "manifest mismatch")

    def test_row_mapping_or_dropped_lab_is_rejected(self):
        self.check_tamper(b8.MAPPING, lambda rows: rows[0].__setitem__("original_locator", "Sheet1!A4:I4"), "mapping mismatch")
        self.check_tamper(b8.OUTPUT / "qinghe-r4.json", lambda data: data["chunks"].pop(), "differs from raw-derived")

    def test_deleted_original_file_or_changed_role_is_rejected(self):
        def remove_form(data):
            data["files"] = [f for f in data["files"] if not f["storage_key"].endswith("qinghe-registration.docx")]
        self.check_tamper(b8.OUTPUT / "qinghe-r3.json", remove_form, "differs from raw-derived")
        self.check_tamper(b8.OUTPUT / "qinghe-r4.json",
            lambda data: data["files"][0].__setitem__("file_role", "original"), "differs from raw-derived")

    def test_rebuild_preserves_legacy_baseline_raw_files_and_approved(self):
        areas = [baseline.OUTPUT, baseline.REVIEW, Path("knowledge_base/processed/alpha/approved")]
        before = {p: sha256(p.read_bytes()).hexdigest() for area in areas for p in (b8.ROOT / area).rglob("*")
                  if p.is_file() and p != b8.ROOT / b8.MAPPING}
        b8.build()
        self.assertEqual(before, {p: sha256(p.read_bytes()).hexdigest() for p in before})

    def test_failed_original_preflight_does_not_write_output(self):
        before = {p: sha256(p.read_bytes()).hexdigest() for p in (b8.ROOT / b8.OUTPUT).rglob("*") if p.is_file()}
        with patch.object(baseline, "check", side_effect=ValueError("preflight failed")):
            with self.assertRaisesRegex(ValueError, "preflight failed"):
                b8.build()
        self.assertEqual(before, {p: sha256(p.read_bytes()).hexdigest() for p in before})


if __name__ == "__main__":
    unittest.main()
