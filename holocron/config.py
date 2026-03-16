from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    blob_dir: Path
    host: str = "127.0.0.1"
    port: int = 8420
    analyzer_command: str | None = None
    max_text_chars: int = 24000
    review_after_days: int = 7

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("HOLOCRON_DATA_DIR", "data")).expanduser().resolve()
        blob_dir = Path(
            os.getenv("HOLOCRON_BLOB_DIR", str(data_dir / "blobs"))
        ).expanduser().resolve()
        database_path = Path(
            os.getenv("HOLOCRON_DB_PATH", str(data_dir / "holocron.db"))
        ).expanduser().resolve()

        analyzer_command = os.getenv("HOLOCRON_ANALYZER_COMMAND")

        return cls(
            data_dir=data_dir,
            database_path=database_path,
            blob_dir=blob_dir,
            host=os.getenv("HOLOCRON_HOST", "127.0.0.1"),
            port=int(os.getenv("HOLOCRON_PORT", "8420")),
            analyzer_command=analyzer_command or None,
            max_text_chars=int(os.getenv("HOLOCRON_MAX_TEXT_CHARS", "24000")),
            review_after_days=int(os.getenv("HOLOCRON_REVIEW_AFTER_DAYS", "7")),
        )
