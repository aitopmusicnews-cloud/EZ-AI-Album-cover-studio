from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_project_env() -> None:
    """Load root .env without adding another dependency.

    Existing shell environment variables win over values in .env.
    """
    path = _PROJECT_ROOT / ".env"
    if not path.exists():
        return
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or not key.replace("_", "").isalnum():
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ.setdefault(key, value)
    except OSError:
        # Configuration still works from the shell environment if .env cannot be read.
        return


_load_project_env()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    app_name: str = "EZ AI Album Cover Studio"
    environment: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", f"sqlite:///{_PROJECT_ROOT / 'data' / 'album_covers.db'}"
        )
    )
    storage_root: Path = field(
        default_factory=lambda: Path(
            os.getenv("STORAGE_ROOT", str(_PROJECT_ROOT / "data" / "storage"))
        ).resolve()
    )
    frontend_root: Path = field(
        default_factory=lambda: Path(
            os.getenv("FRONTEND_ROOT", str(_PROJECT_ROOT / "frontend"))
        ).resolve()
    )
    max_audio_mb: int = field(default_factory=lambda: int(os.getenv("MAX_AUDIO_MB", "30")))
    max_lyrics_chars: int = field(
        default_factory=lambda: int(os.getenv("MAX_LYRICS_CHARS", "50000"))
    )
    audio_analysis_max_seconds: int = field(
        default_factory=lambda: int(os.getenv("AUDIO_ANALYSIS_MAX_SECONDS", "180"))
    )
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_image_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
    )
    openai_image_quality: str = field(
        default_factory=lambda: os.getenv("OPENAI_IMAGE_QUALITY", "medium")
    )
    openai_concept_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_CONCEPT_MODEL", "gpt-5.6-luna")
    )
    use_ai_creative_director: bool = field(
        default_factory=lambda: _env_bool("USE_AI_CREATIVE_DIRECTOR", True)
    )
    openai_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("OPENAI_TIMEOUT_SECONDS", "150"))
    )
    retry_max_attempts: int = field(
        default_factory=lambda: int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
    )
    retry_base_delay_seconds: float = field(
        default_factory=lambda: float(os.getenv("RETRY_BASE_DELAY_SECONDS", "0.75"))
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        )
    )
    auto_create_schema: bool = field(
        default_factory=lambda: _env_bool("AUTO_CREATE_SCHEMA", True)
    )
    allow_mock_images: bool = field(
        default_factory=lambda: _env_bool("ALLOW_MOCK_IMAGES", False)
    )

    @property
    def max_audio_bytes(self) -> int:
        return self.max_audio_mb * 1024 * 1024
