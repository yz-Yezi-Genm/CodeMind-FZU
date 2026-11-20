"""Capture full regression and real blocked-corpus checks without paid calls."""
import asyncio
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from importlib import metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import httpx

from backend.contracts.models import AgentRequest, DocumentPackage, IndexingStatus, RetrievalRequest
from backend.retrieval.local import LocalBM25Retriever
from backend.services.agent_workflow import AgentWorkflow
from backend.services.qwen_client import QwenLLMClient, QwenSettings
from scripts.verify_alpha_upstream_integration import agent_source_state, upstream_snapshot

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/assignment-03/alpha/evidence/agent-integration"
TZ = timezone(timedelta(hours=8))


async def real_policy_check():
    store = LocalBM25Retriever(file_root=ROOT)
    cases = (
        ("competition-recognition-2026", "竞赛创新学分认定条件"),
        ("scholarship-2026", "2026年校级奖学金申请条件"),
        ("recommendation-eligibility-2027", "2027年推免复试条件"),
    )
    indexed_cases = []
    for stem, query in cases:
        path = ROOT / "knowledge_base/processed/alpha" / (stem + ".json")
        raw = path.read_bytes()
        package = DocumentPackage.model_validate_json(raw)
        indexed = await store.index_document(package)
        assert indexed.status == IndexingStatus.INDEXED, indexed.warnings
        assert package.metadata.retrieval_status == "blocked"
        indexed_cases.append({
            "path": path.relative_to(ROOT).as_posix(), "sha256": sha256(raw).hexdigest(),
            "record_code": package.metadata.record_code,
            "source_url": package.metadata.source_url,
            "source_verification_status": package.metadata.source_verification_status,
            "timeliness_verification_status": package.metadata.timeliness_verification_status,
            "retrieval_status": package.metadata.retrieval_status,
            "query": query, "index": indexed.model_dump(mode="json"),
        })

    calls = []

    def unexpected_qwen(request):
        calls.append(str(request.url))
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_qwen)) as upstream:
        llm = QwenLLMClient(QwenSettings(api_key="offline-fixture-not-a-real-key", max_retries=0),
                            http_client=upstream)
        workflow = AgentWorkflow(store, llm, clarification_rule=lambda _: None,
                                 evidence_check=lambda *_: True)
        for case in indexed_cases:
            hits = await store.retrieve(RetrievalRequest(query=case["query"]))
            result = await workflow.run(AgentRequest(
                request_id=uuid4(), conversation_id=uuid4(), query=case["query"],
            ))
            assert hits == []
            assert result.status == "insufficient_evidence"
            assert result.citations == []
            assert result.warnings[0].code == "NO_ELIGIBLE_EVIDENCE"
            case["retrieval_hits"] = len(hits)
            case["agent_result"] = result.model_dump(mode="json")
    assert not calls, "Blocked policy reached Qwen"
    return {
        "dataset": "real_packages_unchanged_blocked",
        "business_rules": "Explicit permissive test callbacks to exercise the retrieval gate; not delivered production rules",
        "retriever": "backend.retrieval.local.LocalBM25Retriever with file_root and SHA-256 checks",
        "model": "Real QwenLLMClient adapter, offline MockTransport, expected zero calls",
        "qwen_calls": len(calls), "cases": indexed_cases,
        "acceptance": "Safety refusal only; approved-policy answer and paid Qwen acceptance remain pending",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-record", action="store_true",
                        help="Read-only: verify current/committed sources and upstream refs match the saved test record")
    args = parser.parse_args()
    if args.check_record:
        recorded = json.loads((OUTPUT / "environment.json").read_text(encoding="utf-8"))
        current = agent_source_state()
        if recorded["agent_source_state"]["source_sha256_lf"] != current["source_sha256_lf"]:
            print("FAIL: sources differ from the executed regression; rerun verification")
            return 1
        if not all(item["in_HEAD"] or item["in_pending_merge"]
                   for item in current["required_merged_history"].values()):
            print("FAIL: required main/#31/#35 history is not included")
            return 1
        if current["pending_merge_parent"] is None:
            for name, expected in current["source_sha256_lf"].items():
                committed = subprocess.run(["git", "show", "HEAD:" + name], cwd=ROOT, capture_output=True)
                if committed.returncode or sha256(committed.stdout.replace(b"\r\n", b"\n")).hexdigest() != expected:
                    print("FAIL: tested source is not included in final HEAD: " + name)
                    return 1
        for source in recorded["upstream_sources"]:
            commit = subprocess.check_output(["git", "rev-parse", source["ref"]], cwd=ROOT, text=True).strip()
            if commit != source["commit"]:
                print("FAIL: upstream ref changed; fetch and rerun verification")
                return 1
        print("PASS: tested source contents, required merged history and upstream commits match; current HEAD=" + current["base_commit"])
        return 0
    OUTPUT.mkdir(parents=True, exist_ok=True)
    agent = agent_source_state()
    started = datetime.now(TZ).isoformat()
    # Include #31's scope-local backend processing/privacy regressions, which
    # unittest discover -s tests alone would not collect.
    suite_code = (
        "import sys,unittest; "
        "suite=unittest.defaultTestLoader.discover('tests'); "
        "suite.addTests(unittest.defaultTestLoader.loadTestsFromNames("
        "['knowledge_base.processing.test_policy_review','knowledge_base.processing.test_policy_forms_privacy'])); "
        "result=unittest.TextTestRunner(verbosity=2).run(suite); "
        "sys.exit(0 if result.wasSuccessful() else 1)"
    )
    command = [sys.executable, "-X", "utf8", "-c", suite_code]
    with upstream_snapshot() as (snapshot, upstream_sources):
        process = subprocess.run(command, cwd=ROOT,
            env=dict(os.environ, PYTHONIOENCODING="utf-8", ALPHA_UPSTREAM_SNAPSHOT=snapshot),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    (OUTPUT / "unittest.txt").write_text(process.stdout, encoding="utf-8")
    if agent["source_sha256_lf"] != agent_source_state()["source_sha256_lf"]:
        raise RuntimeError("Agent sources changed during tests")
    if process.returncode:
        print(process.stdout)
        return process.returncode
    report = asyncio.run(real_policy_check())
    (OUTPUT / "real-policy-check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    environment = {
        "started_at_asia_shanghai": started,
        "finished_at_asia_shanghai": datetime.now(TZ).isoformat(),
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "agent_source_state": agent,
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "python": sys.version,
        "dependencies": {name: metadata.version(name) for name in ("fastapi", "pydantic", "httpx", "uvicorn")},
        "command": command, "exit_code": process.returncode,
        "test_layers": {
            "AgentWorkflowTests / AgentWorkflowApiTests": "Mock or demo dependencies",
            "AgentWorkflowQwenTests": "Real Qwen adapter with mock HTTP, demo retriever",
            "LocalRetrieverQwenIntegrationTests": "Real BM25, indexing, file/hash validation, Qwen adapter and FastAPI; synthetic corpus / test callbacks / mock HTTP",
            "real_policy_check": "Three real unchanged blocked corpora, actual index/hash validation and safety refusal; no Qwen call",
            "DeliveredBusinessRulesTests": "Direct import skipped while upstream module is absent from this checkout; actual delivered rules run in snapshot integration tests",
            "LiveAlphaAcceptanceTests": "Actual approved corpus, rules and paid Qwen; explicit opt-in required",
            "UpstreamRulesRetrieverIntegrationTests": "Unmodified PR #35/#36 Git snapshots, actual rules/loader/BM25, synthetic corpus and mock Qwen HTTP",
            "QwenLiveProbeOfflineTests": "Live-probe opt-in guard, synthetic prompt and production citation verifier using mock transport only",
        },
        "upstream_sources": upstream_sources,
        "qwen_handoff_checks": [
            "Startup script reads explicit packages and injects the same workflow/model into FastAPI",
            "401/403, 408, 429 and 5xx preserve backend status, request ID and CORS headers",
            "Malformed/empty provider envelope is HTTP 502; invalid evidence selection is a business refusal",
            "Read timeout and connection failures map to 504/503 without provider detail leakage",
            "Outer workflow timeout cancels the real adapter request",
            "Mixed transport and HTTP failures share the adapter retry budget",
            "Recommended 28-second/no-retry environment reaches the real Qwen adapter; workflow keeps 30-second outer wait",
        ],
    }
    (OUTPUT / "environment.json").write_text(json.dumps(environment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n".join(process.stdout.strip().splitlines()[-4:]))
    print("Real corpus: 3 packages, 23 indexed chunks, 0 retrieval hits, 0 Qwen calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
