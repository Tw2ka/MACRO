import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from macro.shared.config import openai_api_key


class CredentialTests(unittest.TestCase):
    def test_dotenv_key_takes_precedence_without_mutating_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, ".env").write_text('OPENAI_API_KEY="file-test-key"\n', encoding="utf-8")
            with patch("macro.shared.config.Path.cwd", return_value=Path(folder)), patch.dict(
                os.environ, {"OPENAI_API_KEY": "environment-test-key"}, clear=True
            ):
                self.assertEqual(openai_api_key(), "file-test-key")
                self.assertEqual(os.environ["OPENAI_API_KEY"], "environment-test-key")

    def test_environment_fallback_and_missing_key(self):
        with tempfile.TemporaryDirectory() as folder, patch(
            "macro.shared.config.Path.cwd", return_value=Path(folder)
        ), patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, r"\.env"):
                openai_api_key()
            os.environ["OPENAI_API_KEY"] = "environment-test-key"
            self.assertEqual(openai_api_key(), "environment-test-key")
