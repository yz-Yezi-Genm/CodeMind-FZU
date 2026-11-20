"""Alpha 端到端测试：真实 Retriever + AgentWorkflow + Qwen 适配器 + HTTP 链路。

本文件把「学生提问 → FastAPI → AgentWorkflow → 业务规则 → 真实 BM25 检索 →
Qwen 证据选择 → Citation 校验 → 返回结果」这条链路，用**真实组件**组装起来跑，
只对 Qwen 上游用 httpx MockTransport 做离线替身（因为不能依赖真实 Qwen API）。

测试分类（统计口径不得混淆）：

- 第一类 Mock 测试：MockRetriever/Mock LLM 全部替身（见其他 test_*.py 文件）。
- 第二类 真实资料测试：真实 DocumentPackage + 真实 LocalBM25Retriever + Mock Qwen。
  由 AlphaE2ETests（T1/T2/T3/T4空库/T5/T7/T8/T9）与 AlphaE2EMultiTurnTests（T10）承担。
- 证据准入规则测试（非 BM25 端到端）：AgentWorkflowEvidenceGateTests（T6），
  用自定义 SingleChunkRetriever 验证 _eligible 门槛，不计入 BM25 端到端统计。
- 第三类 真实 Qwen 集成测试：真实 Retriever + 真实 Qwen API（需 QWEN_API_KEY，
  以 test_real_qwen_* 命名并自动 skip，直到环境变量就绪）。

明确标注的「待实现」项（用 @unittest.skip 标记，不冒充已通过）：

- test_future_year_policy_applicability：未来年度政策适用性判定未实现
  （AgentWorkflow 仅处理历史年度）。
- test_conversation_isolation：会话持久化/隔离未实现（依赖 alpha-real-runtime）。

重要：本文件里的合成资料是「测试替身」，retrieval_status=enabled 等状态是
构造出来的，不代表任何真实政策已经人工核验。真实核验资料（approved 目录）就绪前，
T1/T2 的「真实核验资料 answered」验收仍属阻塞项，测试报告须如实标注。
"""
from __future__ import annotations

import json
import unittest
from datetime import date
from uuid import UUID, uuid4

import httpx
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.contracts.models import (
    AgentRequest,
    AnswerStatus,
    ConversationTurn,
    DocumentMetadata,
    DocumentPackage,
    FileProcessingStatus,
    LLMRole,
    ParsedChunk,
    ParsedFile,
    RetrievalStatus,
    RetrievedChunk,
)
from backend.retrieval.local import LocalBM25Retriever
from backend.services.agent_workflow import AgentWorkflow
from backend.services.qwen_client import QwenLLMClient, QwenSettings

# 离线 Qwen 替身：把 workflow 发来的证据列表里的第一个片段，按「逐字原文」选回。
_FAKE_MODEL = "OFFLINE-E2E-FAKE-NOT-QWEN"


def _selection_from_prompt(payload: dict) -> str:
    """从 workflow 发给模型的 prompt 里，选第一条证据并原样 quote 返回。"""
    evidence = json.loads(payload["messages"][-1]["content"])["evidence"]
    assert evidence, "workflow 不应在无证据时调用模型"
    first = evidence[0]
    return json.dumps({
        "evidence": [{"chunk_id": first["chunk_id"], "quote": first["content"]}],
    }, ensure_ascii=False)


class _E2EFixtures:
    """构造真实结构、但明确标注为「测试替身」的 DocumentPackage。

    这些资料不是真实政策、未经人工核验，仅用于验证真实检索/工作流/引用链路。
    """

    @staticmethod
    def competition_package() -> DocumentPackage:
        metadata = DocumentMetadata(
            title="【测试替身】大学生学科竞赛级别认定办法",
            document_type="规范性文件",
            category_name="竞赛与创新创业",
            business_direction_codes=["POLICY_AFFAIRS"],
            record_code="E2E-COMPETITION",
            version_no="v1",
            publisher="测试替身发布方",
            source_url="https://example.invalid/e2e/competition",
            published_on=date(2026, 1, 1),
            effective_on=date(2026, 1, 1),
            source_verification_status="verified",
            timeliness_verification_status="current",
            extraction_status="extracted",
            v1_inclusion_status="included",
            retrieval_status=RetrievalStatus.ENABLED,
        )
        return DocumentPackage(
            metadata=metadata,
            files=[
                ParsedFile(
                    file_role="extracted", storage_key="competition.md",
                    original_name="competition.md",
                    processing_status=FileProcessingStatus.EXTRACTED,
                ),
            ],
            chunks=[
                ParsedChunk(
                    chunk_no=1,
                    content="国家级A类学科竞赛获奖可用于竞赛学分认定，须提供获奖证书原件。",
                    source_file_key="competition.md",
                    locator="第 2 条",
                ),
            ],
        )

    @staticmethod
    def _retrieved_chunk(**updates) -> RetrievedChunk:
        """构造一个来源未核验的 RetrievedChunk，用于测试 _eligible 门槛。"""
        base = dict(
            chunk_id=uuid4(), document_id=uuid4(), version_id=uuid4(),
            file_id=uuid4(),
            title="【测试替身】来源未核验片段",
            content="该片段来源尚未核验，不应进入正式回答。",
            source_url="https://example.invalid/e2e/unverified",
            score=0.9,
            source_verification_status="partial",
            timeliness_verification_status="current",
            retrieval_status="enabled",
        )
        base.update(updates)
        return RetrievedChunk(**base)

    @staticmethod
    def scholarship_package() -> DocumentPackage:
        metadata = DocumentMetadata(
            title="【测试替身】本科生奖学金评定管理办法",
            document_type="规范性文件",
            category_name="综评与奖学金",
            business_direction_codes=["POLICY_AFFAIRS"],
            record_code="E2E-SCHOLARSHIP",
            version_no="v1",
            publisher="测试替身发布方",
            source_url="https://example.invalid/e2e/scholarship",
            published_on=date(2026, 1, 1),
            effective_on=date(2026, 1, 1),
            source_verification_status="verified",
            timeliness_verification_status="current",
            extraction_status="extracted",
            v1_inclusion_status="included",
            retrieval_status=RetrievalStatus.ENABLED,
        )
        return DocumentPackage(
            metadata=metadata,
            files=[
                ParsedFile(
                    file_role="extracted", storage_key="scholarship.md",
                    original_name="scholarship.md",
                    processing_status=FileProcessingStatus.EXTRACTED,
                ),
            ],
            chunks=[
                ParsedChunk(
                    chunk_no=1,
                    content="优秀学生综合奖学金一等奖1500元/学期，评定比例不超过本专业前10%。",
                    source_file_key="scholarship.md",
                    locator="第七条",
                ),
            ],
        )


class _Runtime:
    """真实组件装配：LocalBM25Retriever + AgentWorkflow + Qwen(httpx MockTransport)。"""

    def __init__(self, handler, *, packages=None, today=None):
        transport = httpx.MockTransport(handler)
        self.upstream = httpx.AsyncClient(transport=transport)
        self.llm = QwenLLMClient(
            QwenSettings(api_key="offline-e2e-not-a-real-key", max_retries=0),
            http_client=self.upstream,
        )
        self.retriever = LocalBM25Retriever()
        self.workflow = AgentWorkflow(
            self.retriever, self.llm, today=today or (lambda: date(2026, 11, 20)),
        )
        for package in (packages or []):
            asyncio_run(self.retriever.index_document(package))

    def app(self):
        return create_app(agent_service=self.workflow, llm_client=self.llm)


def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # 在已运行的事件循环里（IsolatedAsyncioTestCase 环境）直接用 run_until_complete 不合适，
    # 这里统一走新线程跑，避免嵌套 loop 报错。
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _answered_handler(request):
    """Qwen 替身：返回逐字证据选择。"""
    payload = json.loads(request.content)
    return httpx.Response(200, json={
        "model": _FAKE_MODEL,
        "choices": [{"message": {"content": _selection_from_prompt(payload)}}],
    })


# ---------------------------------------------------------------------------
# 第二类：真实资料（测试替身）+ 真实 Retriever + Mock Qwen，走 HTTP 全链路
# ---------------------------------------------------------------------------
class AlphaE2ETests(unittest.TestCase):
    """真实 Retriever + AgentWorkflow + Qwen 适配器 + FastAPI HTTP 的端到端链路。"""

    def test_T1_competition_answered_with_traceable_citation(self):
        runtime = _Runtime(_answered_handler, packages=[
            _E2EFixtures.competition_package(),
        ])
        with TestClient(runtime.app()) as client:
            response = client.post("/api/v1/ask", json={"query": "竞赛学分认定有什么条件？"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "answered")
        self.assertEqual(body["answer_mode"], "current_policy")
        self.assertTrue(body["citations"])
        citation = body["citations"][0]
        # 引用必须可追溯：chunk_id/文档/版本/来源网址/原文逐字一致
        self.assertIn("竞赛学分认定", citation["excerpt"])
        self.assertTrue(citation["source_url"].startswith("https://"))
        self.assertEqual(citation["source_verification_status"], "verified")
        self.assertEqual(citation["retrieval_status"], "enabled")
        UUID(citation["chunk_id"])
        self.assertTrue(body["warnings"])

    def test_T2_scholarship_answered_with_exact_excerpt(self):
        package = _E2EFixtures.scholarship_package()
        runtime = _Runtime(_answered_handler, packages=[package])
        with TestClient(runtime.app()) as client:
            # 问题与资料语义匹配：资料讲的是「金额与评定比例」，问题也问这个
            response = client.post("/api/v1/ask", json={"query": "2026学年优秀学生综合奖学金的金额和评定比例是多少？"})
        body = response.json()
        self.assertEqual(body["status"], "answered")
        # 摘录必须与资料原文逐字一致，不能改写或拼接
        self.assertEqual(body["citations"][0]["excerpt"], package.chunks[0].content)
        self.assertIn(package.chunks[0].content, body["answer"])
        # 选中的证据必须与问题相关（金额/比例），而非无关片段
        self.assertIn("1500元", body["citations"][0]["excerpt"])
        self.assertIn("前10%", body["citations"][0]["excerpt"])

    def test_T3_scholarship_without_year_needs_clarification(self):
        runtime = _Runtime(_answered_handler, packages=[_E2EFixtures.scholarship_package()])
        with TestClient(runtime.app()) as client:
            response = client.post("/api/v1/ask", json={"query": "奖学金怎么申请？"})
        body = response.json()
        self.assertEqual(body["status"], "needs_clarification")
        self.assertIsNone(body["answer"])
        self.assertTrue(body["clarifying_question"])
        self.assertEqual(body["citations"], [])

    def test_T4_empty_knowledge_base_yields_insufficient_evidence(self):
        """空知识库：任何问题都应返回 insufficient_evidence（NO_ELIGIBLE_EVIDENCE）。"""
        runtime = _Runtime(_answered_handler, packages=[])
        with TestClient(runtime.app()) as client:
            response = client.post("/api/v1/ask", json={"query": "2026学年推免条件是什么？"})
        body = response.json()
        self.assertEqual(body["status"], "insufficient_evidence")
        self.assertEqual(body["answer_mode"], "insufficient_data")
        self.assertEqual(body["citations"], [])
        self.assertTrue(any(w["code"] == "NO_ELIGIBLE_EVIDENCE" for w in body["warnings"]))

    @unittest.skip(
        "未来年度政策适用性判定未实现：AgentWorkflow 仅处理「历史年度」"
        "（today > period_end 才触发 UNSUPPORTED_POLICY_MODE），对「未来年度」无专门规则，"
        "待业务规则 evidence_check 接入后补充 fail-closed 断言。"
    )
    def test_future_year_policy_applicability(self):
        """【待实现】未来年度无适用政策应 fail-closed，而非照常检索。"""
        package = _E2EFixtures.competition_package()
        runtime = _Runtime(_answered_handler, packages=[package])
        with TestClient(runtime.app()) as client:
            response = client.post("/api/v1/ask", json={"query": "2030年竞赛学分认定条件是什么？"})
        body = response.json()
        # 期望：未来年度问题在仅有 2026 年资料时应返回 insufficient_evidence
        self.assertEqual(body["status"], "insufficient_evidence")
        self.assertTrue(any(w["code"] in {"UNSUPPORTED_POLICY_MODE", "NO_ELIGIBLE_EVIDENCE"} for w in body["warnings"]))

    def test_T5_blocked_data_yields_insufficient_evidence(self):
        # 用真实 blocked 的 processed 资料，验证真实检索器不会泄露未开放资料
        package = _E2EFixtures.scholarship_package()
        package.metadata.retrieval_status = RetrievalStatus.BLOCKED
        # blocked 元数据在 DocumentMetadata 校验里仍合法（blocked 是默认），可建索引
        runtime = _Runtime(_answered_handler, packages=[package])
        with TestClient(runtime.app()) as client:
            response = client.post("/api/v1/ask", json={"query": "2026学年奖学金怎么申请？"})
        body = response.json()
        self.assertEqual(body["status"], "insufficient_evidence")
        self.assertEqual(body["citations"], [])
        self.assertTrue(any(w["code"] == "NO_ELIGIBLE_EVIDENCE" for w in body["warnings"]))

    def test_T7_qwen_timeout_returns_sanitized_error(self):
        def timeout_handler(request):
            raise httpx.TimeoutException("simulated timeout", request=request)

        runtime = _Runtime(timeout_handler, packages=[_E2EFixtures.scholarship_package()])
        with TestClient(runtime.app(), raise_server_exceptions=False) as client:
            response = client.post("/api/v1/ask", json={"query": "2026学年奖学金怎么申请？"})
        body = response.json()
        # 上游超时应映射为 504 MODEL_TIMEOUT，而非业务 answered 或裸 500
        self.assertEqual(response.status_code, 504)
        self.assertEqual(body["error"]["code"], "MODEL_TIMEOUT")
        self.assertNotIn("status", body)

    def test_T8_model_returns_unknown_chunk_id_is_rejected(self):
        def bad_handler(request):
            payload = json.loads(request.content)
            evidence = json.loads(payload["messages"][-1]["content"])["evidence"]
            text = json.dumps({"evidence": [{
                "chunk_id": str(uuid4()),  # 不存在的 chunk_id
                "quote": evidence[0]["content"],
            }]}, ensure_ascii=False)
            return httpx.Response(200, json={
                "model": _FAKE_MODEL,
                "choices": [{"message": {"content": text}}],
            })

        runtime = _Runtime(bad_handler, packages=[_E2EFixtures.scholarship_package()])
        with TestClient(runtime.app()) as client:
            response = client.post("/api/v1/ask", json={"query": "2026学年奖学金怎么申请？"})
        body = response.json()
        self.assertEqual(body["status"], "insufficient_evidence")
        self.assertEqual(body["citations"], [])
        self.assertTrue(any(w["code"] == "UNSUPPORTED_GENERATION" for w in body["warnings"]))

    def test_T9_model_rewrites_quote_is_rejected(self):
        def rewrite_handler(request):
            payload = json.loads(request.content)
            evidence = json.loads(payload["messages"][-1]["content"])["evidence"]
            text = json.dumps({"evidence": [{
                "chunk_id": evidence[0]["chunk_id"],
                "quote": "改写后的政策结论（非原文）",  # 擅自改写原文
            }]}, ensure_ascii=False)
            return httpx.Response(200, json={
                "model": _FAKE_MODEL,
                "choices": [{"message": {"content": text}}],
            })

        runtime = _Runtime(rewrite_handler, packages=[_E2EFixtures.scholarship_package()])
        with TestClient(runtime.app()) as client:
            response = client.post("/api/v1/ask", json={"query": "2026学年奖学金怎么申请？"})
        body = response.json()
        self.assertEqual(body["status"], "insufficient_evidence")
        self.assertEqual(body["citations"], [])
        self.assertTrue(any(w["code"] == "UNSUPPORTED_GENERATION" for w in body["warnings"]))


# ---------------------------------------------------------------------------
# AgentWorkflow 证据准入规则测试（非 BM25 端到端）
# ---------------------------------------------------------------------------
class AgentWorkflowEvidenceGateTests(unittest.TestCase):
    """AgentWorkflow 的证据准入门槛（_eligible）规则测试。

    与 AlphaE2ETests 的区别：这里用自定义 SingleChunkRetriever 直接构造
    RetrievedChunk，验证 AgentWorkflow 的 _eligible 门槛（来源核验等），
    不经过 LocalBM25Retriever 的索引/检索，因此**不计入 BM25 端到端统计**。
    """

    def test_T6_unverified_source_does_not_produce_answer(self):
        # 来源未核验（partial）的片段，即使 retrieval=enabled，也必须被 _eligible 拒绝
        unverified = _E2EFixtures._retrieved_chunk()

        class SingleChunkRetriever:
            async def retrieve(self, request):
                return [unverified]

        retriever = SingleChunkRetriever()
        transport = httpx.MockTransport(_answered_handler)
        upstream = httpx.AsyncClient(transport=transport)
        llm = QwenLLMClient(
            QwenSettings(api_key="offline-e2e-not-a-real-key", max_retries=0),
            http_client=upstream,
        )
        workflow = AgentWorkflow(retriever, llm, today=lambda: date(2026, 11, 20))
        app = create_app(agent_service=workflow, llm_client=llm)

        with TestClient(app) as client:
            response = client.post("/api/v1/ask", json={"query": "竞赛学分认定有什么条件？"})
        body = response.json()
        self.assertEqual(body["status"], "insufficient_evidence")
        self.assertEqual(body["citations"], [])
        self.assertTrue(any(w["code"] == "NO_ELIGIBLE_EVIDENCE" for w in body["warnings"]))


# ---------------------------------------------------------------------------
# 多轮会话 + 会话隔离（第二类：真实 Retriever + Mock Qwen）
# ---------------------------------------------------------------------------
class AlphaE2EMultiTurnTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.package = _E2EFixtures.scholarship_package()
        transport = httpx.MockTransport(_answered_handler)
        self.upstream = httpx.AsyncClient(transport=transport)
        self.llm = QwenLLMClient(
            QwenSettings(api_key="offline-e2e-not-a-real-key", max_retries=0),
            http_client=self.upstream,
        )
        self.retriever = LocalBM25Retriever()
        await self.retriever.index_document(self.package)
        self.workflow = AgentWorkflow(
            self.retriever, self.llm, today=lambda: date(2026, 11, 20),
        )

    async def asyncTearDown(self):
        await self.upstream.aclose()

    def _request(self, query, history=None, conversation_id=None):
        return AgentRequest(
            request_id=uuid4(),
            conversation_id=conversation_id or uuid4(),
            query=query,
            history=history or [],
        )

    async def test_T10_workflow_uses_history_context(self):
        """workflow 层利用 history 上下文（非 FastAPI 会话持久化）。

        注意：这里直接调用 workflow.run 并手动传入 history，只证明 AgentWorkflow
        能利用传入的历史上下文补齐缺失槽位（学年）。**不证明** FastAPI 已实现
        会话持久化——会话持久化依赖 `feat/alpha-real-runtime` 分支的
        `InMemoryConversationStore`，当前未合入 main。
        """
        # 第一轮：追问学年
        first = await self.workflow.run(self._request("奖学金怎么申请？"))
        self.assertEqual(first.status, AnswerStatus.NEEDS_CLARIFICATION)

        # 第二轮：用户补充「院级奖学金」+ 学年，应命中检索而非再追问。
        # 关键：历史里含 user 的「奖学金怎么申请？」和 assistant 的追问，
        # 只有 user 轮次能补齐缺失槽位（学年），assistant 追问本身不算证据。
        history = [
            ConversationTurn(role=LLMRole.USER, content="奖学金怎么申请？"),
            ConversationTurn(role=LLMRole.ASSISTANT, content=first.clarifying_question),
        ]
        second = await self.workflow.run(
            self._request("2026学年院级奖学金", history=history)
        )
        # 第二轮补上学年后，不再追问，直接进入检索并返回 answered
        self.assertEqual(second.status, AnswerStatus.ANSWERED)
        self.assertTrue(second.citations)

    async def test_followup_without_year_still_clarifies(self):
        # 对照：第二轮若仍未补学年，应继续追问（证明不是无条件放行）
        first = await self.workflow.run(self._request("奖学金怎么申请？"))
        history = [
            ConversationTurn(role=LLMRole.USER, content="奖学金怎么申请？"),
            ConversationTurn(role=LLMRole.ASSISTANT, content=first.clarifying_question),
        ]
        again = await self.workflow.run(
            self._request("就是想知道条件", history=history)
        )
        self.assertEqual(again.status, AnswerStatus.NEEDS_CLARIFICATION)

    @unittest.skip(
        "会话隔离测试待实现：main 分支的 AgentWorkflow 无会话持久化，"
        "conversation_id 仅作为请求字段透传，无法验证跨会话历史隔离。"
        "待 feat/alpha-real-runtime 的 InMemoryConversationStore 合入后补测。"
    )
    async def test_conversation_isolation(self):
        """【待实现】不同 conversation_id 的历史应互不影响。"""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 第三类：真实 Qwen 集成测试（需 QWEN_API_KEY，未配置则 skip）
# ---------------------------------------------------------------------------
class AlphaE2ERealQwenTests(unittest.IsolatedAsyncioTestCase):
    """真实 Retriever + 真实 Qwen API。仅在配置 QWEN_API_KEY 时运行。"""

    async def test_real_qwen_end_to_end(self):
        import os
        if not os.getenv("QWEN_API_KEY"):
            self.skipTest("未配置 QWEN_API_KEY，跳过真实 Qwen 集成测试。")

        from backend.services.qwen_client import create_qwen_client_from_env
        retriever = LocalBM25Retriever()
        await retriever.index_document(_E2EFixtures.scholarship_package())
        llm = create_qwen_client_from_env()
        workflow = AgentWorkflow(retriever, llm, today=lambda: date(2026, 11, 20))
        result = await workflow.run(AgentRequest(
            request_id=uuid4(), conversation_id=uuid4(),
            query="2026学年奖学金怎么申请？",
        ))
        self.assertIn(result.status, {
            AnswerStatus.ANSWERED,
            AnswerStatus.INSUFFICIENT_EVIDENCE,
        })
        if result.status == AnswerStatus.ANSWERED:
            self.assertTrue(result.citations)


if __name__ == "__main__":
    unittest.main()
