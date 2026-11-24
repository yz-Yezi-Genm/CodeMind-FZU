"""API 参数校验与健康检查字段规范的补充测试（颜俊宇 · 测试与质量保障）。

本文件补充 test_backend_runtime.py / test_mock_agent_api.py 尚未覆盖的边界用例，
聚焦任务清单中的「异常输入」与「健康检查字段是否符合规范」两个要求：

  1. 健康检查返回字段完整性（status / service / version / timestamp 四字段）。
  2. 超长问题（query 超过 4000 字符）。
  3. 非法请求数据：非 JSON 请求体、缺少 query 字段、query 类型错误、多余字段。
  4. Agent 未注入时的 503 响应（含统一错误 envelope 的完整性）。

运行方式（仓库根目录）：
  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest
from datetime import datetime
from uuid import UUID

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.services.mock_agent import MockAgentService


def _parse_iso(value: str) -> datetime:
    """兼容 Python 3.11+ 的 ISO 8601 解析（含 'Z' 后缀）。"""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


class HealthResponseContractTests(unittest.TestCase):
    """GET /api/v1/health 的字段是否符合接口规范 V1.0 第 5.1 节。"""

    def setUp(self):
        self.client = TestClient(create_app(agent_service=MockAgentService()))

    def test_health_returns_200_and_all_required_fields(self):
        response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()

        # 规范要求的四个字段必须全部存在且类型正确
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "codemind-fzu-api")
        self.assertEqual(body["version"], "0.1.0")

        # timestamp 必须为带时区的 ISO 8601 时间戳（UTC），不能为空或缺失
        self.assertIn("timestamp", body)
        ts = _parse_iso(body["timestamp"])
        self.assertIsNotNone(ts.tzinfo)
        self.assertEqual(ts.tzinfo.utcoffset(ts).total_seconds(), 0)

    def test_health_has_no_extra_fields(self):
        response = self.client.get("/api/v1/health")
        body = response.json()
        # 规范只约定这四个字段，不应出现未声明的多余字段
        self.assertEqual(
            set(body.keys()),
            {"status", "service", "version", "timestamp"},
        )

    def test_health_request_id_header_is_valid_uuid(self):
        response = self.client.get("/api/v1/health")
        UUID(response.headers["X-Request-ID"])


class AskInputValidationTests(unittest.TestCase):
    """POST /api/v1/ask 的异常输入校验。"""

    def setUp(self):
        self.client = TestClient(create_app(agent_service=MockAgentService()))

    def test_overlong_query_is_rejected_with_400(self):
        # query 上限 4000 字符（AskRequest 约束）
        response = self.client.post(
            "/api/v1/ask",
            json={"query": "字" * 4001},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")

    def test_query_exactly_4000_chars_is_accepted(self):
        # 边界值：恰好 4000 字符应当被接受
        response = self.client.post(
            "/api/v1/ask",
            json={"query": "字" * 4000},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "answered")

    def test_missing_query_field_is_rejected(self):
        response = self.client.post("/api/v1/ask", json={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")

    def test_query_wrong_type_is_rejected(self):
        # query 必须是 string，传数字应被拒
        response = self.client.post("/api/v1/ask", json={"query": 12345})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")

    def test_extra_unknown_field_is_rejected(self):
        # AskRequest 采用 extra="forbid"，多余字段应触发校验失败
        response = self.client.post(
            "/api/v1/ask",
            json={"query": "正常问题", "unexpected": "多余字段"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")

    def test_non_json_body_is_rejected(self):
        # 请求体不是合法 JSON 时应返回 400 统一错误 envelope
        response = self.client.post(
            "/api/v1/ask",
            content="这不是 JSON",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["error"]["code"], "INVALID_REQUEST")

    def test_openapi_uses_final_error_statuses(self):
        operation = self.client.get("/openapi.json").json()["paths"]["/api/v1/ask"]["post"]
        responses = operation["responses"]

        self.assertEqual(
            {"200", "400", "429", "500", "503", "504"},
            set(responses),
        )
        self.assertNotIn("422", responses)
        for status_code in ("400", "429", "500", "503", "504"):
            schema_ref = responses[status_code]["content"]["application/json"]["schema"]["$ref"]
            self.assertEqual("#/components/schemas/ApiErrorResponse", schema_ref)


class ServiceNotConfiguredTests(unittest.TestCase):
    """Agent 未注入时的降级行为。"""

    def test_503_envelope_is_complete_and_sanitized(self):
        client = TestClient(create_app())  # 不注入 agent_service

        response = client.post("/api/v1/ask", json={"query": "测试问题"})

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["error"]["code"], "SERVICE_NOT_CONFIGURED")
        self.assertTrue(body["error"]["retryable"])
        self.assertIn("message", body["error"])
        # request_id 必须是合法 UUID
        UUID(body["request_id"])
        # 不泄露内部堆栈或敏感信息
        self.assertNotIn("Traceback", response.text)
        self.assertNotIn("agent_service", response.text)


if __name__ == "__main__":
    unittest.main()
