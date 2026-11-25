"""Run one opt-in real Qwen request for the Beta constrained JSON contract."""

from __future__ import annotations

import asyncio
import json
import time

from backend.contracts.models import (
    LLMGenerateRequest,
    LLMMessage,
    LLMRole,
)
from backend.services.qwen_client import create_qwen_client_from_env


async def main() -> None:
    client = create_qwen_client_from_env()
    started = time.monotonic()
    try:
        result = await client.generate(
            LLMGenerateRequest(
                messages=[
                    LLMMessage(
                        role=LLMRole.SYSTEM,
                        content=(
                            "你是受证据约束的校园信息助手。"
                            "只输出一个 JSON 对象，不使用 Markdown 代码围栏。"
                            '格式必须是 {"answer":"自然语言回答",'
                            '"used_evidence_ids":["E1"]}。'
                            "只能使用本次提供的 evidence_id；证据不足时输出"
                            '{"answer":"现有证据不足以回答。",'
                            '"used_evidence_ids":[]}。'
                        ),
                    ),
                    LLMMessage(
                        role=LLMRole.USER,
                        content=json.dumps(
                            {
                                "question": "奖学金申请需要提交什么？",
                                "evidence": [
                                    {
                                        "evidence_id": "E1",
                                        "text": "申请奖学金需提交申请表和成绩单。",
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ),
                    ),
                ],
                temperature=0,
                max_tokens=256,
            )
        )
    finally:
        await client.aclose()
    payload = json.loads(result.content)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"answer", "used_evidence_ids"}
        or not isinstance(payload["answer"], str)
        or not payload["answer"].strip()
        or not isinstance(payload["used_evidence_ids"], list)
        or any(not isinstance(item, str) for item in payload["used_evidence_ids"])
        or any(item != "E1" for item in payload["used_evidence_ids"])
    ):
        raise ValueError("Qwen did not satisfy the constrained response contract")
    print(
        json.dumps(
            {
                "success": True,
                "model": result.model,
                "usage": result.usage,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "raw_content": result.content,
                "parsed": payload,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
