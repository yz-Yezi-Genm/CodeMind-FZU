"""Replay the offline Retriever handoff against the checked-in Agent work."""

import asyncio
import json
from uuid import uuid4

from backend.contracts import (
    AgentRequest, AnswerStatus, DocumentPackage, IndexingStatus, LLMGenerateRequest, LLMResult,
)
from backend.retrieval import LocalBM25Retriever
from backend.services.agent_workflow import AgentWorkflow
from scripts.demo_local_retrieval import REAL_CASES, ROOT, SYNTHETIC_PACKAGES


class FirstEvidenceLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMGenerateRequest) -> LLMResult:
        self.calls += 1
        hit = json.loads(request.messages[-1].content)["evidence"][0]
        output = {"evidence": [{"chunk_id": hit["chunk_id"], "quote": hit["content"]}]}
        return LLMResult(content=json.dumps(output), model="offline-test-double")


async def check() -> None:
    real = LocalBM25Retriever(file_root=ROOT)
    synthetic = LocalBM25Retriever()
    for stem, _ in REAL_CASES:
        path = ROOT / "knowledge_base/processed/alpha" / f"{stem}.json"
        package = DocumentPackage.model_validate_json(path.read_bytes())
        result = await real.index_document(package)
        if result.status != IndexingStatus.INDEXED:
            raise AssertionError((stem, result.warnings))
    for item in json.loads(SYNTHETIC_PACKAGES.read_bytes()):
        await synthetic.index_document(DocumentPackage.model_validate(item))

    print(f"Agent: {AgentWorkflow.__module__}.{AgentWorkflow.__qualname__} (current checkout)")
    print("LLM: offline test double. Clarification and applicability callbacks are test inputs.")
    cases = [(real, query, AnswerStatus.INSUFFICIENT_EVIDENCE) for _, query in REAL_CASES]
    cases.append((synthetic, "星桥奖学金申请需要什么", AnswerStatus.ANSWERED))
    for store, query, expected in cases:
        llm = FirstEvidenceLLM()
        workflow = AgentWorkflow(
            store, llm, clarification_rule=lambda _: None, evidence_check=lambda *_: True
        )
        result = await workflow.run(AgentRequest(
            request_id=uuid4(), conversation_id=uuid4(), query=query
        ))
        warnings = [item.code for item in result.warnings]
        if result.status != expected:
            raise AssertionError((query, result.status, warnings))
        if expected == AnswerStatus.ANSWERED:
            if llm.calls != 1 or len(result.citations) != 1:
                raise AssertionError("Expected one model call and one synthetic citation")
            citation = result.citations[0]
            if (
                citation.source_url != "https://example.invalid/alpha/scholarship"
                or citation.locator != "第 2 行"
                or citation.original_locator != "第 1 页"
            ):
                raise AssertionError("Synthetic citation lost its source or locator")
        elif llm.calls or result.citations or "NO_ELIGIBLE_EVIDENCE" not in warnings:
            raise AssertionError("Blocked material reached the model or produced a citation")
        print(json.dumps({
            "query": query,
            "status": result.status,
            "warnings": warnings,
            "llm_calls": llm.calls,
            "citations": [item.model_dump(mode="json") for item in result.citations],
        }, ensure_ascii=False))
    print(f"PASS: {len(cases)} Agent -> Retriever cases")


if __name__ == "__main__":
    asyncio.run(check())
