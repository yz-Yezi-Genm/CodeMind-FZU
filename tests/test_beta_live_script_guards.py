from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
import sys
import unittest
from unittest.mock import patch

from backend.app.config import AppSettings
from backend.contracts.models import RetrievalRequest
from backend.services.alpha_runtime import PROJECT_ROOT, build_alpha_retriever
from scripts import check_beta_qwen_e2e, check_beta_qwen_generation


class BetaLiveScriptGuardTests(unittest.TestCase):
    def test_generation_requires_live_before_reading_configuration(self):
        stderr = StringIO()
        with (
            redirect_stderr(stderr),
            patch.object(
                check_beta_qwen_generation,
                "create_qwen_client_from_env",
            ) as factory,
            self.assertRaises(SystemExit) as raised,
        ):
            check_beta_qwen_generation.main([])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("Add --live", stderr.getvalue())
        factory.assert_not_called()

    def test_e2e_requires_live_before_reading_configuration(self):
        stderr = StringIO()
        with (
            redirect_stderr(stderr),
            patch.object(check_beta_qwen_e2e, "create_qwen_client_from_env") as factory,
            patch.dict(sys.modules, {"backend.app.alpha": None}),
            patch.object(AppSettings, "from_env") as settings_factory,
            self.assertRaises(SystemExit) as raised,
        ):
            check_beta_qwen_e2e.main([])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("Add --live", stderr.getvalue())
        factory.assert_not_called()
        settings_factory.assert_not_called()


class BetaLiveSyntheticCorpusTests(unittest.IsolatedAsyncioTestCase):
    async def test_renamed_synthetic_corpus_loads_and_retrieves(self):
        settings = AppSettings(
            alpha_package_dir=check_beta_qwen_e2e.SYNTHETIC_CORPUS,
        )
        retriever, report = await build_alpha_retriever(
            settings,
            file_root=PROJECT_ROOT,
        )

        self.assertEqual(1, len(report.loaded_packages))
        self.assertEqual((), report.skipped_packages)
        self.assertEqual(1, report.total_indexed_chunks)
        hits = await retriever.retrieve(
            RetrievalRequest(query=check_beta_qwen_e2e.POSITIVE_QUERY)
        )
        self.assertEqual(1, len(hits))
        self.assertEqual(
            "2026年优秀学生综合奖学金申请需提交申请表和成绩单。",
            hits[0].content,
        )
        self.assertEqual(
            "https://example.invalid/beta-live/scholarship",
            hits[0].source_url,
        )


if __name__ == "__main__":
    unittest.main()
