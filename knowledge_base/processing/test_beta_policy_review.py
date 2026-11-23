"""Offline regression for real Beta candidates; never enables policy data."""
import asyncio
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.contracts import DocumentMetadata, DocumentPackage, ParsedChunk, ParsedFile, RetrievalRequest
from backend.retrieval.local import LocalBM25Retriever
from knowledge_base.processing import build_beta_policy_review as build


class BetaCandidateTests(unittest.TestCase):
    def assert_tampered_read_fails(self, path, mutate, message):
        real_read = build.read
        def altered_read(candidate):
            value = real_read(candidate)
            if candidate == path:
                mutate(value)
            return value
        with patch.object(build, "read", side_effect=altered_read):
            with self.assertRaisesRegex(ValueError, message):
                asyncio.run(build.check())

    def test_manifest_header_tampering_is_rejected(self):
        cases = [("stage", "approved"), ("stage", None)]
        cases += [(field, value) for field in ("enabled_packages", "human_approved_packages")
                  for value in (1, -1, "0", False, None)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.assert_tampered_read_fails(build.OUTPUT / "manifest.json",
                    lambda data: data.__setitem__(field, value), "Manifest (stage|.*integer zero)")

    def test_manifest_entry_approval_tampering_is_rejected(self):
        cases = [("retrieval_status", "enabled"), ("retrieval_status", "review_only"),
                 ("retrieval_status", None), ("human_approved", True), ("human_approved", "false"),
                 ("human_approved", 0), ("human_approved", None)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.assert_tampered_read_fails(build.OUTPUT / "manifest.json",
                    lambda data: data["packages"][0].__setitem__(field, value), "Manifest entries must remain")

    def test_manifest_fields_must_match_package_metadata_and_counts(self):
        cases = [("record_code", "wrong-record"), ("source_verification_status", "pending"),
                 ("timeliness_verification_status", "current"), ("domains", ["S4"]),
                 ("chunk_count", 223), ("chunk_count", "224"), ("source_units", 1)]
        for field, value in cases:
            with self.subTest(field=field):
                self.assert_tampered_read_fails(build.OUTPUT / "manifest.json",
                    lambda data: data["packages"][0].__setitem__(field, value), "Package manifest inconsistent")
        for field, value in [("source_verification_status", "partial"), ("timeliness_verification_status", "historical")]:
            with self.subTest(metadata_field=field):
                self.assert_tampered_read_fails(build.OUTPUT / "competition.json",
                    lambda data: data["metadata"].__setitem__(field, value), "Package manifest inconsistent")

    def test_manifest_cannot_omit_duplicate_or_redirect_candidates(self):
        for mutate in [lambda data: data["packages"].pop(),
                       lambda data: data["packages"].__setitem__(1, deepcopy(data["packages"][0])),
                       lambda data: data["packages"][0].__setitem__("package", "elsewhere/competition.json")]:
            with self.subTest(mutate=mutate):
                self.assert_tampered_read_fails(build.OUTPUT / "manifest.json", mutate,
                                               "Manifest (must list|candidate package path)")

    def test_mapping_source_file_locator_note_and_transformation_tampering(self):
        cases = [("source_file_key", "texts/wrong.md", "source_file_key mismatch"),
                 ("transformation", "invented-transformation", "transformation mismatch"),
                 ("locator_note", {"char_start": 1, "char_end": 2}, "locator_note mismatch"),
                 ("source_unit", 0, "source_unit outside"),
                 ("source_unit", 999999, "source_unit outside"),
                 ("source_unit", 2, "interval outside mapped source unit")]
        for field, value, message in cases:
            with self.subTest(field=field, value=value):
                self.assert_tampered_read_fails(build.REVIEW / "chunk-source-map.json",
                    lambda data: data[0].__setitem__(field, value), message)
        def change_only_offset(data):
            data[0]["locator_note"]["char_end"] += 1
        self.assert_tampered_read_fails(build.REVIEW / "chunk-source-map.json", change_only_offset,
                                       "locator_note mismatch")
        def change_offset_type(data):
            data[0]["locator_note"]["char_start"] = False  # False == 0 in Python, but not the same JSON type
        self.assert_tampered_read_fails(build.REVIEW / "chunk-source-map.json", change_offset_type,
                                       "locator_note mismatch")

    def test_source_unit_original_file_and_locator_must_match_chunk(self):
        for field, value in [("original_file_key", (build.REVIEW / "scholarship.html").as_posix()),
                             ("locator", "invented original locator")]:
            with self.subTest(field=field):
                self.assert_tampered_read_fails(build.REVIEW / "source-units.json",
                    lambda data: data["documents"]["competition"][0].__setitem__(field, value),
                    "Original mapping mismatch")

    def test_matching_forged_chunk_and_mapping_offsets_still_fail_text_check(self):
        real_read = build.read
        def altered_read(path):
            data = real_read(path)
            if path == build.REVIEW / "chunk-source-map.json":
                data[0]["locator_note"]["char_end"] += 1
            elif path == build.OUTPUT / "competition.json":
                note = json.loads(data["chunks"][0]["locator_note"])
                note["char_end"] += 1
                data["chunks"][0]["locator_note"] = json.dumps(note)
            return data
        with patch.object(build, "read", side_effect=altered_read):
            with self.assertRaisesRegex(ValueError, "Chunk text interval differs"):
                asyncio.run(build.check())

    def test_matching_forged_chunk_and_mapping_locator_still_fail_source_unit_check(self):
        real_read = build.read
        def altered_read(path):
            data = real_read(path)
            if path == build.REVIEW / "chunk-source-map.json":
                data[0]["original_locator"] = "invented locator"
            elif path == build.OUTPUT / "competition.json":
                data["chunks"][0]["original_locator"] = "invented locator"
            return data
        with patch.object(build, "read", side_effect=altered_read):
            with self.assertRaisesRegex(ValueError, "Original mapping mismatch"):
                asyncio.run(build.check())

    def test_real_packages_hashes_intervals_and_four_domain_isolation(self):
        result = asyncio.run(build.check())
        self.assertEqual(result["packages"], 8)
        self.assertEqual(result["chunks"], result["original_mappings"])
        self.assertEqual(result["chunks"], 501)
        self.assertEqual(result["indexed_chunks"], 501)
        self.assertEqual(result["blocked_metadata_lookups_returning_none"], 8)
        self.assertEqual(result["blocked_chunk_lookups_returning_none"], 501)
        for index in result["index_results"]:
            self.assertEqual(index["status"], "indexed")
            self.assertEqual(index["indexed_count"], index["chunk_count"])
            self.assertEqual(index["actual_stored_chunk_count"], index["chunk_count"])
            self.assertEqual(index["warnings"], [])
        self.assertTrue(all(n == 0 for n in result["formal_hits_for_blocked_candidates"].values()))

    def test_business_codes_preserve_original_dictionary(self):
        preview = build.read(Path("docs/assignment-02/database-design/knowledge-base/入库预览_44条.json"))
        known = {r["code"] for r in preview["business_directions"]}
        for row in build.read(build.OUTPUT / "manifest.json")["packages"]:
            package = DocumentPackage.model_validate(build.read(Path(row["package"])))
            self.assertTrue(set(package.metadata.business_direction_codes) <= known)
            self.assertFalse(set(package.metadata.business_direction_codes) & {"S1", "S2", "S3", "S4"})
        qinghe = build.read(build.OUTPUT / "qinghe.json")["metadata"]
        self.assertEqual(qinghe["business_direction_codes"], ["COLLEGE_RESOURCES"])
        self.assertEqual(qinghe["temporal_notes"]["beta_domains"], ["S4"])
        manifest = build.read(build.OUTPUT / "manifest.json")
        self.assertEqual(next(r for r in manifest["packages"] if r["key"] == "qinghe")["domains"], ["S4"])

    def test_each_package_exactly_matches_original_44_record_direction_mapping(self):
        preview = build.read(Path("docs/assignment-02/database-design/knowledge-base/入库预览_44条.json"))
        by_id = {direction["id"]: direction["code"] for direction in preview["business_directions"]}
        for row in build.read(build.OUTPUT / "manifest.json")["packages"]:
            with self.subTest(key=row["key"]):
                version = next(v for v in preview["document_versions"] if v["record_code"] == row["record_code"])
                original = [by_id[link["direction_id"]] for link in preview["document_business_directions"]
                            if link["document_id"] == version["document_id"]]
                metadata = build.read(Path(row["package"]))["metadata"]
                expected = ["COLLEGE_RESOURCES"] if row["key"] == "qinghe" else original
                self.assertEqual(metadata["business_direction_codes"], expected)
                if row["key"] == "qinghe":
                    self.assertEqual(metadata["temporal_notes"]["business_scope_adjustment"]["original_business_direction_codes"], original)

    def test_valid_dictionary_code_in_wrong_package_is_rejected(self):
        for name in ["competition", "scholarship", "college-scholarship", "xinghuo", "recommendation", "innovation", "retest"]:
            with self.subTest(key=name):
                self.assert_tampered_read_fails(build.OUTPUT / f"{name}.json",
                    lambda data: data["metadata"].__setitem__("business_direction_codes", ["GROWTH_PLANNING"]),
                    "Business direction mapping differs from original preview")

    def test_policy_metadata_cannot_drift_from_reviewed_batch(self):
        cases = [("source_url", "https://example.invalid/wrong-policy"),
                 ("source_page_url", "https://example.invalid/wrong-page"),
                 ("publisher", "wrong publisher"), ("published_on", "2025-03-06"),
                 ("deadline_on", "2027-12-31"),
                 ("applicability_raw", {"适用对象": "wrong audience"})]
        for field, value in cases:
            with self.subTest(field=field):
                self.assert_tampered_read_fails(build.OUTPUT / "competition.json",
                    lambda data: data["metadata"].__setitem__(field, value),
                    "Candidate metadata differs from reviewed batch")

    def test_deleted_chunk_with_matching_manifest_and_mapping_is_rejected(self):
        real_read = build.read
        def altered_read(path):
            data = real_read(path)
            if path == build.OUTPUT / "competition.json":
                data["chunks"].pop()
            elif path == build.OUTPUT / "manifest.json":
                data["packages"][0]["chunk_count"] -= 1
            elif path == build.REVIEW / "chunk-source-map.json":
                data[:] = [row for row in data if not (row["package"] == "competition.json" and row["chunk_no"] == 224)]
            return data
        with patch.object(build, "read", side_effect=altered_read):
            with self.assertRaisesRegex(ValueError, "chunk sequence differs from full Markdown parse"):
                asyncio.run(build.check())

    def test_shortened_valid_slice_with_matching_offsets_is_rejected(self):
        real_read = build.read
        def altered_read(path):
            data = real_read(path)
            if path == build.OUTPUT / "competition.json":
                chunk = data["chunks"][0]
                chunk["content"] = chunk["content"][:-1]
                note = json.loads(chunk["locator_note"])
                note["char_end"] -= 1
                chunk["locator_note"] = json.dumps(note, ensure_ascii=False)
            elif path == build.REVIEW / "chunk-source-map.json":
                data[0]["locator_note"]["char_end"] -= 1
            return data
        with patch.object(build, "read", side_effect=altered_read):
            with self.assertRaisesRegex(ValueError, "chunk sequence differs from full Markdown parse"):
                asyncio.run(build.check())

    def test_qinghe_mapping_filters_s1_independently_of_blocked_gate(self):
        # Only the candidate's routing codes are copied. The enabled in-memory
        # fixture has no policy text, origin files, real identity or approval.
        codes = build.read(build.OUTPUT / "qinghe.json")["metadata"]["business_direction_codes"]
        fixture = DocumentPackage(
            metadata=DocumentMetadata(title="SYNTHETIC ROUTING TEST ONLY", document_type="synthetic-test",
                category_name="synthetic-test", record_code="SYNTHETIC-BETA-S4-ROUTING", version_no="test-only",
                business_direction_codes=codes, source_url="https://example.invalid/synthetic",
                source_verification_status="verified", timeliness_verification_status="current",
                extraction_status="extracted", v1_inclusion_status="included", retrieval_status="enabled",
                temporal_notes={"synthetic_test_only": True, "human_approved": False}),
            files=[ParsedFile(storage_key="synthetic-routing.txt", original_name="synthetic-routing.txt",
                              file_role="extracted", processing_status="extracted")],
            chunks=[ParsedChunk(chunk_no=1, content="synthetic routing sentinel",
                                source_file_key="synthetic-routing.txt")])
        async def run():
            store = LocalBM25Retriever()
            result = await store.index_document(fixture)
            self.assertEqual(result.status.value, "indexed")
            self.assertEqual(result.indexed_count, 1)
            s4 = await store.retrieve(RetrievalRequest(query="sentinel", business_direction_code="COLLEGE_RESOURCES"))
            s1 = await store.retrieve(RetrievalRequest(query="sentinel", business_direction_code="COMPETITION_RESEARCH"))
            self.assertEqual(len(s4), 1)
            self.assertEqual(s1, [])
        asyncio.run(run())

    def test_checker_rejects_qinghe_s1_mapping_even_when_blocked(self):
        real_read = build.read
        def altered_read(path):
            value = real_read(path)
            if path == build.OUTPUT / "qinghe.json":
                value["metadata"]["business_direction_codes"].append("COMPETITION_RESEARCH")
            return value
        with patch.object(build, "read", side_effect=altered_read):
            with self.assertRaisesRegex(ValueError, "scoped to S4"):
                asyncio.run(build.check())

    def test_blocked_real_metadata_lookup_returns_none_after_successful_indexing(self):
        async def run():
            store = LocalBM25Retriever(file_root=build.ROOT)
            for row in build.read(build.OUTPUT / "manifest.json")["packages"]:
                package = DocumentPackage.model_validate(build.read(Path(row["package"])))
                indexed = await store.index_document(package)
                self.assertEqual(indexed.status.value, "indexed")
                self.assertEqual(indexed.indexed_count, len(package.chunks))
                self.assertIn(indexed.version_id, store._versions)
                self.assertIsNone(store.get_document_metadata(indexed.version_id), row["key"])
        asyncio.run(run())

    def test_blocked_real_chunk_lookup_returns_none_for_all_stored_ids(self):
        async def run():
            store = LocalBM25Retriever(file_root=build.ROOT)
            checked = 0
            for row in build.read(build.OUTPUT / "manifest.json")["packages"]:
                package = DocumentPackage.model_validate(build.read(Path(row["package"])))
                indexed = await store.index_document(package)
                self.assertEqual(indexed.status.value, "indexed")
                ids = [chunk_id for chunk_id, entry in store._chunk_index.items() if entry[0] == indexed.version_id]
                self.assertEqual(len(ids), len(package.chunks))
                for chunk_id in ids:
                    self.assertIsNone(store.get_parsed_chunk(chunk_id), str(chunk_id))
                    checked += 1
            self.assertEqual(checked, 501)
        asyncio.run(run())

    def test_checker_rejects_failed_partial_or_zero_index_even_with_no_hits(self):
        real_index = LocalBM25Retriever.index_document
        for status, count in [("failed", 0), ("partial", 0), ("indexed", 0)]:
            with self.subTest(status=status, indexed_count=count):
                async def incomplete_index(store, package):
                    result = await real_index(store, package)
                    return result.model_copy(update={"status": type(result.status)(status), "indexed_count": count})
                with patch.object(build.LocalBM25Retriever, "index_document", new=incomplete_index):
                    with self.assertRaisesRegex(ValueError, "indexing incomplete or failed"):
                        asyncio.run(build.check())

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
