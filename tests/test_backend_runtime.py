import asyncio
import json
import os
import sys
import types
import unittest
from importlib.util import find_spec
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from backend.app.alpha import create_alpha_app
from backend.app.config import PROJECT_ROOT, AppSettings, ConfigurationError
from backend.app.main import create_app
from backend.contracts.models import (
    AgentRequest,
    AgentResult,
    AnswerStatus,
    AnswerMode,
    ConversationTurn,
    LLMGenerateRequest,
    LLMResult,
    LLMRole,
)
from backend.services.alpha_runtime import (
    ConversationAgentService,
    InMemoryConversationStore,
    build_alpha_runtime,
)
from backend.services.errors import (
    KnowledgeBaseUnavailableError,
    LLMConfigurationError,
    ServiceError,
)


class CapturingAgentService:
    def __init__(self) -> None:
        self.request = None

    async def run(self, request):
        self.request = request
        return AgentResult(
            status=AnswerStatus.ANSWERED,
            answer_mode=AnswerMode.CURRENT_POLICY,
            answer="契约联调成功。",
        )


class FailingAgentService:
    async def run(self, _request):
        raise ServiceError(
            "检索服务暂时不可用。",
            code="RETRIEVAL_FAILED",
            http_status=503,
            retryable=True,
        )


class InvalidAgentService:
    async def run(self, _request):
        return {"status": "answered"}


class RuntimeFailureAgentService:
    async def run(self, _request):
        raise RuntimeError("unexpected internal detail")


class AsyncioTimeoutAgentService:
    async def run(self, _request):
        raise asyncio.TimeoutError()


class RecordingConversationAgent:
    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    async def run(self, request: AgentRequest) -> AgentResult:
        self.requests.append(
            AgentRequest.model_validate(request.model_dump(mode="python"))
        )
        return AgentResult(
            status=AnswerStatus.ANSWERED,
            answer_mode=AnswerMode.CURRENT_POLICY,
            answer=f"已处理：{request.query}",
        )


class BlockingConversationAgent(RecordingConversationAgent):
    def __init__(self) -> None:
        super().__init__()
        self.first_entered = asyncio.Event()
        self.allow_second = asyncio.Event()

    async def run(self, request: AgentRequest) -> AgentResult:
        if not self.requests:
            self.requests.append(
                AgentRequest.model_validate(request.model_dump(mode="python"))
            )
            self.first_entered.set()
            await self.allow_second.wait()
            return AgentResult(
                status=AnswerStatus.ANSWERED,
                answer_mode=AnswerMode.CURRENT_POLICY,
                answer=f"已处理：{request.query}",
            )
        return await super().run(request)


class EvidenceSelectingRuntimeLLM:
    async def generate(self, request: LLMGenerateRequest) -> LLMResult:
        payload = json.loads(request.messages[-1].content)
        first = payload["evidence"][0]
        return LLMResult(
            content=json.dumps(
                {
                    "evidence": [
                        {
                            "chunk_id": first["chunk_id"],
                            "quote": first["content"],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            model="offline-runtime-rule-fixture",
        )


class BackendRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.settings = AppSettings(
            cors_allow_origins=("http://localhost:5173",),
        )

    def test_health_and_request_id_header(self):
        client = TestClient(create_app(settings=self.settings))

        response = client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        UUID(response.headers["X-Request-ID"])
        self.assertEqual(response.json()["service"], "codemind-fzu-api")

    def test_dev_entry_keeps_mock_agent_enabled(self):
        from backend.app.dev import app

        response = TestClient(app).post(
            "/api/v1/ask",
            json={"query": "Mock 入口验证"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "answered")

    def test_allowed_cors_origin(self):
        client = TestClient(create_app(settings=self.settings))

        response = client.options(
            "/api/v1/ask",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:5173",
        )

    def test_patch_cors_is_enabled_for_admin_contracts(self):
        client = TestClient(create_app(settings=self.settings))

        response = client.options(
            "/api/v1/admin/documents/example",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("PATCH", response.headers["access-control-allow-methods"])

    def test_unlisted_cors_origin_is_not_allowed(self):
        client = TestClient(create_app(settings=self.settings))

        response = client.get(
            "/api/v1/health",
            headers={"Origin": "https://unexpected.example"},
        )

        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_agent_result_is_wrapped_with_shared_ids(self):
        service = CapturingAgentService()
        client = TestClient(create_app(service, settings=self.settings))

        response = client.post("/api/v1/ask", json={"query": "测试问题"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["request_id"], response.headers["X-Request-ID"])
        UUID(body["conversation_id"])
        self.assertEqual(service.request.query, "测试问题")
        self.assertEqual(str(service.request.request_id), body["request_id"])
        self.assertEqual(str(service.request.conversation_id), body["conversation_id"])

    def test_agent_service_error_uses_contract_envelope(self):
        client = TestClient(create_app(FailingAgentService(), settings=self.settings))

        response = client.post("/api/v1/ask", json={"query": "测试问题"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "RETRIEVAL_FAILED")
        self.assertTrue(response.json()["error"]["retryable"])
        UUID(response.json()["request_id"])

    def test_asyncio_timeout_maps_to_504_for_python310_compatibility(self):
        client = TestClient(
            create_app(AsyncioTimeoutAgentService(), settings=self.settings)
        )

        response = client.post("/api/v1/ask", json={"query": "测试超时"})

        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["error"]["code"], "MODEL_TIMEOUT")
        self.assertEqual(
            response.headers["x-request-id"],
            response.json()["request_id"],
        )

    def test_invalid_agent_return_type_is_hidden_as_internal_error(self):
        client = TestClient(create_app(InvalidAgentService(), settings=self.settings))

        response = client.post("/api/v1/ask", json={"query": "测试问题"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("AgentService.run", response.text)
        self.assertNotIn("Traceback", response.text)

    def test_runtime_error_keeps_request_id_and_cors_headers(self):
        client = TestClient(
            create_app(RuntimeFailureAgentService(), settings=self.settings),
            raise_server_exceptions=False,
        )

        response = client.post(
            "/api/v1/ask",
            json={"query": "测试 RuntimeError"},
            headers={"Origin": "http://localhost:5173"},
        )

        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertEqual(body["error"]["code"], "INTERNAL_ERROR")
        UUID(body["request_id"])
        self.assertEqual(body["request_id"], response.headers["X-Request-ID"])
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"],
            "http://localhost:5173",
        )
        self.assertNotIn("unexpected internal detail", response.text)
        self.assertNotIn("Traceback", response.text)

    def test_wildcard_cors_origin_is_rejected(self):
        with patch.dict(os.environ, {"CORS_ALLOW_ORIGINS": "*"}, clear=False):
            with self.assertRaises(ConfigurationError):
                AppSettings.from_env()

    def test_cors_origins_can_be_overridden_from_environment(self):
        with patch.dict(
            os.environ,
            {"CORS_ALLOW_ORIGINS": "http://localhost:4173,http://127.0.0.1:4173"},
            clear=False,
        ):
            settings = AppSettings.from_env()

        self.assertEqual(
            settings.cors_allow_origins,
            ("http://localhost:4173", "http://127.0.0.1:4173"),
        )

    def test_alpha_package_dir_environment_is_relative_to_project_root(self):
        with patch.dict(
            os.environ,
            {
                "ALPHA_PACKAGE_DIR": "knowledge_base/processed/alpha/approved",
                "CONVERSATION_MAX_MESSAGES": "8",
                "CONVERSATION_HISTORY_CHAR_LIMIT": "3000",
                "CONVERSATION_MAX_COUNT": "25",
                "CONVERSATION_IDLE_SECONDS": "600",
                "CONVERSATION_CLEANUP_INTERVAL_SECONDS": "30",
            },
            clear=False,
        ):
            settings = AppSettings.from_env()

        self.assertEqual(
            settings.alpha_package_dir,
            (PROJECT_ROOT / "knowledge_base/processed/alpha/approved").resolve(),
        )
        self.assertEqual(settings.conversation_max_messages, 8)
        self.assertEqual(settings.conversation_history_char_limit, 3000)
        self.assertEqual(settings.conversation_max_count, 25)
        self.assertEqual(settings.conversation_idle_seconds, 600)
        self.assertEqual(settings.conversation_cleanup_interval_seconds, 30)

    def test_health_stays_available_when_qwen_configuration_is_missing(self):
        settings = AppSettings(
            alpha_package_dir=PROJECT_ROOT / "tests/fixtures/alpha_approved",
        )
        with patch.dict(os.environ, {"QWEN_API_KEY": ""}, clear=False):
            app = create_alpha_app(settings=settings)
            with TestClient(app) as client:
                health = client.get("/api/v1/health")
                response = client.post(
                    "/api/v1/ask",
                    json={"query": "测试未配置模型"},
                )

        self.assertEqual(health.status_code, 200)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["error"]["code"],
            "SERVICE_NOT_CONFIGURED",
        )
        self.assertEqual(
            response.headers["x-request-id"],
            response.json()["request_id"],
        )


class ConversationRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def request(
        self,
        conversation_id: UUID,
        query: str,
    ) -> AgentRequest:
        return AgentRequest(
            request_id=uuid4(),
            conversation_id=conversation_id,
            query=query,
        )

    async def test_history_is_injected_and_reply_is_saved(self):
        agent = RecordingConversationAgent()
        store = InMemoryConversationStore(max_messages=8, max_chars=4000)
        service = ConversationAgentService(agent, store)
        conversation_id = uuid4()

        await service.run(self.request(conversation_id, "奖学金有哪些类别？"))
        await service.run(self.request(conversation_id, "院级奖学金。"))

        self.assertEqual(agent.requests[0].history, [])
        self.assertEqual(len(agent.requests[1].history), 2)
        self.assertEqual(
            agent.requests[1].history[0],
            ConversationTurn(
                role=LLMRole.USER,
                content="奖学金有哪些类别？",
                created_at=agent.requests[1].history[0].created_at,
            ),
        )
        self.assertEqual(
            agent.requests[1].history[1].role,
            LLMRole.ASSISTANT,
        )
        self.assertEqual(
            agent.requests[1].history[1].content,
            "已处理：奖学金有哪些类别？",
        )

    async def test_conversation_histories_are_isolated(self):
        agent = RecordingConversationAgent()
        store = InMemoryConversationStore()
        service = ConversationAgentService(agent, store)
        first_id = uuid4()
        second_id = uuid4()

        await service.run(self.request(first_id, "第一组会话问题"))
        await service.run(self.request(second_id, "第二组会话问题"))

        self.assertEqual(agent.requests[1].history, [])
        self.assertEqual(len(store.history(first_id)), 2)
        self.assertEqual(len(store.history(second_id)), 2)
        self.assertNotEqual(
            store.history(first_id)[0].content,
            store.history(second_id)[0].content,
        )

    async def test_history_is_bounded_by_complete_turns(self):
        agent = RecordingConversationAgent()
        store = InMemoryConversationStore(max_messages=4, max_chars=10000)
        service = ConversationAgentService(agent, store)
        conversation_id = uuid4()

        for index in range(3):
            await service.run(
                self.request(conversation_id, f"第{index + 1}轮问题")
            )

        history = store.history(conversation_id)
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0].role, LLMRole.USER)
        self.assertEqual(history[0].content, "第2轮问题")
        self.assertEqual(history[2].role, LLMRole.USER)
        self.assertEqual(history[2].content, "第3轮问题")

    async def test_odd_message_limit_is_rounded_down_to_complete_turns(self):
        agent = RecordingConversationAgent()
        store = InMemoryConversationStore(max_messages=5)
        service = ConversationAgentService(agent, store)
        conversation_id = uuid4()

        for index in range(4):
            await service.run(
                self.request(conversation_id, f"第{index + 1}轮")
            )

        self.assertEqual(store.max_messages, 4)
        self.assertEqual(len(store.history(conversation_id)), 4)

    async def test_same_conversation_requests_are_serialized(self):
        agent = BlockingConversationAgent()
        store = InMemoryConversationStore()
        service = ConversationAgentService(agent, store)
        conversation_id = uuid4()

        first = asyncio.create_task(
            service.run(self.request(conversation_id, "第一轮"))
        )
        await agent.first_entered.wait()
        second = asyncio.create_task(
            service.run(self.request(conversation_id, "第二轮"))
        )
        await asyncio.sleep(0)
        self.assertEqual(len(agent.requests), 1)
        agent.allow_second.set()
        await asyncio.gather(first, second)

        self.assertEqual(agent.requests[0].history, [])
        self.assertEqual(len(agent.requests[1].history), 2)
        self.assertEqual(agent.requests[1].history[0].content, "第一轮")

    async def test_failed_turn_does_not_corrupt_history(self):
        class FailOnceAgent:
            def __init__(self) -> None:
                self.calls = 0
                self.last_request = None

            async def run(self, request: AgentRequest) -> AgentResult:
                self.calls += 1
                self.last_request = request
                if self.calls == 1:
                    raise RuntimeError("temporary failure")
                return AgentResult(
                    status=AnswerStatus.ANSWERED,
                    answer_mode=AnswerMode.CURRENT_POLICY,
                    answer="重试成功",
                )

        agent = FailOnceAgent()
        store = InMemoryConversationStore()
        service = ConversationAgentService(agent, store)
        conversation_id = uuid4()

        with self.assertRaises(RuntimeError):
            await service.run(self.request(conversation_id, "失败的一轮"))
        await service.run(self.request(conversation_id, "重试问题"))

        self.assertEqual(agent.last_request.history, [])
        self.assertEqual(
            [turn.content for turn in store.history(conversation_id)],
            ["重试问题", "重试成功"],
        )

    async def test_retriever_initialization_failure_is_sanitized(self):
        settings = AppSettings(
            alpha_package_dir=(
                PROJECT_ROOT / "tests/fixtures/alpha_approved"
            ),
        )
        with self.assertRaises(KnowledgeBaseUnavailableError):
            await build_alpha_runtime(
                settings,
                llm_client=object(),
                file_root=PROJECT_ROOT / "missing-retriever-root",
            )

    async def test_global_cleanup_removes_idle_and_protects_active_state(self):
        agent = BlockingConversationAgent()
        store = InMemoryConversationStore(max_messages=4, max_chars=1000)
        service = ConversationAgentService(agent, store)
        conversation_id = uuid4()

        task = asyncio.create_task(
            service.run(self.request(conversation_id, "清理测试"))
        )
        await agent.first_entered.wait()
        self.assertEqual(await store.clear_all(), 0)
        self.assertEqual(store.conversation_count, 1)
        agent.allow_second.set()
        await task

        # Windows 的 time.monotonic 分辨率约 15ms，1e-9 阈值会因差值被舍入为 0
        # 而无法过期；这里等待一个可观测的时间片再按 20ms 阈值清理。
        await asyncio.sleep(0.05)
        self.assertEqual(await store.prune_idle(idle_seconds=0.02), 1)
        self.assertEqual(store.conversation_count, 0)

    async def test_global_cleanup_drops_inactive_sessions(self):
        agent = RecordingConversationAgent()
        store = InMemoryConversationStore(
            max_conversations=2,
            idle_seconds=1,
        )
        service = ConversationAgentService(agent, store)

        for _ in range(3):
            await service.run(self.request(uuid4(), "独立会话"))

        self.assertEqual(store.conversation_count, 2)
        # 同上：等待可观测时间片，避免 Windows 低分辨率时钟导致未过期。
        await asyncio.sleep(0.05)
        self.assertEqual(await store.prune_idle(idle_seconds=0.02), 2)
        self.assertEqual(store.conversation_count, 0)

    async def test_business_rules_factory_binds_the_live_retriever(self):
        observed = {}

        class UnexpectedLLM:
            async def generate(self, _request):
                raise AssertionError("Rejected evidence must not call Qwen")

        rules = types.ModuleType("backend.services.alpha_business_rules")
        rules.alpha_clarification_rule = lambda _request: None

        def build_from_retriever(retriever):
            observed["retriever"] = retriever
            return lambda _request, _chunk: False

        rules.build_from_retriever = build_from_retriever
        settings = AppSettings(
            alpha_package_dir=PROJECT_ROOT / "tests/fixtures/alpha_approved",
        )
        with patch.dict(
            sys.modules,
            {"backend.services.alpha_business_rules": rules},
        ):
            runtime = await build_alpha_runtime(
                settings,
                llm_client=UnexpectedLLM(),
                file_root=PROJECT_ROOT,
            )
        try:
            self.assertIs(observed["retriever"], runtime.retriever)
            result = await runtime.agent_service.run(
                self.request(
                    uuid4(),
                    "2026年奖学金申请需要提交什么材料？",
                )
            )
        finally:
            await runtime.close()

        self.assertEqual(result.status, AnswerStatus.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.warnings[0].code, "NO_ELIGIBLE_EVIDENCE")
        self.assertEqual(result.citations, [])

    async def test_runtime_rejects_unapproved_enabled_corpus(self):
        settings = AppSettings(
            alpha_package_dir=PROJECT_ROOT / "tests/fixtures/alpha_unapproved",
        )
        with self.assertRaises(KnowledgeBaseUnavailableError):
            await build_alpha_runtime(
                settings,
                llm_client=object(),
                file_root=PROJECT_ROOT,
                clarification_rule=lambda _request: None,
                evidence_check=lambda _request, _chunk: True,
            )

    async def test_runtime_rejects_partial_or_warning_index(self):
        settings = AppSettings(
            alpha_package_dir=PROJECT_ROOT / "tests/fixtures/alpha_partial",
        )
        with self.assertRaises(KnowledgeBaseUnavailableError):
            await build_alpha_runtime(
                settings,
                llm_client=object(),
                file_root=PROJECT_ROOT,
                clarification_rule=lambda _request: None,
                evidence_check=lambda _request, _chunk: True,
            )

    async def test_runtime_rejects_qwen_retry_budget_above_workflow_timeout(self):
        settings = AppSettings(
            alpha_package_dir=PROJECT_ROOT / "tests/fixtures/alpha_approved",
        )
        with patch.dict(
            os.environ,
            {
                "QWEN_API_KEY": "offline-budget-fixture",
                "QWEN_TIMEOUT_SECONDS": "20",
                "QWEN_MAX_RETRIES": "1",
            },
            clear=False,
        ):
            with self.assertRaises(LLMConfigurationError) as raised:
                await build_alpha_runtime(
                    settings,
                    file_root=PROJECT_ROOT,
                )

        self.assertEqual(raised.exception.code, "SERVICE_NOT_CONFIGURED")
        self.assertIn("预算超过", raised.exception.message)


@unittest.skipUnless(
    find_spec("backend.services.alpha_business_rules"),
    "PR #36 business rules are not merged into this checkout",
)
class DeliveredBusinessRulesRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_approved_corpus_and_retriever_bound_rules_reach_qwen(self):
        settings = AppSettings(
            alpha_package_dir=PROJECT_ROOT / "tests/fixtures/alpha_approved",
        )
        runtime = await build_alpha_runtime(
            settings,
            llm_client=EvidenceSelectingRuntimeLLM(),
            file_root=PROJECT_ROOT,
        )
        try:
            result = await runtime.agent_service.run(
                AgentRequest(
                    request_id=uuid4(),
                    conversation_id=uuid4(),
                    query="2026年校级优秀学生综合奖学金申请需要什么条件？",
                )
            )
        finally:
            await runtime.close()

        self.assertEqual(result.status, AnswerStatus.ANSWERED)
        self.assertEqual(len(result.citations), 1)
        self.assertEqual(
            result.citations[0].excerpt,
            "2026年奖学金申请需提交申请表和成绩单。",
        )


if __name__ == "__main__":
    unittest.main()
