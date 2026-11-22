"""Diagnostic Alpha assembly with explicit policy packages and environment settings.

Run from the repository root: python -m scripts.run_alpha_agent --help
The team's official runtime is backend.app.alpha:app (backend owner branch).
This diagnostic path does not include its ConversationAgentService wrapper.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

from fastapi import FastAPI
import uvicorn

from backend.app.main import create_app
from backend.contracts.models import DocumentPackage
from backend.services.agent_workflow import create_alpha_workflow
from backend.services.errors import ServiceError

ROOT = Path(__file__).resolve().parents[1]


async def build_alpha_app(
    package_paths: list[Path] | None = None, *, file_root: Path = ROOT,
    corpus_dir: Path | None = None,
    workflow_timeout_seconds: float = 30.0,
) -> FastAPI:
    """Load an explicit diagnostic corpus and inject the workflow into FastAPI.

    Does not load .env files, change review states, or use demo dependencies.
    Relative package paths and all package file keys use file_root as their base.
    """
    root = file_root.resolve(strict=True)
    if package_paths is not None and not package_paths:
        raise ValueError("At least one policy package is required")
    if package_paths is not None and corpus_dir is not None:
        raise ValueError("Use explicit packages or an approved corpus directory")
    packages = [] if package_paths is not None else None
    for requested in package_paths or ():
        path = (root / requested).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("Policy package must be within file_root")
        packages.append(DocumentPackage.model_validate_json(path.read_bytes()))
    workflow = await create_alpha_workflow(
        packages, file_root=root,
        corpus_dir=(root / corpus_dir) if corpus_dir is not None else None,
        timeout_seconds=workflow_timeout_seconds,
    )
    return create_app(agent_service=workflow, llm_client=workflow.llm_client)


async def serve(args: argparse.Namespace) -> None:
    app = await build_alpha_app(
        args.package, file_root=args.file_root, corpus_dir=args.corpus_dir,
        workflow_timeout_seconds=args.workflow_timeout_seconds,
    )
    config = uvicorn.Config(app, host=args.host, port=args.port)
    await uvicorn.Server(config).serve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--package", type=Path, action="append",
                        help="Explicit human-approved DocumentPackage JSON, relative to file_root; repeatable")
    source.add_argument("--corpus-dir", type=Path,
                        help="Approved corpus directory; default knowledge_base/processed/alpha/approved")
    parser.add_argument("--file-root", type=Path, default=ROOT)
    parser.add_argument("--workflow-timeout-seconds", type=float, default=30.0,
                        help="Total wait for each retrieval/generate stage, including model retries")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        asyncio.run(serve(args))
    except ServiceError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        # Validation errors can contain policy text or settings. Do not print
        # their raw exception representation into startup logs.
        print("SERVICE_NOT_CONFIGURED: 资料读取或配置校验失败，请检查路径、文件和环境配置。", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
