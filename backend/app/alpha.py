"""Beta FastAPI entry point with a lifespan-managed real runtime."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.config import AppSettings
from backend.app.main import create_app
from backend.services.alpha_runtime import (
    AlphaRuntime,
    UnavailableAgentService,
    build_alpha_runtime,
)
from backend.services.errors import (
    RuntimeUnavailableError,
    ServiceError,
)


logger = logging.getLogger(__name__)
RuntimeBuilder = Callable[[], Awaitable[AlphaRuntime]]


def create_alpha_app(
    *,
    settings: AppSettings | None = None,
    runtime_builder: RuntimeBuilder | None = None,
) -> FastAPI:
    app_settings = settings or AppSettings.from_env()
    builder = runtime_builder or (
        lambda: build_alpha_runtime(app_settings)
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime: AlphaRuntime | None = None
        app.state.alpha_runtime = None
        app.state.alpha_runtime_error = None
        try:
            runtime = await builder()
        except Exception as exc:
            error = exc if isinstance(exc, ServiceError) else RuntimeUnavailableError()
            if not isinstance(exc, ServiceError):
                logger.exception("Alpha runtime startup failed")
            else:
                logger.error(
                    "Alpha runtime startup unavailable code=%s",
                    error.code,
                )
            app.state.alpha_runtime_error = error
            app.state.agent_service = UnavailableAgentService(error)
        else:
            app.state.alpha_runtime = runtime
            app.state.agent_service = runtime.agent_service
            app.state.llm_client = runtime.llm_client
        try:
            yield
        finally:
            if runtime is not None:
                await runtime.close()

    return create_app(
        settings=app_settings,
        lifespan=lifespan,
        description=(
            "Beta real runtime: approved BM25 corpus, AgentWorkflow, "
            "Qwen evidence selection and bounded conversations."
        ),
    )


app = create_alpha_app()
