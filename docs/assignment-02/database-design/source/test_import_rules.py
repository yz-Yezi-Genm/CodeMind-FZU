import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import shutil
import build_deliverables as builder

from build_deliverables import calendar_date, compute_file_sha256, deadline_nodes, resolve_file_record

class ImportRulesTests(unittest.TestCase):
    def test_default_clean_clone_prefers_complete_fixture(self):
        """无外部资料且旧31条索引存在时默认仍选44条夹具；显式配置优先。"""
        import csv
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = root / 'source/fixtures'
            fixture.mkdir(parents=True)
            fixture_csv = fixture / '知识库索引_44条_fixture.csv'
            shutil.copyfile(builder.FIXTURE_DIR / fixture_csv.name, fixture_csv)
            legacy = root / 'knowledge_base/政策资料'
            legacy.mkdir(parents=True)
            with fixture_csv.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                fields, rows = reader.fieldnames, list(reader)
            with (legacy / '知识库索引.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows[:31])
            with patch.object(builder, 'ROOT', root), patch.object(builder, 'FIXTURE_DIR', fixture), patch.dict(os.environ, {'CODEMIND_KB_ROOT': ''}):
                self.assertEqual(builder.project_root(root / 'docs/assignment-02/database-design'), root)
                self.assertEqual(builder.project_root(root / 'standalone-package'), root / 'standalone-package')
                chosen, index = builder.resolve_kb_path()
                self.assertEqual((chosen, index), (fixture, fixture_csv))
                with index.open(encoding='utf-8-sig', newline='') as stream:
                    self.assertEqual(len(list(csv.DictReader(stream))), 44)
                self.assertEqual(builder.resolve_kb_path(legacy)[0], legacy)
                with self.assertRaises(FileNotFoundError):
                    builder.resolve_kb_path(root / 'missing-cli')
                with patch('os.getcwd', return_value=str(root)):
                    self.assertEqual(builder.resolve_kb_path('source/fixtures'), (fixture, fixture_csv))
                with patch.dict(os.environ, {'CODEMIND_KB_ROOT': str(legacy)}):
                    self.assertEqual(builder.resolve_kb_path()[0], legacy)
                    self.assertEqual(builder.resolve_kb_path(fixture)[0], fixture)
                with patch.dict(os.environ, {'CODEMIND_KB_ROOT': str(root / 'missing-env')}):
                    with self.assertRaises(FileNotFoundError):
                        builder.resolve_kb_path()
                external = root / 'audit_materials/knowledge/知识库/政策资料'
                external.mkdir(parents=True)
                shutil.copyfile(fixture_csv, external / '知识库索引.csv')
                self.assertEqual(builder.resolve_kb_path()[0], external)

    def test_real_date(self):
        self.assertEqual(calendar_date('2026-09-09'), '2026-09-09')

    def test_grade_is_not_date(self):
        self.assertIsNone(calendar_date('2023级开始施行'))

    def test_multiple_deadlines_not_collapsed(self):
        self.assertIsNone(calendar_date('线上学习2026-11-29；线上考试2026-12-06'))

    def test_timestamp_not_truncated(self):
        self.assertIsNone(calendar_date('2026-09-09 21:00'))

    def test_deadline_nodes_split_without_losing_raw(self):
        raw = '线上学习2026-11-29；线上考试2026-12-06'
        nodes = deadline_nodes(raw)
        self.assertEqual([n['due_on'] for n in nodes], ['2026-11-29', '2026-12-06'])
        self.assertEqual('；'.join(n['raw_text'] for n in nodes), raw)
        self.assertTrue(all(n['verification_status'] == 'pending' for n in nodes))

    def test_deadline_exact_time_and_unknown(self):
        nodes = deadline_nodes('2026-09-09 21:00；缴费按系统通知')
        self.assertEqual(nodes[0]['due_at'], '2026-09-09T21:00:00+08:00')
        self.assertEqual(nodes[1]['precision'], 'unknown')
        self.assertEqual(deadline_nodes('网上报名2026-10-12 24:00')[0]['precision'], 'unknown')

    def test_file_sha256_when_file_exists(self):
        """测试文件存在时：正常计算真实文件内容的 SHA-256 哈希值，状态与备注如实记录物理文件存在"""
        content = b'CodeMind-FZU test content for SHA-256 computation'
        with tempfile.NamedTemporaryFile('wb', delete=False) as tf:
            tf.write(content)
            temp_path = tf.name
        try:
            expected_sha = hashlib.sha256(content).hexdigest()
            actual_sha = compute_file_sha256(temp_path)
            self.assertEqual(actual_sha, expected_sha)
            self.assertEqual(len(actual_sha), 64)

            # 验证 resolve_file_record 在物理文件存在时的状态与说明
            raw_rec = {'正文文件': '正文.md', '正文提取状态': '已提取正文', '附件处理状态': ''}
            sha, status, note = resolve_file_record(Path(temp_path), raw_rec, 'extracted', '正文.md')
            self.assertEqual(sha, expected_sha)
            self.assertEqual(status, 'extracted')
            self.assertIn('已登记物理文件存在', note)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_file_sha256_when_file_not_exists(self):
        """测试文件不存在时：sha256 严格为 None (NULL)，区分物理缺失与原始索引状态并置为 failed"""
        non_existent = 'non_existent_dummy_file_path_xyz123.pdf'
        self.assertIsNone(compute_file_sha256(non_existent))

        # 验证 resolve_file_record 在内置夹具/物理文件缺失时的状态与说明
        raw_rec = {'正文文件': '正文.md', '正文提取状态': '已提取正文，待人工复核', '附件处理状态': '网页含附件'}
        sha, status, note = resolve_file_record(Path(non_existent), raw_rec, 'extracted', '正文.md')
        self.assertIsNone(sha)
        self.assertEqual(status, 'failed')
        self.assertIn('原始索引记录状态：[已提取正文，待人工复核]', note)
        self.assertIn('当前运行环境物理文件缺失', note)
        for role in ('original', 'attachment', 'curated'):
            sha, status, note = resolve_file_record(Path(non_existent), raw_rec, role, 'missing.pdf')
            self.assertIsNone(sha)
            self.assertEqual(status, 'failed')
            self.assertIn('原始索引记录状态', note)

if __name__ == '__main__':
    unittest.main(verbosity=2)
