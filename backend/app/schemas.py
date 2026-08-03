from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


MoodPath = Literal["auto", "blend", "audio", "lyrics"]


class GenerateRequest(BaseModel):
    mood_path: MoodPath = "auto"
    variation_count: int = Field(default=4, ge=3, le=8)
    run_async: bool = True


class RegenerateRequest(BaseModel):
    mood_path: Literal["blend", "audio", "lyrics"] = "blend"
    variation_count: int = Field(default=4, ge=3, le=8)
    run_async: bool = True


class VariationResponse(BaseModel):
    id: str
    position: int
    image_url: str
    download_url: str
    mime_type: str
    width: int
    height: int
    selected: bool
    created_at: datetime


class VariationSetResponse(BaseModel):
    id: str
    set_number: int
    mood_path: str
    prompt: str
    requested_count: int
    status: str
    error: dict[str, Any] | None
    created_at: datetime
    variations: list[VariationResponse]


class AuditEventResponse(BaseModel):
    id: int
    step: str
    attempt: int
    outcome: str
    message: str | None
    details: dict[str, Any] | None
    created_at: datetime


class GenerationResponse(BaseModel):
    id: str
    collection_id: str
    version: int
    input_hash: str
    status: str
    cache_hit: bool = False
    has_audio: bool
    has_lyrics: bool
    title: str | None
    artist: str | None
    parental_advisory: bool
    analysis: dict[str, Any] | None
    conflict: dict[str, Any] | None
    last_error: dict[str, Any] | None
    selected_variation_id: str | None
    created_at: datetime
    updated_at: datetime
    variation_sets: list[VariationSetResponse]
    audit_events: list[AuditEventResponse] = []


class HistoryResponse(BaseModel):
    collection_id: str
    versions: list[GenerationResponse]


class ErrorResponse(BaseModel):
    detail: str
    code: str
