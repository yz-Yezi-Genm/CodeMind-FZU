"""Offline regression for real Beta candidates; never enables policy data."""
import asyncio
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.contracts import DocumentPackage
from knowledge_base.processing import build_beta_policy_review as build


class BetaCandidateTests(unittest.TestCase):
    def test_real_packages_hashes_intervals_and_four_domain_isolation(self):
        result = asyncio.run(build.check())
        self.assertEqual(result["packages"], 8)
        self.assertEqual(result["chunks"], result["original_mappings"])
        self.assertGreaterEqual(result["chunks"], 501)
        self.assertTrue(all(n == 0 for n in result["formal_hits_for_blocked_candidates"].values()))

    def test_business_codes_preserve_original_dictionary(self):
        preview = build.read(Path("docs/assignment-02/database-design/knowledge-base/入库预览_44条.json"))
        known = {r["code"] for r in preview["business_directions"]}
        for row in build.read(build.OUTPUT / "manifest.json")["packages"]:
            package = DocumentPackage.model_validate(build.read(Path(row["package"])))
            self.assertTrue(set(package.metadata.business_direction_codes) <= known)
            self.assertFalse(set(package.metadata.business_direction_codes) & {"S1", "S2", "S3", "S4"})
        qinghe = build.read(build.OUTPUT / "qinghe.json")["metadata"]
        self.assertIn("COLLEGE_RESOURCES", qinghe["business_direction_codes"])

    def test_original_44_records_preserved_as_import_snapshots(self):
        preview = build.read(Path("docs/assignment-02/database-design/knowledge-base/入库预览_44条.json"))
        self.assertEqual(len(preview["document_versions"]), 44)
        for row in build.read(build.OUTPUT / "manifest.json")["packages"]:
            metadata = build.read(Path(row["package"]))["metadata"]
            original = next(v for v in preview["document_versions"] if v["record_code"] == row["record_code"])
            self.assertEqual(metadata["import_snapshot"], original["import_snapshot"])

    def test_expired_cohorts_and_conflict_not_marked_current(self):
        for name in ["recommendation", "retest", "xinghuo", "qinghe"]:
            m = build.read(build.OUTPUT / f"{name}.json")["metadata"]
            self.assertEqual(m["timeliness_verification_status"], "expired")
            self.assertEqual(m["retrieval_status"], "blocked")
            self.assertFalse(m["temporal_notes"]["human_approved"])
        m = build.read(build.OUTPUT / "college-scholarship.json")["metadata"]
        self.assertEqual(m["timeliness_verification_status"], "uncertain")
        self.assertIn("歧义", m["policy_status"])

    def test_qinghe_cells_and_contact_fields_survive_markdown(self):
        audit = build.read(build.REVIEW / "qinghe-conversion-audit.json")
        text = (build.ROOT / build.OUTPUT / "texts/qinghe.md").read_text(encoding="utf-8")
        self.assertEqual(audit["lab_count"], 24)
        self.assertEqual(audit["converted_nonempty_cells"], 226)
        self.assertEqual(audit["uncovered_nonempty_cells"], 0)
        self.assertEqual(audit["empty_sheets"], ["Sheet2", "Sheet3"])
        for cell in audit["cells"]:
            self.assertIn(cell["value"], text, cell["cell"])
            if cell["hyperlink"]:
                self.assertIn(cell["hyperlink"], text)
        for links in audit["wps_rich_text_links"].values():
            for link in links:
                self.assertIn(link, text)
        self.assertIn("2026年10月31日前报名，已过期", text)

    def test_original_tamper_fails_closed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.html").write_bytes(b"changed")
            with patch.object(build, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "Original hash changed"):
                    build.verify_inputs({"inputs": {"source.html": sha256(b"original").hexdigest()}})

    def test_enabled_candidate_is_rejected(self):
        real_read = build.read
        def altered_read(path):
            value = real_read(path)
            if path == build.OUTPUT / "competition.json":
                value = deepcopy(value)
                value["metadata"]["timeliness_verification_status"] = "current"
                value["metadata"]["retrieval_status"] = "enabled"
            return value
        with patch.object(build, "read", side_effect=altered_read):
            with self.assertRaisesRegex(ValueError, "cannot approve/enable"):
                asyncio.run(build.check())

    def test_mapping_tamper_is_rejected(self):
        real_read = build.read
        def altered_read(path):
            value = real_read(path)
            if path == build.REVIEW / "chunk-source-map.json":
                value[0]["original_locator"] = "invented locator"
            return value
        with patch.object(build, "read", side_effect=altered_read):
            with self.assertRaisesRegex(ValueError, "Original mapping mismatch"):
                asyncio.run(build.check())

    def test_rebuild_does_not_change_approved_or_alpha_candidates(self):
        paths = [* (build.ROOT / "knowledge_base/processed/alpha/approved").rglob("*"),
                 * (build.ROOT / "knowledge_base/processed/alpha/pending-review").glob("*.json")]
        before = {p: sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
        build.build()
        after = {p: sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(set(before), set(after))


if __name__ == "__main__":
    unittest.main()
