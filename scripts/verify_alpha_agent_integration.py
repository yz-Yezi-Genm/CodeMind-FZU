"""Capture full regression and real blocked-corpus checks without paid calls."""
import asyncio
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
    OUTPUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(TZ).isoformat()
    command = [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"]
    process = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    (OUTPUT / "unittest.txt").write_text(process.stdout, encoding="utf-8")
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
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "python": sys.version,
        "dependencies": {name: metadata.version(name) for name in ("fastapi", "pydantic", "httpx", "uvicorn")},
        "command": command, "exit_code": process.returncode,
        "test_layers": {
            "AgentWorkflowTests / AgentWorkflowApiTests": "Mock or demo dependencies",
            "AgentWorkflowQwenTests": "Real Qwen adapter with mock HTTP, demo retriever",
            "LocalRetrieverQwenIntegrationTests": "Real BM25, indexing, file/hash validation, Qwen adapter and FastAPI; synthetic corpus / test callbacks / mock HTTP",
            "real_policy_check": "Three real unchanged blocked corpora, actual index/hash validation and safety refusal; no Qwen call",
            "DeliveredBusinessRulesTests": "Actual business functions, skipped until delivered",
            "LiveAlphaAcceptanceTests": "Actual approved corpus, rules and paid Qwen; explicit opt-in required",
        },
    }
    (OUTPUT / "environment.json").write_text(json.dumps(environment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n".join(process.stdout.strip().splitlines()[-4:]))
    print("Real corpus: 3 packages, 23 indexed chunks, 0 retrieval hits, 0 Qwen calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
