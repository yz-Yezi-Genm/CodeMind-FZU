import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from build_deliverables import calendar_date, compute_file_sha256, deadline_nodes

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
        """测试文件存在时：正常计算真实文件内容的 SHA-256 哈希值"""
        content = b'CodeMind-FZU test content for SHA-256 computation'
        with tempfile.NamedTemporaryFile('wb', delete=False) as tf:
            tf.write(content)
            temp_path = tf.name
        try:
            expected_sha = hashlib.sha256(content).hexdigest()
            actual_sha = compute_file_sha256(temp_path)
            self.assertEqual(actual_sha, expected_sha)
            self.assertEqual(len(actual_sha), 64)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_file_sha256_when_file_not_exists(self):
        """测试文件不存在时：sha256 严格为 None (NULL)，严禁生成虚假哈希"""
        non_existent = 'non_existent_dummy_file_path_xyz123.pdf'
        self.assertIsNone(compute_file_sha256(non_existent))

if __name__ == '__main__':
    unittest.main(verbosity=2)
