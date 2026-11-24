"""V2.1 §5.3 response-shape regression tests for both public DTOs."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.contracts.models import AgentResult, AskResponse, AnswerMode, AnswerStatus


def build(model, **payload):
    if model is AskResponse:
        payload.update(
            request_id=uuid4(), conversation_id=uuid4(),
            created_at=datetime.now(timezone.utc),
        )
    return model(**payload)


def citation():
    return {
        "document_id": uuid4(), "version_id": uuid4(), "chunk_id": uuid4(),
        "title": "合成测试资料", "source_url": "https://example.invalid/test",
        "excerpt": "合成测试片段", "source_verification_status": "verified",
        "timeliness_verification_status": "current", "retrieval_status": "enabled",
    }


@pytest.mark.parametrize("model", [AgentResult, AskResponse])
@pytest.mark.parametrize("answer", [None, "", " \t\n"])
def test_answered_requires_nonblank_answer(model, answer):
    with pytest.raises(ValidationError, match="answer"):
        build(model, status="answered", answer=answer, answer_mode="current_policy")


@pytest.mark.parametrize("model", [AgentResult, AskResponse])
def test_answered_requires_explicit_mode(model):
    with pytest.raises(ValidationError, match="answer_mode"):
        build(model, status="answered", answer="合成测试回答")


@pytest.mark.parametrize("model", [AgentResult, AskResponse])
@pytest.mark.parametrize("mode", list(AnswerMode))
def test_answered_explicit_modes_preserve_existing_contract(model, mode):
    # V2.1 requires an explicit mode; it does not explicitly forbid a particular
    # enum value here. Do not silently tighten the frozen enum/state contract.
    result = build(model, status="answered", answer="合成测试回答", answer_mode=mode)
    assert result.model_dump(mode="json")["answer_mode"] == mode.value


@pytest.mark.parametrize("model", [AgentResult, AskResponse])
@pytest.mark.parametrize("field,value", [
    ("answer", "不允许的答案"), ("answer", ""),
    ("answer_mode", "historical"), ("citations", "citation"),
    ("clarifying_question", None), ("clarifying_question", ""),
    ("clarifying_question", " \t\n"),
])
def test_clarification_rejects_incompatible_fields(model, field, value):
    payload = {"status": "needs_clarification", "clarifying_question": "请补充年份"}
    payload[field] = [citation()] if value == "citation" else value
    with pytest.raises(ValidationError, match=field):
        build(model, **payload)


@pytest.mark.parametrize("model", [AgentResult, AskResponse])
def test_clarification_serialization(model):
    result = build(model, status="needs_clarification", clarifying_question="请补充年份")
    data = result.model_dump(mode="json")
    assert data["status"] == "needs_clarification"
    assert data["answer"] is None and data["answer_mode"] is None
    assert data["clarifying_question"] == "请补充年份"
    assert data["citations"] == []


@pytest.mark.parametrize("model", [AgentResult, AskResponse])
@pytest.mark.parametrize("mode", [None, "current_policy", "historical", "procedure_reference"])
def test_insufficient_requires_matching_mode(model, mode):
    with pytest.raises(ValidationError, match="answer_mode"):
        build(model, status="insufficient_evidence", answer="缺少已审核证据", answer_mode=mode)


@pytest.mark.parametrize("model", [AgentResult, AskResponse])
def test_insufficient_rejects_citations(model):
    with pytest.raises(ValidationError, match="citations"):
        build(model, status="insufficient_evidence", answer="缺少已审核证据",
              answer_mode="insufficient_data", citations=[citation()])


@pytest.mark.parametrize("model", [AgentResult, AskResponse])
@pytest.mark.parametrize("answer", [None, "", " \t\n"])
def test_insufficient_requires_reason(model, answer):
    with pytest.raises(ValidationError, match="证据不足原因"):
        build(model, status="insufficient_evidence", answer=answer,
              answer_mode="insufficient_data", warnings=[])


@pytest.mark.parametrize("model", [AgentResult, AskResponse])
@pytest.mark.parametrize("reason_field", ["answer", "warnings", "both"])
def test_insufficient_accepts_reason_and_serializes(model, reason_field):
    payload = {"status": "insufficient_evidence", "answer_mode": "insufficient_data"}
    if reason_field in {"answer", "both"}:
        payload["answer"] = "缺少已审核证据"
    if reason_field in {"warnings", "both"}:
        payload["warnings"] = [{"code": "NO_EVIDENCE", "message": "缺少已审核证据"}]
    result = build(model, **payload)
    data = result.model_dump(mode="json")
    assert data["status"] == "insufficient_evidence"
    assert data["answer_mode"] == "insufficient_data"
    assert data["citations"] == []
    assert data["answer"] or data["warnings"]


@pytest.mark.parametrize("reason_field", ["answer", "warnings"])
def test_http_insufficient_remains_200(reason_field):
    class InsufficientService:
        async def run(self, request):
            payload = {"status": AnswerStatus.INSUFFICIENT_EVIDENCE,
                       "answer_mode": AnswerMode.INSUFFICIENT_DATA}
            if reason_field == "answer":
                payload["answer"] = "缺少已审核证据"
            else:
                payload["warnings"] = [{"code": "NO_EVIDENCE", "message": "缺少已审核证据"}]
            return AgentResult(**payload)

    with TestClient(create_app(agent_service=InsufficientService())) as client:
        response = client.post("/api/v1/ask", json={"query": "合成测试问题"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_evidence"
    assert body["answer_mode"] == "insufficient_data"
    assert body["citations"] == []
    assert body["answer"] or body["warnings"]
