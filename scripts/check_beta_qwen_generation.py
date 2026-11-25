"""Run one opt-in real Qwen request for the Beta constrained JSON contract."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import time

from backend.contracts.models import (
    LLMGenerateRequest,
    LLMMessage,
    LLMRole,
)
from backend.services.qwen_client import create_qwen_client_from_env


async def run_live(env_file: Path | None) -> None:
    if env_file is not None:
        from dotenv import load_dotenv

        if not env_file.is_file():
            raise ValueError("Environment file does not exist")
        load_dotenv(env_file, override=False)
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
        or payload["used_evidence_ids"] != ["E1"]
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly allow a paid Qwen request",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Optional local environment file; existing process values win",
    )
    args = parser.parse_args(argv)
    if not args.live:
        parser.error(
            "Add --live to explicitly run the paid probe; no request was sent"
        )
    asyncio.run(run_live(args.env_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
