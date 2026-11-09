import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from build_deliverables import calendar_date, compute_file_sha256, deadline_nodes, resolve_file_record

class ImportRulesTests(unittest.TestCase):
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
        self.assertIn('物理文件缺失（测试夹具模式）', note)

if __name__ == '__main__':
    unittest.main(verbosity=2)
