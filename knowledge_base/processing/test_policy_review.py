"""Scope-local review tests: traceability and conservative retrieval gates."""
import asyncio
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from knowledge_base.processing import build_policy_review as review


class PolicyReviewTests(unittest.TestCase):
    def test_real_packages_index_but_do_not_answer(self):
        report = asyncio.run(review.check())
        self.assertEqual(report["package_count"], 5)
        self.assertEqual(report["mapped_chunks"], 371)
        self.assertEqual(report["retrieval_status_counts"], {"blocked": 2, "review_only": 3})
        self.assertTrue(all(n == 0 for n in report["formal_retrieval_hit_counts"].values()))

    def test_tampered_original_stops_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("changed", encoding="utf-8")
            with patch.object(review, "ROOT", root), patch.object(review, "read", return_value=[]):
                with self.assertRaisesRegex(ValueError, "哈希改变"):
                    review.verify_inputs({"inputs": {"source.txt": "0" * 64}})

    def test_review_checker_rejects_enabled_export(self):
        original_read = review.read

        def changed(path):
            value = original_read(path)
            if Path(path).name == "scholarship.json":
                value = copy.deepcopy(value)
                value["metadata"].update(retrieval_status="enabled", timeliness_verification_status="current")
            return value

        with patch.object(review, "read", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "cannot approve or enable"):
                asyncio.run(review.check())

    def test_cohort_deadline_and_import_history_preserved(self):
        package = review.read(review.OUTPUT / "recommendation.json")
        meta = package["metadata"]
        self.assertEqual(meta["deadline_on"], "2026-09-09")
        self.assertEqual(meta["temporal_notes"]["deadline_exact_local"], "2026-09-09T21:00:00+08:00")
        self.assertEqual(meta["timeliness_verification_status"], "expired")
        self.assertEqual(meta["import_snapshot"]["最后核验日期"], "2026-10-21")
        self.assertFalse(meta["temporal_notes"]["human_approved"])

    def test_ambiguous_annual_college_notice_is_blocked(self):
        meta = review.read(review.OUTPUT / "college-scholarship.json")["metadata"]
        self.assertEqual(meta["retrieval_status"], "blocked")
        self.assertEqual(meta["timeliness_verification_status"], "uncertain")
        self.assertIn("2025年度", meta["applicability_raw"]["年度歧义"])

    def test_teacher_and_student_conditions_keep_heading_context(self):
        package = review.read(review.OUTPUT / "xinghuo.json")
        teacher = next(c for c in package["chunks"] if "每年评选16人" in c["content"])
        student = next(c for c in package["chunks"] if "每年评选30人" in c["content"])
        self.assertIn("星火奖教金", teacher["content"])
        self.assertIn("星火奖学金", student["content"])

    def test_competition_table_structure_and_page4_numeric_columns(self):
        audit = review.read(review.REVIEW / "extraction-audit.json")
        self.assertEqual([audit[f"competition-attachment-{i}"]["tables"][0]["rows_including_header"] for i in (1, 2, 3)], [78, 109, 21])
        self.assertEqual(sum(audit[f"competition-attachment-{i}"]["footnotes_and_endnotes"] for i in (1, 2, 3)), 0)
        layout = review.read(review.REVIEW / "recommendation-page-4-layout.json")
        cells = [u["cells"] for u in layout["units"] if "cells" in u]
        self.assertEqual(cells[-1], ["国家级", "三等奖", "2", "1.5"])
        self.assertEqual(cells[0], ["国际级", "特等奖（第1名）", "6", "5"])
        self.assertEqual(len(cells), 8)


if __name__ == "__main__":
    unittest.main()
