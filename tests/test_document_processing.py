"""Parser and repository sample tests; no network, model, database or vector store."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from backend.contracts.models import DocumentMetadata, DocumentPackage, FileRole
from backend.contracts.protocols import DocumentParser
from backend.document_processing import DocumentProcessingError, TextDocumentParser


def make_metadata(**updates):
    return DocumentMetadata.model_validate({
        "title": "测试政策", "document_type": "办法", "category_name": "综评与奖学金",
        "record_code": "TEST-001", "version_no": "import-1", "publisher": "福州大学",
        "source_url": "https://jwch.fzu.edu.cn/test", "published_on": "2026-05-18",
        "applicability_raw": {"适用年级": "大一至大三", "适用对象": "本科生"},
        **updates,
    })


class DocumentProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.parser: DocumentParser = TextDocumentParser(self.root, max_chunk_chars=80)
        self.metadata = make_metadata()

    def write(self, text, name="policy.md", encoding="utf-8"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode(encoding))
        return path

    def assert_error(self, path, code):
        with self.assertRaises(DocumentProcessingError) as caught:
            self.parser.parse_document(path, self.metadata)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn(str(self.root), str(caught.exception))

    def assert_locations(self, package, text):
        normalized = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        for chunk in package.chunks:
            note = json.loads(chunk.locator_note)
            a, b = note["char_start"], note["char_end"]
            self.assertEqual(chunk.content, normalized[a:b])
            self.assertEqual(note["line_start"], normalized[:a].count("\n") + 1)
            self.assertEqual(note["line_end"], normalized[:b-1].count("\n") + 1)
            self.assertLessEqual(len(chunk.content), 80)
            self.assertIsNone(chunk.original_file_key)
            self.assertIsNone(chunk.original_locator)

    def test_markdown_front_matter_hierarchy_and_real_line_numbers(self):
        text = '---\nretrieval_status: enabled\n标题: 不能覆盖\n---\n# 总则\n说明\n## 申请条件\n本科生。\n### 材料\n成绩单。\n## 流程\n提交申请。'
        path = self.write(text)
        package = self.parser.parse_document(path, self.metadata)
        self.assertEqual(package.metadata.title, self.metadata.title)
        self.assertEqual(package.metadata.retrieval_status, "blocked")
        self.assertEqual(len(package.chunks), 4)
        self.assertNotIn("retrieval_status", "".join(x.content for x in package.chunks))
        self.assertEqual(json.loads(package.chunks[2].locator_note)["heading_path"], [
            {"level": 1, "title": "总则"}, {"level": 2, "title": "申请条件"},
            {"level": 3, "title": "材料"},
        ])
        self.assertEqual(json.loads(package.chunks[0].locator_note)["line_start"], 5)
        self.assert_locations(package, text)

    def test_long_chinese_paragraph_no_text_loss_or_duplicate_and_sequential_numbers(self):
        text = "# 条款\n" + "第十二条，学生须核对申请条件和所属年度。" * 40
        package = self.parser.parse_document(self.write(text), self.metadata)
        self.assertGreater(len(package.chunks), 5)
        self.assertEqual([x.chunk_no for x in package.chunks], list(range(1, len(package.chunks)+1)))
        self.assertEqual("".join(x.content for x in package.chunks).replace("\n", ""), text.replace("\n", ""))
        self.assert_locations(package, text)

    def test_unbroken_line_is_bounded_and_keeps_final_character(self):
        text = "甲" * 321 + "终"
        package = self.parser.parse_document(self.write(text, "long.txt"), self.metadata)
        self.assertEqual("".join(x.content for x in package.chunks), text)
        self.assert_locations(package, text)

    def test_txt_with_markdown_like_text_is_not_treated_as_headings(self):
        text = "# 原始标题字符\n正文\n## 仅为文本\n尾句"
        package = self.parser.parse_document(self.write(text, "note.TXT"), self.metadata)
        self.assertEqual(len(package.chunks), 1)
        self.assertEqual(json.loads(package.chunks[0].locator_note)["heading_path"], [])
        self.assertEqual(package.files[0].file_role, "extracted")
        self.assert_locations(package, text)

    def test_bom_crlf_unicode_filename_hash_and_source_reference(self):
        text = "\ufeff# 奖学金\r\n正文一。\r\n\r\n正文二。\r\n"
        path = self.write(text, "整理资料/奖学金.MD")
        package = self.parser.parse_document(path, self.metadata)
        file = package.files[0]
        self.assertEqual(file.sha256, sha256(path.read_bytes()).hexdigest())
        self.assertEqual(file.storage_key, "整理资料/奖学金.MD")
        self.assertEqual(package.chunks[0].source_file_key, file.storage_key)
        self.assertEqual(file.media_type, "text/markdown")
        self.assert_locations(package, text)

    def test_markdown_explicit_extracted_role_preserves_content_and_metadata(self):
        text = "# 政策正文\n提取文字。"
        path = self.write(text)
        before = self.metadata.model_dump()
        parser: DocumentParser = TextDocumentParser(self.root, file_role=FileRole.EXTRACTED)
        package = parser.parse_document(path, self.metadata)
        self.assertEqual(package.files[0].file_role, FileRole.EXTRACTED)
        self.assertEqual(package.files[0].processing_status, "extracted")
        self.assertEqual(package.chunks[0].content, text)
        self.assertEqual(package.metadata.retrieval_status, "blocked")
        self.assertEqual(self.metadata.model_dump(), before)
        self.assert_locations(package, text)

    def test_markdown_explicit_curated_role_is_not_overridden_by_front_matter(self):
        path = self.write("---\nfile_role: extracted\n---\n# 人工整理\n核对说明。")
        package = TextDocumentParser(self.root, file_role="curated").parse_document(path, self.metadata)
        self.assertEqual(package.files[0].file_role, FileRole.CURATED)
        self.assertEqual(package.chunks[0].content, "# 人工整理\n核对说明。")
        self.assertEqual(package.metadata.retrieval_status, "blocked")

    def test_docx_explicit_attachment_role_does_not_enable_extraction(self):
        path = self.root / "attachment.docx"
        path.write_bytes(b"PK\x00\x00")
        package = TextDocumentParser(self.root, file_role="attachment").parse_document(path, self.metadata)
        self.assertEqual(package.files[0].file_role, FileRole.ATTACHMENT)
        self.assertEqual(package.files[0].sha256, sha256(path.read_bytes()).hexdigest())
        self.assertEqual(package.files[0].processing_status, "saved")
        self.assertEqual(package.chunks, [])
        self.assertEqual(package.metadata.extraction_status, "pending")
        self.assertEqual(package.metadata.retrieval_status, "blocked")

    def test_invalid_explicit_file_role_is_rejected(self):
        for role in ("unknown", "", "EXTRACTED"):
            with self.subTest(role=role), self.assertRaises(ValueError):
                TextDocumentParser(self.root, file_role=role)

    def test_omitted_file_role_preserves_legacy_defaults(self):
        for name, role in (("legacy.md", "curated"), ("legacy.txt", "extracted"), ("legacy.docx", "original")):
            with self.subTest(name=name):
                package = self.parser.parse_document(self.write("正文", name), self.metadata)
                self.assertEqual(package.files[0].file_role, role)

    def test_setext_headings_and_fenced_hash_are_handled(self):
        text = "总则\n===\n正文\n条件\n---\n```python\n# 代码不是标题\n```\n附则\n---\n尾句。"
        package = self.parser.parse_document(self.write(text), self.metadata)
        paths = [json.loads(x.locator_note)["heading_path"] for x in package.chunks]
        self.assertEqual(paths[-1], [{"level": 1, "title": "总则"}, {"level": 2, "title": "附则"}])
        self.assertFalse(any("代码不是标题" == y["title"] for x in paths for y in x))
        self.assertIn("# 代码不是标题", "".join(x.content for x in package.chunks))
        self.assert_locations(package, text)

    def test_markdown_table_text_and_values_are_preserved(self):
        text = "# 认定\n\n| 项目 | 分值 |\n| --- | --- |\n" + "| 示例项目 | 2分 |\n" * 20
        package = self.parser.parse_document(self.write(text), self.metadata)
        strip_space = lambda value: "".join(value.split())
        self.assertEqual(strip_space("".join(x.content for x in package.chunks)), strip_space(text))
        self.assert_locations(package, text)

    def test_metadata_is_not_mutated_and_verification_is_not_promoted(self):
        before = self.metadata.model_dump()
        package = self.parser.parse_document(self.write("# 条款\n正文。"), self.metadata)
        self.assertEqual(self.metadata.model_dump(), before)
        self.assertEqual(package.metadata.source_verification_status, "pending")
        self.assertEqual(package.metadata.timeliness_verification_status, "pending")
        self.assertEqual(package.metadata.applicability_raw, before["applicability_raw"])
        self.assertEqual(package.metadata.published_on, self.metadata.published_on)
        self.assertEqual(package.metadata.extraction_status, "extracted")
        self.assertEqual(package.chunks[0].index_status, "pending")

    def test_even_explicit_enabled_metadata_is_returned_blocked(self):
        metadata = make_metadata(source_verification_status="verified", timeliness_verification_status="current",
                                 extraction_status="extracted", v1_inclusion_status="included", retrieval_status="enabled")
        package = self.parser.parse_document(self.write("正文"), metadata)
        self.assertEqual(package.metadata.retrieval_status, "blocked")
        self.assertEqual(metadata.retrieval_status, "enabled")

    def test_review_only_also_remains_blocked_in_this_parser(self):
        package = self.parser.parse_document(self.write("正文"), make_metadata(retrieval_status="review_only"))
        self.assertEqual(package.metadata.retrieval_status, "blocked")

    def test_parse_twice_is_identical_and_json_validates_against_public_contract(self):
        path = self.write("# 条款\n正文。")
        first = self.parser.parse_document(path, self.metadata)
        second = self.parser.parse_document(path, self.metadata)
        self.assertEqual(first.model_dump_json(), second.model_dump_json())
        self.assertEqual(DocumentPackage.model_validate_json(first.model_dump_json()), first)

    def test_pdf_waiting_for_ocr_produces_no_fabricated_chunks(self):
        path = self.root / "scan.pdf"
        path.write_bytes(b"%PDF-1.7\nnot extracted")
        package = self.parser.parse_document(path, make_metadata(extraction_status="needs_ocr"))
        self.assertEqual(package.chunks, [])
        self.assertEqual(package.metadata.extraction_status, "needs_ocr")
        self.assertEqual(package.files[0].processing_status, "needs_ocr")
        self.assertEqual(package.metadata.retrieval_status, "blocked")

    def test_unknown_pdf_type_is_pending_not_assumed_scanned(self):
        path = self.root / "unknown.pdf"
        path.write_bytes(b"%PDF-1.7")
        package = self.parser.parse_document(path, self.metadata)
        self.assertEqual(package.chunks, [])
        self.assertEqual(package.metadata.extraction_status, "pending")
        self.assertEqual(package.files[0].processing_status, "saved")

    def test_markdown_ocr_placeholder_is_not_treated_as_extracted_policy(self):
        path = self.write("# 待OCR\n扫描文件还没有正文。")
        package = self.parser.parse_document(path, make_metadata(extraction_status="needs_ocr"))
        self.assertEqual(package.chunks, [])
        self.assertEqual(package.metadata.extraction_status, "needs_ocr")

    def test_docx_is_registered_pending_without_extracting_zip_bytes(self):
        path = self.root / "file.docx"
        path.write_bytes(b"PK\x00\x00")
        package = self.parser.parse_document(path, self.metadata)
        self.assertEqual(package.chunks, [])
        self.assertEqual(package.metadata.extraction_status, "pending")

    def test_missing_file(self):
        self.assert_error(self.root / "missing.md", "DOCUMENT_NOT_FOUND")

    def test_empty_or_front_matter_only_file_is_rejected(self):
        for text in ("  \n\t", "---\n标题: 示例\n---\n"):
            with self.subTest(text=text):
                self.assert_error(self.write(text), "EMPTY_DOCUMENT")

    def test_unclosed_front_matter_is_rejected(self):
        self.assert_error(self.write("---\n标题: 示例\n# 正文"), "INVALID_FRONT_MATTER")

    def test_invalid_encoding_is_not_silently_replaced(self):
        path = self.root / "bad.txt"
        path.write_bytes(b"\xff\xfe\x00")
        self.assert_error(path, "TEXT_DECODE_FAILED")

    def test_declared_gb18030_is_supported(self):
        path = self.write("# 中文\n正文", "gb.md", "gb18030")
        package = TextDocumentParser(self.root, encoding="gb18030").parse_document(path, self.metadata)
        self.assertEqual(package.chunks[0].content, "# 中文\n正文")

    def test_binary_control_character_in_txt_is_rejected(self):
        self.assert_error(self.write("hello\x00world", "binary.txt"), "BINARY_TEXT")

    def test_relative_path_resolves_against_root(self):
        self.write("正文", "folder/test.md")
        package = self.parser.parse_document(Path("folder/test.md"), self.metadata)
        self.assertEqual(package.files[0].storage_key, "folder/test.md")

    def test_directory_traversal_is_rejected_before_read(self):
        self.assert_error(Path("../outside.md"), "OUTSIDE_STORAGE_ROOT")

    def test_symlink_escaping_storage_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "source.md"
            target.write_text("外部正文", encoding="utf-8")
            link = self.root / "escape.md"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("当前操作系统账户不允许创建符号链接")
            self.assert_error(link, "OUTSIDE_STORAGE_ROOT")

    def test_file_size_limit_and_invalid_chunk_limit(self):
        path = self.write("123456")
        with self.assertRaises(DocumentProcessingError) as caught:
            TextDocumentParser(self.root, max_file_bytes=5).parse_document(path, self.metadata)
        self.assertEqual(caught.exception.code, "FILE_TOO_LARGE")
        with self.assertRaises(ValueError):
            TextDocumentParser(self.root, max_chunk_chars=0)

    def test_cli_success_and_exception_exit_codes(self):
        path = self.write("# 正文\n测试文本。")
        meta = self.root / "metadata.json"
        meta.write_text(self.metadata.model_dump_json(), encoding="utf-8")
        output = self.root / "result.json"
        command = [sys.executable, "-X", "utf8", "-m", "backend.document_processing", str(path),
                   "--metadata", str(meta), "--storage-root", str(self.root), "--output", str(output)]
        success = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(DocumentPackage.model_validate_json(output.read_text(encoding="utf-8")).metadata.retrieval_status, "blocked")
        command[5] = str(self.root / "missing.md")
        failure = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(failure.returncode, 1)
        self.assertIn("DOCUMENT_NOT_FOUND", failure.stderr)

    def test_cli_explicit_markdown_and_docx_roles(self):
        meta = self.root / "metadata.json"
        meta.write_text(self.metadata.model_dump_json(), encoding="utf-8")
        for name, role in (("extracted.md", "extracted"), ("curated.md", "curated"), ("attachment.docx", "attachment")):
            with self.subTest(role=role):
                path = self.write("# 正文\n示例文字。", name)
                if path.suffix == ".docx":
                    path.write_bytes(b"PK\x00\x00")
                output = self.root / (name + ".json")
                result = subprocess.run(
                    [sys.executable, "-X", "utf8", "-m", "backend.document_processing", str(path),
                     "--metadata", str(meta), "--storage-root", str(self.root), "--output", str(output),
                     "--file-role", role], capture_output=True, text=True, encoding="utf-8",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                package = DocumentPackage.model_validate_json(output.read_text(encoding="utf-8"))
                self.assertEqual(package.files[0].file_role, role)
                self.assertEqual(package.files[0].sha256, sha256(path.read_bytes()).hexdigest())
                self.assertEqual(package.metadata.retrieval_status, "blocked")
                self.assertEqual(bool(package.chunks), path.suffix == ".md")
                self.assertEqual(package.metadata.extraction_status, "pending" if path.suffix == ".docx" else "extracted")

    def test_cli_invalid_file_role_exits_before_writing_output(self):
        path = self.write("正文")
        meta = self.root / "metadata.json"
        meta.write_text(self.metadata.model_dump_json(), encoding="utf-8")
        output = self.root / "invalid-role.json"
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "backend.document_processing", str(path),
             "--metadata", str(meta), "--storage-root", str(self.root), "--output", str(output),
             "--file-role", "unknown"], capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--file-role", result.stderr)
        self.assertFalse(output.exists())

    def test_cli_does_not_overwrite_input(self):
        path = self.write("原始正文不能被覆盖。")
        before = path.read_bytes()
        meta = self.root / "metadata.json"
        meta.write_text(self.metadata.model_dump_json(), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "backend.document_processing", str(path),
             "--metadata", str(meta), "--storage-root", str(self.root), "--output", str(path)],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(path.read_bytes(), before)

    def test_heading_level_gaps_and_same_level_siblings(self):
        text = "# 总则\n正文\n### 材料\n甲\n### 时间\n乙\n# 附则\n丙"
        package = self.parser.parse_document(self.write(text), self.metadata)
        self.assertEqual(json.loads(package.chunks[2].locator_note)["heading_path"],
                         [{"level": 1, "title": "总则"}, {"level": 3, "title": "时间"}])
        self.assertEqual(json.loads(package.chunks[3].locator_note)["heading_path"],
                         [{"level": 1, "title": "附则"}])


class RepositoryPackageTests(unittest.TestCase):
    def test_checked_in_three_scenarios_match_contract_and_source_files(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "knowledge_base/processing/alpha-manifest.json").read_text(encoding="utf-8"))
        preview = json.loads((root / manifest["preview_path"]).read_text(encoding="utf-8-sig"))
        versions = {row["record_code"]: row for row in preview["document_versions"]}
        self.assertEqual({x["scenario"] for x in manifest["samples"]}, {"竞赛认定", "奖学金", "推免"})
        for sample in manifest["samples"]:
            with self.subTest(sample=sample["key"]):
                package = DocumentPackage.model_validate_json(
                    (root / f'knowledge_base/processed/alpha/{sample["key"]}.json').read_text(encoding="utf-8")
                )
                self.assertEqual(package.metadata.record_code, sample["record_code"])
                self.assertEqual(package.metadata.retrieval_status, "blocked")
                self.assertTrue(package.chunks)
                version = versions[sample["record_code"]]
                self.assertEqual(package.metadata.source_verification_status, version["source_verification_status"])
                self.assertEqual(package.metadata.timeliness_verification_status, version["timeliness_verification_status"])
                input_metadata = DocumentMetadata.model_validate_json(
                    (root / f'knowledge_base/processed/alpha/{sample["key"]}.metadata.json').read_text(encoding="utf-8")
                )
                for field in ("publisher", "source_url", "published_on", "applicability_raw", "import_snapshot"):
                    self.assertEqual(getattr(package.metadata, field), getattr(input_metadata, field))
                registered = {row["storage_key"]: row for row in preview["document_files"]
                              if row["version_id"] == version["id"]}
                self.assertEqual({file.storage_key for file in package.files}, set(registered))
                for file in package.files:
                    self.assertFalse(Path(file.storage_key).is_absolute())
                    self.assertEqual(file.sha256, sha256((root / file.storage_key).read_bytes()).hexdigest())
                    self.assertEqual(file.file_role, registered[file.storage_key]["file_role"])
                text = (root / sample["file_path"]).read_text(encoding="utf-8-sig")
                for chunk in package.chunks:
                    note = json.loads(chunk.locator_note)
                    self.assertEqual(chunk.content, text[note["char_start"]:note["char_end"]])
                    self.assertEqual(chunk.source_file_key, sample["file_path"])
                    self.assertIsNone(chunk.original_locator)
                    self.assertEqual(chunk.index_status, "pending")

    def test_revised_samples_cover_actual_recognition_rules_and_recommendation_eligibility(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "knowledge_base/processing/alpha-manifest.json").read_text(encoding="utf-8"))
        expected = {
            "竞赛认定": ("福大-2026-竞赛项目级别认定", "校教〔2026〕9号"),
            "奖学金": ("福大-2026-本科奖学金", "第十五条"),
            "推免": ("计算机学院-2027-推免资格推荐", "PDF第4页"),
        }
        for sample in manifest["samples"]:
            package = DocumentPackage.model_validate_json(
                (root / f'knowledge_base/processed/alpha/{sample["key"]}.json').read_text(encoding="utf-8")
            )
            record_code, marker = expected[sample["scenario"]]
            self.assertEqual(package.metadata.record_code, record_code)
            text = (root / sample["file_path"]).read_text(encoding="utf-8-sig")
            body = text.partition("\n---\n")[2]  # The known fixture's closing metadata delimiter.
            self.assertTrue(body)
            combined = "".join(chunk.content for chunk in package.chunks)
            self.assertIn(marker, combined)
            # Covers real long tables/page text, not just artificial short inputs.
            self.assertEqual("".join(combined.split()), "".join(body.split()))
            self.assertTrue(all(len(chunk.content) <= manifest["max_chunk_chars"] for chunk in package.chunks))

    def test_copied_archives_keep_recorded_bytes_without_claiming_new_policy_verification(self):
        root = Path(__file__).resolve().parents[1]
        provenance = json.loads((root / "knowledge_base/processing/sample-provenance.json").read_text(encoding="utf-8"))
        self.assertFalse(provenance["policy_verification_performed"])
        for item in provenance["files"]:
            raw = (root / item["storage_key"]).read_bytes()
            self.assertEqual(sha256(raw).hexdigest(), item["sha256"])
            self.assertEqual(len(raw), item["byte_size"])

    def test_sample_generation_is_repeatable_in_an_isolated_checkout(self):
        from scripts.parse_alpha_documents import build_samples, MANIFEST, OUTPUT, REPORT

        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        paths = {MANIFEST.as_posix(), manifest["preview_path"]}
        for sample in manifest["samples"]:
            package = DocumentPackage.model_validate_json(
                (root / OUTPUT / (sample["key"] + ".json")).read_text(encoding="utf-8")
            )
            paths.update(file.storage_key for file in package.files)
        with tempfile.TemporaryDirectory() as directory:
            isolated = Path(directory)
            for relative in paths:
                target = isolated / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / relative, target)
            first = build_samples(isolated)
            snapshot = {p.relative_to(isolated): p.read_bytes() for p in (isolated / OUTPUT).glob("*.json")}
            report = (isolated / REPORT).read_bytes()
            self.assertEqual(build_samples(isolated), first)
            self.assertEqual({p.relative_to(isolated): p.read_bytes() for p in (isolated / OUTPUT).glob("*.json")}, snapshot)
            self.assertEqual((isolated / REPORT).read_bytes(), report)


if __name__ == "__main__":
    unittest.main()
