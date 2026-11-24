"""Alpha 端到端测试：T1-T10 业务场景，走正式 Alpha 入口。

本文件把「学生提问 → FastAPI /api/v1/ask → Alpha Runtime 装配 → 业务规则 →
真实 BM25 检索 → Qwen 证据选择 → Citation 校验 → 返回结果」这条完整链路，
用**正式入口**（build_alpha_runtime + create_alpha_app）组装起来验证。

只对 Qwen 上游用 httpx.MockTransport 做离线替身（不消耗真实 API 额度）。

测试分类（统计口径不得混淆）：

- 第一类 Mock 测试：全替身（见其他 test_*.py）。
- 第二类 真实资料 + Mock Qwen：真实 DocumentPackage（官方 fixture / 临时合成）+ 真实
  LocalBM25Retriever + 真实业务规则 + Mock Qwen。本文件 AlphaE2ETests / AlphaE2EMultiTurnTests。
- 契约测试（非端到端）：AlphaContractGateTests（T6 来源核验门槛，Pydantic 契约层），
  不计入端到端统计。
- 第三类 真实 Qwen 集成测试：真实 Qwen API，需同时满足 QWEN_API_KEY 与
  RUN_LIVE_QWEN_TESTS=1 两个开关才运行，避免普通全量测试意外消耗额度。

重要：本文件使用的资料是「测试夹具」，不代表任何真实政策已经人工核验。
真实核验资料（knowledge_base/processed/alpha/approved/）就绪前，T1/T2 的
「真实核验资料 answered」验收仍属阻塞项，报告须如实标注，不降低生产审核门槛。
"""
from __future__ import annotations

import asyncio
import json
import os
import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

import httpx
from fastapi.testclient import TestClient

from backend.app.alpha import create_alpha_app
from backend.app.config import AppSettings, PROJECT_ROOT
from backend.contracts.models import (
    DocumentMetadata,
    DocumentPackage,
    FileProcessingStatus,
    ParsedChunk,
    ParsedFile,
    RetrievalStatus,
)
from backend.services.alpha_runtime import build_alpha_runtime
from backend.services.qwen_client import QwenLLMClient, QwenSettings

# 官方测试夹具目录（含 human_approved=true 的奖学金资料）
APPROVED_DIR = PROJECT_ROOT / "tests/fixtures/alpha_approved"
UNAPPROVED_DIR = PROJECT_ROOT / "tests/fixtures/alpha_unapproved"
PARTIAL_DIR = PROJECT_ROOT / "tests/fixtures/alpha_partial"
MISSING_DIR = PROJECT_ROOT / "tests/fixtures/missing-approved"
_APPROVED_CONTENT = "2026年奖学金申请需提交申请表和成绩单。"


def _build_package(
    *,
    record_code: str,
    title: str,
    content: str,
    category_name: str,
    applicability: dict,
    retrieval_status: RetrievalStatus = RetrievalStatus.ENABLED,
    human_approved: bool = True,
    source_verified: str = "verified",
    timeliness: str = "current",
) -> DocumentPackage:
    """构造真实结构、明确标注为「测试替身」的 DocumentPackage。

    这些资料不是真实政策、未经人工核验，仅用于验证正式运行链路。
    """
    return DocumentPackage(
        metadata=DocumentMetadata(
            title=title,
            document_type="管理办法",
            category_name=category_name,
            business_direction_codes=["POLICY_AFFAIRS"],
            record_code=record_code,
            version_no="e2e-v1",
            publisher="测试替身发布方",
            source_url="https://example.invalid/e2e-policy",
            published_on=date(2026, 1, 1),
            effective_on=date(2026, 1, 1),
            source_verification_status=source_verified,
            timeliness_verification_status=timeliness,
            extraction_status="extracted",
            v1_inclusion_status="included",
            retrieval_status=retrieval_status,
            temporal_notes={"human_approved": human_approved},
            applicability_raw=applicability,
        ),
        files=[
            ParsedFile(
                file_role="extracted",
                storage_key="policy.md",
                original_name="policy.md",
                processing_status=FileProcessingStatus.EXTRACTED,
            ),
        ],
        chunks=[
            ParsedChunk(
                chunk_no=1,
                content=content,
                source_file_key="policy.md",
                locator="第 1 条",
            ),
        ],
    )


def _write_package_files(root: Path, package: DocumentPackage) -> None:
    """把 package 的 source file 落盘并回填 sha256，供正式 loader 的完整性检查。"""
    for file in package.files:
        path = root / file.storage_key
        path.parent.mkdir(parents=True, exist_ok=True)
        data = ("SYNTHETIC E2E FIXTURE ONLY\n" + "\n".join(
            c.content for c in package.chunks
        )).encode()
        path.write_bytes(data)
        file.sha256 = sha256(data).hexdigest()


class _MockQwen:
    """离线 Qwen 替身：从 workflow 发来的证据里选第一条逐字返回。

    通过 `output` 可返回固定内容（用于伪造证据 ID / 改写答案 测试），
    通过 `fail` / `status` 模拟超时与上游错误。所有出站 HTTP client 由测试
    用例通过 `addCleanup` 统一 await 关闭。
    """

    def __init__(self, *, output=None, fail=None, status=None):
        self.observed: list[dict] = []
        self._output = output  # 固定输出（用于伪造/改写测试）
        self._fail = fail      # 抛异常（用于超时测试）
        self._status = status  # 固定 HTTP 状态码
        self.llm = None
        self.upstream = None

    def build(self):
        def handler(request):
            payload = json.loads(request.content)
            self.observed.append(payload)
            if self._fail is not None:
                raise self._fail
            if self._status is not None:
                return httpx.Response(self._status)
            evidence = json.loads(payload["messages"][-1]["content"])["evidence"]
            if self._output is not None:
                content = json.dumps(self._output(evidence), ensure_ascii=False)
            elif not evidence:
                content = json.dumps({"answer": "", "used_evidence_ids": []}, ensure_ascii=False)
            else:
                content = json.dumps({
                    "answer": evidence[0]["content"],
                    "used_evidence_ids": [evidence[0]["evidence_id"]],
                }, ensure_ascii=False)
            return httpx.Response(200, json={
                "model": "offline-e2e-qwen-fixture",
                "choices": [{"message": {"content": content}}],
            })

        self.upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.llm = QwenLLMClient(
            QwenSettings(api_key="offline-e2e-not-a-real-key", max_retries=0),
            http_client=self.upstream,
        )
        return self.llm

    async def aclose(self):
        """异步关闭底层 HTTP client，避免遗留资源。"""
        if self.upstream is not None:
            await self.upstream.aclose()


def _close_qwen_sync(qwen: _MockQwen) -> None:
    """同步 addCleanup 包装：在独立事件循环里 await 关闭 upstream。"""
    if qwen.upstream is not None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(qwen.aclose())
            return
        # 若已有运行中的循环（极少见于同步 TestCase），交给异步侧处理
        asyncio.get_event_loop().run_until_complete(qwen.aclose())


def _install_qwen_cleanup(testcase: unittest.TestCase, qwen: _MockQwen) -> None:
    """注册统一清理，确保每个用例结束时关闭 Mock Qwen 的 HTTP client。"""
    testcase.addCleanup(_close_qwen_sync, qwen)


# ---------------------------------------------------------------------------
# 第二类：正式 Alpha 入口 + 官方 fixture + Mock Qwen，走 HTTP 全链路
# ---------------------------------------------------------------------------
class AlphaE2ETests(unittest.TestCase):
    """通过 build_alpha_runtime + create_alpha_app 的正式入口做端到端验收。"""

    def _app(self, qwen, *, package_dir=APPROVED_DIR, clarification=None, evidence=None):
        settings = AppSettings(alpha_package_dir=package_dir)

        async def runtime_builder():
            return await build_alpha_runtime(
                settings,
                llm_client=qwen.llm,
                file_root=PROJECT_ROOT,
                clarification_rule=clarification,
                evidence_check=evidence,
            )

        return create_alpha_app(settings=settings, runtime_builder=runtime_builder)

    def test_T1_competition_answered_with_traceable_citation(self):
        """T1 竞赛认定：补齐业务所需信息（竞赛级别认定 + 具体竞赛名），
        严格断言 answered 且引用可追溯。"""
        with TemporaryDirectory() as folder:
            root = Path(folder)
            package = _build_package(
                record_code="福大-2026-竞赛项目级别认定",
                title="福州大学2026年大学生学科竞赛级别认定结果",
                category_name="竞赛与创新创业",
                content="蓝桥杯全国软件和信息技术专业人才大赛认定为国家级A类学科竞赛。",
                applicability={"适用对象": "本科生", "适用年度": "2026年"},
            )
            _write_package_files(root, package)
            (root / "competition.json").write_text(
                package.model_dump_json(), encoding="utf-8"
            )

            qwen = _MockQwen()
            qwen.build()
            _install_qwen_cleanup(self, qwen)
            settings = AppSettings(alpha_package_dir=root)

            async def runtime_builder():
                return await build_alpha_runtime(
                    settings, llm_client=qwen.llm, file_root=root,
                )

            app = create_alpha_app(settings=settings, runtime_builder=runtime_builder)
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/ask",
                    json={"query": "学科竞赛级别认定，蓝桥杯是什么级别？"},
                )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "answered")
        self.assertTrue(body["citations"])
        citation = body["citations"][0]
        self.assertEqual(citation["excerpt"], package.chunks[0].content)
        self.assertEqual(citation["source_url"], "https://example.invalid/e2e-policy")
        self.assertEqual(len(qwen.observed), 1)

    def test_T2_scholarship_answered_with_exact_excerpt(self):
        """T2 奖学金场景：官方 fixture + 真实业务规则，问具体类别触发 answered。"""
        qwen = _MockQwen()
        qwen.build()
        _install_qwen_cleanup(self, qwen)
        app = self._app(qwen)
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                json={"query": "优秀学生综合奖学金申请需要提交什么材料？"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "answered")
        self.assertEqual(body["citations"][0]["excerpt"], _APPROVED_CONTENT)
        self.assertEqual(
            body["citations"][0]["source_url"],
            "https://example.invalid/test-policy",
        )
        self.assertEqual(len(qwen.observed), 1)

    def test_T3_scholarship_without_category_needs_clarification(self):
        """T3 缺类别：业务规则应追问类别（明确断言追问内容），而非生成笼统答案。"""
        qwen = _MockQwen()
        qwen.build()
        _install_qwen_cleanup(self, qwen)
        app = self._app(qwen)
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                json={"query": "奖学金申请需要什么材料？"},
            )
        body = response.json()
        self.assertEqual(body["status"], "needs_clarification")
        self.assertIsNone(body["answer"])
        self.assertEqual(
            body["clarifying_question"],
            "你想问的是校级优秀学生综合奖学金、国家奖学金，还是学院层面的院级奖学金？",
        )
        self.assertEqual(body["citations"], [])
        self.assertEqual(qwen.observed, [])  # 追问时不调用模型

    def test_T4_missing_knowledge_base_dir_yields_503(self):
        """T4a 知识库目录缺失：正式入口应返回 503 KNOWLEDGE_BASE_UNAVAILABLE。"""
        qwen = _MockQwen()
        qwen.build()
        _install_qwen_cleanup(self, qwen)
        app = self._app(qwen, package_dir=MISSING_DIR)
        with TestClient(app) as client:
            response = client.post("/api/v1/ask", json={"query": "推免条件是什么？"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "KNOWLEDGE_BASE_UNAVAILABLE")

    def test_T4_empty_knowledge_base_dir_yields_503(self):
        """T4b 知识库目录存在但为空：正式入口同样返回 503（无可用已审核资料）。"""
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            empty_dir = Path(folder) / "approved"
            empty_dir.mkdir()
            qwen = _MockQwen()
            qwen.build()
            _install_qwen_cleanup(self, qwen)
            app = self._app(qwen, package_dir=empty_dir)
            with TestClient(app) as client:
                response = client.post("/api/v1/ask", json={"query": "推免条件是什么？"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"]["code"], "KNOWLEDGE_BASE_UNAVAILABLE")

    def test_T5_unapproved_data_is_skipped(self):
        """T5 未审核资料：human_approved=false 的资料被加载器跳过，无法装配正式运行时。"""
        qwen = _MockQwen()
        qwen.build()
        _install_qwen_cleanup(self, qwen)
        app = self._app(qwen, package_dir=UNAPPROVED_DIR)
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                json={"query": "优秀学生综合奖学金申请需要提交什么材料？"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "KNOWLEDGE_BASE_UNAVAILABLE")

    def test_T6b_partial_index_package_is_rejected_by_runtime(self):
        """T6b：human_approved 但源文件未就绪（needs_ocr）的部分索引资料，
        无法装配正式运行时（返回 503 KNOWLEDGE_BASE_UNAVAILABLE）。"""
        qwen = _MockQwen()
        qwen.build()
        _install_qwen_cleanup(self, qwen)
        app = self._app(qwen, package_dir=PARTIAL_DIR)
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                json={"query": "优秀学生综合奖学金申请需要提交什么材料？"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "KNOWLEDGE_BASE_UNAVAILABLE")

    def test_T7_qwen_timeout_returns_sanitized_error(self):
        """T7 Qwen 超时：上游超时应映射为 504 MODEL_TIMEOUT，而非业务 answered。"""
        qwen = _MockQwen(fail=httpx.TimeoutException("simulated", request=None))
        qwen.build()
        _install_qwen_cleanup(self, qwen)
        app = self._app(qwen)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/v1/ask",
                json={"query": "优秀学生综合奖学金申请需要提交什么材料？"},
            )
        body = response.json()
        self.assertEqual(response.status_code, 504)
        self.assertEqual(body["error"]["code"], "MODEL_TIMEOUT")
        self.assertNotIn("status", body)

    def test_T8_model_returns_unknown_evidence_id_is_rejected(self):
        """T8 正确答案搭配未知证据 ID 时拒答。"""
        qwen = _MockQwen()
        qwen.build()
        _install_qwen_cleanup(self, qwen)
        app = self._app(qwen)

        qwen._output = lambda evidence: {"answer": _APPROVED_CONTENT, "used_evidence_ids": [str(uuid4())]}
        with TestClient(app) as client:
            response = client.post("/api/v1/ask", json={"query": "优秀学生综合奖学金申请需要提交什么材料？"})
        body = response.json()
        self.assertEqual(body["status"], "insufficient_evidence")
        self.assertEqual(body["citations"], [])
        self.assertTrue(any(w["code"] == "UNSUPPORTED_GENERATION" for w in body["warnings"]))

    def test_T9_model_answer_can_be_rejected_even_with_valid_evidence_id(self):
        """T9 使用本次合法证据 ID，验证篡改的答案仍会被拦截。"""
        qwen = _MockQwen()
        qwen.build()
        _install_qwen_cleanup(self, qwen)
        app = self._app(qwen)

        qwen._output = lambda evidence: {
            "answer": "改写后的政策结论（非原文）",
            "used_evidence_ids": [evidence[0]["evidence_id"]],
        }
        with TestClient(app) as client:
            response = client.post("/api/v1/ask", json={"query": "优秀学生综合奖学金申请需要提交什么材料？"})
        body = response.json()
        self.assertEqual(body["status"], "insufficient_evidence")
        self.assertEqual(body["citations"], [])
        self.assertTrue(any(w["code"] == "UNSUPPORTED_GENERATION" for w in body["warnings"]))


# ---------------------------------------------------------------------------
# 契约测试（非端到端）：T6 来源核验门槛在 Pydantic 契约层强制
# ---------------------------------------------------------------------------
class AlphaContractGateTests(unittest.TestCase):
    """资料审核契约门槛测试，不计入端到端（E2E）统计。"""

    def test_T6_unverified_source_cannot_be_enabled(self):
        """T6 来源核验未通过：source_verification_status 非 verified 的资料，
        无法以 retrieval_status=enabled 构造（Pydantic 契约强制），不能绕过审核。"""
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            _build_package(
                record_code="E2E-SCHOLARSHIP",
                title="本科生奖学金评定管理办法",
                category_name="综评与奖学金",
                content="优秀学生综合奖学金一等奖1500元/学期。",
                applicability={"适用对象": "本科生", "适用年度": "2026年"},
                source_verified="pending",  # 未核验
            )


# ---------------------------------------------------------------------------
# T10 多轮会话（HTTP 层，正式入口）
# ---------------------------------------------------------------------------
class AlphaE2EMultiTurnTests(unittest.TestCase):
    """同 conversation_id 连续 HTTP 请求，验证会话上下文跨轮次生效。"""

    def test_T10_http_conversation_context_across_turns(self):
        qwen = _MockQwen()
        qwen.build()
        _install_qwen_cleanup(self, qwen)
        settings = AppSettings(alpha_package_dir=APPROVED_DIR)

        async def runtime_builder():
            return await build_alpha_runtime(
                settings, llm_client=qwen.llm, file_root=PROJECT_ROOT,
            )

        app = create_alpha_app(settings=settings, runtime_builder=runtime_builder)
        with TestClient(app) as client:
            first = client.post(
                "/api/v1/ask",
                json={"query": "优秀学生综合奖学金申请需要提交什么材料？"},
            )
            conversation_id = first.json()["conversation_id"]
            self.assertEqual(first.json()["status"], "answered")

            second = client.post(
                "/api/v1/ask",
                json={"query": "还需要成绩单吗？", "conversation_id": conversation_id},
            )
            fresh = client.post("/api/v1/ask", json={"query": "还需要成绩单吗？"})
            history = app.state.alpha_runtime.session_store.history(
                UUID(conversation_id)
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(fresh.json()["status"], "needs_clarification")
        self.assertNotEqual(fresh.json()["conversation_id"], conversation_id)
        # 第二轮正常完成问答：状态 answered 且带有效引用
        second_body = second.json()
        self.assertEqual(second_body["status"], "answered")
        self.assertTrue(second_body["citations"])
        self.assertEqual(second_body["citations"][0]["excerpt"], _APPROVED_CONTENT)
        # 会话存储确实保存了 4 条记录（2 用户 + 2 助手）
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0].content, "优秀学生综合奖学金申请需要提交什么材料？")
        self.assertEqual(history[2].content, "还需要成绩单吗？")

        # 第二轮触发了第二次模型调用，且发给 Qwen 的用户上下文包含了第一轮问题
        self.assertEqual(len(qwen.observed), 2)
        second_payload = qwen.observed[-1]
        user_message = json.loads(second_payload["messages"][-1]["content"])
        context = "\n".join([*user_message["user_context"], user_message["question"]])
        self.assertIn("优秀学生综合奖学金申请需要提交什么材料？", context)
        self.assertIn("还需要成绩单吗？", context)


# ---------------------------------------------------------------------------
# 第三类：真实 Qwen 集成测试（需 QWEN_API_KEY 且 RUN_LIVE_QWEN_TESTS=1）
# ---------------------------------------------------------------------------
class AlphaE2ERealQwenTests(unittest.TestCase):
    """真实 Retriever + 真实 Qwen API。

    仅当同时满足 QWEN_API_KEY 与 RUN_LIVE_QWEN_TESTS=1 两个条件时才运行，
    避免普通全量测试意外消耗真实 API 额度。
    """

    def test_real_qwen_end_to_end(self):
        if os.getenv("RUN_LIVE_QWEN_TESTS") != "1":
            self.skipTest("未启用 RUN_LIVE_QWEN_TESTS=1，跳过真实 Qwen 集成测试。")
        if not os.getenv("QWEN_API_KEY"):
            self.skipTest("未配置 QWEN_API_KEY，跳过真实 Qwen 集成测试。")

        from backend.services.qwen_client import create_qwen_client_from_env

        settings = AppSettings(alpha_package_dir=APPROVED_DIR)

        async def runtime_builder():
            return await build_alpha_runtime(
                settings, llm_client=create_qwen_client_from_env(),
                file_root=PROJECT_ROOT,
            )

        app = create_alpha_app(settings=settings, runtime_builder=runtime_builder)
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                json={"query": "优秀学生综合奖学金申请需要提交什么材料？"},
            )
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(body["status"], {"answered", "insufficient_evidence"})


if __name__ == "__main__":
    unittest.main()
