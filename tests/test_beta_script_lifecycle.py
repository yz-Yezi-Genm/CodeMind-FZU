"""Verify diagnostic scripts close Qwen clients they create."""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.contracts.models import LLMResult
from backend.services.errors import LLMTimeoutError
from scripts import check_qwen_live, check_qwen_runtime_live, run_alpha_agent


class CheckQwenLiveLifecycleTests(unittest.TestCase):
    def run_main(self, probe_mock):
        client = SimpleNamespace(aclose=AsyncMock())
        with (
            patch.object(sys, "argv", ["check_qwen_live", "--live"]),
            patch.object(
                check_qwen_live,
                "create_qwen_client_from_env",
                return_value=client,
            ),
            patch.object(check_qwen_live, "probe", probe_mock),
            redirect_stdout(io.StringIO()),
        ):
            code = check_qwen_live.main()
        return code, client

    def test_success_closes_client(self):
        code, client = self.run_main(
            AsyncMock(return_value={"success": True})
        )

        self.assertEqual(code, 0)
        client.aclose.assert_awaited_once()

    def test_failure_closes_client(self):
        code, client = self.run_main(
            AsyncMock(side_effect=LLMTimeoutError())
        )

        self.assertEqual(code, 1)
        client.aclose.assert_awaited_once()


class QwenRuntimeScriptLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_closes_client_on_success(self):
        client = SimpleNamespace(
            generate=AsyncMock(
                return_value=LLMResult(
                    content="OK",
                    model="qwen-flash",
                    usage={"total_tokens": 2},
                )
            ),
            aclose=AsyncMock(),
        )
        with (
            patch.object(
                check_qwen_runtime_live,
                "create_qwen_client_from_env",
                return_value=client,
            ),
            redirect_stdout(io.StringIO()),
        ):
            await check_qwen_runtime_live.main()

        client.aclose.assert_awaited_once()

    async def test_probe_closes_client_on_failure(self):
        client = SimpleNamespace(
            generate=AsyncMock(side_effect=LLMTimeoutError()),
            aclose=AsyncMock(),
        )
        with patch.object(
            check_qwen_runtime_live,
            "create_qwen_client_from_env",
            return_value=client,
        ):
            with self.assertRaises(LLMTimeoutError):
                await check_qwen_runtime_live.main()

        client.aclose.assert_awaited_once()


class RunAlphaAgentScriptLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def args(self):
        return SimpleNamespace(
            package=None,
            corpus_dir=None,
            file_root=run_alpha_agent.ROOT,
            workflow_timeout_seconds=30.0,
            host="127.0.0.1",
            port=8000,
        )

    async def test_server_shutdown_closes_injected_client(self):
        client = SimpleNamespace(aclose=AsyncMock())
        app = SimpleNamespace(state=SimpleNamespace(llm_client=client))
        server = SimpleNamespace(serve=AsyncMock())
        with (
            patch.object(
                run_alpha_agent,
                "build_alpha_app",
                AsyncMock(return_value=app),
            ),
            patch.object(run_alpha_agent.uvicorn, "Config", return_value=object()),
            patch.object(run_alpha_agent.uvicorn, "Server", return_value=server),
        ):
            await run_alpha_agent.serve(self.args())

        client.aclose.assert_awaited_once()

    async def test_server_error_still_closes_injected_client(self):
        client = SimpleNamespace(aclose=AsyncMock())
        app = SimpleNamespace(state=SimpleNamespace(llm_client=client))
        server = SimpleNamespace(serve=AsyncMock(side_effect=RuntimeError()))
        with (
            patch.object(
                run_alpha_agent,
                "build_alpha_app",
                AsyncMock(return_value=app),
            ),
            patch.object(run_alpha_agent.uvicorn, "Config", return_value=object()),
            patch.object(run_alpha_agent.uvicorn, "Server", return_value=server),
        ):
            with self.assertRaises(RuntimeError):
                await run_alpha_agent.serve(self.args())

        client.aclose.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
