"""Run the final Beta Qwen -> AgentWorkflow -> POST /api/v1/ask integration."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import socket
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
import httpx
import uvicorn

from backend.app.alpha import create_alpha_app
from backend.app.config import AppSettings
from backend.contracts.models import LLMGenerateRequest, LLMResult, RetrievalRequest
from backend.services.alpha_runtime import build_alpha_retriever, build_alpha_runtime
from backend.services.qwen_client import create_qwen_client_from_env


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_CORPUS = ROOT / "tests/fixtures/beta_live_approved"
FORMAL_CORPUS = ROOT / "knowledge_base/processed/alpha/approved"
POSITIVE_QUERY = "2026年优秀学生综合奖学金申请需要提交什么材料？"
REFUSAL_QUERY = "2026年优秀学生综合奖学金金额是多少？"


class RecordingLLM:
    """Delegate to the real adapter while retaining safe diagnostic metadata."""

    def __init__(self) -> None:
        self.client = create_qwen_client_from_env()
        self.last_result: LLMResult | None = None

    async def generate(self, request: LLMGenerateRequest) -> LLMResult:
        self.last_result = await self.client.generate(request)
        return self.last_result

    async def aclose(self) -> None:
        await self.client.aclose()


def _runtime_builder(settings: AppSettings, llm_client=None):
    async def build():
        return await build_alpha_runtime(
            settings,
            file_root=ROOT,
            llm_client=llm_client,
        )

    return build


async def _inspect_synthetic_corpus(settings: AppSettings, query: str) -> dict:
    retriever, report = await build_alpha_retriever(settings, file_root=ROOT)
    hits = await retriever.retrieve(RetrievalRequest(query=query))
    return {
        "loaded_packages": len(report.loaded_packages),
        "skipped_packages": list(report.skipped_packages),
        "indexed_chunks": report.total_indexed_chunks,
        "hit_count": len(hits),
        "hit_excerpts": [hit.content for hit in hits],
    }


@contextmanager
def _serve(app):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [sock]},
        daemon=True,
        name="beta-qwen-e2e-server",
    )
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        raise RuntimeError("uvicorn did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("uvicorn did not stop")


def _post(client: httpx.Client, query: str) -> tuple[int, dict, dict[str, str]]:
    response = client.post("/api/v1/ask", json={"query": query})
    return response.status_code, response.json(), dict(response.headers)


def main() -> int:
    env_path = ROOT / "backend/.env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    if not os.getenv("QWEN_API_KEY"):
        raise RuntimeError("QWEN_API_KEY is not configured")

    settings = AppSettings(alpha_package_dir=SYNTHETIC_CORPUS)
    llm = RecordingLLM()
    retrieval_diagnostic = asyncio.run(
        _inspect_synthetic_corpus(settings, POSITIVE_QUERY)
    )
    synthetic_app = create_alpha_app(
        settings=settings,
        runtime_builder=_runtime_builder(settings, llm),
    )
    started = time.monotonic()
    with _serve(synthetic_app) as base_url:
        with httpx.Client(base_url=base_url, timeout=60) as client:
            positive_status, positive_body, positive_headers = _post(
                client,
                POSITIVE_QUERY,
            )
            refusal_status, refusal_body, refusal_headers = _post(
                client,
                REFUSAL_QUERY,
            )
    elapsed_ms = round((time.monotonic() - started) * 1000)

    if positive_status != 200:
        raise RuntimeError(f"Synthetic live request returned HTTP {positive_status}")
    if positive_body.get("status") != "answered":
        raise RuntimeError(
            "Synthetic live request did not answer: "
            + json.dumps(
                {
                    "status": positive_body.get("status"),
                    "answer": positive_body.get("answer"),
                    "answer_mode": positive_body.get("answer_mode"),
                    "clarifying_question": positive_body.get("clarifying_question"),
                    "warnings": positive_body.get("warnings"),
                    "error": positive_body.get("error"),
                    "raw_model_content": (
                        llm.last_result.content
                        if llm.last_result is not None
                        else None
                    ),
                    "retrieval_diagnostic": retrieval_diagnostic,
                },
                ensure_ascii=False,
            )
        )
    citations = positive_body.get("citations")
    if not isinstance(citations, list) or not citations:
        raise RuntimeError("Synthetic live request returned no citation")
    if any(
        not isinstance(citation, dict)
        or not citation.get("chunk_id")
        or not citation.get("excerpt")
        or not citation.get("source_url")
        for citation in citations
    ):
        raise RuntimeError("Citation fields are incomplete")

    if refusal_status != 200 or refusal_body.get("status") != "insufficient_evidence":
        raise RuntimeError("Missing-fact request did not fail closed")
    if refusal_body.get("citations"):
        raise RuntimeError("Insufficient-evidence response contains citations")

    formal_settings = AppSettings(alpha_package_dir=FORMAL_CORPUS)
    formal_app = create_alpha_app(
        settings=formal_settings,
        runtime_builder=_runtime_builder(formal_settings),
    )
    with _serve(formal_app) as base_url:
        with httpx.Client(base_url=base_url, timeout=60) as client:
            formal_status, formal_body, formal_headers = _post(
                client,
                POSITIVE_QUERY,
            )
    if formal_status != 503:
        raise RuntimeError(f"Unreleased formal corpus returned HTTP {formal_status}")
    if formal_body.get("error", {}).get("code") != "KNOWLEDGE_BASE_UNAVAILABLE":
        raise RuntimeError("Unreleased formal corpus returned the wrong error code")

    print(
        json.dumps(
            {
                "time_asia_shanghai": datetime.now(
                    timezone(timedelta(hours=8))
                ).isoformat(),
                "scope": (
                    "Real Qwen HTTP -> current AgentWorkflow -> FastAPI; "
                    "synthetic example.invalid corpus only"
                ),
                "model": os.getenv("QWEN_MODEL", "qwen-flash"),
                "synthetic": {
                    "query": POSITIVE_QUERY,
                    "http_status": positive_status,
                    "request_id": positive_body.get("request_id"),
                    "transport": "uvicorn TCP HTTP",
                    "x_request_id": positive_headers.get("x-request-id"),
                    "status": positive_body.get("status"),
                    "answer": positive_body.get("answer"),
                    "answer_mode": positive_body.get("answer_mode"),
                    "citations": citations,
                    "warnings": positive_body.get("warnings"),
                    "elapsed_ms": elapsed_ms,
                    "retrieval": retrieval_diagnostic,
                    "model_response": {
                        "model": (
                            llm.last_result.model
                            if llm.last_result is not None
                            else None
                        ),
                        "usage": (
                            llm.last_result.usage
                            if llm.last_result is not None
                            else None
                        ),
                        "raw_content": (
                            llm.last_result.content
                            if llm.last_result is not None
                            else None
                        ),
                    },
                },
                "synthetic_insufficient_evidence": {
                    "query": REFUSAL_QUERY,
                    "http_status": refusal_status,
                    "request_id": refusal_body.get("request_id"),
                    "transport": "uvicorn TCP HTTP",
                    "x_request_id": refusal_headers.get("x-request-id"),
                    "status": refusal_body.get("status"),
                    "answer_mode": refusal_body.get("answer_mode"),
                    "citations": refusal_body.get("citations"),
                    "warnings": refusal_body.get("warnings"),
                },
                "formal_unreleased": {
                    "query": POSITIVE_QUERY,
                    "http_status": formal_status,
                    "request_id": formal_body.get("request_id"),
                    "transport": "uvicorn TCP HTTP",
                    "x_request_id": formal_headers.get("x-request-id"),
                    "error": formal_body.get("error"),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
