"""Beta Qwen 受约束输出格式校验测试（V2.1-Final §11.3）。

V2.1 规定 Qwen 内部输出必须为严格 JSON（无 Markdown 围栏）：

    {"answer": "基于已提供证据形成的自然语言回答。", "used_evidence_ids": ["E1", "E2"]}

本文件测试「输出格式与证据引用安全」的校验规则，覆盖任务书 §11.3/11.4 列出的
非法输出场景。

定位说明：AgentWorkflow 的受约束生成尚未实现（Beta 开发中），因此本文件用一个
**参考校验函数** `_validate_qwen_output` 作为测试靶子，把 V2.1 的格式/ID 校验规则
固化为可执行、可测试的用例。该函数**不是**生产实现，后续阶段应替换为吴诗莹
交付的真实校验逻辑——届时本文件的测试用例直接作用于真实校验函数，验证结果不变。

明确边界：
- 本文件只校验「输出格式 + 证据 ID 合法性」，不校验「答案内容与原文一致」——
  后者需要 Agent 接真实 RetrievedChunk 才能做，属于后续阶段的事实一致性测试。
- 证据 ID 校验只能证明引用指向真实片段，不能单独证明答案正确（V2.1 §11.4）。
"""
from __future__ import annotations

import json
import unittest


def _validate_qwen_output(
    content: str,
    *,
    available_ids: set[str],
) -> tuple[bool, str]:
    """参考校验实现：解析并校验 Qwen 受约束输出。

    返回 (是否通过, 拒绝原因)。这不是生产实现，仅用于固化 V2.1 校验规则。

    规则（V2.1 §11.3）：
    1. 必须是合法 JSON（严格，无 Markdown 代码围栏）。
    2. 顶层必须且只能有 answer / used_evidence_ids 两个字段。
    3. answer 必须是非空字符串。
    4. used_evidence_ids 必须是非空字符串列表，且每个 ID 都在 available_ids 中。
    5. 不得出现 citation / source_url 等模型自造字段。
    """
    stripped = content.strip()

    # 1. 拒绝 Markdown 代码围栏（V2.1 明确不允许）
    if stripped.startswith("```"):
        return False, "模型输出包含 Markdown 代码围栏"

    # 2. 解析 JSON
    try:
        payload = json.loads(stripped)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False, "模型输出不是合法 JSON"

    if not isinstance(payload, dict):
        return False, "模型输出顶层不是 JSON 对象"

    # 3. 只允许 answer / used_evidence_ids 两个字段（禁止自造 citation/url）
    allowed = {"answer", "used_evidence_ids"}
    extra = set(payload.keys()) - allowed
    if extra:
        return False, f"模型输出包含非法字段：{sorted(extra)}"

    # 4. answer 非空
    answer = payload.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        return False, "模型输出缺少或包含空的 answer"

    # 5. used_evidence_ids 非空且元素为字符串
    ids = payload.get("used_evidence_ids")
    if not isinstance(ids, list) or not ids:
        return False, "模型输出缺少或包含空的 used_evidence_ids"
    if not all(isinstance(item, str) for item in ids):
        return False, "used_evidence_ids 包含非字符串元素"

    # 6. 每个 ID 必须在本次请求的可用集合中
    for eid in ids:
        if eid not in available_ids:
            return False, f"引用了不存在的 evidence_id：{eid}"

    return True, ""


class QwenOutputFormatTests(unittest.TestCase):
    """V2.1 §11.3 输出格式校验：正常与非法 JSON。"""

    AVAILABLE = {"E1", "E2"}

    def test_valid_output_passes(self):
        # Q-1：仅验证「JSON 格式 + evidence_id 合法性」通过。
        # 注意：本测试**不**覆盖「ID 映射到真实 RetrievedChunk → 构造 Citation」
        # 的完整过程（那是后续 Agent 集成测试，需生产实现）。
        ok, reason = _validate_qwen_output(
            '{"answer": "校级奖学金需提交申请表。", "used_evidence_ids": ["E1"]}',
            available_ids=self.AVAILABLE,
        )
        self.assertTrue(ok, reason)

    def test_invalid_json_rejected(self):
        for bad in ["这不是 JSON", "{", "null", "[]", "42"]:
            with self.subTest(content=bad):
                ok, _ = _validate_qwen_output(bad, available_ids=self.AVAILABLE)
                self.assertFalse(ok)

    def test_markdown_fence_rejected(self):
        content = '```json\n{"answer":"x","used_evidence_ids":["E1"]}\n```'
        ok, reason = _validate_qwen_output(content, available_ids=self.AVAILABLE)
        self.assertFalse(ok)
        self.assertIn("围栏", reason)

    def test_missing_answer_rejected(self):
        ok, reason = _validate_qwen_output(
            '{"used_evidence_ids": ["E1"]}', available_ids=self.AVAILABLE,
        )
        self.assertFalse(ok)
        self.assertIn("answer", reason)

    def test_empty_answer_rejected(self):
        ok, _ = _validate_qwen_output(
            '{"answer": "   ", "used_evidence_ids": ["E1"]}',
            available_ids=self.AVAILABLE,
        )
        self.assertFalse(ok)

    def test_missing_used_evidence_ids_rejected(self):
        ok, reason = _validate_qwen_output(
            '{"answer": "校级奖学金需提交申请表。"}', available_ids=self.AVAILABLE,
        )
        self.assertFalse(ok)
        self.assertIn("used_evidence_ids", reason)

    def test_empty_used_evidence_ids_rejected(self):
        ok, _ = _validate_qwen_output(
            '{"answer": "x", "used_evidence_ids": []}', available_ids=self.AVAILABLE,
        )
        self.assertFalse(ok)


class QwenEvidenceIdSafetyTests(unittest.TestCase):
    """V2.1 §11.4 证据 ID 与引用安全。"""

    AVAILABLE = {"E1", "E2"}

    def test_unknown_evidence_id_rejected(self):
        # Q-6：引用一个完全不存在于本次可用集合的 ID
        ok, reason = _validate_qwen_output(
            '{"answer": "x", "used_evidence_ids": ["E99"]}',
            available_ids=self.AVAILABLE,
        )
        self.assertFalse(ok)
        self.assertIn("E99", reason)

    def test_id_not_in_current_request_set_rejected(self):
        # Q-7：同一次请求内，引用一个「不属于本次证据集合」的 ID
        # （区别于 Q-8：这里只有单次请求语境，ID 就是不在本次集合里）
        ok, reason = _validate_qwen_output(
            '{"answer": "x", "used_evidence_ids": ["E3"]}',
            available_ids=self.AVAILABLE,  # 本次集合只有 E1、E2
        )
        self.assertFalse(ok)
        self.assertIn("E3", reason)

    def test_cross_request_evidence_id_rejected(self):
        # Q-8：两个不同请求各自持有独立证据集合，模型引用对方请求的 ID。
        # 请求 A 的集合 = {E1, E2}，请求 B 的集合 = {F1, F2}。
        # 处理请求 A 时，模型却返回了请求 B 的 F1，应被拒绝（跨请求隔离）。
        request_a_ids = {"E1", "E2"}
        request_b_ids = {"F1", "F2"}
        # 模拟请求 A：available_ids 是 A 的集合，模型返回了 B 的 ID
        ok, reason = _validate_qwen_output(
            '{"answer": "x", "used_evidence_ids": ["F1"]}',
            available_ids=request_a_ids,
        )
        self.assertFalse(ok)
        self.assertIn("F1", reason)
        # 反向验证：F1 确实属于请求 B 的集合（证明这是「跨请求」而非「随机不存在」）
        self.assertIn("F1", request_b_ids)
        self.assertNotIn("F1", request_a_ids)

    def test_model_generated_citation_field_rejected(self):
        # V2.1 §11.3：模型不得自行生成 Citation / 来源 URL
        ok, reason = _validate_qwen_output(
            json.dumps({
                "answer": "x",
                "used_evidence_ids": ["E1"],
                "citation": {"source_url": "https://example.com"},
            }),
            available_ids=self.AVAILABLE,
        )
        self.assertFalse(ok)
        self.assertIn("citation", reason)

    def test_model_generated_url_field_rejected(self):
        ok, reason = _validate_qwen_output(
            json.dumps({
                "answer": "x",
                "used_evidence_ids": ["E1"],
                "source_url": "https://example.com",
            }),
            available_ids=self.AVAILABLE,
        )
        self.assertFalse(ok)
        self.assertIn("source_url", reason)


if __name__ == "__main__":
    unittest.main()
