
import unittest

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.services.mock_agent import MockAgentService


class MockAgentApiTests(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(
            create_app(agent_service=MockAgentService())
        )

    def test_health_endpoint(self):
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)

    def test_normal_answer(self):
        response = self.client.post(
            "/api/v1/ask",
            json={"query": "测试一下 Mock Agent"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["status"], "answered")
        self.assertIn("Mock 演示", body["answer"])
        self.assertEqual(body["citations"], [])

    def test_clarification(self):
        response = self.client.post(
            "/api/v1/ask",
            json={"query": "__mock_clarify__"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["status"], "needs_clarification")
        self.assertIsNone(body["answer"])
        self.assertIsNotNone(body["clarifying_question"])

    def test_insufficient_evidence(self):
        response = self.client.post(
            "/api/v1/ask",
            json={"query": "__mock_insufficient__"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["status"], "insufficient_evidence")
        self.assertEqual(
            body["answer_mode"],
            "insufficient_data",
        )

    def test_invalid_request(self):
        response = self.client.post(
            "/api/v1/ask",
            json={"query": ""},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "INVALID_REQUEST",
        )

    def test_default_app_does_not_enable_mock(self):
        client = TestClient(create_app())

        response = client.post(
            "/api/v1/ask",
            json={"query": "测试"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["error"]["code"],
            "SERVICE_NOT_CONFIGURED",
        )


if __name__ == "__main__":
    unittest.main()
