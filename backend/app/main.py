from __future__ import annotations

from dataclasses import dataclass
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .audio_analysis import AudioAnalyzer
from .concept_ranking import GeminiConceptRanker
from .config import Settings
from .cover_critic import GeminiCoverCritic
from .creative_director import GeminiCreativeDirector
from .database import create_database
from .image_client import OpenAIImageClient
from .lyrics_analysis import LyricsAnalyzer
from .major_label_service import MajorLabelGenerationService
from .routers.generations import router
from .storage import LocalStorage


@dataclass(slots=True)
class AppDependencies:
    audio_analyzer: object | None = None
    lyrics_analyzer: object | None = None
    image_client: object | None = None
    creative_director: object | None = None
    concept_ranker: object | None = None
    cover_critic: object | None = None


def create_app(
    settings: Settings | None = None, dependencies: AppDependencies | None = None
) -> FastAPI:
    settings = settings or Settings()
    dependencies = dependencies or AppDependencies()
    database = create_database(settings.database_url)
    storage = LocalStorage(settings.storage_root)
    storage.root.mkdir(parents=True, exist_ok=True)
    audio_analyzer = dependencies.audio_analyzer or AudioAnalyzer(
        settings.audio_analysis_max_seconds
    )
    lyrics_analyzer = dependencies.lyrics_analyzer or LyricsAnalyzer()
    image_client = dependencies.image_client or OpenAIImageClient(
        api_key=settings.openai_api_key,
        model=settings.openai_image_model,
        quality=settings.openai_image_quality,
        timeout_seconds=settings.openai_timeout_seconds,
        allow_mock_images=settings.allow_mock_images,
    )
    creative_director = dependencies.creative_director or GeminiCreativeDirector(
        api_key=settings.gemini_api_key,
        model=settings.gemini_concept_model,
        timeout_seconds=min(settings.openai_timeout_seconds, 90),
        enabled=settings.use_gemini_creative_director,
    )
    concept_ranker = dependencies.concept_ranker or GeminiConceptRanker(
        api_key=settings.gemini_api_key,
        model=settings.gemini_concept_model,
        timeout_seconds=min(settings.openai_timeout_seconds, 90),
        enabled=settings.enable_concept_ranking,
    )
    cover_critic = dependencies.cover_critic or GeminiCoverCritic(
        api_key=settings.gemini_api_key,
        model=settings.gemini_critic_model,
        timeout_seconds=min(settings.openai_timeout_seconds, 120),
        enabled=settings.enable_cover_critic,
    )
    generation_service = MajorLabelGenerationService(
        settings=settings,
        database=database,
        storage=storage,
        audio_analyzer=audio_analyzer,
        lyrics_analyzer=lyrics_analyzer,
        image_client=image_client,
        creative_director=creative_director,
        concept_ranker=concept_ranker,
        cover_critic=cover_critic,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.auto_create_schema:
            database.create_all()
        yield

    app = FastAPI(title=settings.app_name, version="1.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.database = database
    app.state.generation_service = generation_service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.mount("/media", StaticFiles(directory=settings.storage_root), name="media")

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "pipeline": {
                "concept_count": settings.concept_count,
                "selected_concept_count": settings.selected_concept_count,
                "renders_per_concept": settings.renders_per_concept,
                "render_count": settings.render_count,
            },
            "providers": {
                "gemini_creative_director": {
                    "configured": bool(settings.gemini_api_key),
                    "model": settings.gemini_concept_model,
                },
                "gemini_concept_ranker": {
                    "configured": bool(settings.gemini_api_key),
                    "enabled": settings.enable_concept_ranking,
                    "model": settings.gemini_concept_model,
                },
                "gemini_cover_critic": {
                    "configured": bool(settings.gemini_api_key),
                    "enabled": settings.enable_cover_critic,
                    "model": settings.gemini_critic_model,
                },
                "openai_images": {
                    "configured": bool(settings.openai_api_key),
                    "model": settings.openai_image_model,
                },
            },
        }

    if settings.frontend_root.exists():
        app.mount("/", StaticFiles(directory=settings.frontend_root, html=True), name="frontend")

    return app


app = create_app()
