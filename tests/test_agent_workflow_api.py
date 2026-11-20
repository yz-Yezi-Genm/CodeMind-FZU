"""Verify injection into the existing HTTP shell, with offline fakes only."""
import unittest
from datetime import date
from uuid import UUID
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.contracts.models import AskResponse
from backend.services.agent_workflow import AgentWorkflow
from examples.agent_workflow_demo import DemoLLMClient, DemoRetriever, demo_chunk


class AgentWorkflowApiTests(unittest.TestCase):
    def client(self, chunks):
        service = AgentWorkflow(
            DemoRetriever(chunks), DemoLLMClient(), today=lambda: date(2026, 11, 17),
        )
        return TestClient(create_app(agent_service=service))

    def test_injected_workflow_returns_all_three_contract_statuses(self):
        for query, chunks, expected in [
            ("奖学金怎么申请？", [], "needs_clarification"),
            ("选课有哪些步骤？", [], "insufficient_evidence"),
            ("选课有哪些步骤？", [demo_chunk()], "answered"),
        ]:
            with self.subTest(expected=expected), self.client(chunks) as client:
                response = client.post("/api/v1/ask", json={"query": query})
                self.assertEqual(response.status_code, 200)
                body = AskResponse.model_validate(response.json())
                self.assertEqual(body.status, expected)
                self.assertIsInstance(body.request_id, UUID)
                self.assertIsInstance(body.conversation_id, UUID)
                self.assertIsNotNone(body.created_at.tzinfo)

    def test_backend_preserves_conversation_id(self):
        conversation_id = "550e8400-e29b-41d4-a716-446655440001"
        with self.client([demo_chunk()]) as client:
            response = client.post("/api/v1/ask", json={
                "query": "选课有哪些步骤？", "conversation_id": conversation_id,
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["conversation_id"], conversation_id)

    def test_invalid_http_query_still_returns_existing_error_envelope(self):
        with self.client([]) as client:
            response = client.post("/api/v1/ask", json={"query": ""})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")

    def test_unexpected_model_exception_uses_sanitized_backend_error_envelope(self):
        llm = AsyncMock()
        llm.generate.side_effect = RuntimeError("private-api-key-or-endpoint")
        workflow = AgentWorkflow(DemoRetriever([demo_chunk()]), llm)
        with TestClient(create_app(agent_service=workflow)) as client:
            response = client.post("/api/v1/ask", json={"query": "选课有哪些步骤？"})
        body = response.json()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(body["error"]["code"], "MODEL_UNAVAILABLE")
        self.assertEqual(response.headers["x-request-id"], body["request_id"])
        self.assertNotIn("status", body)
        self.assertNotIn("private-api-key-or-endpoint", response.text)


if __name__ == "__main__":
    unittest.main()
