"""Verify injection into the existing HTTP shell, with offline fakes only."""
import json
import unittest
from datetime import date
from pathlib import Path
from uuid import UUID
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from backend.app.alpha import create_alpha_app
from backend.app.config import AppSettings, PROJECT_ROOT
from backend.app.main import create_app
from backend.contracts.models import (
    AskResponse,
    LLMGenerateRequest,
    LLMResult,
)
from backend.retrieval.local import LocalBM25Retriever
from backend.services.agent_workflow import AgentWorkflow
from backend.services.alpha_runtime import build_alpha_runtime
from backend.services.errors import LLMTimeoutError
from examples.agent_workflow_demo import DemoLLMClient, DemoRetriever, demo_chunk


class EvidenceSelectingLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMGenerateRequest) -> LLMResult:
        self.calls += 1
        payload = json.loads(request.messages[-1].content)
        first = payload["evidence"][0]
        return LLMResult(
            content=json.dumps(
                {
                    "answer": first["content"],
                    "used_evidence_ids": [first["evidence_id"]]
                },
                ensure_ascii=False,
            ),
            model="offline-evidence-fixture",
        )


class TimeoutLLM:
    async def generate(self, _request: LLMGenerateRequest) -> LLMResult:
        raise LLMTimeoutError()


FIXTURE_DIR = (
    PROJECT_ROOT / "tests/fixtures/alpha_approved"
)
FIXTURE_CONTENT = "2026年奖学金申请需提交申请表和成绩单。"


def no_clarification(_request):
    return None


def allow_test_evidence(_request, _chunk):
    return True


def clarify_scholarship_year(request):
    user_context = "\n".join(
        [
            *(turn.content for turn in request.history if turn.role.value == "user"),
            request.query,
        ]
    )
    if "奖学金" in user_context and "2026" not in user_context:
        return "请问你咨询的是哪一学年的评定？"
    return None


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

    def test_alpha_lifespan_uses_real_bm25_workflow_and_http_adapter(self):
        llm = EvidenceSelectingLLM()
        settings = AppSettings(
            alpha_package_dir=FIXTURE_DIR,
            conversation_max_messages=8,
        )

        async def runtime_builder():
            return await build_alpha_runtime(
                settings,
                llm_client=llm,
                file_root=PROJECT_ROOT,
                clarification_rule=clarify_scholarship_year,
                evidence_check=allow_test_evidence,
            )

        app = create_alpha_app(
            settings=settings,
            runtime_builder=runtime_builder,
        )
        with TestClient(app) as client:
            self.assertIsInstance(
                app.state.alpha_runtime.retriever,
                LocalBM25Retriever,
            )
            response = client.post(
                "/api/v1/ask",
                json={"query": "2026年奖学金申请需要提交什么材料？"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "answered")
        self.assertEqual(
            body["citations"][0]["excerpt"],
            FIXTURE_CONTENT,
        )
        self.assertEqual(
            body["citations"][0]["source_url"],
            "https://example.invalid/test-policy",
        )
        self.assertEqual(llm.calls, 1)

    def test_alpha_runtime_uses_prior_user_history_across_http_turns(self):
        llm = EvidenceSelectingLLM()
        settings = AppSettings(alpha_package_dir=FIXTURE_DIR)

        async def runtime_builder():
            return await build_alpha_runtime(
                settings,
                llm_client=llm,
                file_root=PROJECT_ROOT,
                clarification_rule=clarify_scholarship_year,
                evidence_check=allow_test_evidence,
            )

        app = create_alpha_app(
            settings=settings,
            runtime_builder=runtime_builder,
        )
        with TestClient(app) as client:
            first = client.post(
                "/api/v1/ask",
                json={"query": "奖学金有哪些类别？"},
            )
            conversation_id = first.json()["conversation_id"]
            second = client.post(
                "/api/v1/ask",
                json={"query": "2026年。", "conversation_id": conversation_id},
            )
            history = app.state.alpha_runtime.session_store.history(
                UUID(conversation_id)
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "needs_clarification")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "answered")
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0].content, "奖学金有哪些类别？")
        self.assertEqual(history[2].content, "2026年。")
        self.assertEqual(llm.calls, 1)

    def test_alpha_runtime_model_timeout_is_not_answered_status(self):
        settings = AppSettings(alpha_package_dir=FIXTURE_DIR)

        async def runtime_builder():
            return await build_alpha_runtime(
                settings,
                llm_client=TimeoutLLM(),
                file_root=PROJECT_ROOT,
                clarification_rule=no_clarification,
                evidence_check=allow_test_evidence,
            )

        app = create_alpha_app(
            settings=settings,
            runtime_builder=runtime_builder,
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                json={"query": "2026年奖学金申请需要提交什么材料？"},
            )

        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["error"]["code"], "MODEL_TIMEOUT")
        self.assertNotIn("status", response.json())

    def test_alpha_lifespan_failure_is_reported_without_crashing_app(self):
        settings = AppSettings(
            alpha_package_dir=PROJECT_ROOT / "tests/fixtures/missing-approved",
        )

        async def runtime_builder():
            return await build_alpha_runtime(
                settings=settings,
                llm_client=EvidenceSelectingLLM(),
                file_root=PROJECT_ROOT,
            )

        app = create_alpha_app(
            settings=settings,
            runtime_builder=runtime_builder,
        )
        with TestClient(app) as client:
            health = client.get("/api/v1/health")
            response = client.post(
                "/api/v1/ask",
                json={"query": "选课有哪些步骤？"},
            )

        self.assertEqual(health.status_code, 200)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["error"]["code"],
            "KNOWLEDGE_BASE_UNAVAILABLE",
        )
        self.assertIsNotNone(app.state.alpha_runtime_error)
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
