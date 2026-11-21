"""FastAPI application and HTTP contract adaptation."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.config import AppSettings
from backend.contracts.models import (
    AgentRequest,
    AgentResult,
    ApiErrorDetail,
    ApiErrorResponse,
    AskRequest,
    AskResponse,
    HealthResponse,
)
from backend.contracts.protocols import AgentService, LLMClient
from backend.services.errors import ServiceContractError, ServiceError


logger = logging.getLogger(__name__)


def _request_id(request: Request) -> UUID:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, UUID) else uuid4()


def _error_response(
    request_id: UUID,
    *,
    status_code: int,
    code: str,
    message: str,
    retryable: bool = False,
) -> JSONResponse:
    body = ApiErrorResponse(
        request_id=request_id,
        error=ApiErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
        ),
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
    )


def _service_error_response(request: Request, exc: ServiceError) -> JSONResponse:
    public_message = (
        "服务处理请求时发生内部错误。"
        if exc.code == "INTERNAL_ERROR"
        else exc.message
    )
    if exc.code == "INTERNAL_ERROR":
        logger.error(
            "Internal service contract error request_id=%s detail=%s",
            _request_id(request),
            exc.message,
        )
    return _error_response(
        _request_id(request),
        status_code=exc.http_status,
        code=exc.code,
        message=public_message,
        retryable=exc.retryable,
    )


def create_app(
    agent_service: AgentService | None = None,
    *,
    llm_client: LLMClient | None = None,
    settings: AppSettings | None = None,
    lifespan: Any | None = None,
    description: str | None = None,
) -> FastAPI:
    app_settings = settings or AppSettings.from_env()
    app = FastAPI(
        title="CodeMind-FZU API",
        version="0.1.0",
        description=(
            description
            or "Alpha interface contract; business services are injected separately."
        ),
        lifespan=lifespan,
    )
    app.state.agent_service = agent_service
    app.state.llm_client = llm_client
    app.state.settings = app_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_allow_origins),
        allow_credentials=False,
        allow_methods=list(app_settings.cors_allow_methods),
        allow_headers=list(app_settings.cors_allow_headers),
        max_age=600,
    )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next: Any):
        request.state.request_id = uuid4()
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(request.state.request_id)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            _request_id(request),
            status_code=422,
            code="INVALID_REQUEST",
            message="请求参数不符合接口规范，请检查字段和数据类型。",
        )

    @app.exception_handler(ServiceError)
    async def service_error_handler(
        request: Request,
        exc: ServiceError,
    ) -> JSONResponse:
        return _service_error_response(request, exc)

    @app.exception_handler(TimeoutError)
    @app.exception_handler(asyncio.TimeoutError)
    async def timeout_error_handler(request: Request, _exc: BaseException) -> JSONResponse:
        return _error_response(
            _request_id(request),
            status_code=504,
            code="MODEL_TIMEOUT",
            message="上游服务响应超时，请稍后重试。",
            retryable=True,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        code = "RESOURCE_NOT_FOUND" if exc.status_code == 404 else "INVALID_REQUEST"
        message = "请求的资源不存在。" if exc.status_code == 404 else "请求无法处理。"
        return _error_response(
            _request_id(request),
            status_code=exc.status_code,
            code=code,
            message=message,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled backend error request_id=%s type=%s",
            _request_id(request),
            type(exc).__name__,
        )
        return _error_response(
            _request_id(request),
            status_code=500,
            code="INTERNAL_ERROR",
            message="服务处理请求时发生内部错误。",
        )

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="codemind-fzu-api",
            version=app.version,
            timestamp=datetime.now(timezone.utc),
        )

    @app.post(
        "/api/v1/ask",
        response_model=AskResponse,
        responses={
            422: {"model": ApiErrorResponse},
            500: {"model": ApiErrorResponse},
            503: {"model": ApiErrorResponse},
            504: {"model": ApiErrorResponse},
        },
        tags=["assistant"],
    )
    async def ask(payload: AskRequest, request: Request):
        request_id = _request_id(request)
        conversation_id = payload.conversation_id or uuid4()
        service: AgentService | None = request.app.state.agent_service

        if service is None:
            return _error_response(
                request_id,
                status_code=503,
                code="SERVICE_NOT_CONFIGURED",
                message="Agent 服务尚未接入；当前接口仅提供契约入口。",
                retryable=True,
            )

        try:
            result = await service.run(
                AgentRequest(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    query=payload.query,
                )
            )
        except ServiceError as exc:
            return _service_error_response(request, exc)
        except (asyncio.TimeoutError, TimeoutError):
            return _error_response(
                request_id,
                status_code=504,
                code="MODEL_TIMEOUT",
                message="上游服务响应超时，请稍后重试。",
                retryable=True,
            )
        except Exception as exc:
            logger.exception(
                "Unhandled AgentService error request_id=%s type=%s",
                request_id,
                type(exc).__name__,
            )
            return _error_response(
                request_id,
                status_code=500,
                code="INTERNAL_ERROR",
                message="服务处理请求时发生内部错误。",
            )

        if not isinstance(result, AgentResult):
            raise ServiceContractError("AgentService.run() 必须返回 AgentResult。")

        return AskResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            status=result.status,
            answer=result.answer,
            answer_mode=result.answer_mode,
            clarifying_question=result.clarifying_question,
            citations=result.citations,
            warnings=result.warnings,
            created_at=datetime.now(timezone.utc),
        )

    return app


app = create_app()
