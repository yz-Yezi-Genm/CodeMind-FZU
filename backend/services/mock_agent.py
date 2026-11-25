
"""Deterministic Mock Agent for local API integration."""
from backend.contracts.models import (
    AgentRequest,
    AgentResult,
    AnswerMode,
    AnswerStatus,
    WarningItem,
)


class MockAgentService:
    """A local-only Agent implementation for API integration tests."""

    async def run(self, request: AgentRequest) -> AgentResult:
        query = request.query.strip()

        # Test scenario 1: clarification required
        if query == "__mock_clarify__":
            return AgentResult(
                status=AnswerStatus.NEEDS_CLARIFICATION,
                answer=None,
                answer_mode=None,
                clarifying_question="请问你咨询的是哪一学年的相关政策？",
                citations=[],
                warnings=[
                    WarningItem(
                        code="MOCK_AGENT",
                        message="当前使用模拟 Agent。",
                    )
                ],
            )

        # Test scenario 2: insufficient evidence
        if query == "__mock_insufficient__":
            return AgentResult(
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                answer="目前尚未接入真实知识库，无法提供经过核验的政策结论。",
                answer_mode=AnswerMode.INSUFFICIENT_DATA,
                clarifying_question=None,
                citations=[],
                warnings=[
                    WarningItem(
                        code="MOCK_NO_EVIDENCE",
                        message="当前没有可用于正式回答的真实证据。",
                    )
                ],
            )

        # Test scenario 3: normal response
        return AgentResult(
            status=AnswerStatus.ANSWERED,
            answer=(
                f"[Mock 演示] 已收到你的问题：{query}\n\n"
                "当前 API 已成功调用模拟 Agent 并返回结果。"
                "这不是经过核验的真实政策答案。"
            ),
            # Synthetic mode for UI contract exercise; not a verified policy answer.
            answer_mode=AnswerMode.CURRENT_POLICY,
            clarifying_question=None,
            citations=[],
            warnings=[
                WarningItem(
                    code="MOCK_AGENT",
                    message="当前响应由 MockAgentService 生成，未调用真实模型和知识库。",
                )
            ],
        )
