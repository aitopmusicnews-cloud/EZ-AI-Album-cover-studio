from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
        default_factory=lambda: os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
    )
    openai_image_quality: str = field(
        default_factory=lambda: os.getenv("OPENAI_IMAGE_QUALITY", "medium")
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
