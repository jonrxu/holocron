from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from holocron.config import Settings


class SettingsTests(unittest.TestCase):
    def test_settings_loads_dotenv_without_overriding_existing_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            previous_cwd = Path.cwd()
            previous_gemini = os.environ.get("GEMINI_API_KEY")
            previous_port = os.environ.get("HOLOCRON_PORT")
            previous_data_dir = os.environ.get("HOLOCRON_DATA_DIR")
            try:
                os.chdir(root)
                for key in ("GEMINI_API_KEY", "HOLOCRON_PORT", "HOLOCRON_DATA_DIR"):
                    os.environ.pop(key, None)

                (root / ".env").write_text(
                    "GEMINI_API_KEY=dotenv-key\n"
                    "HOLOCRON_PORT=9001\n"
                    "HOLOCRON_DATA_DIR=./custom-data\n",
                    encoding="utf-8",
                )
                settings = Settings.from_env()

                self.assertEqual(settings.gemini_api_key, "dotenv-key")
                self.assertEqual(settings.port, 9001)
                self.assertEqual(settings.data_dir, (root / "custom-data").resolve())

                os.environ["GEMINI_API_KEY"] = "real-env-key"
                overridden = Settings.from_env()
                self.assertEqual(overridden.gemini_api_key, "real-env-key")
            finally:
                os.chdir(previous_cwd)
                if previous_gemini is None:
                    os.environ.pop("GEMINI_API_KEY", None)
                else:
                    os.environ["GEMINI_API_KEY"] = previous_gemini
                if previous_port is None:
                    os.environ.pop("HOLOCRON_PORT", None)
                else:
                    os.environ["HOLOCRON_PORT"] = previous_port
                if previous_data_dir is None:
                    os.environ.pop("HOLOCRON_DATA_DIR", None)
                else:
                    os.environ["HOLOCRON_DATA_DIR"] = previous_data_dir
