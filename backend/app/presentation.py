from __future__ import annotations

from .models import Generation
from .schemas import (
    AuditEventResponse,
    GenerationResponse,
    VariationResponse,
    VariationSetResponse,
)


def generation_response(
    generation: Generation, *, cache_hit: bool = False, include_audit: bool = True
) -> GenerationResponse:
    sets = []
    for item in generation.variation_sets:
        variations = [
            VariationResponse(
                id=variation.id,
                position=variation.position,
                image_url=f"/media/{variation.image_path}",
                download_url=f"/api/variations/{variation.id}/download",
                mime_type=variation.mime_type,
                width=variation.width,
                height=variation.height,
                selected=generation.selected_variation_id == variation.id,
                created_at=variation.created_at,
            )
            for variation in item.variations
        ]
        sets.append(
            VariationSetResponse(
                id=item.id,
                set_number=item.set_number,
                mood_path=item.mood_path,
                prompt=item.prompt,
                requested_count=item.requested_count,
                status=item.status,
                error=item.error_json,
                created_at=item.created_at,
                variations=variations,
            )
        )
    audit = (
        [
            AuditEventResponse(
                id=event.id,
                step=event.step,
                attempt=event.attempt,
                outcome=event.outcome,
                message=event.message,
                details=event.details_json,
                created_at=event.created_at,
            )
            for event in generation.audit_events
        ]
        if include_audit
        else []
    )
    return GenerationResponse(
        id=generation.id,
        collection_id=generation.collection_id,
        version=generation.version,
        input_hash=generation.input_hash,
        status=generation.status,
        cache_hit=cache_hit,
        has_audio=bool(generation.audio_path),
        has_lyrics=bool(generation.lyrics_text),
        title=generation.title,
        artist=generation.artist,
        parental_advisory=bool(generation.parental_advisory),
        analysis=generation.analysis_json,
        conflict=generation.conflict_json,
        last_error=generation.last_error,
        selected_variation_id=generation.selected_variation_id,
        created_at=generation.created_at,
        updated_at=generation.updated_at,
        variation_sets=sets,
        audit_events=audit,
    )
