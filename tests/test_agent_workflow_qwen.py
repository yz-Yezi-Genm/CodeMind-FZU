"""Existing Qwen adapter + workflow + HTTP integration, mock transport only."""
import json
import unittest
from datetime import date

import httpx
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.services.agent_workflow import AgentWorkflow
from backend.services.qwen_client import QwenLLMClient, QwenSettings
from examples.agent_workflow_demo import DemoRetriever, demo_chunk


class AgentWorkflowQwenTests(unittest.TestCase):
    def app(self, handler):
        transport = httpx.MockTransport(handler)
        upstream = httpx.AsyncClient(transport=transport)
        llm = QwenLLMClient(
            QwenSettings(api_key="offline-fixture-not-a-real-key", max_retries=0),
            http_client=upstream,
        )
        agent = AgentWorkflow(
            DemoRetriever([demo_chunk()]), llm, today=lambda: date(2026, 11, 18),
        )
        return create_app(agent_service=agent, llm_client=llm), upstream

    def test_existing_qwen_adapter_can_supply_verified_extractive_answer(self):
        observed = []

        def handler(request):
            payload = json.loads(request.content)
            observed.append(payload)
            evidence = json.loads(payload["messages"][-1]["content"])["evidence"][0]
            text = json.dumps({"evidence": [{
                "chunk_id": evidence["chunk_id"], "quote": evidence["content"],
            }]}, ensure_ascii=False)
            return httpx.Response(200, json={
                "model": "offline-qwen-response-fixture",
                "choices": [{"message": {"content": text}}],
            })

        app, upstream = self.app(handler)
        with TestClient(app) as client:
            response = client.post("/api/v1/ask", json={"query": "选课有哪些步骤？"})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["status"], "answered")
            self.assertEqual(body["citations"][0]["excerpt"], demo_chunk().content)
            self.assertEqual(body["citations"][0]["source_url"], demo_chunk().source_url)
            self.assertEqual(len(observed), 1)
            self.assertEqual(observed[0]["model"], "qwen-plus")
            self.assertEqual(observed[0]["temperature"], 0)
            client.portal.call(upstream.aclose)

    def test_model_failures_keep_backend_error_codes_instead_of_business_status(self):
        for status, expected_status, code in [
            (429, 429, "RATE_LIMITED"),
            (500, 503, "MODEL_UNAVAILABLE"),
            (408, 504, "MODEL_TIMEOUT"),
            (401, 503, "SERVICE_NOT_CONFIGURED"),
        ]:
            with self.subTest(upstream_status=status):
                app, upstream = self.app(lambda request: httpx.Response(status))
                with TestClient(app) as client:
                    response = client.post("/api/v1/ask", json={"query": "选课有哪些步骤？"})
                    body = response.json()
                    self.assertEqual(response.status_code, expected_status)
                    self.assertEqual(body["error"]["code"], code)
                    self.assertEqual(response.headers["x-request-id"], body["request_id"])
                    self.assertNotIn("status", body)
                    client.portal.call(upstream.aclose)

    def test_qwen_free_text_cannot_bypass_workflow_evidence_verification(self):
        app, upstream = self.app(lambda request: httpx.Response(200, json={
            "choices": [{"message": {"content": "没有任何依据的政策结论"}}],
        }))
        with TestClient(app) as client:
            response = client.post("/api/v1/ask", json={"query": "选课有哪些步骤？"})
            body = response.json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(body["status"], "insufficient_evidence")
            self.assertEqual(body["warnings"][0]["code"], "UNSUPPORTED_GENERATION")
            self.assertEqual(body["citations"], [])
            client.portal.call(upstream.aclose)


if __name__ == "__main__":
    unittest.main()
