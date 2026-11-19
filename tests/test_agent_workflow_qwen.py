"""Existing Qwen adapter + workflow + HTTP integration, mock transport only."""
import json
import os
import unittest
from datetime import date
from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.contracts.models import (
    AgentRequest, DocumentPackage, FileProcessingStatus, RetrievalRequest,
    TimelinessVerificationStatus,
)
from backend.retrieval.local import LocalBM25Retriever
from backend.services.agent_workflow import AgentWorkflow, create_alpha_workflow
from backend.services.errors import LLMConfigurationError, ServiceError
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


ROOT = Path(__file__).resolve().parents[1]


def fixture_clarification(request):
    """Test double, not Lei Jiayu's production business implementation."""
    context = "\n".join([*(t.content for t in request.history if t.role == "user"), request.query])
    if "奖学金" in context and "星桥" not in context:
        return "请问你咨询的是哪一类奖学金？"
    return None


class LocalRetrieverQwenIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Real BM25, indexing, disk integrity, Qwen adapter and API; synthetic data,
    fixture business callbacks and MockTransport. No paid Qwen call.
    """

    async def asyncSetUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.file_root = Path(self.temporary.name)
        items = json.loads((ROOT / "docs/assignment-03/alpha/examples/retrieval-synthetic-packages.json").read_bytes())
        self.package = DocumentPackage.model_validate(items[0])
        for file in self.package.files:
            path = self.file_root / file.storage_key
            path.parent.mkdir(parents=True, exist_ok=True)
            data = ("SYNTHETIC FIXTURE ONLY\n" + "\n".join(c.content for c in self.package.chunks)).encode()
            path.write_bytes(data)
            file.sha256 = sha256(data).hexdigest()
        self.observed = []
        self.output = None
        self.upstream = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        self.addAsyncCleanup(self.upstream.aclose)
        self.llm = QwenLLMClient(
            QwenSettings(api_key="offline-fixture-not-a-real-key", max_retries=0),
            http_client=self.upstream,
        )

    def handler(self, request):
        payload = json.loads(request.content)
        self.observed.append(payload)
        evidence = json.loads(payload["messages"][-1]["content"])["evidence"][0]
        output = self.output if self.output is not None else {"evidence": [{
            "chunk_id": evidence["chunk_id"], "quote": evidence["content"],
        }]}
        return httpx.Response(200, json={
            "model": "offline-qwen-response-fixture",
            "choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}],
        })

    async def workflow(self, *, packages=None, evidence_check=lambda *_: True, file_root=None,
                       clarification_rule=fixture_clarification):
        return await create_alpha_workflow(
            [self.package] if packages is None else packages,
            file_root=file_root or self.file_root, llm_client=self.llm,
            clarification_rule=clarification_rule, evidence_check=evidence_check,
            today=lambda: date(2026, 11, 19),
        )

    async def ask(self, workflow, query):
        app = create_app(agent_service=workflow, llm_client=workflow.llm_client)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/v1/ask", json={"query": query})

    async def test_real_modules_complete_clarify_retrieve_select_cite_chain(self):
        workflow = await self.workflow()
        self.assertIsInstance(workflow.retriever, LocalBM25Retriever)
        response = await self.ask(workflow, "奖学金申请条件是什么？")
        self.assertEqual(response.json()["status"], "needs_clarification")
        self.assertEqual(response.json()["clarifying_question"], "请问你咨询的是哪一类奖学金？")
        self.assertEqual(self.observed, [])
        # HTTP has no persisted history: resend the complete, supplemented query.
        response = await self.ask(workflow, "星桥奖学金申请需要什么？")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "answered")
        hits = await workflow.retriever.retrieve(RetrievalRequest(query="星桥奖学金申请需要什么？"))
        citation = body["citations"][0]
        self.assertEqual(citation["chunk_id"], str(hits[0].chunk_id))
        self.assertEqual(citation["document_id"], str(hits[0].document_id))
        self.assertEqual(citation["version_id"], str(hits[0].version_id))
        for field in ("source_url", "title", "publisher", "locator", "original_locator"):
            self.assertEqual(citation[field], getattr(hits[0], field))
        self.assertEqual(citation["excerpt"], hits[0].content)
        self.assertEqual(len(self.observed), 1)
        self.assertEqual(self.observed[0]["temperature"], 0)
        self.assertEqual(response.headers["x-request-id"], body["request_id"])

    async def test_empty_index_and_no_match_never_call_qwen(self):
        for packages, query in [([], "星桥奖学金条件"), ([self.package], "量子纠缠")]:
            with self.subTest(query=query):
                response = await self.ask(await self.workflow(packages=packages), query)
                self.assertEqual(response.json()["status"], "insufficient_evidence")
                self.assertEqual(response.json()["citations"], [])
        self.assertEqual(self.observed, [])

    async def test_rule_rejection_occurs_after_real_retrieval_before_qwen(self):
        observed = []

        def reject(request, chunk):
            observed.append(chunk)
            return False

        workflow = await self.workflow(evidence_check=reject)
        response = await self.ask(workflow, "星桥奖学金条件")
        self.assertEqual(response.json()["status"], "insufficient_evidence")
        self.assertTrue(observed)
        self.assertTrue(all(c.retrieval_method == "bm25" for c in observed))
        self.assertEqual(self.observed, [])

    async def test_real_retriever_historical_evidence_is_not_current_answer(self):
        self.package.metadata.timeliness_verification_status = TimelinessVerificationStatus.HISTORICAL
        workflow = await self.workflow()
        self.assertTrue(await workflow.retriever.retrieve(RetrievalRequest(query="星桥奖学金")))
        response = await self.ask(workflow, "星桥奖学金条件")
        self.assertEqual(response.json()["status"], "insufficient_evidence")
        self.assertEqual(self.observed, [])

    async def test_forged_chunk_id_or_rewritten_quote_fails_through_real_modules(self):
        workflow = await self.workflow()
        hits = await workflow.retriever.retrieve(RetrievalRequest(query="星桥奖学金条件"))
        for output in [
            {"evidence": [{"chunk_id": str(uuid4()), "quote": hits[0].content}]},
            {"evidence": [{"chunk_id": str(hits[0].chunk_id), "quote": "申请可获得99999元"}]},
        ]:
            with self.subTest(output=output):
                self.output = output
                response = await self.ask(workflow, "星桥奖学金条件")
                body = response.json()
                self.assertEqual(body["status"], "insufficient_evidence")
                self.assertEqual(body["citations"], [])
                self.assertNotIn("99999", body["answer"])

    async def test_corrupt_missing_and_partial_sources_block_assembly(self):
        file = self.package.files[0]
        path = self.file_root / file.storage_key
        original = path.read_bytes()
        for defect in ("hash", "missing", "partial"):
            with self.subTest(defect=defect):
                path.write_bytes(original)
                file.processing_status = FileProcessingStatus.EXTRACTED
                if defect == "hash":
                    path.write_bytes(b"corrupt")
                elif defect == "missing":
                    path.unlink()
                else:
                    file.processing_status = FileProcessingStatus.NEEDS_OCR
                with self.assertRaises(ServiceError) as raised:
                    await self.workflow()
                self.assertEqual(raised.exception.code, "SERVICE_NOT_CONFIGURED")
        self.assertEqual(self.observed, [])

    async def test_real_three_policy_packages_stay_blocked_and_skip_qwen(self):
        packages = [DocumentPackage.model_validate_json(
            (ROOT / "knowledge_base/processed/alpha" / (stem + ".json")).read_bytes()
        ) for stem in ("competition-recognition-2026", "scholarship-2026", "recommendation-eligibility-2027")]
        snapshots = [package.model_dump() for package in packages]
        workflow = await self.workflow(packages=packages, file_root=ROOT, clarification_rule=lambda _: None)
        for query in ("竞赛创新学分认定条件", "2026年校级奖学金申请条件", "2027年推免复试条件"):
            with self.subTest(query=query):
                response = await self.ask(workflow, query)
                self.assertEqual(response.json()["status"], "insufficient_evidence")
                self.assertEqual(response.json()["warnings"][0]["code"], "NO_ELIGIBLE_EVIDENCE")
                self.assertEqual(response.json()["citations"], [])
        self.assertEqual([p.model_dump() for p in packages], snapshots)
        self.assertEqual(self.observed, [])

    async def test_default_factory_uses_owner_rule_module_and_qwen_env_factory(self):
        # Patch only the delivery boundary, not BM25/Qwen implementation.
        from types import SimpleNamespace
        rules = SimpleNamespace(
            alpha_clarification_rule=fixture_clarification,
            alpha_evidence_check=lambda *_: True,
        )
        with patch.dict("sys.modules", {"backend.services.alpha_business_rules": rules}), patch.dict(
            os.environ, {"QWEN_API_KEY": "offline-fixture-not-a-real-key"},
        ):
            workflow = await create_alpha_workflow([self.package], file_root=self.file_root)
        self.assertIsInstance(workflow.llm_client, QwenLLMClient)
        self.assertIs(workflow.clarification_rule, rules.alpha_clarification_rule)
        self.assertIs(workflow.evidence_check, rules.alpha_evidence_check)
        self.assertTrue(await workflow.retriever.retrieve(RetrievalRequest(query="星桥奖学金")))

    async def test_missing_owner_rules_never_fall_back_to_demo_rules(self):
        with patch.dict("sys.modules", {"backend.services.alpha_business_rules": None}):
            with self.assertRaises(LLMConfigurationError):
                await create_alpha_workflow([], file_root=self.file_root, llm_client=self.llm)
        for callbacks in ({"clarification_rule": fixture_clarification}, {"evidence_check": lambda *_: True}):
            with self.assertRaises(ValueError):
                await create_alpha_workflow([], file_root=self.file_root, llm_client=self.llm, **callbacks)


@unittest.skipUnless(find_spec("backend.services.alpha_business_rules") is not None,
                     "Upstream alpha_business_rules.py has not been delivered")
class DeliveredBusinessRulesTests(unittest.IsolatedAsyncioTestCase):
    """Runs the real rule functions once the owner delivers their module."""

    async def test_missing_scholarship_category_clarifies_without_model(self):
        from backend.services.alpha_business_rules import alpha_clarification_rule, alpha_evidence_check
        llm = AsyncMock()
        workflow = AgentWorkflow(LocalBM25Retriever(), llm,
            clarification_rule=alpha_clarification_rule, evidence_check=alpha_evidence_check)
        result = await workflow.run(AgentRequest(
            request_id=uuid4(), conversation_id=uuid4(), query="奖学金申请条件是什么？"))
        self.assertEqual(result.status, "needs_clarification")
        self.assertTrue(result.clarifying_question)
        llm.generate.assert_not_awaited()


@unittest.skipUnless(os.getenv("ALPHA_LIVE_QWEN_TEST") == "1",
                     "Real Qwen acceptance requires explicit opt-in and approved packages")
class LiveAlphaAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    """Paid endpoint + delivered rules + manually approved corpus; no mocks."""

    async def test_approved_policy_answer_has_real_retrieved_citations(self):
        paths = json.loads(os.environ["ALPHA_APPROVED_PACKAGES_JSON"])
        self.assertIsInstance(paths, list)
        self.assertTrue(paths)
        packages = [DocumentPackage.model_validate_json((ROOT / path).read_bytes()) for path in paths]
        self.assertTrue(all(p.metadata.retrieval_status == "enabled" for p in packages))
        workflow = await create_alpha_workflow(packages, file_root=ROOT)
        query = os.environ["ALPHA_ACCEPTANCE_QUERY"]
        result = await workflow.run(AgentRequest(
            request_id=uuid4(), conversation_id=uuid4(), query=query))
        self.assertEqual(result.status, "answered")
        hits = {c.chunk_id: c for c in await workflow.retriever.retrieve(RetrievalRequest(query=query))}
        self.assertTrue(result.citations)
        for citation in result.citations:
            self.assertIn(citation.chunk_id, hits)
            self.assertEqual(citation.excerpt, hits[citation.chunk_id].content)
            self.assertEqual(citation.source_url, hits[citation.chunk_id].source_url)


if __name__ == "__main__":
    unittest.main()
