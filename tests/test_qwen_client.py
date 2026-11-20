import json
import os
import unittest
from unittest.mock import patch

import httpx

from backend.contracts.models import LLMGenerateRequest, LLMMessage, LLMRole
from backend.services.errors import (
    LLMConfigurationError,
    LLMRateLimitedError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from backend.services.qwen_client import QwenLLMClient, QwenSettings


class QwenClientTests(unittest.IsolatedAsyncioTestCase):
    def request(self) -> LLMGenerateRequest:
        return LLMGenerateRequest(
            messages=[
                LLMMessage(role=LLMRole.SYSTEM, content="只依据已核验证据回答。"),
                LLMMessage(role=LLMRole.USER, content="测试问题"),
            ],
            temperature=0.1,
            max_tokens=256,
        )

    async def test_success_response_is_adapted(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["authorization"] = request.headers["authorization"]
            captured["payload"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "model": "qwen-plus-test",
                    "choices": [{"message": {"content": "测试回答"}}],
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 5,
                        "total_tokens": 17,
                    },
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = QwenLLMClient(
                QwenSettings(
                    api_key="test-key",
                    base_url="https://qwen.example/v1",
                    model="qwen-test",
                ),
                http_client=http_client,
            )
            result = await client.generate(self.request())

        self.assertEqual(result.content, "测试回答")
        self.assertEqual(result.model, "qwen-plus-test")
        self.assertEqual(result.usage["total_tokens"], 17)
        self.assertEqual(captured["url"], "https://qwen.example/v1/chat/completions")
        self.assertEqual(captured["authorization"], "Bearer test-key")
        self.assertEqual(captured["payload"]["model"], "qwen-test")
        self.assertEqual(captured["payload"]["max_tokens"], 256)

    async def test_retryable_status_is_retried(self):
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503, json={"error": "temporary"})
            return httpx.Response(
                200,
                json={
                    "model": "qwen-test",
                    "choices": [{"message": {"content": "重试成功"}}],
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = QwenLLMClient(
                QwenSettings(
                    api_key="test-key",
                    base_url="https://qwen.example/v1",
                    model="qwen-test",
                    max_retries=1,
                ),
                http_client=http_client,
            )
            result = await client.generate(self.request())

        self.assertEqual(calls, 2)
        self.assertEqual(result.content, "重试成功")

    async def test_mixed_failures_share_one_retry_budget(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503, json={"error": "temporary"})
            raise httpx.ReadTimeout("timed out", request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = QwenLLMClient(
                QwenSettings(
                    api_key="test-key",
                    base_url="https://qwen.example/v1",
                    model="qwen-test",
                    max_retries=1,
                ),
                http_client=http_client,
            )
            with self.assertRaises(LLMTimeoutError):
                await client.generate(self.request())

        self.assertEqual(calls, 2)

    async def test_timeout_maps_to_sanitized_service_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = QwenLLMClient(
                QwenSettings(
                    api_key="test-key",
                    base_url="https://qwen.example/v1",
                    model="qwen-test",
                    max_retries=0,
                ),
                http_client=http_client,
            )
            with self.assertRaises(LLMTimeoutError):
                await client.generate(self.request())

    async def test_rate_limit_maps_to_rate_limited_error(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": "too many requests"})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = QwenLLMClient(
                QwenSettings(
                    api_key="test-key",
                    base_url="https://qwen.example/v1",
                    model="qwen-test",
                    max_retries=0,
                ),
                http_client=http_client,
            )
            with self.assertRaises(LLMRateLimitedError):
                await client.generate(self.request())

    async def test_server_failure_maps_to_unavailable_error(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "failed"})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = QwenLLMClient(
                QwenSettings(
                    api_key="test-key",
                    base_url="https://qwen.example/v1",
                    model="qwen-test",
                    max_retries=0,
                ),
                http_client=http_client,
            )
            with self.assertRaises(LLMUnavailableError):
                await client.generate(self.request())

    async def test_missing_api_key_fails_before_network_call(self):
        with self.assertRaises(LLMConfigurationError):
            QwenLLMClient(QwenSettings(api_key="", model="qwen-test"))

    def test_settings_do_not_expose_api_key(self):
        with patch.dict(
            os.environ,
            {
                "QWEN_API_KEY": "local-secret",
                "QWEN_BASE_URL": "https://qwen.example/v1",
                "QWEN_MODEL": "qwen-test",
            },
            clear=False,
        ):
            settings = QwenSettings.from_env()

        self.assertNotIn("local-secret", repr(settings))

    def test_default_budget_fits_agent_timeout(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = QwenSettings.from_env()

        self.assertEqual(settings.timeout_seconds, 28.0)
        self.assertEqual(settings.max_retries, 0)


if __name__ == "__main__":
    unittest.main()
