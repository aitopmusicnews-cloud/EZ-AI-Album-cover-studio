from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..metrics import collection_metrics
from ..presentation import generation_response
from ..schemas import (
    CollectionMetricsResponse,
    GenerationResponse,
    HistoryResponse,
    RegenerateRequest,
)
from ..validation import read_lyrics_file, read_validated_mp3, sanitize_lyrics, sanitize_metadata_text


router = APIRouter(prefix="/api", tags=["album-covers"])


def get_db(request: Request):
    yield from request.app.state.database.session()


def service(request: Request):
    return request.app.state.generation_service


@router.post("/generations", response_model=GenerationResponse)
async def create_generation(
    response: Response,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    audio: UploadFile | None = File(default=None),
    lyrics_file: UploadFile | None = File(default=None),
    lyrics_text: str | None = Form(default=None),
    title: str | None = Form(default=None),
    artist: str | None = Form(default=None),
    parental_advisory: bool = Form(default=False),
    collection_id: str | None = Form(default=None),
    mood_path: str = Form(default="auto", pattern="^(auto|blend|audio|lyrics)$"),
    variation_count: int = Form(default=4, ge=3, le=5),
    run_async: bool = Form(default=True),
):
    settings = request.app.state.settings
    audio_bytes = await read_validated_mp3(audio, settings.max_audio_bytes) if audio else None
    file_lyrics = await read_lyrics_file(lyrics_file, settings.max_lyrics_chars) if lyrics_file else ""
    pasted_lyrics = sanitize_lyrics(lyrics_text or "", settings.max_lyrics_chars)
    combined_lyrics = "\n\n".join(part for part in (pasted_lyrics, file_lyrics) if part).strip() or None
    clean_title = sanitize_metadata_text(title, field_name="Title")
    clean_artist = sanitize_metadata_text(artist, field_name="Artist")
    if not audio_bytes and not combined_lyrics:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="Upload an MP3, provide lyrics, or provide both.")

    svc = service(request)
    created = svc.create_or_get(
        db,
        collection_id=collection_id,
        audio_bytes=audio_bytes,
        lyrics_text=combined_lyrics,
        title=clean_title,
        artist=clean_artist,
        parental_advisory=parental_advisory,
    )
    if created.cache_hit:
        response.status_code = 200
        return generation_response(created.generation, cache_hit=True)

    if run_async:
        background_tasks.add_task(
            svc.process_generation, created.generation.id, variation_count, mood_path
        )
        response.status_code = 202
        return generation_response(created.generation)

    await svc.process_generation(created.generation.id, variation_count, mood_path)
    response.status_code = 201
    return generation_response(svc.get(db, created.generation.id))


@router.get("/generations/{generation_id}", response_model=GenerationResponse)
def get_generation(generation_id: str, request: Request, db: Session = Depends(get_db)):
    return generation_response(service(request).get(db, generation_id))


@router.get("/collections/{collection_id}/versions", response_model=HistoryResponse)
def get_history(collection_id: str, request: Request, db: Session = Depends(get_db)):
    versions = service(request).history(db, collection_id)
    return HistoryResponse(
        collection_id=collection_id,
        versions=[generation_response(item, include_audit=False) for item in versions],
    )


@router.get(
    "/collections/{collection_id}/metrics",
    response_model=CollectionMetricsResponse,
)
def get_metrics(collection_id: str, db: Session = Depends(get_db)):
    return CollectionMetricsResponse(**collection_metrics(db, collection_id))


@router.post("/generations/{generation_id}/generate", response_model=GenerationResponse)
async def generate_after_choice(
    generation_id: str,
    payload: RegenerateRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    svc = service(request)
    svc.get(db, generation_id)
    if payload.run_async:
        background_tasks.add_task(
            svc.regenerate, generation_id, payload.variation_count, payload.mood_path
        )
        response.status_code = 202
    else:
        await svc.regenerate(generation_id, payload.variation_count, payload.mood_path)
        response.status_code = 200
    return generation_response(svc.get(db, generation_id))


@router.post("/generations/{generation_id}/regenerate", response_model=GenerationResponse)
async def regenerate(
    generation_id: str,
    payload: RegenerateRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    svc = service(request)
    svc.get(db, generation_id)
    if payload.run_async:
        background_tasks.add_task(
            svc.regenerate, generation_id, payload.variation_count, payload.mood_path
        )
        response.status_code = 202
    else:
        await svc.regenerate(generation_id, payload.variation_count, payload.mood_path)
        response.status_code = 200
    return generation_response(svc.get(db, generation_id))


@router.post("/generations/{generation_id}/improve", response_model=GenerationResponse)
async def generate_better(
    generation_id: str,
    payload: RegenerateRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    svc = service(request)
    svc.get(db, generation_id)
    improve = getattr(svc, "generate_better", None)
    if improve is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="Generate Better is not enabled.")
    if payload.run_async:
        background_tasks.add_task(
            improve, generation_id, payload.variation_count, payload.mood_path
        )
        response.status_code = 202
    else:
        await improve(generation_id, payload.variation_count, payload.mood_path)
        response.status_code = 200
    return generation_response(svc.get(db, generation_id))


@router.post("/generations/{generation_id}/retry", response_model=GenerationResponse)
async def retry_generation(
    generation_id: str,
    response: Response,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    run_async: bool = True,
):
    svc = service(request)
    svc.get(db, generation_id)
    if run_async:
        background_tasks.add_task(svc.retry_failed, generation_id)
        response.status_code = 202
    else:
        await svc.retry_failed(generation_id)
        response.status_code = 200
    return generation_response(svc.get(db, generation_id))


@router.post("/variations/{variation_id}/select", response_model=GenerationResponse)
def select_variation(variation_id: str, request: Request, db: Session = Depends(get_db)):
    return generation_response(service(request).select_variation(db, variation_id))


@router.get("/variations/{variation_id}/download")
def download_variation(variation_id: str, request: Request, db: Session = Depends(get_db)):
    path, mime_type = service(request).variation_file(db, variation_id)
    return FileResponse(
        path,
        media_type=mime_type,
        filename=f"album-cover-{variation_id}.png",
        content_disposition_type="attachment",
    )
