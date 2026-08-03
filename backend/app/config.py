from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_project_env() -> None:
    """Load the project .env while preserving values already exported by the host."""
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
        return


_load_project_env()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


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
    max_audio_mb: int = field(default_factory=lambda: _env_int("MAX_AUDIO_MB", 30))
    max_lyrics_chars: int = field(default_factory=lambda: _env_int("MAX_LYRICS_CHARS", 50_000))
    audio_analysis_max_seconds: int = field(
        default_factory=lambda: _env_int("AUDIO_ANALYSIS_MAX_SECONDS", 180)
    )

    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_image_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
    )
    openai_image_quality: str = field(
        default_factory=lambda: os.getenv("OPENAI_IMAGE_QUALITY", "medium")
    )
    openai_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("OPENAI_TIMEOUT_SECONDS", "150"))
    )

    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_concept_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_CONCEPT_MODEL", "gemini-3.6-flash")
    )
    gemini_critic_model: str = field(
        default_factory=lambda: os.getenv(
            "GEMINI_CRITIC_MODEL", os.getenv("GEMINI_CONCEPT_MODEL", "gemini-3.6-flash")
        )
    )
    use_gemini_creative_director: bool = field(
        default_factory=lambda: _env_bool("USE_GEMINI_CREATIVE_DIRECTOR", True)
    )

    concept_count: int = field(default_factory=lambda: _env_int("CONCEPT_COUNT", 8))
    selected_concept_count: int = field(
        default_factory=lambda: _env_int("SELECTED_CONCEPT_COUNT", 2)
    )
    renders_per_concept: int = field(
        default_factory=lambda: _env_int("RENDERS_PER_CONCEPT", 2)
    )
    max_parallel_renders: int = field(
        default_factory=lambda: _env_int("MAX_PARALLEL_RENDERS", 2)
    )
    enable_concept_ranking: bool = field(
        default_factory=lambda: _env_bool("ENABLE_CONCEPT_RANKING", True)
    )
    enable_cover_critic: bool = field(
        default_factory=lambda: _env_bool("ENABLE_COVER_CRITIC", True)
    )
    enable_platform_scoring: bool = field(
        default_factory=lambda: _env_bool("ENABLE_PLATFORM_SCORING", True)
    )
    enable_market_positioning: bool = field(
        default_factory=lambda: _env_bool("ENABLE_MARKET_POSITIONING", False)
    )
    enable_commercial_benchmarking: bool = field(
        default_factory=lambda: _env_bool("ENABLE_COMMERCIAL_BENCHMARKING", False)
    )

    retry_max_attempts: int = field(default_factory=lambda: _env_int("RETRY_MAX_ATTEMPTS", 3))
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

    def __post_init__(self) -> None:
        if self.concept_count < 4:
            raise ValueError("CONCEPT_COUNT must be at least 4")
        if not 1 <= self.selected_concept_count <= self.concept_count:
            raise ValueError("SELECTED_CONCEPT_COUNT must be between 1 and CONCEPT_COUNT")
        if self.renders_per_concept < 1:
            raise ValueError("RENDERS_PER_CONCEPT must be at least 1")
        if self.max_parallel_renders < 1:
            raise ValueError("MAX_PARALLEL_RENDERS must be at least 1")

    @property
    def render_count(self) -> int:
        return self.selected_concept_count * self.renders_per_concept

    @property
    def max_audio_bytes(self) -> int:
        return self.max_audio_mb * 1024 * 1024
