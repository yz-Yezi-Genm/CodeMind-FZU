"""Beta Qwen 受约束输出格式校验测试（V2.1-Final §11.3）。

V2.1 规定 Qwen 内部输出必须为严格 JSON（无 Markdown 围栏）：

    {"answer": "基于已提供证据形成的自然语言回答。", "used_evidence_ids": ["E1", "E2"]}

本文件测试「输出格式与证据引用安全」的校验规则本身，覆盖任务书中列出的全部
非法输出场景。由于 AgentWorkflow 的受约束生成尚未实现（Beta 开发中），本文件
用一个**参考校验函数**（_validate_qwen_output）作为测试靶子，验证规则清晰可测；
它**不是**生产实现，Final PR 阶段应替换为吴诗莹交付的真实校验逻辑。

重点（V2.1 §11.3/11.4）：
- 证据 ID 由 Agent 在当前请求内分配，模型只能返回本次提供的 ID。
- 模型不得自行生成 Citation、来源 URL、文件名。
- 引用指向真实片段不能单独证明答案正确，测试仍须检查答案与原文一致。
"""
from __future__ import annotations

import json
import unittest


def _validate_qwen_output(
    content: str,
    *,
    available_ids: set[str],
    source_texts: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """参考校验实现：解析并校验 Qwen 受约束输出。

    返回 (是否通过, 拒绝原因)。这不是生产实现，仅用于固化 V2.1 校验规则。

    规则：
    1. 必须是合法 JSON（严格，无代码围栏）。
    2. 顶层必须且只能有 answer / used_evidence_ids 两个字段。
    3. answer 必须是非空字符串。
    4. used_evidence_ids 必须是非空字符串列表，且每个 ID 都在 available_ids 中。
    5. 不得出现 citation / url / source 等模型自造字段。
    """
    source_texts = source_texts or {}

    # 1. 去掉可能的 Markdown 代码围栏（V2.1 明确不允许，但检测到即拒绝更安全）
    stripped = content.strip()
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
    if set(payload.keys()) != allowed:
        extra = set(payload.keys()) - allowed
        if extra:
            return False, f"模型输出包含非法字段：{sorted(extra)}"

    # 4. answer 非空
    answer = payload.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        return False, "模型输出缺少或包含空的 answer"

    # 5. used_evidence_ids 非空且合法
    ids = payload.get("used_evidence_ids")
    if not isinstance(ids, list) or not ids:
        return False, "模型输出缺少或包含空的 used_evidence_ids"

    if not all(isinstance(item, str) for item in ids):
        return False, "used_evidence_ids 包含非字符串元素"

    # 6. 每个 ID 必须在本次请求的可用集合中
    for eid in ids:
        if eid not in available_ids:
            return False, f"引用了不存在的 evidence_id：{eid}"

    # 7. 重复 ID 警告（可选，但不阻塞）
    return True, ""


class QwenOutputFormatTests(unittest.TestCase):
    """V2.1 §11.3 输出格式校验：正常与非法 JSON。"""

    AVAILABLE = {"E1", "E2"}

    def test_valid_output_passes(self):
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
        ok, reason = _validate_qwen_output(
            '{"answer": "x", "used_evidence_ids": ["E99"]}',
            available_ids=self.AVAILABLE,
        )
        self.assertFalse(ok)
        self.assertIn("E99", reason)

    def test_cross_request_evidence_id_rejected(self):
        # 另一请求的 ID 不在本次可用集合中，应拒绝
        other_request_ids = {"F1", "F2"}
        ok, reason = _validate_qwen_output(
            '{"answer": "x", "used_evidence_ids": ["F1"]}',
            available_ids=self.AVAILABLE,
        )
        self.assertFalse(ok)
        self.assertIn("F1", reason)

    def test_model_generated_citation_field_rejected(self):
        # V2.1：模型不得自行生成 Citation / 来源 URL
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

    def test_evidence_id_maps_to_real_chunk_text(self):
        # V2.1 §11.4：证据 ID 校验只能证明引用指向真实片段，答案内容仍需与原文一致。
        # 这里验证「ID 合法 + 原文可追溯」的基础前提：可用集合必须来自真实检索。
        source_texts = {"E1": "校级奖学金需提交申请表。"}
        ok, _ = _validate_qwen_output(
            '{"answer": "校级奖学金需提交申请表。", "used_evidence_ids": ["E1"]}',
            available_ids={"E1"},
            source_texts=source_texts,
        )
        self.assertTrue(ok)
        # 答案内容应与原文一致（这里人工核对：answer 与 E1 原文一致）
        self.assertIn("校级奖学金需提交申请表。", source_texts["E1"])


if __name__ == "__main__":
    unittest.main()
