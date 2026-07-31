from __future__ import annotations

from dataclasses import dataclass
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .audio_analysis import AudioAnalyzer
from .config import Settings
from .database import create_database
from .image_client import OpenAIImageClient
from .lyrics_analysis import LyricsAnalyzer
from .routers.generations import router
from .service import GenerationService
from .storage import LocalStorage


@dataclass(slots=True)
class AppDependencies:
    audio_analyzer: object | None = None
    lyrics_analyzer: object | None = None
    image_client: object | None = None


def create_app(
    settings: Settings | None = None, dependencies: AppDependencies | None = None
) -> FastAPI:
    settings = settings or Settings()
    dependencies = dependencies or AppDependencies()
    database = create_database(settings.database_url)
    storage = LocalStorage(settings.storage_root)
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
    generation_service = GenerationService(
        settings=settings,
        database=database,
        storage=storage,
        audio_analyzer=audio_analyzer,
        lyrics_analyzer=lyrics_analyzer,
        image_client=image_client,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.auto_create_schema:
            database.create_all()
        yield

    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
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
        return {"status": "ok"}

    if settings.frontend_root.exists():
        app.mount("/", StaticFiles(directory=settings.frontend_root, html=True), name="frontend")

    return app


app = create_app()
