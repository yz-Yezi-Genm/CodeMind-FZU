"""Run one opt-in, minimal Qwen request using environment configuration."""

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
                        content="只输出 OK 两个字母。",
                    ),
                    LLMMessage(
                        role=LLMRole.USER,
                        content="连接测试",
                    ),
                ],
                temperature=0,
                max_tokens=8,
            )
        )
    finally:
        await client.aclose()
    print(
        json.dumps(
            {
                "content": result.content,
                "model": result.model,
                "usage": result.usage,
                "latency_ms": round((time.monotonic() - started) * 1000),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
