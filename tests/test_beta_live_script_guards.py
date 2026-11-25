from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
import unittest
from unittest.mock import patch

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
            patch.object(check_beta_qwen_e2e, "create_alpha_app") as app_factory,
            self.assertRaises(SystemExit) as raised,
        ):
            check_beta_qwen_e2e.main([])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("Add --live", stderr.getvalue())
        factory.assert_not_called()
        app_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
