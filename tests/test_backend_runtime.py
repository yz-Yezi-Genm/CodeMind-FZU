import asyncio
import os
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from backend.app.config import PROJECT_ROOT, AppSettings, ConfigurationError
from backend.app.main import create_app
from backend.contracts.models import (
    AgentRequest,
    AgentResult,
    AnswerStatus,
    ConversationTurn,
    LLMRole,
)
from backend.services.alpha_runtime import (
    ConversationAgentService,
    InMemoryConversationStore,
    build_alpha_runtime,
)
from backend.services.errors import RuntimeUnavailableError, ServiceError


class CapturingAgentService:
    def __init__(self) -> None:
        self.request = None

    async def run(self, request):
        self.request = request
        return AgentResult(
            status=AnswerStatus.ANSWERED,
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


class RecordingConversationAgent:
    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    async def run(self, request: AgentRequest) -> AgentResult:
        self.requests.append(
            AgentRequest.model_validate(request.model_dump(mode="python"))
        )
        return AgentResult(
            status=AnswerStatus.ANSWERED,
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
                answer=f"已处理：{request.query}",
            )
        return await super().run(request)


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
        with self.assertRaises(RuntimeUnavailableError):
            await build_alpha_runtime(
                settings,
                llm_client=object(),
                file_root=PROJECT_ROOT / "missing-retriever-root",
            )


if __name__ == "__main__":
    unittest.main()
