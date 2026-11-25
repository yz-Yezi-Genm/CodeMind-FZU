"""Existing Qwen adapter + workflow + HTTP integration, mock transport only."""
import asyncio
import json
import os
import sys
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
from backend.app.config import AppSettings
from backend.contracts.models import (
    AgentRequest, DocumentPackage, FileProcessingStatus, RetrievalRequest, RetrievalStatus,
    TimelinessVerificationStatus,
)
from backend.retrieval.alpha_corpus import load_approved_alpha_retriever
from backend.retrieval.local import LocalBM25Retriever
from backend.services import alpha_business_rules
from backend.services.agent_workflow import AgentWorkflow, create_alpha_workflow
from backend.services.alpha_runtime import ConversationAgentService, InMemoryConversationStore
from backend.services.errors import LLMConfigurationError, ServiceError
from backend.services.qwen_client import QwenLLMClient, QwenSettings
from examples.agent_workflow_demo import DemoRetriever, demo_chunk
from scripts.run_alpha_agent import build_alpha_app


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
        return create_app(agent_service=agent, llm_client=llm,
                          settings=AppSettings(cors_allow_origins=("http://localhost:5173",))), upstream

    def test_existing_qwen_adapter_can_supply_verified_extractive_answer(self):
        observed = []

        def handler(request):
            payload = json.loads(request.content)
            observed.append(payload)
            evidence = json.loads(payload["messages"][-1]["content"])["evidence"][0]
            text = json.dumps({"answer": evidence["content"], "used_evidence_ids": [evidence["evidence_id"]]}, ensure_ascii=False)
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
            self.assertEqual(observed[0]["model"], "qwen-flash")
            self.assertEqual(observed[0]["temperature"], 0)
            client.portal.call(upstream.aclose)

    def test_model_failures_keep_backend_error_codes_instead_of_business_status(self):
        for status, expected_status, code in [
            (429, 429, "RATE_LIMITED"),
            (500, 503, "MODEL_UNAVAILABLE"),
            (408, 504, "MODEL_TIMEOUT"),
            (401, 503, "SERVICE_NOT_CONFIGURED"),
            (403, 503, "SERVICE_NOT_CONFIGURED"),
        ]:
            with self.subTest(upstream_status=status):
                app, upstream = self.app(lambda request: httpx.Response(status))
                with TestClient(app) as client:
                    response = client.post("/api/v1/ask", json={"query": "选课有哪些步骤？"},
                                           headers={"Origin": "http://localhost:5173"})
                    body = response.json()
                    self.assertEqual(response.status_code, expected_status)
                    self.assertEqual(body["error"]["code"], code)
                    self.assertEqual(response.headers["x-request-id"], body["request_id"])
                    self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
                    self.assertNotIn("status", body)
                    client.portal.call(upstream.aclose)

    def test_invalid_provider_envelope_is_503_with_cors_and_request_id(self):
        for payload in [None, [], {}, {"choices": []},
                        {"choices": [{"message": {"content": " "}}]}]:
            with self.subTest(payload=payload):
                app, upstream = self.app(lambda request: httpx.Response(200, json=payload))
                with TestClient(app) as client:
                    response = client.post("/api/v1/ask", json={"query": "选课有哪些步骤？"},
                                           headers={"Origin": "http://localhost:5173"})
                    body = response.json()
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(body["error"]["code"], "MODEL_UNAVAILABLE")
                    self.assertFalse(body["error"]["retryable"])
                    self.assertEqual(response.headers["x-request-id"], body["request_id"])
                    self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
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


def fixture_clarification(request, *, today=None):
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
        # Synthetic review input only; never promote a real policy fixture.
        self.package.metadata.temporal_notes = {"human_approved": True}
        self.package.metadata.applicability_raw = {"适用对象": "合成资料中的测试学生"}
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
        output = self.output(evidence) if self.output is not None else {"answer": evidence["content"], "used_evidence_ids": [evidence["evidence_id"]]}
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
        self.assertTrue(callable(workflow.retriever.get_document_metadata))
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

    async def test_live_bm25_withdrawal_during_generation_discards_citations(self):
        query = "星桥奖学金申请需要什么？"
        for status in (RetrievalStatus.REVIEW_ONLY, RetrievalStatus.BLOCKED):
            with self.subTest(status=status):
                workflow = await self.workflow()
                hit = (await workflow.retriever.retrieve(RetrievalRequest(query=query)))[0]
                self.assertIsNotNone(workflow.retriever.get_document_metadata(hit.version_id))
                self.assertIsNotNone(workflow.retriever.get_parsed_chunk(hit.chunk_id))

                async def withdraw_before_returning_model_response(request):
                    response = self.handler(request)
                    withdrawn = self.package.model_copy(deep=True)
                    withdrawn.metadata.retrieval_status = status
                    await workflow.retriever.index_document(withdrawn)
                    return response

                async with httpx.AsyncClient(transport=httpx.MockTransport(withdraw_before_returning_model_response)) as upstream:
                    workflow.llm_client = QwenLLMClient(
                        QwenSettings(api_key="offline-fixture-not-a-real-key", max_retries=0),
                        http_client=upstream,
                    )
                    body = (await self.ask(workflow, query)).json()

                self.assertIsNone(workflow.retriever.get_document_metadata(hit.version_id))
                self.assertIsNone(workflow.retriever.get_parsed_chunk(hit.chunk_id))
                self.assertEqual(body["status"], "insufficient_evidence")
                self.assertEqual(body["answer_mode"], "insufficient_data")
                self.assertEqual(body["warnings"][0]["code"], "EVIDENCE_APPROVAL_CHANGED")
                self.assertEqual(body["citations"], [])
        self.assertEqual(len(self.observed), 2)

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
            lambda item: {"answer": item["content"], "used_evidence_ids": [str(hits[0].chunk_id)]},
            lambda item: {"answer": "申请可获得99999元", "used_evidence_ids": [item["evidence_id"]]},
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

    async def test_direct_packages_reject_missing_or_false_review_before_indexing(self):
        for notes in [None, {}, {"human_approved": False}, {"human_approved": "true"}, {"human_approved": 1}]:
            with self.subTest(notes=notes):
                self.package.metadata.temporal_notes = notes
                original = self.package.model_dump()
                with patch("backend.retrieval.local.LocalBM25Retriever") as constructor:
                    with self.assertRaises(ServiceError) as raised:
                        await self.workflow()
                    constructor.assert_not_called()
                self.assertEqual(raised.exception.code, "SERVICE_NOT_CONFIGURED")
                self.assertEqual(self.package.model_dump(), original)
        self.assertEqual(self.observed, [])

    async def test_legacy_retriever_without_read_only_lookups_cannot_supply_evidence(self):
        class LegacyRetriever:
            def __init__(self, **kwargs):
                self.store = LocalBM25Retriever(**kwargs)

            async def index_document(self, package):
                return await self.store.index_document(package)

            async def retrieve(self, request):
                return await self.store.retrieve(request)

        with patch("backend.retrieval.local.LocalBM25Retriever", LegacyRetriever):
            workflow = await self.workflow()
        hits = await workflow.retriever.retrieve(RetrievalRequest(query="星桥奖学金"))
        self.assertTrue(hits)
        response = await self.ask(workflow, "星桥奖学金条件")
        self.assertEqual(response.json()["status"], "insufficient_evidence")
        self.assertEqual(self.observed, [])

    async def test_real_three_policy_packages_stay_blocked_and_skip_qwen(self):
        packages = [DocumentPackage.model_validate_json(
            (ROOT / "knowledge_base/processed/alpha" / (stem + ".json")).read_bytes()
        ) for stem in ("competition-recognition-2026", "scholarship-2026", "recommendation-eligibility-2027")]
        snapshots = [package.model_dump() for package in packages]
        with self.assertRaises(ServiceError):
            await self.workflow(packages=packages, file_root=ROOT, clarification_rule=lambda _: None)
        store = LocalBM25Retriever(file_root=ROOT)
        for package in packages:
            await store.index_document(package)
        workflow = AgentWorkflow(store, self.llm, clarification_rule=lambda _: None,
                                 evidence_check=lambda *_: True)
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
            build_from_retriever=lambda retriever, *, today: bound_check,
        )
        bound_check = lambda *_: True
        with patch.dict("sys.modules", {"backend.services.alpha_business_rules": rules}), patch.dict(
            os.environ, {"QWEN_API_KEY": "offline-fixture-not-a-real-key"},
        ):
            workflow = await create_alpha_workflow([self.package], file_root=self.file_root)
        self.assertIsInstance(workflow.llm_client, QwenLLMClient)
        self.assertIs(workflow.clarification_rule.func, rules.alpha_clarification_rule)
        self.assertIs(workflow.evidence_check, bound_check)
        self.assertTrue(await workflow.retriever.retrieve(RetrievalRequest(query="星桥奖学金")))

    async def test_factory_reuses_preloaded_retriever_and_its_citation_identities(self):
        # The approved loader in PR #35 returns a preloaded local retriever.
        # Exercise the stable handoff without copying that unmerged module here.
        retriever = (await self.workflow()).retriever
        before = await retriever.retrieve(RetrievalRequest(query="星桥奖学金申请需要什么？"))
        workflow = await create_alpha_workflow(
            file_root=self.file_root, retriever=retriever, llm_client=self.llm,
            clarification_rule=fixture_clarification, evidence_check=lambda *_: True,
        )
        self.assertIs(workflow.retriever, retriever)
        response = await self.ask(workflow, "星桥奖学金申请需要什么？")
        body = response.json()
        self.assertEqual(body["status"], "answered")
        self.assertEqual(body["citations"][0]["chunk_id"], str(before[0].chunk_id))
        self.assertEqual(body["citations"][0]["version_id"], str(before[0].version_id))
        self.assertEqual(body["citations"][0]["excerpt"], before[0].content)

    async def test_factory_rejects_ambiguous_or_missing_corpus_source(self):
        for options in [{"packages": [self.package], "retriever": LocalBM25Retriever()},
                        {"packages": [], "corpus_dir": self.file_root}]:
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    await create_alpha_workflow(
                        file_root=self.file_root, llm_client=self.llm,
                        clarification_rule=fixture_clarification, evidence_check=lambda *_: True,
                        **options,
                    )
        self.assertEqual(self.observed, [])

    async def test_missing_owner_rules_never_fall_back_to_demo_rules(self):
        with patch.dict("sys.modules", {"backend.services.alpha_business_rules": None}):
            with self.assertRaises(LLMConfigurationError):
                await create_alpha_workflow([], file_root=self.file_root, llm_client=self.llm)
        for callbacks in ({"clarification_rule": fixture_clarification}, {"evidence_check": lambda *_: True}):
            with self.assertRaises(ValueError):
                await create_alpha_workflow([], file_root=self.file_root, llm_client=self.llm, **callbacks)

    async def test_startup_entry_reads_packages_and_serves_same_qwen_workflow(self):
        from types import SimpleNamespace
        rules = SimpleNamespace(alpha_clarification_rule=fixture_clarification,
                                build_from_retriever=lambda retriever, *, today: lambda *_: True)
        package_path = self.file_root / "package.json"
        package_path.write_text(self.package.model_dump_json(), encoding="utf-8")
        with patch.dict("sys.modules", {"backend.services.alpha_business_rules": rules}), patch(
            "backend.services.qwen_client.create_qwen_client_from_env", return_value=self.llm,
        ):
            app = await build_alpha_app([Path("package.json")], file_root=self.file_root,
                                        workflow_timeout_seconds=12.0)
        self.assertIs(app.state.llm_client, self.llm)
        self.assertIs(app.state.agent_service.llm_client, self.llm)
        self.assertEqual(app.state.agent_service.timeout_seconds, 12.0)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            health = await client.get("/api/v1/health")
            response = await client.post("/api/v1/ask", json={"query": "星桥奖学金申请需要什么？"})
        self.assertEqual(health.status_code, 200)
        self.assertEqual(response.json()["status"], "answered")
        self.assertEqual(response.json()["citations"][0]["excerpt"], self.package.chunks[0].content)
        self.assertEqual(len(self.observed), 1)

    async def test_startup_entry_requires_packages_inside_file_root(self):
        path = self.file_root / "package.json"
        path.write_text(self.package.model_dump_json(), encoding="utf-8")
        for paths, root in [([], self.file_root), ([path], self.file_root / "synthetic")]:
            with self.subTest(paths=paths, root=root):
                with self.assertRaises(ValueError):
                    await build_alpha_app(paths, file_root=root)
        self.assertEqual(self.observed, [])

    async def test_adapter_timeout_and_connection_error_keep_backend_mapping(self):
        for exception, status, code in [
            (httpx.ReadTimeout, 504, "MODEL_TIMEOUT"),
            (httpx.ConnectError, 503, "MODEL_UNAVAILABLE"),
        ]:
            with self.subTest(exception=exception):
                def handler(request):
                    raise exception("private-provider-detail", request=request)
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
                    self.llm = QwenLLMClient(
                        QwenSettings(api_key="offline-fixture-not-a-real-key", max_retries=0),
                        http_client=upstream,
                    )
                    response = await self.ask(await self.workflow(), "星桥奖学金条件")
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()["error"]["code"], code)
                self.assertEqual(response.headers["x-request-id"], response.json()["request_id"])
                self.assertNotIn("private-provider-detail", response.text)
                self.assertNotIn("status", response.json())

    async def test_workflow_total_timeout_cancels_real_adapter_request(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def handler(request):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
            self.llm = QwenLLMClient(
                QwenSettings(api_key="offline-fixture-not-a-real-key", max_retries=1),
                http_client=upstream,
            )
            workflow = await self.workflow()
            workflow.timeout_seconds = 0.05
            response = await self.ask(workflow, "星桥奖学金条件")
        self.assertTrue(started.is_set())
        self.assertTrue(cancelled.is_set())
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["error"]["code"], "MODEL_TIMEOUT")
        self.assertNotIn("status", response.json())

    async def test_mixed_network_and_http_failures_share_adapter_retry_budget(self):
        attempts = []

        def handler(request):
            attempts.append(request)
            if len(attempts) == 1:
                raise httpx.ConnectError("private-provider-detail", request=request)
            return httpx.Response(503)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
            self.llm = QwenLLMClient(
                QwenSettings(api_key="offline-fixture-not-a-real-key", max_retries=1),
                http_client=upstream,
            )
            response = await self.ask(await self.workflow(), "星桥奖学金条件")
        self.assertEqual(len(attempts), 2)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "MODEL_UNAVAILABLE")
        self.assertNotIn("private-provider-detail", response.text)

    async def test_recommended_live_profile_reaches_transport_and_does_not_retry(self):
        from types import SimpleNamespace
        rules = SimpleNamespace(alpha_clarification_rule=fixture_clarification,
                                build_from_retriever=lambda retriever, *, today: lambda *_: True)
        for failure in ("http", "timeout"):
            with self.subTest(failure=failure):
                attempts = []

                def handler(request):
                    attempts.append(json.loads(request.content))
                    if failure == "timeout":
                        raise httpx.ReadTimeout("private-provider-detail", request=request)
                    return httpx.Response(503)

                # A real Qwen adapter creates its client with the environment
                # timeout; only the external network transport is substituted.
                upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
                self.addAsyncCleanup(upstream.aclose)
                with patch.dict("sys.modules", {"backend.services.alpha_business_rules": rules}), patch.dict(
                    os.environ, {"QWEN_API_KEY": "offline-fixture-not-a-real-key",
                                 "QWEN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                                 "QWEN_MODEL": "qwen-flash", "QWEN_TIMEOUT_SECONDS": "28",
                                 "QWEN_MAX_RETRIES": "0"},
                ):
                    workflow = await create_alpha_workflow([self.package], file_root=self.file_root)
                app = create_app(agent_service=workflow, llm_client=workflow.llm_client)
                # Create the ASGI client before substituting the adapter's
                # network-client constructor (httpx is a shared module).
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
                    with patch("backend.services.qwen_client.httpx.AsyncClient", return_value=upstream) as factory:
                        response = await api.post("/api/v1/ask", json={"query": "星桥奖学金条件"})
                self.assertEqual(workflow.timeout_seconds, 30.0)
                self.assertEqual(factory.call_args.kwargs["timeout"].read, 28.0)
                self.assertEqual(len(attempts), 1)
                self.assertEqual(attempts[0]["temperature"], 0)
                self.assertEqual(attempts[0]["model"], "qwen-flash")
                self.assertEqual(attempts[0]["max_tokens"], 8192)
                self.assertEqual(response.status_code, 504 if failure == "timeout" else 503)
                self.assertNotIn("private-provider-detail", response.text)


class QwenLiveProbeOfflineTests(unittest.IsolatedAsyncioTestCase):
    """Verify the paid-probe tool without calling a real endpoint."""

    async def test_probe_uses_short_synthetic_evidence_and_verified_output(self):
        from scripts.check_qwen_live import probe
        seen = []

        def handler(request):
            data = json.loads(request.content)
            seen.append(data)
            evidence = json.loads(data["messages"][-1]["content"])["evidence"][0]
            return httpx.Response(200, json={"model": "qwen-flash", "usage": {"total_tokens": 103},
                "choices": [{"message": {"content": json.dumps({"answer": evidence["content"], "used_evidence_ids": [evidence["evidence_id"]]})}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
            report = await probe(QwenLLMClient(QwenSettings(
                api_key="offline-fixture-not-a-real-key", model="qwen-flash", max_retries=0), http_client=upstream))
        self.assertTrue(report["json_and_full_quote_verified"])
        self.assertEqual(report["selection"]["evidence"][0]["quote"], "测试原文。")
        self.assertEqual(report["usage"], {"total_tokens": 103})
        self.assertEqual(seen[0]["max_tokens"], 128)
        self.assertEqual(seen[0]["temperature"], 0)

    async def test_probe_rejects_fabricated_quote(self):
        from backend.contracts.models import LLMResult
        from scripts.check_qwen_live import probe
        client = AsyncMock()

        async def fabricate(prompt):
            first = json.loads(prompt.messages[-1].content)["evidence"][0]
            return LLMResult(model="offline", content=json.dumps({
                "answer": "篡改原文", "used_evidence_ids": [first["evidence_id"]],
            }))

        client.generate.side_effect = fabricate
        with self.assertRaises(ValueError):
            await probe(client)

    def test_probe_does_not_read_environment_or_create_client_without_opt_in(self):
        from scripts.check_qwen_live import main
        from contextlib import redirect_stderr
        from io import StringIO
        with patch.object(sys, "argv", ["check_qwen_live", "--env-file", "not-read.env"]), patch(
            "scripts.check_qwen_live.create_qwen_client_from_env") as factory, redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main()
        self.assertEqual(raised.exception.code, 2)
        factory.assert_not_called()


class MergedRulesRetrieverIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Use the checked-out rules and BM25 with a synthetic corpus and mock Qwen HTTP."""

    async def asyncSetUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        items = json.loads((ROOT / "docs/assignment-03/alpha/examples/retrieval-synthetic-packages.json").read_bytes())
        self.package = DocumentPackage.model_validate(items[0])
        self.package.metadata.temporal_notes = {"human_approved": True}
        self.package.metadata.title = "合成测试：本科生奖学金评定管理办法（2026年版）"
        self.package.metadata.record_code = "SYNTH-2026-本科奖学金"
        self.package.metadata.applicability_raw = {"适用年级": "全体本科生", "适用专业": "全校相关本科专业"}
        self.package.chunks = [self.package.chunks[0]]
        self.package.chunks[0].content = "【合成测试，非政策】优秀学生综合奖学金申请需要提交申请表。"
        for file in self.package.files:
            path = self.root / file.storage_key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic fixture only")
            file.sha256 = sha256(path.read_bytes()).hexdigest()
        self.observed = []

        def handler(request):
            evidence = json.loads(json.loads(request.content)["messages"][-1]["content"])["evidence"]
            self.observed.append(evidence)
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
                "answer": evidence[0]["content"],
                "used_evidence_ids": [evidence[0]["evidence_id"]],
            }, ensure_ascii=False)}}]})

        self.upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(self.upstream.aclose)
        self.llm = QwenLLMClient(QwenSettings(api_key="offline-fixture-not-a-real-key", max_retries=0),
                                 http_client=self.upstream)

    async def workflow(self, package=None):
        approved = self.root / "approved"
        approved.mkdir(exist_ok=True)
        (approved / "policy.json").write_text(
            (package or self.package).model_dump_json(), encoding="utf-8")
        return await create_alpha_workflow(
            file_root=self.root, corpus_dir=approved, llm_client=self.llm,
            today=lambda: date(2026, 11, 20),
        )

    def request(self, query="优秀学生综合奖学金一等奖要什么条件？", history=None):
        from backend.contracts.models import ConversationTurn
        return AgentRequest(request_id=uuid4(), conversation_id=uuid4(), query=query,
                            history=[ConversationTurn(role="user", content=t) for t in history or []])

    async def test_real_rules_clarify_before_retrieval_and_model(self):
        workflow = await self.workflow()
        with patch.object(workflow.retriever, "retrieve", wraps=workflow.retriever.retrieve) as retrieve:
            result = await workflow.run(self.request("我想问奖学金的事"))
        self.assertEqual(result.status, "needs_clarification")
        self.assertEqual(result.clarifying_question, alpha_business_rules.QUESTION_SCHOLARSHIP_CATEGORY)
        retrieve.assert_not_called()
        self.assertEqual(self.observed, [])

    async def test_real_loader_rules_and_qwen_adapter_answer_with_source(self):
        workflow = await self.workflow()
        result = await workflow.run(self.request())
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.citations[0].excerpt, self.package.chunks[0].content)
        self.assertEqual(result.citations[0].source_url, self.package.metadata.source_url)
        self.assertEqual(len(self.observed), 1)

    async def test_real_rules_use_user_history_to_complete_category(self):
        result = await (await self.workflow()).run(self.request("一等奖要什么条件？",
            ["我想问奖学金的事情", "优秀学生综合奖学金"]))
        self.assertEqual(result.status, "answered")
        self.assertEqual(len(self.observed), 1)

    async def test_missing_or_broken_metadata_blocks_before_qwen(self):
        workflow = await self.workflow()
        for lookup in (lambda _: None, lambda _: (_ for _ in ()).throw(RuntimeError("lookup unavailable"))):
            with self.subTest(lookup=lookup), patch.object(workflow.retriever, "get_document_metadata", lookup):
                workflow.evidence_check = alpha_business_rules.build_from_retriever(workflow.retriever)
                result = await workflow.run(self.request())
                self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(self.observed, [])

    async def test_unknown_applicability_and_wrong_policy_kind_rejected(self):
        for application, query in [(None, "优秀学生综合奖学金一等奖要什么条件？"),
                                   ({"适用年级": "全体本科生"}, "国家奖学金需要什么条件？")]:
            with self.subTest(query=query):
                self.package.metadata.applicability_raw = application
                result = await (await self.workflow()).run(self.request(query))
                self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(self.observed, [])

    async def test_year_mismatch_rejected_using_real_metadata(self):
        self.package.metadata.record_code = "SYNTH-2026-院级奖学金"
        self.package.metadata.title = "合成测试：2026年院级奖学金通知"
        self.package.metadata.applicability_raw["适用年度"] = "2026年"
        self.package.chunks[0].content = "【合成测试】院级学科竞赛类爱国者之星奖学金申请条件。"
        result = await (await self.workflow()).run(self.request("2027年院级学科竞赛类爱国者之星奖学金申请条件是什么？"))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(self.observed, [])

    async def test_teacher_section_filtered_out_of_real_qwen_prompt(self):
        self.package.metadata.record_code = "SYNTH-2024-创新创业学分认定"
        self.package.metadata.title = "合成测试：创新创业学分认定办法"
        teacher = self.package.chunks[0].model_copy(deep=True)
        teacher.content = "【合成测试】竞赛创新学分教师指导绩效需要提交申请表。"
        teacher.locator_note = "教师指导工作量与绩效认定"
        student = teacher.model_copy(deep=True)
        student.chunk_no = 2
        student.content = "【合成测试】竞赛创新学分学生申请需要提交申请表。"
        student.locator_note = "学生学分申请与记载"
        self.package.chunks = [teacher, student]
        workflow = await self.workflow()
        result = await workflow.run(self.request(
            "全国大学生数学建模竞赛国家二等奖，作品名称《测试交通预测》，团队作品，我为第一完成人，创新学分原始分是多少？"))
        self.assertEqual(result.status, "answered")
        self.assertEqual([x["content"] for x in self.observed[0]], [student.content])
        self.assertEqual(result.citations[0].excerpt, student.content)

    async def test_sensitive_sections_fail_closed_for_every_missing_lookup_case(self):
        self.package.metadata.record_code = "SYNTH-2024-创新创业学分认定"
        self.package.metadata.title = "合成测试：创新创业学分认定办法"
        self.package.chunks[0].content = "【合成测试】竞赛创新学分学生申请需要提交申请表。"
        self.package.chunks[0].locator_note = "学生学分申请与记载"
        query = "全国大学生数学建模竞赛国家二等奖，作品名称《测试交通预测》，团队作品，我为第一完成人，创新学分原始分是多少？"
        for failure in ("method_absent", "exception", "unknown_chunk", "missing_note", "empty_note"):
            with self.subTest(failure=failure):
                workflow = await self.workflow()
                real_lookup = workflow.retriever.get_parsed_chunk

                def lookup(chunk_id):
                    if failure == "exception":
                        raise RuntimeError("private-chapter-query-detail")
                    if failure == "unknown_chunk":
                        return None
                    parsed = real_lookup(chunk_id)
                    parsed.locator_note = None if failure == "missing_note" else ""
                    return parsed

                with patch.object(workflow.retriever, "get_parsed_chunk",
                                  None if failure == "method_absent" else lookup):
                    workflow.evidence_check = alpha_business_rules.build_from_retriever(
                        workflow.retriever, today=lambda: date(2026, 11, 19))
                    result = await workflow.run(self.request(query))
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.answer_mode, "insufficient_data")
                self.assertEqual(result.warnings[0].code, "NO_ELIGIBLE_EVIDENCE")
                self.assertEqual(result.citations, [])
                self.assertNotIn("private-chapter-query-detail", result.model_dump_json())
        self.assertEqual(self.observed, [])

    async def test_missing_indexed_chunk_blocks_even_when_the_rule_needs_no_section(self):
        workflow = await self.workflow()
        with patch.object(workflow.retriever, "get_parsed_chunk", return_value=None):
            workflow.evidence_check = alpha_business_rules.build_from_retriever(workflow.retriever)
            result = await workflow.run(self.request())
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.citations, [])
        self.assertEqual(self.observed, [])

    async def test_clarification_exception_has_strict_agent_refusal_contract(self):
        workflow = await self.workflow()

        def broken_rule(request):
            raise RuntimeError("private-clarification-detail")

        workflow.clarification_rule = broken_rule
        with patch.object(workflow.retriever, "retrieve", wraps=workflow.retriever.retrieve) as retrieve:
            result = await workflow.run(self.request())
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.answer_mode, "insufficient_data")
        self.assertEqual(result.warnings[0].code, "CLARIFICATION_RULE_FAILED")
        self.assertEqual(result.citations, [])
        self.assertNotIn("private-clarification-detail", result.model_dump_json())
        retrieve.assert_not_called()
        self.assertEqual(self.observed, [])

    async def test_per_retriever_rule_closures_do_not_share_metadata(self):
        first = await self.workflow()
        self.package.metadata.applicability_raw = None
        second = await self.workflow()
        self.assertEqual((await second.run(self.request())).status, "insufficient_evidence")
        self.assertEqual((await first.run(self.request())).status, "answered")
        self.assertEqual(len(self.observed), 1)

    async def test_historical_evidence_stays_blocked_by_workflow_gate(self):
        self.package.metadata.timeliness_verification_status = TimelinessVerificationStatus.HISTORICAL
        workflow = await self.workflow()
        self.assertTrue(await workflow.retriever.retrieve(RetrievalRequest(query="奖学金")))
        result = await workflow.run(self.request())
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(self.observed, [])

    async def test_review_only_package_skipped_by_actual_approved_loader(self):
        from backend.contracts.models import RetrievalStatus
        self.package.metadata.retrieval_status = RetrievalStatus.REVIEW_ONLY
        with self.assertRaises(ServiceError):
            await self.workflow()
        self.assertEqual(self.observed, [])

    async def test_latest_loader_and_agent_reject_every_unapproved_marker(self):
        approved = self.root / "approved"
        approved.mkdir()
        for notes in [None, {}, {"human_approved": False}, {"human_approved": "true"}, {"human_approved": 1}]:
            with self.subTest(notes=notes):
                self.package.metadata.temporal_notes = notes
                (approved / "policy.json").write_text(self.package.model_dump_json(), encoding="utf-8")
                retriever, report = await load_approved_alpha_retriever(
                    corpus_dir=approved, file_root=self.root, allow_missing=False)
                self.assertEqual(report.loaded_packages, ())
                self.assertEqual(report.total_indexed_chunks, 0)
                self.assertTrue(report.skipped_packages)
                with self.assertRaises(ServiceError):
                    await self.workflow()
                # Bypass the loader on purpose: Agent's own approval gate must
                # still reject enabled hits even with a permissive business rule.
                store = LocalBM25Retriever(file_root=self.root)
                await store.index_document(self.package)
                self.assertTrue(await store.retrieve(RetrievalRequest(query="奖学金")))
                result = await AgentWorkflow(store, self.llm, clarification_rule=lambda _: None,
                    evidence_check=lambda *_: True).run(self.request())
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.citations, [])
        self.assertEqual(self.observed, [])

    async def test_formal_corpus_report_rejects_partial_failed_empty_and_missing(self):
        for problem in ("partial", "failed", "no_chunks", "empty", "missing"):
            with self.subTest(problem=problem):
                with TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    package = self.package.model_copy(deep=True)
                    if problem == "partial":
                        package.files[0].processing_status = FileProcessingStatus.NEEDS_OCR
                    elif problem == "failed":
                        package.files[0].sha256 = "0" * 64
                    elif problem == "no_chunks":
                        package.chunks = []
                    if problem not in {"empty", "missing"}:
                        # Keep corpus under the configured root as required by
                        # latest PR #35 path validation.
                        directory = self.root / ("report-" + problem)
                        directory.mkdir()
                        (directory / "policy.json").write_text(package.model_dump_json(), encoding="utf-8")
                    else:
                        directory = self.root / ("report-" + problem)
                        if problem == "empty":
                            directory.mkdir()
                    with self.assertRaises(ServiceError) as raised:
                        await create_alpha_workflow(file_root=self.root, corpus_dir=directory,
                            llm_client=self.llm, clarification_rule=lambda _: None, evidence_check=lambda *_: True)
                    self.assertEqual(raised.exception.code, "SERVICE_NOT_CONFIGURED")
        self.assertEqual(self.observed, [])

    async def test_manifest_approval_cannot_replace_package_approval(self):
        directory = self.root / "approved"
        directory.mkdir()
        self.package.metadata.temporal_notes = {}
        (directory / "policy.json").write_text(self.package.model_dump_json(), encoding="utf-8")
        (directory / "manifest.json").write_text(json.dumps({"packages": [
            {"package": "approved/policy.json", "human_approved": True}]}), encoding="utf-8")
        with self.assertRaises(ServiceError):
            await self.workflow()
        self.assertEqual(self.observed, [])

    async def test_recommendation_grade_eligibility_and_reference_are_distinct(self):
        self.package.metadata.record_code = "SYNTH-2027-推免资格推荐"
        self.package.metadata.title = "合成测试：2027届本科推免资格推荐办法"
        self.package.metadata.applicability_raw = {
            "适用年级": "2027届应届本科毕业生；大一至大三仅升学准备参考",
            "适用专业": "计算机科学与技术、软件工程",
            "适用对象": "学院申请取得本科推免推荐资格的学生", "目标届别": "2027届",
        }
        self.package.chunks[0].content = "【合成测试，非政策】2027届推免推荐资格按本通知核对材料与排名。"
        workflow = await self.workflow()
        for grade in ("大一", "大二", "大三", "2024级"):
            with self.subTest(grade=grade):
                result = await workflow.run(self.request(f"我是{grade}，2027届推免推荐资格怎么排名？"))
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.citations, [])
        self.assertEqual(self.observed, [])
        for query in ("我是大四，2027届推免推荐资格怎么排名？",
                      "我是2023级，2027届推免推荐资格怎么排名？",
                      "我是大二，2027届推免要提前准备什么？"):
            with self.subTest(query=query):
                result = await workflow.run(self.request(query))
                self.assertEqual(result.status, "answered")
                self.assertEqual(result.citations[0].excerpt, self.package.chunks[0].content)

    async def test_competition_or_work_switch_does_not_inherit_previous_rank(self):
        self.package.metadata.record_code = "SYNTH-2024-创新创业学分认定"
        self.package.metadata.title = "合成测试：创新创业学分认定办法"
        self.package.chunks[0].content = "【合成测试】竞赛创新学分学生申请需要提交申请表。"
        self.package.chunks[0].locator_note = "学生学分申请与记载"
        workflow = await self.workflow()
        history = ["数学建模竞赛国家级二等奖，团队作品，作品《交通预测》，我是第二完成人"]
        for query in ("蓝桥杯省赛二等奖，团队作品，作品《校园二手平台》，创新学分能认定多少？",
                      "数学建模竞赛省级二等奖，团队作品，作品《空气质量预测》，创新学分能认定多少？"):
            with self.subTest(query=query), patch.object(workflow.retriever, "retrieve",
                    wraps=workflow.retriever.retrieve) as retrieve:
                result = await workflow.run(self.request(query, history))
                self.assertEqual(result.status, "needs_clarification")
                self.assertEqual(result.clarifying_question, alpha_business_rules.QUESTION_TOP_EIGHT)
                retrieve.assert_not_called()
        self.assertEqual(self.observed, [])
        same = "数学建模竞赛国家级二等奖，团队作品，作品《交通预测》，创新学分能认定多少？"
        result = await workflow.run(self.request(same, history))
        self.assertEqual(result.status, "answered")
        self.assertEqual(len(self.observed), 1)

    async def test_expired_scholarship_notice_with_real_rules_answers_its_own_year(self):
        self.package.metadata.record_code = "SYNTH-2026-星火奖学金"
        self.package.metadata.title = "合成测试：2026年星火奖教奖学金评选通知"
        self.package.metadata.timeliness_verification_status = TimelinessVerificationStatus.EXPIRED
        self.package.metadata.deadline_on = date(2026, 4, 26)
        self.package.chunks[0].content = "【合成测试】星火奖学金申请截止时间为2026年4月26日。"
        self.package.chunks[0].locator_note = json.dumps({"heading_path": [
            {"level": 2, "title": "星火奖学金评选细则（学生）"}]}, ensure_ascii=False)
        workflow = await self.workflow()
        hits = await workflow.retriever.retrieve(RetrievalRequest(query="星火奖学金"))
        self.assertTrue(hits)
        historical = self.request("2026年星火奖学金当时截止到什么时候？")
        current = self.request("星火奖学金现在还能申请吗，有什么资格要求？")
        self.assertIs(workflow.evidence_check(historical, hits[0]), True)
        self.assertIs(workflow.evidence_check(current, hits[0]), False)
        result = await workflow.run(historical)
        self.assertEqual(result.answer_mode, "historical")
        self.assertIn("2026年历史资料", result.answer)
        self.assertEqual(result.citations[0].excerpt, self.package.chunks[0].content)
        result = await workflow.run(current)
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.citations, [])
        self.assertEqual(len(self.observed), 1)

    async def test_beta_s4_rules_with_bm25_and_qwen_adapter(self):
        direction = alpha_business_rules.RESOURCE_DIRECTION_CODE
        metadata = self.package.metadata
        metadata.record_code = "SYNTH-LAB-INTRO"
        metadata.title = "合成测试：计算机学院实验室研究方向简介"
        metadata.document_type = "学院资源"
        metadata.category_name = "研究方向与公开介绍"
        metadata.business_direction_codes = [direction]
        metadata.source_url = "https://ccds.fzu.edu.cn/test/lab-intro.htm"
        metadata.applicability_raw = None
        self.package.chunks[0].content = "EDA实验室研究方向为集成电路设计自动化。"
        workflow = await self.workflow()
        result = await workflow.run(self.request("EDA 实验室主要研究什么？"))
        self.assertEqual(result.answer_mode, "current_policy")
        self.assertEqual(result.citations[0].excerpt, self.package.chunks[0].content)
        for query in ("EDA实验室现在还招人吗？", "我大二能进 EDA 实验室吗？"):
            with self.subTest(query=query):
                result = await workflow.run(self.request(query))
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.citations, [])
        metadata.source_url = "https://ccds.fzu.edu.cn.example.invalid/lab-intro.htm"
        workflow = await self.workflow()
        result = await workflow.run(self.request("EDA 实验室主要研究什么？"))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(len(self.observed), 1)

    async def test_beta_s4_public_contact_without_applicability_requires_direct_college_page(self):
        direction = alpha_business_rules.RESOURCE_DIRECTION_CODE
        metadata = self.package.metadata
        metadata.record_code = "SYNTH-PUBLIC-CONTACT"
        metadata.title = "合成测试：学院办公室公开联系方式"
        metadata.document_type = "学院资源"
        metadata.category_name = "学院公开信息与联系方式"
        metadata.business_direction_codes = [direction]
        metadata.applicability_raw = None
        metadata.source_url = "https://ccds.fzu.edu.cn/test/contact.htm"
        self.package.chunks[0].content = "合成测试：学院办公室电话为示例号码，办公地点为示例楼。"
        query = self.request("学院办公室电话和办公地点是什么？")
        workflow = await self.workflow()
        result = await workflow.run(query)
        self.assertEqual(result.answer_mode, "current_policy")
        self.assertEqual(result.citations[0].source_url, metadata.source_url)

        result = await workflow.run(self.request("我大二能联系学院办公室办理吗？"))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.citations, [])
        for url in ("https://news.fzu.edu.cn/test/contact.htm", "https://ccds.fzu.edu.cn.example.invalid/contact.htm",
                    "http://ccds.fzu.edu.cn/test/contact.htm", "https://fake@ccds.fzu.edu.cn/test/contact.htm"):
            with self.subTest(url=url):
                metadata.source_url = url
                result = await (await self.workflow()).run(query)
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.citations, [])
        self.assertEqual(len(self.observed), 1)

    async def test_beta_s4_applicability_is_still_required_for_other_categories(self):
        direction = alpha_business_rules.RESOURCE_DIRECTION_CODE
        metadata = self.package.metadata
        metadata.title = "合成测试：学院资源资料"
        metadata.document_type = "学院资源"
        metadata.business_direction_codes = [direction]
        metadata.source_url = "https://ccds.fzu.edu.cn/test/resource.htm"
        metadata.applicability_raw = None
        for category, query in (
            ("通知与办事渠道", "学院通知在哪里看？"),
            ("培养方案与课程", "计算机专业培养方案有哪些课程？"),
            ("实验室与科研团队", "我大二能进 EDA 实验室吗？"),
            ("科研实践与竞赛", "学院有哪些科研项目？"),
        ):
            with self.subTest(category=category):
                metadata.category_name = category
                self.package.chunks[0].content = f"合成测试：{query} 附合成资料。"
                workflow = await self.workflow()
                self.assertTrue(await workflow.retriever.retrieve(RetrievalRequest(query=query)))
                result = await workflow.run(self.request(query))
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.citations, [])
        self.assertEqual(self.observed, [])

    async def test_beta_s4_expired_recruitment_with_bm25_and_qwen_adapter(self):
        direction = alpha_business_rules.RESOURCE_DIRECTION_CODE
        metadata = self.package.metadata
        metadata.record_code = "SYNTH-LAB-RECRUITMENT-2026"
        metadata.title = "合成测试：2026年EDA实验室报名通知"
        metadata.document_type = "学院资源"
        metadata.category_name = "实验室与科研团队"
        metadata.business_direction_codes = [direction]
        metadata.source_url = "https://ccds.fzu.edu.cn/test/lab-recruitment.htm"
        metadata.applicability_raw = {"适用年度": "2026年", "适用对象": "全体本科生"}
        metadata.deadline_on = date(2026, 10, 31)
        metadata.timeliness_verification_status = TimelinessVerificationStatus.EXPIRED
        self.package.chunks[0].content = "EDA实验室报名须提交报名表，报名截止2026-10-31。"
        workflow = await self.workflow()
        result = await workflow.run(self.request("2026年EDA实验室当时报名流程和截止时间是什么？"))
        self.assertEqual(result.answer_mode, "historical")
        self.assertIn("2026年历史资料", result.answer)
        self.assertEqual(result.citations[0].excerpt, self.package.chunks[0].content)
        for query, history in (
            ("EDA 实验室现在还招吗？", None),
            ("现在还可以报名 EDA 实验室吗？", None),
            ("现在还招吗？", ["EDA 实验室主要研究什么？"]),
        ):
            with self.subTest(query=query):
                result = await workflow.run(self.request(query, history))
                self.assertEqual(result.status, "answered")
                self.assertEqual(result.answer_mode, "historical")
                self.assertEqual(result.citations[0].excerpt, self.package.chunks[0].content)
                self.assertIn("2026年度报名已于2026年10月31日截止", result.answer)
                self.assertIn("目前是否有新一轮招募，暂无法确认", result.answer)
        for query in ("EDA 实验室现在还剩几个名额？", "EDA 实验室现在还招几个？",
                      "AI 实验室现在还招吗？", "EDA 实验室现在还招吗，想知道剩余名额"):
            with self.subTest(query=query):
                result = await workflow.run(self.request(query))
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.answer_mode, "insufficient_data")
                self.assertEqual(result.citations, [])
        query = self.request("EDA 实验室现在还招吗？")

        active = self.package.model_copy(deep=True)
        active.metadata.version_no = "v2"
        active.metadata.timeliness_verification_status = TimelinessVerificationStatus.CURRENT
        active.metadata.deadline_on = date(2026, 12, 1)
        active.chunks[0].content = "EDA实验室正在接收报名，请于2026年12月1日前提交报名表。"
        await workflow.retriever.index_document(active)
        result = await workflow.run(query)
        self.assertEqual(result.answer_mode, "procedure_reference")
        self.assertEqual(result.citations[0].excerpt, active.chunks[0].content)
        self.assertEqual(len(self.observed[-1]), 1)

        workflow = await self.workflow()
        original_check = workflow.evidence_check

        def withdrawn_after_first_check(request, chunk):
            return check.call_count == 1 and original_check(request, chunk)

        with patch.object(workflow, "evidence_check", side_effect=withdrawn_after_first_check) as check:
            result = await workflow.run(query)
        self.assertEqual(check.call_count, 2)
        self.assertEqual(result.warnings[0].code, "EVIDENCE_APPROVAL_CHANGED")
        self.assertEqual(result.citations, [])

        for title, applicability, deadline in (
            (metadata.title, metadata.applicability_raw, None),
            ("合成测试：EDA实验室报名通知", {"适用对象": "全体本科生"}, metadata.deadline_on),
        ):
            with self.subTest(title=title, deadline=deadline):
                metadata.title, metadata.applicability_raw, metadata.deadline_on = title, applicability, deadline
                workflow = await self.workflow()
                result = await workflow.run(query)
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.citations, [])
        self.assertEqual(len(self.observed), 2)

    async def test_beta_s4_current_recruitment_respects_applicability(self):
        direction = alpha_business_rules.RESOURCE_DIRECTION_CODE
        metadata = self.package.metadata
        metadata.record_code = "SYNTH-ACTIVE-LAB-RECRUITMENT-2026"
        metadata.title = "合成测试：2026年EDA实验室报名通知"
        metadata.document_type = "学院资源"
        metadata.category_name = "实验室与科研团队"
        metadata.business_direction_codes = [direction]
        metadata.source_url = "https://ccds.fzu.edu.cn/test/lab-recruitment.htm"
        metadata.applicability_raw = {"适用年度": "2026年", "适用年级": "大二", "适用对象": "本科生"}
        metadata.deadline_on = date(2026, 12, 1)
        self.package.chunks[0].content = "EDA实验室面向大二本科生，报名须提交报名表，报名截止2026-12-01。"
        workflow = await self.workflow()
        result = await workflow.run(self.request("我大二能报名EDA实验室吗？"))
        self.assertEqual(result.answer_mode, "procedure_reference")
        self.assertIn("大二本科生", result.answer)
        result = await workflow.run(self.request("我大一能报名EDA实验室吗？"))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.citations, [])
        self.assertEqual(len(self.observed), 1)

        metadata.title = "合成测试：EDA实验室长期接收条件"
        metadata.applicability_raw.pop("适用年度")
        metadata.deadline_on = None
        self.package.chunks[0].content = "EDA实验室面向大二本科生，需提交学习经历和项目材料。"
        result = await (await self.workflow()).run(self.request("我大二能进 EDA 实验室吗？"))
        self.assertEqual(result.answer_mode, "current_policy")
        self.assertEqual(result.answer, self.package.chunks[0].content)

    async def test_beta_s4_closure_and_quota_use_the_existing_ask_endpoint(self):
        direction = alpha_business_rules.RESOURCE_DIRECTION_CODE
        metadata = self.package.metadata
        metadata.title = "合成测试：2026年EDA实验室报名通知"
        metadata.document_type = "学院资源"
        metadata.category_name = "实验室与科研团队"
        metadata.business_direction_codes = [direction]
        metadata.source_url = "https://ccds.fzu.edu.cn/test/lab-recruitment.htm"
        metadata.applicability_raw = {"适用年度": "2026年", "适用对象": "全体本科生"}
        metadata.deadline_on = date(2026, 10, 31)
        metadata.timeliness_verification_status = TimelinessVerificationStatus.EXPIRED
        self.package.chunks[0].content = "合成测试：EDA实验室报名截止2026-10-31。"
        workflow = await self.workflow()
        app = create_app(agent_service=workflow)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            closure = await client.post("/api/v1/ask", json={"query": "EDA 实验室现在还招吗？"})
            quota = await client.post("/api/v1/ask", json={"query": "EDA 实验室现在还剩几个名额？"})
        self.assertEqual(closure.status_code, 200)
        self.assertEqual(closure.json()["status"], "answered")
        self.assertEqual(closure.json()["answer_mode"], "historical")
        self.assertEqual(closure.json()["citations"][0]["excerpt"], self.package.chunks[0].content)
        self.assertEqual(quota.status_code, 200)
        self.assertEqual(quota.json()["status"], "insufficient_evidence")
        self.assertEqual(quota.json()["answer_mode"], "insufficient_data")
        self.assertEqual(quota.json()["citations"], [])
        self.assertEqual(self.observed, [])

    async def test_beta_s4_qinghe_status_uses_r3_notice_and_preserves_personal_scope(self):
        direction = alpha_business_rules.RESOURCE_DIRECTION_CODE
        metadata = self.package.metadata
        metadata.title = "合成测试：2026-2027学年青禾计划本科生进实验室报名通知"
        metadata.document_type = "年度通知"
        metadata.category_name = "实验室与科研团队"
        metadata.business_direction_codes = [direction]
        metadata.source_url = "https://ccds.fzu.edu.cn/test/qinghe.htm"
        metadata.applicability_raw = {"对象": "计算机与大数据学院全体本科生", "批次": "2026—2027学年青禾计划"}
        metadata.deadline_on = date(2026, 10, 31)
        self.package.chunks[0].content = "合成测试：青禾计划本科生进实验室报名截止日期为2026年10月31日。"
        for status in (TimelinessVerificationStatus.HISTORICAL, TimelinessVerificationStatus.EXPIRED):
            metadata.timeliness_verification_status = status
            workflow = await self.workflow()
            for query, history in (
                ("青禾计划现在还招吗？", None),
                ("现在还招吗？", ["我想了解青禾计划的实验室。"]),
            ):
                with self.subTest(status=status, query=query):
                    result = await workflow.run(self.request(query, history))
                    self.assertEqual(result.answer_mode, "historical")
                    self.assertIn("2026年10月31日截止", result.answer)
                    self.assertIn("目前是否有新一轮招募，暂无法确认", result.answer)
                    self.assertEqual(result.citations[0].excerpt, self.package.chunks[0].content)
            for query, history in (
                ("青禾计划现在还剩几个名额？", None),
                ("现在还剩几个名额？", ["我想了解青禾计划的实验室。"]),
            ):
                with self.subTest(status=status, query=query):
                    result = await workflow.run(self.request(query, history))
                    self.assertEqual(result.status, "insufficient_evidence")
                    self.assertEqual(result.citations, [])

        # The pending-review package's old category must still fail the R3 gate.
        metadata.category_name = "科研实践与实验室"
        workflow = await self.workflow()
        result = await workflow.run(self.request("青禾计划现在还招吗？"))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.citations, [])
        self.assertEqual(self.observed, [])

    def lab_recruitment_fixture(self, deadline, timeliness, lab="EDA 实验室"):
        metadata = self.package.metadata
        metadata.title = f"合成测试：2026年 {lab}报名通知"
        metadata.document_type = "年度通知"
        metadata.category_name = "实验室与科研团队"
        metadata.business_direction_codes = [alpha_business_rules.RESOURCE_DIRECTION_CODE]
        metadata.source_url = "https://ccds.fzu.edu.cn/test/eda.htm"
        metadata.applicability_raw = {"适用年度": "2026年", "适用对象": "全体本科生"}
        metadata.deadline_on = deadline
        metadata.timeliness_verification_status = timeliness
        self.package.chunks[0].content = (
            f"合成测试：{lab}计划招收 8 人，报名截止日期为{deadline:%Y-%m-%d}，请提交报名表。"
        )

    async def test_beta_s4_current_plan_counts_cannot_answer_live_quota(self):
        self.lab_recruitment_fixture(date(2026, 12, 1), TimelinessVerificationStatus.CURRENT)
        workflow = await self.workflow()
        for query in (
            "EDA 实验室现在还招吗？",
            "2026年 EDA 实验室计划招几人？",
            "EDA 实验室目前公布的计划名额是多少？",
        ):
            result = await workflow.run(self.request(query))
            self.assertEqual(result.answer_mode, "procedure_reference")
            self.assertEqual(result.citations[0].excerpt, self.package.chunks[0].content)

        for query, history in (
            ("EDA 实验室现在还剩几个名额？", None),
            ("EDA 实验室目前还招多少人？", None),
            ("还剩几个名额？", ["2026年 EDA 实验室怎么报名？"]),
        ):
            with self.subTest(query=query):
                result = await workflow.run(self.request(query, history))
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.answer_mode, "insufficient_data")
                self.assertEqual(result.citations, [])
                self.assertEqual(result.warnings[0].code, "LIVE_LAB_QUOTA_UNVERIFIED")
        self.assertEqual(len(self.observed), 3)

    async def test_beta_s4_mixed_lab_research_and_quota_over_http(self):
        self.lab_recruitment_fixture(date(2026, 12, 1), TimelinessVerificationStatus.CURRENT)
        workflow = await self.workflow()
        retriever = workflow.retriever
        quota_question = "EDA 实验室现在还剩几个名额？"
        research_question = "EDA 实验室研究什么？"
        mixed_question = "EDA 实验室研究什么，还有几个名额？"
        app = create_app(agent_service=workflow)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            quota = (await client.post("/api/v1/ask", json={"query": quota_question})).json()
            without_intro = (await client.post("/api/v1/ask", json={"query": mixed_question})).json()
            self.assertEqual(self.observed, [])

            introduction = self.package.model_copy(deep=True)
            introduction.metadata.record_code = "SYNTH-EDA-RESEARCH"
            introduction.metadata.title = "合成测试：EDA 实验室研究方向"
            introduction.metadata.document_type = "研究方向与公开介绍"
            introduction.metadata.category_name = "研究方向与公开介绍"
            introduction.metadata.source_url = "https://ccds.fzu.edu.cn/test/eda-intro.htm"
            introduction.metadata.applicability_raw = None
            introduction.metadata.deadline_on = None
            introduction.chunks[0].content = "合成测试：EDA 实验室研究方向为集成电路设计自动化。"
            await retriever.index_document(introduction)

            # Both sources enter BM25's results. The rules must keep the annual plan out of the prompt.
            hits = await retriever.retrieve(RetrievalRequest(query=research_question))
            self.assertEqual({hit.source_url for hit in hits}, {
                self.package.metadata.source_url, introduction.metadata.source_url,
            })
            for query in (mixed_question, "EDA 实验室还有几个名额，研究什么？",
                          "EDA 实验室研究什么同时还有几个名额", research_question):
                with self.subTest(query=query):
                    response = await client.post("/api/v1/ask", json={"query": query})
                    self.assertEqual(response.status_code, 200)
                    result = response.json()
                    self.assertEqual((result["status"], result["answer_mode"]), ("answered", "current_policy"))
                    self.assertIn("集成电路设计自动化", result["answer"])
                    self.assertNotIn("8 人", result["answer"])
                    self.assertEqual([citation["excerpt"] for citation in result["citations"]], [introduction.chunks[0].content])
                    self.assertEqual([entry["content"] for entry in self.observed[-1]], [introduction.chunks[0].content])
                    if query == research_question:
                        self.assertEqual(result["warnings"], [])
                    else:
                        self.assertIn("暂无经过核验的实时剩余名额", result["answer"])
                        self.assertEqual([warning["code"] for warning in result["warnings"]], ["LIVE_LAB_QUOTA_UNVERIFIED"])

        for result in (quota, without_intro):
            self.assertEqual((result["status"], result["answer_mode"]), ("insufficient_evidence", "insufficient_data"))
            self.assertEqual(result["citations"], [])
            self.assertIn("LIVE_LAB_QUOTA_UNVERIFIED", [warning["code"] for warning in result["warnings"]])
        self.assertEqual(len(self.observed), 4)

    async def test_beta_cross_domain_quota_reaches_the_original_workflow_over_http(self):
        workflow = await self.workflow()
        clarification = workflow.clarification_rule
        app = create_app(agent_service=workflow)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for query in (
                "EDA 实验室研究什么？另外，奖学金还有几个名额？",
                "EDA 实验室研究什么？另外说一下奖学金，还剩几个名额？",
            ):
                with self.subTest(query=query), patch.object(workflow, "clarification_rule", wraps=clarification) as rule:
                    response = await client.post("/api/v1/ask", json={"query": query})
                    self.assertEqual(response.status_code, 200)
                    result = response.json()
                    self.assertEqual(rule.call_args.args[0].query, query)
                    self.assertEqual(result["status"], "needs_clarification")
                    self.assertEqual(result["clarifying_question"], alpha_business_rules.QUESTION_SCHOLARSHIP_CATEGORY)
                    self.assertEqual(result["warnings"], [])

            query = "EDA 实验室研究什么？另外，优秀学生综合奖学金还有几个名额？"
            with patch.object(workflow.retriever, "retrieve", wraps=workflow.retriever.retrieve) as retrieve:
                response = await client.post("/api/v1/ask", json={"query": query})
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(retrieve.call_args.args[0].query, query)
            self.assertEqual(result["status"], "insufficient_evidence")
            self.assertEqual(result["citations"], [])
            self.assertNotIn("LIVE_LAB_QUOTA_UNVERIFIED", [warning["code"] for warning in result["warnings"]])

            query = "EDA 实验室现在还剩几个名额？另外，奖学金还有几个名额？"
            with patch.object(workflow, "clarification_rule", wraps=clarification) as rule:
                response = await client.post("/api/v1/ask", json={"query": query})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(rule.call_args.args[0].query, "奖学金还有几个名额")
            result = response.json()
            self.assertEqual(result["clarifying_question"], alpha_business_rules.QUESTION_SCHOLARSHIP_CATEGORY)
            self.assertEqual([warning["code"] for warning in result["warnings"]], ["LIVE_LAB_QUOTA_UNVERIFIED"])
        self.assertEqual(self.observed, [])

    async def test_beta_s4_year_reply_keeps_historical_curriculum_intent_over_http(self):
        metadata = self.package.metadata
        metadata.title = "合成测试：2024年计算机科学与技术专业旧版培养方案"
        metadata.document_type = "培养方案"
        metadata.category_name = "培养方案与课程"
        metadata.business_direction_codes = [alpha_business_rules.RESOURCE_DIRECTION_CODE]
        metadata.source_url = "https://ccds.fzu.edu.cn/test/curriculum.htm"
        metadata.applicability_raw = {"适用年度": "2024年", "适用专业": "计算机科学与技术"}
        metadata.timeliness_verification_status = TimelinessVerificationStatus.SUPERSEDED
        self.package.chunks[0].content = "合成测试：2024年旧版培养方案规定开设离散数学与编译原理。"
        workflow = await self.workflow()
        hit = (await workflow.retriever.retrieve(RetrievalRequest(query="2024年培养方案")))[0]
        service = ConversationAgentService(workflow, InMemoryConversationStore())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(agent_service=service)),
                                     base_url="http://test") as client:
            first = (await client.post("/api/v1/ask", json={
                "query": "以前计算机科学与技术专业的旧版培养方案有哪些课程？",
            })).json()
            self.assertEqual(first["status"], "needs_clarification")
            session = first["conversation_id"]
            historical = (await client.post("/api/v1/ask", json={"query": "2024年呢？", "conversation_id": session})).json()
            current = (await client.post("/api/v1/ask", json={
                "query": "计算机科学与技术专业现在的培养方案有哪些课程？", "conversation_id": session,
            })).json()
        self.assertEqual(historical["status"], "answered")
        self.assertEqual(historical["answer_mode"], "historical")
        self.assertEqual(historical["citations"][0]["chunk_id"], str(hit.chunk_id))
        self.assertEqual(current["status"], "insufficient_evidence")
        self.assertEqual(current["citations"], [])
        self.assertEqual(len(self.observed), 1)

    async def test_beta_s4_short_registration_reply_uses_expired_lab_notice_over_http(self):
        for lab in ("EDA 实验室", "人工智能自主创新实验室", "福州大学图机器学习课题组",
                    "网络流量分析与异常检测课题组", "EDA创新实验室", "“AI+复杂工业系统”创新实验室"):
            with self.subTest(lab=lab):
                await self.assert_short_registration_reply(lab)

    async def assert_short_registration_reply(self, lab):
        self.lab_recruitment_fixture(date(2026, 10, 31), TimelinessVerificationStatus.EXPIRED, lab)
        workflow = await self.workflow()
        service = ConversationAgentService(workflow, InMemoryConversationStore())
        calls_before = len(self.observed)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(agent_service=service)),
                                     base_url="http://test") as client:
            first = (await client.post("/api/v1/ask", json={"query": f"2026年{lab}怎么报名？"})).json()
            follow_up = (await client.post("/api/v1/ask", json={
                "query": "还可以报名吗？", "conversation_id": first["conversation_id"],
            })).json()
        self.assertEqual(first["answer_mode"], "historical")
        self.assertEqual(follow_up["status"], "answered")
        self.assertEqual(follow_up["answer_mode"], "historical")
        self.assertIn("2026年10月31日截止", follow_up["answer"])
        self.assertEqual(follow_up["citations"], first["citations"])
        self.assertEqual(len(self.observed), calls_before + 1)

    async def test_beta_s4_switching_named_labs_discards_previous_lab_and_intent_over_http(self):
        first_lab = "人工智能自主创新实验室"
        second_lab = "福州大学图机器学习课题组"
        self.lab_recruitment_fixture(date(2026, 10, 31), TimelinessVerificationStatus.EXPIRED, first_lab)
        first_excerpt = self.package.chunks[0].content
        workflow = await self.workflow()
        self.lab_recruitment_fixture(date(2026, 9, 30), TimelinessVerificationStatus.EXPIRED, second_lab)
        self.package.metadata.record_code = "SYNTH-GRAPH-RECRUITMENT"
        await workflow.retriever.index_document(self.package)
        service = ConversationAgentService(workflow, InMemoryConversationStore())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(agent_service=service)),
                                     base_url="http://test") as client:
            first = (await client.post("/api/v1/ask", json={"query": f"2026年{first_lab}怎么报名？"})).json()
            self.assertEqual(first["citations"][0]["excerpt"], first_excerpt)
            session = first["conversation_id"]
            with patch.object(workflow.retriever, "retrieve", wraps=workflow.retriever.retrieve) as retrieve:
                switch = (await client.post("/api/v1/ask", json={
                    "query": f"那{second_lab}研究什么？", "conversation_id": session,
                })).json()
                self.assertEqual(retrieve.call_args.args[0].query, f"那{second_lab}研究什么？")
            follow_up = (await client.post("/api/v1/ask", json={
                "query": "还可以报名吗？", "conversation_id": session,
            })).json()
        self.assertEqual(switch["status"], "insufficient_evidence")
        self.assertEqual(switch["citations"], [])
        self.assertEqual((follow_up["status"], follow_up["answer_mode"]), ("answered", "historical"))
        self.assertIn("2026年9月30日截止", follow_up["answer"])
        self.assertEqual([citation["excerpt"] for citation in follow_up["citations"]], [self.package.chunks[0].content])
        self.assertEqual(len(self.observed), 1)

    async def test_beta_s4_lab_name_disambiguation_preserves_explicit_applicability_and_review(self):
        lab = "人工智能自主创新实验室"
        self.lab_recruitment_fixture(date(2026, 10, 31), TimelinessVerificationStatus.EXPIRED, lab)
        workflow = await self.workflow()
        scoped = await workflow.run(self.request(f"2026年{lab}是否接收人工智能专业学生？"))
        self.assertEqual(scoped.status, "insufficient_evidence")
        self.assertEqual(scoped.citations, [])

        self.package.metadata.temporal_notes["human_approved"] = False
        await workflow.retriever.index_document(self.package)
        hit = (await workflow.retriever.retrieve(RetrievalRequest(query=lab)))[0]
        self.assertIs(workflow.retriever.get_document_metadata(hit.version_id).temporal_notes["human_approved"], False)
        pending = await workflow.run(self.request("还可以报名吗？", [f"2026年{lab}怎么报名？"]))
        self.assertEqual(pending.status, "insufficient_evidence")
        self.assertEqual(pending.citations, [])
        self.assertEqual(self.observed, [])

    async def test_beta_s4_verified_team_registration_and_quota_over_http(self):
        for lab in ("福州大学超算团队", "ROIS 团队"):
            with self.subTest(lab=lab):
                self.lab_recruitment_fixture(date(2026, 10, 31), TimelinessVerificationStatus.EXPIRED, lab)
                workflow = await self.workflow()
                service = ConversationAgentService(workflow, InMemoryConversationStore())
                calls = len(self.observed)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(agent_service=service)),
                                             base_url="http://test") as client:
                    first = (await client.post("/api/v1/ask", json={"query": f"{lab}怎么报名？"})).json()
                    self.assertEqual((first["status"], first["answer_mode"]), ("answered", "historical"))
                    self.assertIn("报名已截止", first["answer"])
                    self.assertIn("请提交报名表", first["answer"])
                    self.assertEqual(first["citations"][0]["excerpt"], self.package.chunks[0].content)
                    for query, code in (("还可以报名吗？", "HISTORICAL_POLICY"),
                                        ("现在还剩几个名额？", "LIVE_LAB_QUOTA_UNVERIFIED")):
                        result = (await client.post("/api/v1/ask", json={
                            "query": query, "conversation_id": first["conversation_id"],
                        })).json()
                        self.assertEqual(result["warnings"][0]["code"], code)
                        if query.startswith("还可以"):
                            self.assertEqual((result["status"], result["answer_mode"]), ("answered", "historical"))
                            self.assertIn("2026年10月31日截止", result["answer"])
                            self.assertEqual(result["citations"], first["citations"])
                        else:
                            self.assertEqual((result["status"], result["answer_mode"]),
                                             ("insufficient_evidence", "insufficient_data"))
                            self.assertEqual(result["citations"], [])
                self.assertEqual(len(self.observed), calls + 1)

    async def test_beta_s4_verified_team_needs_matching_reviewed_recruitment_evidence(self):
        lab = "ROIS 团队"
        self.lab_recruitment_fixture(date(2026, 10, 31), TimelinessVerificationStatus.EXPIRED,
                                     "福州大学超算团队")
        workflow = await self.workflow()
        result = await workflow.run(self.request(f"{lab}怎么报名？"))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.citations, [])
        self.assertEqual(self.observed, [])

        from backend.retrieval.alpha_corpus import load_approved_alpha_retriever

        candidate_path = (ROOT / "knowledge_base/processed/alpha/pending-review"
                          / "qinghe-b8-2026-11-23/qinghe-r3.json")
        candidate = DocumentPackage.model_validate_json(candidate_path.read_bytes())
        self.assertEqual(candidate.metadata.retrieval_status, "blocked")
        self.assertIs(candidate.metadata.temporal_notes["human_approved"], False)
        # Even an accidental copy into an approved directory must stay excluded.
        candidate_dir = self.root / "pending-fixture"
        candidate_dir.mkdir()
        (candidate_dir / candidate_path.name).write_bytes(candidate_path.read_bytes())
        pending, report = await load_approved_alpha_retriever(
            file_root=self.root, corpus_dir=candidate_dir, allow_missing=False,
        )
        self.assertEqual(report.loaded_packages, ())
        self.assertEqual(await pending.retrieve(RetrievalRequest(query=lab)), [])
        source_info = "合成测试：ROIS 团队需提交报名表。"
        self.lab_recruitment_fixture(date(2026, 10, 31), TimelinessVerificationStatus.EXPIRED, lab)
        self.package.metadata.deadline_on = None
        for content, expected_deadline in (
            (source_info, None),
            (source_info + "报名截止日期为2026年10月31日。", "2026年10月31日"),
            (source_info + "请于10月31日前提交。", "10月31日"),
        ):
            with self.subTest(content=content):
                self.package.chunks[0].content = content
                workflow = await self.workflow()
                result = await workflow.run(self.request("还可以报名吗？", [f"{lab}怎么报名？"]))
                self.assertEqual((result.status, result.answer_mode), ("answered", "historical"))
                self.assertIn("截止", result.answer)
                self.assertEqual("月" in result.answer, expected_deadline is not None)
                if expected_deadline:
                    self.assertIn(expected_deadline, result.answer)
                self.assertEqual(result.citations[0].excerpt, content)

        self.package.metadata.temporal_notes["human_approved"] = False
        await workflow.retriever.index_document(self.package)
        result = await workflow.run(self.request(f"{lab}怎么报名？"))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.citations, [])
        self.assertEqual(self.observed, [])

    async def test_beta_s4_verified_team_purpose_intro_and_current_plan(self):
        lab = "ROIS 团队"
        self.lab_recruitment_fixture(date(2026, 12, 1), TimelinessVerificationStatus.CURRENT, lab)
        workflow = await self.workflow()
        intro = self.package.model_copy(deep=True)
        intro.metadata.record_code = "SYNTH-ROIS-INTRO"
        intro.metadata.title = "合成测试：ROIS 团队研究方向"
        intro.metadata.category_name = "研究方向与公开介绍"
        intro.metadata.applicability_raw = None
        intro.metadata.deadline_on = None
        intro.metadata.document_type = "研究方向与公开介绍"
        intro.chunks[0].content = "合成测试：ROIS 团队研究方向为合成示例。"
        await workflow.retriever.index_document(intro)
        result = await workflow.run(self.request(lab))
        self.assertEqual(result.clarifying_question, alpha_business_rules.QUESTION_LAB_PURPOSE)
        for query, history in ((f"{lab}研究什么？", []), ("研究什么？", [lab])):
            with self.subTest(query=query):
                result = await workflow.run(self.request(query, history))
                self.assertEqual(result.answer_mode, "current_policy")
                self.assertEqual([citation.excerpt for citation in result.citations], [intro.chunks[0].content])
                self.assertEqual([entry["content"] for entry in self.observed[-1]], [intro.chunks[0].content])
        active = await workflow.run(self.request(f"{lab}怎么报名？"))
        self.assertEqual(active.answer_mode, "procedure_reference")
        self.assertEqual([citation.excerpt for citation in active.citations], [self.package.chunks[0].content])
        for query, history in ((f"{lab}现在还剩几个名额？", []), ("现在还剩几个名额？", [f"{lab}怎么报名？"])):
            result = await workflow.run(self.request(query, history))
            self.assertEqual(result.warnings[0].code, "LIVE_LAB_QUOTA_UNVERIFIED")
            self.assertEqual(result.citations, [])
        self.assertEqual(len(self.observed), 3)

    async def test_beta_team_routing_keeps_unknown_and_competition_teams_out_of_s4(self):
        workflow = await self.workflow()
        with patch.object(workflow.retriever, "retrieve", wraps=workflow.retriever.retrieve) as retrieve:
            for query in ("陌生团队怎么报名？", "NOTROIS 团队怎么报名？", "福州大学超算团队二队怎么报名？"):
                with self.subTest(query=query):
                    result = await workflow.run(self.request(query, ["ROIS 团队怎么报名？"]))
                    self.assertEqual(result.clarifying_question, alpha_business_rules.QUESTION_TOPIC)
            for history, expected in (
                ([], alpha_business_rules.QUESTION_COMPETITION_NAME),
                (["蓝桥杯竞赛怎么报名？"], alpha_business_rules.QUESTION_LEVEL),
                (["ROIS 团队怎么报名？"], alpha_business_rules.QUESTION_COMPETITION_NAME),
            ):
                result = await workflow.run(self.request("我们竞赛团队还能报名吗？", history))
                self.assertEqual(result.clarifying_question, expected)
            result = await workflow.run(self.request("ROIS 团队参加蓝桥杯竞赛怎么报名？"))
            self.assertEqual(result.clarifying_question, alpha_business_rules.QUESTION_LEVEL)
            retrieve.assert_not_awaited()
        self.assertEqual(self.observed, [])

    async def test_clarification_and_evidence_share_injected_clock(self):
        workflow = await self.workflow()
        query = self.request("2029年推免政策是什么？")
        self.assertIsNone(workflow.clarification_rule(query))
        workflow = await create_alpha_workflow(file_root=self.root, retriever=workflow.retriever,
            llm_client=self.llm, today=lambda: date(2030, 1, 1))
        result = await workflow.run(query)
        self.assertEqual(result.status, "needs_clarification")
        self.assertEqual(result.clarifying_question, alpha_business_rules.QUESTION_RECOMMENDATION_OBJECT)
        self.assertEqual(self.observed, [])

    def recommendation_package(self):
        self.package.metadata.record_code = "SYNTH-2027-推免资格推荐"
        self.package.metadata.title = "合成测试：2027届本科推免资格推荐办法"
        self.package.metadata.applicability_raw = {
            "适用年级": "2027届应届本科毕业生；大一至大三仅升学准备参考",
            "适用专业": "计算机科学与技术、软件工程", "目标届别": "2027届",
        }
        self.package.chunks[0].content = "【合成测试，非政策】2027届推免推荐资格按本通知核对材料与排名。"

    def volunteer_scoring_package(self):
        self.recommendation_package()
        self.package.metadata.title = "合成测试：2027届本科推免资格推荐方案"
        self.package.metadata.record_code = "计算机学院-2027-推免资格推荐"
        self.package.metadata.source_url = "https://ccds.fzu.edu.cn/info/1119/11932.htm"
        self.package.metadata.deadline_on = date(2026, 9, 9)
        self.package.metadata.timeliness_verification_status = TimelinessVerificationStatus.EXPIRED
        self.package.chunks[0].content = ("合成测试：参加志愿服务按时长加原始分，0-30小时加原始分2分；"
                                          "30-60小时）加原始分4分，60-100小时及以上加原始分6分，不重复累加。")
        for content in (
            "合成测试：2027届推免综合测评总成绩含参加志愿服务成绩×0.3%。",
            "合成测试：参加志愿服务成绩=（基础分 60+被推荐学生参加志愿服务成绩）/（基础分\n"
            "60+本专业推免入围学生参加志愿服务成绩最高值）× 100。",
            "合成测试：2027届推免推荐资格须提交资格申请表。",
        ):
            self.package.chunks.append(self.package.chunks[0].model_copy(update={
                "chunk_no": len(self.package.chunks) + 1, "content": content,
            }))

    async def test_beta_volunteer_scoring_concepts_use_distinct_citations(self):
        self.volunteer_scoring_package()
        workflow = await self.workflow()
        raw, weight, formula, _ = [chunk.content for chunk in self.package.chunks]
        for hours, score in ((0, 2), (1, 2), (29, 2), (29.5, 2), (30, 4), (31, 4), (59, 4),
                             (59.5, 4), (60, 6), (60.5, 6), (61, 6), (100, 6), (200, 6)):
            with self.subTest(hours=hours):
                result = await workflow.run(self.request(f"2027届推免志愿服务{hours}小时算多少分？"))
                self.assertEqual((result.status, result.answer_mode), ("answered", "historical"))
                self.assertIn(f"{hours} 小时的原始分为 {score} 分", result.answer)
                self.assertIn("组长确认的项目解释口径", result.answer)
                self.assertNotIn("0.3%", result.answer)
                self.assertEqual([citation.excerpt for citation in result.citations], [raw])
        result = await workflow.run(self.request("2027届推免志愿服务在综合测评总成绩占比多少？"))
        self.assertIn("换算为百分制后的志愿服务成绩", result.answer)
        self.assertIn("0.3%", result.answer)
        self.assertEqual([citation.excerpt for citation in result.citations], [weight])
        result = await workflow.run(self.request("2027届推免志愿服务怎么用个人原始分和专业最高原始分换算百分制成绩？"))
        self.assertIn("（60 + 个人志愿服务原始分）", result.answer)
        self.assertIn("（60 + 本专业推免入围学生的志愿服务最高原始分）× 100", result.answer)
        self.assertNotIn("0.3%", result.answer)
        self.assertEqual([citation.excerpt for citation in result.citations], [formula])
        result = await workflow.run(self.request("2027届推免志愿服务60小时的原始分、百分制成绩和总评权重分别是多少？"))
        self.assertIn("60 小时的原始分为 6 分", result.answer)
        self.assertIn("百分制成绩 =", result.answer)
        self.assertIn("0.3%", result.answer)
        self.assertEqual([citation.excerpt for citation in result.citations], [raw, formula, weight])
        self.assertEqual(self.observed, [])

    async def test_beta_volunteer_scoring_followups_over_http_keep_cohort_and_latest_hours(self):
        self.volunteer_scoring_package()
        workflow = await self.workflow()
        service = ConversationAgentService(workflow, InMemoryConversationStore())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(agent_service=service)),
                                     base_url="http://test") as client:
            first = (await client.post("/api/v1/ask", json={"query": "推免志愿服务原始分怎么计分？"})).json()
            self.assertEqual(first["clarifying_question"], alpha_business_rules.QUESTION_VOLUNTEER_COHORT)
            session = first["conversation_id"]
            for query, expected in (("2027届", "0 ≤ h < 30 计 2 分"),
                                    ("那30小时呢", "30 小时的原始分为 4 分"),
                                    ("那60小时呢", "60 小时的原始分为 6 分")):
                with self.subTest(query=query):
                    response = await client.post("/api/v1/ask", json={"query": query, "conversation_id": session})
                    self.assertEqual(response.status_code, 200)
                    result = response.json()
                    self.assertEqual((result["status"], result["answer_mode"]), ("answered", "historical"))
                    self.assertIn(expected, result["answer"])
                    self.assertEqual([citation["excerpt"] for citation in result["citations"]],
                                     [self.package.chunks[0].content])
            for query in ("那30到60小时呢", "那不到30小时呢", "那30小时以上呢", "那30小时以内呢", "那30小时左右呢"):
                origin = (await client.post("/api/v1/ask", json={"query": "2027届推免志愿服务原始分怎么算？"})).json()
                follow_up = {"query": query, "conversation_id": origin["conversation_id"]}
                with patch.object(workflow.retriever, "retrieve", wraps=workflow.retriever.retrieve) as retrieve:
                    response = await client.post("/api/v1/ask", json=follow_up)
                    self.assertEqual(response.status_code, 200)
                    result = response.json()
                    self.assertEqual(result["status"], "needs_clarification")
                    self.assertEqual(result["clarifying_question"], alpha_business_rules.QUESTION_VOLUNTEER_HOURS)
                    self.assertEqual(result["citations"], [])
                    retrieve.assert_not_awaited()
                corrected = (await client.post("/api/v1/ask", json={**follow_up, "query": "29.5小时"})).json()
                self.assertIn("29.5 小时的原始分为 2 分", corrected["answer"])
            isolated = (await client.post("/api/v1/ask", json={"query": "那30小时呢"})).json()
            self.assertEqual(isolated["status"], "needs_clarification")
        self.assertEqual(self.observed, [])

    async def test_beta_volunteer_scoring_clarifies_concept_and_keeps_the_user_choice_over_http(self):
        self.volunteer_scoring_package()
        workflow = await self.workflow()
        service = ConversationAgentService(workflow, InMemoryConversationStore())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(agent_service=service)),
                                     base_url="http://test") as client:
            with patch.object(workflow.retriever, "retrieve", wraps=workflow.retriever.retrieve) as retrieve:
                first = (await client.post("/api/v1/ask", json={"query": "推免志愿服务成绩怎么算？"})).json()
                self.assertEqual(first["clarifying_question"], alpha_business_rules.QUESTION_VOLUNTEER_SCORE_KIND)
                session = first["conversation_id"]
                selected = (await client.post("/api/v1/ask", json={"query": "百分制成绩", "conversation_id": session})).json()
                self.assertEqual(selected["clarifying_question"], alpha_business_rules.QUESTION_VOLUNTEER_COHORT)
                retrieve.assert_not_awaited()
            for query in ("2027届", "那30小时呢"):
                result = (await client.post("/api/v1/ask", json={"query": query, "conversation_id": session})).json()
                self.assertIn("百分制成绩 =", result["answer"])
                self.assertEqual([citation["excerpt"] for citation in result["citations"]], [self.package.chunks[2].content])
        self.assertEqual(self.observed, [])

    async def test_beta_volunteer_scoring_requires_source_and_requested_terms(self):
        self.volunteer_scoring_package()
        self.package.chunks = self.package.chunks[:1]
        approved = await self.workflow()
        raw_query = "2027届推免志愿服务29小时的原始分是多少？"
        result = await approved.run(self.request(raw_query))
        self.assertEqual(result.status, "answered")
        for query in ("2027届推免志愿服务29小时的原始分和总评权重分别是多少？",
                      "2027届推免志愿服务的百分制成绩怎么换算？"):
            result = await approved.run(self.request(query))
            self.assertEqual(result.status, "insufficient_evidence")
            self.assertEqual(result.citations, [])
        self.package.metadata.source_url = "https://ccds.fzu.edu.cn/test/unrelated.htm"
        unrelated = await self.workflow()
        result = await unrelated.run(self.request(raw_query))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.citations, [])
        self.assertEqual(self.observed, [])

    async def test_beta_volunteer_scoring_respects_evidence_and_non_scoring_questions(self):
        self.volunteer_scoring_package()
        approved = await self.workflow()
        for question in ("2028届推免志愿服务30小时算多少分？", "最新推免志愿服务30小时算多少分？"):
            result = await approved.run(self.request(question))
            self.assertEqual(result.status, "insufficient_evidence")
            self.assertEqual(result.citations, [])
        switched = await approved.run(self.request("那30小时呢", ["2027届推免志愿服务计分？", "奖学金有哪些？"]))
        self.assertEqual(switched.status, "needs_clarification")
        self.assertEqual(self.observed, [])

        # Unrelated requests still use the standard constrained generation path.
        for question in ("2027届推免推荐资格申请流程是什么？", "2027届推免推荐资格要提交什么材料？"):
            before = len(self.observed)
            result = await approved.run(self.request(question, ["2027届志愿服务30小时加几分？"]))
            self.assertEqual(result.status, "answered")
            self.assertEqual(len(self.observed), before + 1)
            self.assertNotIn("项目解释口径", result.answer)

        source = (ROOT / "knowledge_base/processed/alpha/pending-review/beta-2026-11-23/recommendation.json")
        candidate = DocumentPackage.model_validate_json(source.read_bytes())
        self.assertEqual(candidate.metadata.retrieval_status, "blocked")
        self.assertIs(candidate.metadata.temporal_notes["human_approved"], False)
        # Verify the original PDF extracts are recognized without enabling the candidate.
        query = self.request("2027届推免志愿服务原始分、百分制成绩和总评权重怎么算？")
        scoring = alpha_business_rules.volunteer_scoring_request(query)
        hits = await approved.retriever.retrieve(RetrievalRequest(query=query.query))
        matched = [
            kinds for parsed in candidate.chunks
            if (kinds := alpha_business_rules.volunteer_scoring_evidence(
                candidate.metadata.record_code, hits[0].model_copy(update={"content": parsed.content}), scoring,
            ))
        ]
        self.assertCountEqual(matched, [
            {alpha_business_rules.VolunteerScoreKind.RAW},
            {alpha_business_rules.VolunteerScoreKind.PERCENT, alpha_business_rules.VolunteerScoreKind.WEIGHT},
        ])
        # Fixture files stay in the temporary test corpus.
        from backend.retrieval.alpha_corpus import load_approved_alpha_retriever
        pending_dir = self.root / "blocked-fixture"
        pending_dir.mkdir()
        (pending_dir / source.name).write_bytes(source.read_bytes())
        retriever, report = await load_approved_alpha_retriever(corpus_dir=pending_dir, file_root=self.root)
        self.assertEqual(report.loaded_packages, ())
        blocked = await create_alpha_workflow(file_root=self.root, retriever=retriever, llm_client=self.llm,
                                              today=lambda: date(2026, 11, 20))
        calls = len(self.observed)
        result = await blocked.run(self.request("2027届推免志愿服务30小时算多少分？"))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.citations, [])
        self.assertEqual(len(self.observed), calls)

    async def test_formal_eligibility_overrides_preparation_wording_before_qwen(self):
        self.recommendation_package()
        workflow = await self.workflow()
        query = "我是大二，想提前准备2027届推免推荐资格排名，现在能做什么？"
        with patch.object(workflow.retriever, "retrieve", wraps=workflow.retriever.retrieve) as retrieve:
            result = await workflow.run(self.request(query))
        retrieve.assert_awaited_once()
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.citations, [])
        self.assertEqual(self.observed, [])
        # A pure preparation question remains usable under the owner's rules.
        result = await workflow.run(self.request("我是大二，2027届推免要提前准备什么？"))
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.citations[0].excerpt, self.package.chunks[0].content)

    async def test_external_college_without_scope_field_is_filtered_before_qwen(self):
        self.recommendation_package()
        self.assertNotIn("适用学院", self.package.metadata.applicability_raw)
        workflow = await self.workflow()
        with patch.object(workflow.retriever, "retrieve", wraps=workflow.retriever.retrieve) as retrieve:
            result = await workflow.run(self.request("数学与统计学院的2027届推免推荐资格怎么排名？"))
        retrieve.assert_awaited_once()
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.citations, [])
        self.assertEqual(self.observed, [])
        # The fixture really is retrievable/applicable for the supported query.
        result = await workflow.run(self.request("2027届推免推荐资格怎么排名？"))
        self.assertEqual(result.status, "answered")

    async def test_no_current_work_cannot_inherit_history_rank_or_reach_retriever(self):
        workflow = await self.workflow()
        history = ["数学建模竞赛国家级二等奖，团队作品，作品《交通预测》，我是第二完成人"]
        query = ("数学建模竞赛校级最高等级奖，团队作品，综测能加几分？"
                 "成果是上一学期取得的，以福州大学为第一署名单位。")
        with patch.object(workflow.retriever, "retrieve", wraps=workflow.retriever.retrieve) as retrieve:
            result = await workflow.run(self.request(query, history))
        self.assertEqual(result.status, "needs_clarification")
        self.assertEqual(result.clarifying_question, alpha_business_rules.QUESTION_ORDER)
        self.assertEqual(result.citations, [])
        retrieve.assert_not_called()
        self.assertEqual(self.observed, [])



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
        self.assertTrue(all(isinstance(p.metadata.temporal_notes, dict)
            and p.metadata.temporal_notes.get("human_approved") is True for p in packages))
        approved = ROOT / "knowledge_base/processed/alpha/approved"
        self.assertTrue(all((ROOT / path).resolve().is_relative_to(approved.resolve()) for path in paths))
        workflow = await create_alpha_workflow(file_root=ROOT, corpus_dir=approved)
        query = os.environ["ALPHA_ACCEPTANCE_QUERY"]
        app = create_app(agent_service=workflow, llm_client=workflow.llm_client)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://acceptance") as client:
            response = await client.post("/api/v1/ask", json={"query": query})
        self.assertEqual(response.status_code, 200)
        from backend.contracts.models import AskResponse
        result = AskResponse.model_validate(response.json())
        self.assertEqual(result.status, "answered")
        self.assertEqual(response.headers["x-request-id"], str(result.request_id))
        hits = {c.chunk_id: c for c in await workflow.retriever.retrieve(RetrievalRequest(query=query))}
        self.assertTrue(result.citations)
        for citation in result.citations:
            self.assertIn(citation.chunk_id, hits)
            self.assertEqual(citation.excerpt, hits[citation.chunk_id].content)
            self.assertEqual(citation.source_url, hits[citation.chunk_id].source_url)


if __name__ == "__main__":
    unittest.main()
