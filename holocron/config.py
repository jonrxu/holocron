from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path | None = None) -> None:
    env_path = (path or Path(".env")).expanduser()
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    blob_dir: Path
    host: str = "127.0.0.1"
    port: int = 8420
    analyzer_command: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-5"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: int = 90
    openai_reasoning_effort: str = "low"
    gemini_api_key: str | None = None
    gemini_analysis_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_generation_model: str = "gemini-2.5-flash-lite"
    gemini_embedding_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_embedding_dimensions: int = 768
    gemini_timeout_seconds: int = 30
    max_text_chars: int = 24000
    review_after_days: int = 7

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        data_dir = Path(os.getenv("HOLOCRON_DATA_DIR", "data")).expanduser().resolve()
        blob_dir = Path(
            os.getenv("HOLOCRON_BLOB_DIR", str(data_dir / "blobs"))
        ).expanduser().resolve()
        database_path = Path(
            os.getenv("HOLOCRON_DB_PATH", str(data_dir / "holocron.db"))
        ).expanduser().resolve()

        analyzer_command = os.getenv("HOLOCRON_ANALYZER_COMMAND")
        openai_api_key = os.getenv("HOLOCRON_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        gemini_api_key = os.getenv("HOLOCRON_GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

        return cls(
            data_dir=data_dir,
            database_path=database_path,
            blob_dir=blob_dir,
            host=os.getenv("HOLOCRON_HOST", "127.0.0.1"),
            port=int(os.getenv("HOLOCRON_PORT", "8420")),
            analyzer_command=analyzer_command or None,
            openai_api_key=openai_api_key or None,
            openai_model=os.getenv("HOLOCRON_OPENAI_MODEL", "gpt-5"),
            openai_base_url=os.getenv("HOLOCRON_OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_timeout_seconds=int(os.getenv("HOLOCRON_OPENAI_TIMEOUT_SECONDS", "90")),
            openai_reasoning_effort=os.getenv("HOLOCRON_OPENAI_REASONING_EFFORT", "low"),
            gemini_api_key=gemini_api_key or None,
            gemini_analysis_model=os.getenv("HOLOCRON_GEMINI_ANALYSIS_MODEL", "gemini-2.5-flash"),
            gemini_embedding_model=os.getenv("HOLOCRON_GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
            gemini_generation_model=os.getenv("HOLOCRON_GEMINI_GENERATION_MODEL", "gemini-2.5-flash-lite"),
            gemini_embedding_base_url=os.getenv(
                "HOLOCRON_GEMINI_EMBEDDING_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta",
            ),
            gemini_embedding_dimensions=int(os.getenv("HOLOCRON_GEMINI_EMBEDDING_DIMENSIONS", "768")),
            gemini_timeout_seconds=int(os.getenv("HOLOCRON_GEMINI_TIMEOUT_SECONDS", "30")),
            max_text_chars=int(os.getenv("HOLOCRON_MAX_TEXT_CHARS", "24000")),
            review_after_days=int(os.getenv("HOLOCRON_REVIEW_AFTER_DAYS", "7")),
        )
