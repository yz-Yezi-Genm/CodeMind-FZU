"""Explicitly opt in to a paid Qwen format probe using fixed synthetic evidence."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from backend.contracts.models import AnswerMode
from backend.contracts.protocols import LLMClient
from backend.services.agent_generation import Evidence, generation_request, verify_answer
from backend.services.errors import ServiceError
from backend.services.qwen_client import QwenLLMClient, create_qwen_client_from_env
from examples.agent_workflow_demo import demo_chunk, demo_metadata, demo_parsed_chunk


async def probe(client: LLMClient) -> dict:
    """Validate synthetic quotes through the production citation verifier.

    Return only fixed evidence, normalized usage and the reported model name.
    A provider's raw response or exception text is never a probe artifact.
    """
    chunk = demo_chunk().model_copy(update={"content": "测试原文。"})
    evidence = {f"E1-{uuid4().hex}": Evidence(
        chunk, demo_metadata(chunk), AnswerMode.CURRENT_POLICY, None, demo_parsed_chunk(chunk),
    )}
    prompt = generation_request("请给出测试原文。", [], evidence).model_copy(update={"max_tokens": 128})
    started = perf_counter()
    generated = await asyncio.wait_for(client.generate(prompt), timeout=30)
    _, selected, _ = verify_answer(generated.content, evidence)
    citations = [item.citation() for item in selected]
    return {
        "time_asia_shanghai": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "model": generated.model,
        "elapsed_seconds": round(perf_counter() - started, 3),
        "usage": generated.usage,
        "adapter_result": "success",
        "json_and_full_quote_verified": True,
        "selection": {"evidence": [{"chunk_id": str(c.chunk_id), "quote": c.excerpt} for c in citations]},
        "scope": "Synthetic format probe only; no retrieval, business applicability or real policy acceptance",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly allow a paid model request")
    parser.add_argument("--env-file", type=Path, help="Optional local environment file; existing process values win")
    args = parser.parse_args()
    if not args.live:
        parser.error("Add --live to explicitly run the paid probe; no request was sent")
    async def run_probe(client: QwenLLMClient) -> dict:
        try:
            return await probe(client)
        finally:
            await client.aclose()

    try:
        if args.env_file is not None:
            from dotenv import load_dotenv
            if not args.env_file.is_file():
                raise ValueError("Missing environment file")
            load_dotenv(args.env_file, override=False)
        result = asyncio.run(run_probe(create_qwen_client_from_env()))
    except ServiceError as exc:
        # No raw exception or provider payload: messages may include private
        # configuration details from future adapters.
        print(json.dumps({"success": False, "code": exc.code,
                          "mapped_http_status": exc.http_status}, ensure_ascii=False))
        return 1
    except (TimeoutError, ValueError, TypeError, KeyError, ImportError):
        print('{"success":false,"code":"PROBE_NOT_VERIFIED"}')
        return 1
    except Exception:
        print('{"success":false,"code":"PROBE_FAILED"}')
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
