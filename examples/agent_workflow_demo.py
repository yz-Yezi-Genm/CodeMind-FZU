"""OFFLINE DEMO ONLY: synthetic evidence and fake LLM; no Qwen/index access.

Run from repository root: python -m examples.agent_workflow_demo
"""
import asyncio
import json
from datetime import date
from uuid import UUID

from backend.contracts.models import (
    AgentRequest, DocumentMetadata, LLMGenerateRequest, LLMResult, RetrievalRequest, RetrievedChunk,
)
from backend.services.agent_workflow import AgentWorkflow


def demo_chunk() -> RetrievedChunk:
    """Synthetic fixture, not an actual FZU policy or a released KB document."""
    return RetrievedChunk(
        chunk_id=UUID(int=101), document_id=UUID(int=102),
        version_id=UUID(int=103), file_id=UUID(int=104),
        title="【模拟资料】测试用选课说明（非学校政策）",
        content="【模拟资料，非学校政策】测试流程：先阅读选课说明，再核对课程信息。",
        source_url="https://example.invalid/agent-workflow-demo",
        publisher="离线测试替身", score=0.01,
        published_on=date(2026, 1, 1),
        source_verification_status="verified",
        timeliness_verification_status="current", retrieval_status="enabled",
    )


def demo_metadata(chunk: RetrievedChunk) -> DocumentMetadata:
    """Synthetic review marker for offline fixtures only, never policy approval."""
    fields = chunk.model_dump(include={"title", "publisher", "source_url", "published_on", "effective_on",
        "source_verification_status", "timeliness_verification_status", "retrieval_status"})
    return DocumentMetadata(**fields, document_type="合成测试", category_name="测试",
        record_code="DEMO-NOT-POLICY", version_no="fixture-1", extraction_status="extracted",
        v1_inclusion_status="included", temporal_notes={"human_approved": True})


class DemoRetriever:
    """Fake Retriever. 'verified/enabled' are fixture values, not real reviews."""

    def __init__(self, chunks: list[RetrievedChunk]):
        self.chunks = chunks

    async def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        return self.chunks

    def get_document_metadata(self, version_id: UUID) -> DocumentMetadata | None:
        chunk = next((chunk for chunk in self.chunks if chunk.version_id == version_id), None)
        return demo_metadata(chunk) if chunk is not None else None


class DemoLLMClient:
    """Fake LLMClient selecting the first supplied fixture; no model is called."""

    async def generate(self, request: LLMGenerateRequest) -> LLMResult:
        first = json.loads(request.messages[-1].content)["evidence"][0]
        return LLMResult(model="DEMO-FAKE-NOT-QWEN", content=json.dumps({
            "evidence": [{"chunk_id": first["chunk_id"], "quote": first["content"]}],
        }, ensure_ascii=False))


async def main() -> None:
    for label, query, chunks in [
        ("缺少必要信息", "奖学金怎么申请？", []),
        ("没有有效证据", "选课有哪些步骤？", []),
        ("有证据进入生成", "选课有哪些步骤？", [demo_chunk()]),
    ]:
        service = AgentWorkflow(DemoRetriever(chunks), DemoLLMClient())
        result = await service.run(AgentRequest(
            request_id=UUID(int=1), conversation_id=UUID(int=2), query=query,
        ))
        print(json.dumps({
            "demo_only": True, "scenario": label,
            "result": result.model_dump(mode="json"),
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
