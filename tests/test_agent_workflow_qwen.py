"""Existing Qwen adapter + workflow + HTTP integration, mock transport only."""
import asyncio
import json
import os
import importlib.util
import sys
import types
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
    AgentRequest, DocumentPackage, FileProcessingStatus, RetrievalRequest,
    TimelinessVerificationStatus,
)
from backend.retrieval.local import LocalBM25Retriever
from backend.services.agent_workflow import AgentWorkflow, create_alpha_workflow
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

    def test_invalid_provider_envelope_is_502_with_cors_and_request_id(self):
        for payload in [None, [], {}, {"choices": []},
                        {"choices": [{"message": {"content": " "}}]}]:
            with self.subTest(payload=payload):
                app, upstream = self.app(lambda request: httpx.Response(200, json=payload))
                with TestClient(app) as client:
                    response = client.post("/api/v1/ask", json={"query": "选课有哪些步骤？"},
                                           headers={"Origin": "http://localhost:5173"})
                    body = response.json()
                    self.assertEqual(response.status_code, 502)
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

    async def test_legacy_package_snapshot_is_read_only_and_metadata_is_detached(self):
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
        metadata = workflow.retriever.get_document_metadata(hits[0].version_id)
        metadata.temporal_notes["human_approved"] = False
        self.assertIs(workflow.retriever.get_document_metadata(hits[0].version_id).temporal_notes["human_approved"], True)
        self.assertFalse(hasattr(workflow.retriever, "index_document"))

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
                "choices": [{"message": {"content": json.dumps({"evidence": [{
                    "chunk_id": evidence["chunk_id"], "quote": evidence["content"],
                }]})}}]})

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
        client.generate.return_value = LLMResult(model="offline", content=json.dumps({
            "evidence": [{"chunk_id": str(demo_chunk().chunk_id), "quote": "篡改原文"}]}))
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


@unittest.skipUnless(os.getenv("ALPHA_UPSTREAM_SNAPSHOT"),
                     "Run scripts.verify_alpha_upstream_integration for PR #35/#36 integration")
class UpstreamRulesRetrieverIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Unmodified PR #35/#36 implementations, synthetic corpus, mock Qwen HTTP.
    The runner extracts reviewed Git blobs without merging upstream branches.
    """

    async def asyncSetUp(self):
        snapshot = Path(os.environ["ALPHA_UPSTREAM_SNAPSHOT"])
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.modules = patch.dict(sys.modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        namespace = types.ModuleType("_alpha_upstream_retrieval")
        namespace.__path__ = [str(snapshot / "retrieval")]
        sys.modules[namespace.__name__] = namespace

        def load(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module

        local = load("_alpha_upstream_retrieval.local", snapshot / "retrieval/local.py")
        self.loader = load("_alpha_upstream_retrieval.alpha_corpus", snapshot / "retrieval/alpha_corpus.py")
        self.rules = load("backend.services.alpha_business_rules", snapshot / "alpha_business_rules.py")
        self.local_class = local.LocalBM25Retriever
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
                "evidence": [{"chunk_id": evidence[0]["chunk_id"], "quote": evidence[0]["content"]}],
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
        with patch.dict(sys.modules, {"backend.retrieval.alpha_corpus": self.loader}):
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
        self.assertEqual(result.clarifying_question, self.rules.QUESTION_SCHOLARSHIP_CATEGORY)
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
                workflow.evidence_check = self.rules.build_from_retriever(workflow.retriever)
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
                    workflow.evidence_check = self.rules.build_from_retriever(
                        workflow.retriever, today=lambda: date(2026, 11, 19))
                    result = await workflow.run(self.request(query))
                self.assertEqual(result.status, "insufficient_evidence")
                self.assertEqual(result.answer_mode, "insufficient_data")
                self.assertEqual(result.warnings[0].code, "NO_ELIGIBLE_EVIDENCE")
                self.assertEqual(result.citations, [])
                self.assertNotIn("private-chapter-query-detail", result.model_dump_json())
        self.assertEqual(self.observed, [])

    async def test_non_sensitive_document_can_answer_without_chapter_metadata(self):
        workflow = await self.workflow()
        with patch.object(workflow.retriever, "get_parsed_chunk", return_value=None):
            workflow.evidence_check = self.rules.build_from_retriever(workflow.retriever)
            result = await workflow.run(self.request())
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.citations[0].excerpt, self.package.chunks[0].content)
        self.assertEqual(len(self.observed), 1)

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
                retriever, report = await self.loader.load_approved_alpha_retriever(
                    corpus_dir=approved, file_root=self.root, allow_missing=False)
                self.assertEqual(report.loaded_packages, ())
                self.assertEqual(report.total_indexed_chunks, 0)
                self.assertTrue(report.skipped_packages)
                with self.assertRaises(ServiceError):
                    await self.workflow()
                # Bypass the loader on purpose: Agent's own approval gate must
                # still reject enabled hits even with a permissive business rule.
                store = self.local_class(file_root=self.root)
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
                    with patch.dict(sys.modules, {"backend.retrieval.alpha_corpus": self.loader}):
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
                self.assertEqual(result.clarifying_question, self.rules.QUESTION_TOP_EIGHT)
                retrieve.assert_not_called()
        self.assertEqual(self.observed, [])
        same = "数学建模竞赛国家级二等奖，团队作品，作品《交通预测》，创新学分能认定多少？"
        result = await workflow.run(self.request(same, history))
        self.assertEqual(result.status, "answered")
        self.assertEqual(len(self.observed), 1)

    async def test_historical_rule_applicability_cannot_relax_agent_current_gate(self):
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
        historical = self.request("星火奖学金去年截止到什么时候？")
        current = self.request("星火奖学金现在还能申请吗，有什么资格要求？")
        self.assertIs(workflow.evidence_check(historical, hits[0]), True)
        self.assertIs(workflow.evidence_check(current, hits[0]), False)
        for request in (historical, current):
            result = await workflow.run(request)
            self.assertEqual(result.status, "insufficient_evidence")
            self.assertEqual(result.citations, [])
        self.assertEqual(self.observed, [])

    async def test_clarification_and_evidence_share_injected_clock(self):
        workflow = await self.workflow()
        query = self.request("2029年推免政策是什么？")
        self.assertIsNone(workflow.clarification_rule(query))
        workflow = await create_alpha_workflow(file_root=self.root, retriever=workflow.retriever,
            llm_client=self.llm, today=lambda: date(2030, 1, 1))
        result = await workflow.run(query)
        self.assertEqual(result.status, "needs_clarification")
        self.assertEqual(result.clarifying_question, self.rules.QUESTION_RECOMMENDATION_OBJECT)
        self.assertEqual(self.observed, [])

    async def test_merged_retriever_matches_latest_upstream_without_replacement(self):
        # Actual imported main implementation, not the temporary PR module.
        self.assertEqual((ROOT / "backend/retrieval/local.py").read_bytes().replace(b"\r\n", b"\n"),
            (Path(os.environ["ALPHA_UPSTREAM_SNAPSHOT"]) / "retrieval/local.py").read_bytes().replace(b"\r\n", b"\n"))
        from backend.retrieval.alpha_corpus import load_approved_alpha_retriever
        directory = self.root / "merged-approved"
        directory.mkdir()
        (directory / "policy.json").write_text(self.package.model_dump_json(), encoding="utf-8")
        store, report = await load_approved_alpha_retriever(corpus_dir=directory,
            file_root=self.root, allow_missing=False)
        self.assertTrue(report.loaded_packages)
        workflow = await create_alpha_workflow(file_root=self.root, retriever=store, llm_client=self.llm)
        self.assertEqual((await workflow.run(self.request())).status, "answered")


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
