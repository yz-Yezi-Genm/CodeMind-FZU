"""Qwen OpenAI-compatible chat-completions adapter."""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

from backend.contracts.models import LLMGenerateRequest, LLMResult
from backend.services.errors import (
    LLMConfigurationError,
    LLMRateLimitedError,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)


DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_MODEL = "qwen-plus"
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class QwenSettings:
    """Qwen settings; the secret is excluded from object representations."""

    api_key: str = field(default="", repr=False)
    base_url: str = DEFAULT_QWEN_BASE_URL
    model: str = DEFAULT_QWEN_MODEL
    timeout_seconds: float = 20.0
    max_retries: int = 1

    @classmethod
    def from_env(cls) -> "QwenSettings":
        timeout_raw = os.getenv("QWEN_TIMEOUT_SECONDS", "20")
        retries_raw = os.getenv("QWEN_MAX_RETRIES", "1")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise LLMConfigurationError("QWEN_TIMEOUT_SECONDS 必须是数字。") from exc
        try:
            max_retries = int(retries_raw)
        except ValueError as exc:
            raise LLMConfigurationError("QWEN_MAX_RETRIES 必须是整数。") from exc

        if timeout_seconds <= 0:
            raise LLMConfigurationError("QWEN_TIMEOUT_SECONDS 必须大于 0。")
        if not 0 <= max_retries <= 3:
            raise LLMConfigurationError("QWEN_MAX_RETRIES 必须在 0 到 3 之间。")

        return cls(
            api_key=os.getenv("QWEN_API_KEY", "").strip(),
            base_url=os.getenv("QWEN_BASE_URL", DEFAULT_QWEN_BASE_URL).strip(),
            model=os.getenv("QWEN_MODEL", DEFAULT_QWEN_MODEL).strip(),
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )


class QwenLLMClient:
    """Calls a Qwen endpoint using the OpenAI chat-completions shape."""

    def __init__(
        self,
        settings: QwenSettings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client
        self._validate_settings()

    def _validate_settings(self) -> None:
        if not self._settings.api_key:
            raise LLMConfigurationError("未配置 QWEN_API_KEY，模型服务不可用。")
        if not self._settings.model:
            raise LLMConfigurationError("QWEN_MODEL 不能为空。")

        parsed = urlsplit(self._settings.base_url)
        local_host = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or (parsed.scheme != "https" and not local_host)
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise LLMConfigurationError("QWEN_BASE_URL 必须是有效的 HTTP(S) 服务地址。")

    @property
    def endpoint(self) -> str:
        return f"{self._settings.base_url.rstrip('/')}/chat/completions"

    async def generate(self, request: LLMGenerateRequest) -> LLMResult:
        payload = {
            "model": self._settings.model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Content-Type": "application/json",
        }
        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(self._settings.timeout_seconds),
            follow_redirects=False,
        )

        try:
            for attempt in range(self._settings.max_retries + 1):
                response = await self._post(client, payload, headers, attempt)
                if response.status_code < 400:
                    return self._parse_response(response)

                if (
                    response.status_code in _RETRYABLE_STATUS_CODES
                    and attempt < self._settings.max_retries
                ):
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                self._raise_for_status(response.status_code)

            raise LLMUnavailableError()
        finally:
            if owns_client:
                await client.aclose()

    async def _post(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        headers: dict[str, str],
        attempt: int,
    ) -> httpx.Response:
        try:
            return await client.post(self.endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            if attempt < self._settings.max_retries:
                await asyncio.sleep(0.25 * (2**attempt))
                return await self._post(client, payload, headers, attempt + 1)
            raise LLMTimeoutError() from exc
        except httpx.RequestError as exc:
            if attempt < self._settings.max_retries:
                await asyncio.sleep(0.25 * (2**attempt))
                return await self._post(client, payload, headers, attempt + 1)
            raise LLMUnavailableError() from exc

    def _parse_response(self, response: httpx.Response) -> LLMResult:
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            model = body.get("model") or self._settings.model
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMResponseError() from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("模型服务返回了空回答。")

        usage_raw = body.get("usage")
        usage = None
        if isinstance(usage_raw, dict):
            normalized = {
                key: value
                for key, value in usage_raw.items()
                if isinstance(value, int)
            }
            usage = normalized or None

        return LLMResult(content=content.strip(), model=str(model), usage=usage)

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if status_code == 429:
            raise LLMRateLimitedError()
        if status_code == 408:
            raise LLMTimeoutError()
        if status_code in {401, 403}:
            raise LLMConfigurationError("模型服务认证失败，请检查服务端配置。")
        if status_code >= 500:
            raise LLMUnavailableError()
        raise LLMResponseError("模型服务拒绝了本次请求。")


def create_qwen_client_from_env(
    *,
    http_client: httpx.AsyncClient | None = None,
) -> QwenLLMClient:
    """Build the adapter from environment variables for Agent integration."""
    return QwenLLMClient(QwenSettings.from_env(), http_client=http_client)
