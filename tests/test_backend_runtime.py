import os
import unittest
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from backend.app.config import AppSettings, ConfigurationError
from backend.app.main import create_app
from backend.contracts.models import AgentResult, AnswerStatus
from backend.services.errors import ServiceError


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


if __name__ == "__main__":
    unittest.main()
