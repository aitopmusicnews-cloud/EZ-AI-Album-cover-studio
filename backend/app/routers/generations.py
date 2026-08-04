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
    ImproveRequest,
    RegenerateRequest,
)
from ..validation import read_lyrics_file, read_validated_mp3, sanitize_lyrics, sanitize_metadata_text


router = APIRouter(prefix="/api", tags=["album-covers"])
_COMPLETED_STATUSES = {"complete", "partial", "needs_mood_choice"}
_BRAND_FINISH_ALLOWED = {
    "Clean editorial",
    "Warm film",
    "Cool cinematic",
    "Vintage print",
    "High contrast",
    "Soft glow",
    "Black and white",
    "Grainy documentary",
}

_CREATIVE_DIRECTION_ALLOWED = {
    "artist_presentation": {
        "Male artist",
        "Female artist",
        "Duo or group",
        "Nonbinary or androgynous",
        "Do not show the artist",
        "Let AI decide",
    },
    "genre_direction": {
        "Auto-detect from song",
        "Hip-hop / trap",
        "R&B / soul",
        "Pop",
        "Rock / alternative",
        "Country / Americana",
        "Electronic / dance",
        "Gospel / inspirational",
        "Afrobeats / Amapiano",
        "Reggae / dancehall",
        "Latin",
        "Jazz / blues",
        "Other",
    },
    "mood_direction": {
        "Auto-detect from song",
        "Confident / powerful",
        "Romantic / sensual",
        "Dark / moody",
        "Joyful / uplifting",
        "Raw / emotional",
        "Mysterious / cinematic",
        "Energetic / party",
        "Peaceful / reflective",
    },
    "visual_style": {
        "Let AI decide",
        "Photoreal editorial",
        "Luxury / glamour",
        "Gritty street",
        "Minimal / clean",
        "Cinematic story",
        "Retro / vintage",
        "Abstract / symbolic",
        "Illustrated",
    },
    "color_direction": {
        "Let AI decide",
        "Warm tones",
        "Cool tones",
        "Black and white",
        "Dark with neon accents",
        "Earth tones",
        "Pastels",
        "Bold primary colors",
    },
}


def _creative_choice(value: str | None, key: str, default: str) -> str:
    from fastapi import HTTPException

    clean = sanitize_metadata_text(
        value,
        field_name=key.replace("_", " ").title(),
        max_chars=80,
    ) or default
    if clean not in _CREATIVE_DIRECTION_ALLOWED[key]:
        raise HTTPException(status_code=422, detail=f"Invalid {key.replace('_', ' ')}.")
    return clean


def get_db(request: Request):
    yield from request.app.state.database.session()


def service(request: Request):
    return request.app.state.generation_service


def submit_async_job(
    *,
    request: Request,
    background_tasks: BackgroundTasks,
    action: str,
    generation_id: str,
    variation_count: int = 4,
    mood_path: str = "auto",
    user_instructions: str | None = None,
    callback,
    callback_args: tuple = (),
) -> None:
    queue = request.app.state.job_queue
    if queue.enabled:
        try:
            queue.enqueue(
                action=action,
                generation_id=generation_id,
                variation_count=variation_count,
                mood_path=mood_path,
                user_instructions=user_instructions,
            )
        except Exception as exc:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=503,
                detail="The generation queue is temporarily unavailable. Please retry.",
            ) from exc
        return

    background_tasks.add_task(callback, *callback_args)


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
    artist_presentation: str | None = Form(default=None),
    genre_direction: str | None = Form(default=None),
    mood_direction: str | None = Form(default=None),
    visual_style: str | None = Form(default=None),
    color_direction: str | None = Form(default=None),
    creative_idea: str | None = Form(default=None),
    brand_lock_enabled: bool = Form(default=False),
    brand_lock_name: str | None = Form(default=None),
    brand_aesthetic: str | None = Form(default=None),
    brand_palette: str | None = Form(default=None),
    brand_finish: str | None = Form(default=None),
    brand_signature: str | None = Form(default=None),
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
    creative_direction = {
        "artist_presentation": _creative_choice(
            artist_presentation,
            "artist_presentation",
            "Let AI decide",
        ),
        "genre_direction": _creative_choice(
            genre_direction,
            "genre_direction",
            "Auto-detect from song",
        ),
        "mood_direction": _creative_choice(
            mood_direction,
            "mood_direction",
            "Auto-detect from song",
        ),
        "visual_style": _creative_choice(
            visual_style,
            "visual_style",
            "Let AI decide",
        ),
        "color_direction": _creative_choice(
            color_direction,
            "color_direction",
            "Let AI decide",
        ),
    }
    creative_direction = {
        key: value
        for key, value in creative_direction.items()
        if value not in {"Let AI decide", "Auto-detect from song"}
    }
    clean_creative_idea = sanitize_metadata_text(creative_idea, field_name="Creative idea", max_chars=1000)
    if clean_creative_idea:
        creative_direction["creative_idea"] = clean_creative_idea

    if brand_lock_enabled:
        clean_brand_finish = sanitize_metadata_text(
            brand_finish,
            field_name="Brand finish",
            max_chars=80,
        ) or "Clean editorial"
        if clean_brand_finish not in _BRAND_FINISH_ALLOWED:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail="Invalid brand finish.")

        brand_lock = {
            "name": sanitize_metadata_text(
                brand_lock_name,
                field_name="Brand lock name",
                max_chars=100,
            ),
            "aesthetic": sanitize_metadata_text(
                brand_aesthetic,
                field_name="Brand aesthetic",
                max_chars=120,
            ),
            "palette": sanitize_metadata_text(
                brand_palette,
                field_name="Brand palette",
                max_chars=160,
            ),
            "finish": clean_brand_finish,
            "signature": sanitize_metadata_text(
                brand_signature,
                field_name="Brand signature",
                max_chars=500,
            ),
        }
        creative_direction["brand_lock"] = {
            key: value for key, value in brand_lock.items() if value
        }

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
        creative_direction=creative_direction,
        parental_advisory=parental_advisory,
    )

    if created.cache_hit:
        if created.generation.status not in _COMPLETED_STATUSES:
            submit_async_job(
                request=request,
                background_tasks=background_tasks,
                action="process",
                generation_id=created.generation.id,
                variation_count=variation_count,
                mood_path=mood_path,
                callback=svc.process_generation,
                callback_args=(created.generation.id, variation_count, mood_path),
            )
            response.status_code = 202
        else:
            response.status_code = 200
        return generation_response(created.generation, cache_hit=True)

    if request.app.state.job_queue.enabled or run_async:
        submit_async_job(
            request=request,
            background_tasks=background_tasks,
            action="process",
            generation_id=created.generation.id,
            variation_count=variation_count,
            mood_path=mood_path,
            callback=svc.process_generation,
            callback_args=(created.generation.id, variation_count, mood_path),
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
    if request.app.state.job_queue.enabled or payload.run_async:
        submit_async_job(
            request=request,
            background_tasks=background_tasks,
            action="regenerate",
            generation_id=generation_id,
            variation_count=payload.variation_count,
            mood_path=payload.mood_path,
            callback=svc.regenerate,
            callback_args=(generation_id, payload.variation_count, payload.mood_path),
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
    if request.app.state.job_queue.enabled or payload.run_async:
        submit_async_job(
            request=request,
            background_tasks=background_tasks,
            action="regenerate",
            generation_id=generation_id,
            variation_count=payload.variation_count,
            mood_path=payload.mood_path,
            callback=svc.regenerate,
            callback_args=(generation_id, payload.variation_count, payload.mood_path),
        )
        response.status_code = 202
    else:
        await svc.regenerate(generation_id, payload.variation_count, payload.mood_path)
        response.status_code = 200
    return generation_response(svc.get(db, generation_id))


@router.post("/generations/{generation_id}/improve", response_model=GenerationResponse)
async def generate_better(
    generation_id: str,
    payload: ImproveRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    svc = service(request)
    svc.get(db, generation_id)
    user_instructions = sanitize_metadata_text(payload.user_instructions, field_name="Cover edit request", max_chars=1000)
    improve = getattr(svc, "generate_better", None)
    if improve is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="Generate Better is not enabled.")
    if request.app.state.job_queue.enabled or payload.run_async:
        submit_async_job(
            request=request,
            background_tasks=background_tasks,
            action="improve",
            generation_id=generation_id,
            variation_count=payload.variation_count,
            mood_path=payload.mood_path,
            user_instructions=user_instructions,
            callback=improve,
            callback_args=(generation_id, payload.variation_count, payload.mood_path, user_instructions),
        )
        response.status_code = 202
    else:
        await improve(generation_id, payload.variation_count, payload.mood_path, user_instructions)
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
    if request.app.state.job_queue.enabled or run_async:
        submit_async_job(
            request=request,
            background_tasks=background_tasks,
            action="retry",
            generation_id=generation_id,
            callback=svc.retry_failed,
            callback_args=(generation_id,),
        )
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
