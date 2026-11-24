"""生产 verify_answer() 的独立黑盒测试（V2.1 §11.3/11.4）。

直接针对 `backend/services/agent_generation.py` 的生产 `verify_answer()` 做黑盒测试，
不再使用参考校验函数。验证 Agent 对 Qwen 受约束输出的校验逻辑：

    {"answer": "基于已提供证据形成的自然语言回答。", "used_evidence_ids": ["E1", "E2"]}

覆盖边界（V2.1 §11.3/11.4）：
- 正常 JSON / 非法 JSON / 重复键
- 缺 answer / answer 为空 / 缺 used_evidence_ids / 空 used_evidence_ids
- 不存在 evidence_id / 重复 evidence_id / 跨请求（不属于本次 evidence 集合）evidence_id
- 答案与所选证据不一致（改写原文）
- 答案含证据无法支持的额外文本
- 请求的金额/日期事实未被所选证据覆盖

定位说明：
- 吴诗莹的 test_agent_workflow.py / test_agent_workflow_qwen.py 已通过 workflow 集成层
  覆盖了历史政策、跨请求证据隔离、精确引用等，本文件**不重复**那些集成测试。
- 本文件聚焦 verify_answer() 这个函数的**独立单元黑盒**边界（生产函数本身，
  不经 workflow 编排），补充集成测试难以单独触达的边界分支。
"""
from __future__ import annotations

import json
import re
import unittest
from datetime import date
from uuid import UUID

from backend.contracts.models import (
    AnswerMode,
    DocumentMetadata,
    ParsedChunk,
    RetrievedChunk,
)
from backend.services.agent_generation import PARTIAL_ANSWER, Evidence, verify_answer


def _chunk(chunk_id: int, content: str) -> RetrievedChunk:
    """构造合成 RetrievedChunk（非真实政策资料）。"""
    return RetrievedChunk(
        chunk_id=UUID(int=chunk_id), document_id=UUID(int=1000 + chunk_id),
        version_id=UUID(int=2000 + chunk_id), file_id=UUID(int=3000 + chunk_id),
        title=f"【测试替身】契约黑盒测试片段 {chunk_id}",
        content=content,
        source_url="https://example.invalid/blackbox",
        publisher="离线测试替身", score=0.01,
        published_on=date(2026, 1, 1),
        source_verification_status="verified",
        timeliness_verification_status="current", retrieval_status="enabled",
    )


def _evidence(chunk_id: int, content: str, *, mode: AnswerMode = AnswerMode.CURRENT_POLICY) -> Evidence:
    chunk = _chunk(chunk_id, content)
    metadata = DocumentMetadata(
        title=chunk.title, document_type="合成测试", category_name="测试",
        business_direction_codes=["POLICY_AFFAIRS"],
        record_code=f"BB-{chunk_id}", version_no="v1", publisher=chunk.publisher,
        source_url=chunk.source_url, published_on=chunk.published_on,
        effective_on=chunk.published_on,
        source_verification_status="verified", timeliness_verification_status="current",
        extraction_status="extracted", v1_inclusion_status="included",
        retrieval_status="enabled", temporal_notes={"human_approved": True},
        applicability_raw={"适用对象": "离线测试"},
    )
    parsed = ParsedChunk(chunk_no=1, source_file_key="synthetic.md", content=chunk.content)
    return Evidence(chunk=chunk, metadata=metadata, mode=mode, period=None, parsed=parsed)


E1_CONTENT = "校级奖学金需提交申请表和成绩单。"
E2_CONTENT = "国家奖学金每人每年8000元。"


def _evidence_map() -> dict[str, Evidence]:
    return {"E1": _evidence(1, E1_CONTENT), "E2": _evidence(2, E2_CONTENT)}


class VerifyAnswerFormatTests(unittest.TestCase):
    """verify_answer() 的 JSON 格式与字段校验（V2.1 §11.3）。"""

    def test_valid_output_passes(self):
        content = json.dumps({"answer": E1_CONTENT, "used_evidence_ids": ["E1"]}, ensure_ascii=False)
        answer, selected, partial = verify_answer(content, _evidence_map())
        self.assertEqual(answer, E1_CONTENT)
        self.assertEqual(len(selected), 1)
        self.assertFalse(partial)

    def test_invalid_json_rejected(self):
        for bad in ["这不是 JSON", "{", "null", "[]", "42"]:
            with self.subTest(content=bad):
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    verify_answer(bad, _evidence_map())

    def test_duplicate_json_key_rejected(self):
        content = '{"answer": "a", "answer": "b", "used_evidence_ids": ["E1"]}'
        with self.assertRaises(ValueError):
            verify_answer(content, _evidence_map())

    def test_wrong_shape_rejected(self):
        # 顶层多了非法字段
        content = json.dumps({"answer": E1_CONTENT, "used_evidence_ids": ["E1"], "citation": {}})
        with self.assertRaises(ValueError):
            verify_answer(content, _evidence_map())

    def test_missing_answer_rejected(self):
        content = json.dumps({"used_evidence_ids": ["E1"]})
        with self.assertRaises(ValueError):
            verify_answer(content, _evidence_map())

    def test_blank_answer_rejected(self):
        content = json.dumps({"answer": "   ", "used_evidence_ids": ["E1"]}, ensure_ascii=False)
        with self.assertRaises(ValueError):
            verify_answer(content, _evidence_map())

    def test_missing_used_evidence_ids_rejected(self):
        content = json.dumps({"answer": E1_CONTENT}, ensure_ascii=False)
        with self.assertRaises(ValueError):
            verify_answer(content, _evidence_map())

    def test_empty_used_evidence_ids_rejected(self):
        content = json.dumps({"answer": E1_CONTENT, "used_evidence_ids": []}, ensure_ascii=False)
        with self.assertRaises(ValueError):
            verify_answer(content, _evidence_map())


class VerifyAnswerEvidenceIdSafetyTests(unittest.TestCase):
    """verify_answer() 的证据 ID 与引用安全（V2.1 §11.4）。"""

    def test_unknown_evidence_id_rejected(self):
        content = json.dumps({"answer": E1_CONTENT, "used_evidence_ids": ["E99"]}, ensure_ascii=False)
        with self.assertRaises(ValueError):
            verify_answer(content, _evidence_map())

    def test_duplicate_evidence_id_rejected(self):
        content = json.dumps({"answer": E1_CONTENT, "used_evidence_ids": ["E1", "E1"]}, ensure_ascii=False)
        with self.assertRaises(ValueError):
            verify_answer(content, _evidence_map())

    def test_cross_request_evidence_id_rejected(self):
        # 另一请求的 evidence 集合是 {F1}，本请求的 evidence 集合是 {E1, E2}
        content = json.dumps({"answer": E1_CONTENT, "used_evidence_ids": ["F1"]}, ensure_ascii=False)
        with self.assertRaises(ValueError):
            verify_answer(content, _evidence_map())  # 本请求集合没有 F1


class VerifyAnswerContentFidelityTests(unittest.TestCase):
    """verify_answer() 的答案与证据一致性校验（V2.1 §11.4）。"""

    def test_answer_rewritten_from_evidence_rejected(self):
        # 模型改写原文（加了证据不支持的结论）
        content = json.dumps({
            "answer": "校级奖学金需提交申请表和成绩单，且必须本人到场。",
            "used_evidence_ids": ["E1"],
        }, ensure_ascii=False)
        with self.assertRaises(ValueError):
            verify_answer(content, _evidence_map())

    def test_answer_with_unsupported_extra_text_rejected(self):
        content = json.dumps({
            "answer": E1_CONTENT + "\n还可以申请额外补助。",
            "used_evidence_ids": ["E1"],
        }, ensure_ascii=False)
        with self.assertRaises(ValueError):
            verify_answer(content, _evidence_map())

    def test_multiple_evidence_joined_by_newline_passes(self):
        content = json.dumps({
            "answer": E1_CONTENT + "\n" + E2_CONTENT,
            "used_evidence_ids": ["E1", "E2"],
        }, ensure_ascii=False)
        answer, selected, _ = verify_answer(content, _evidence_map())
        self.assertEqual(len(selected), 2)
        self.assertIn(E2_CONTENT, answer)

    def test_partial_answer_allowed(self):
        # 只回答了部分证据，最后带 PARTIAL_ANSWER 提示
        content = json.dumps({
            "answer": E1_CONTENT + "\n" + PARTIAL_ANSWER,
            "used_evidence_ids": ["E1"],
        }, ensure_ascii=False)
        _, selected, partial = verify_answer(content, _evidence_map())
        self.assertEqual(len(selected), 1)
        self.assertTrue(partial)

    def test_requested_amount_must_be_covered_by_selected_evidence(self):
        # 问题明确询问金额，但所选证据 E1 不含金额信息
        facts = (re.compile(r"\d[\d,.]*\s*(?:万元|元)"),)
        content = json.dumps({"answer": E1_CONTENT, "used_evidence_ids": ["E1"]}, ensure_ascii=False)
        with self.assertRaises(ValueError):
            verify_answer(content, _evidence_map(), facts=facts)

    def test_requested_amount_covered_by_evidence_passes(self):
        facts = (re.compile(r"\d[\d,.]*\s*(?:万元|元)"),)
        content = json.dumps({"answer": E2_CONTENT, "used_evidence_ids": ["E2"]}, ensure_ascii=False)
        _, selected, _ = verify_answer(content, _evidence_map(), facts=facts)
        self.assertEqual(len(selected), 1)


if __name__ == "__main__":
    unittest.main()
