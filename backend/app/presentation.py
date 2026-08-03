from __future__ import annotations

from .models import Generation
from .schemas import (
    AuditEventResponse,
    ConceptResponse,
    GenerationResponse,
    VariationResponse,
    VariationSetResponse,
)


def generation_response(
    generation: Generation, *, cache_hit: bool = False, include_audit: bool = True
) -> GenerationResponse:
    sets = []
    for item in generation.variation_sets:
        concepts_by_id = {concept.id: concept for concept in item.concepts}
        concepts = [
            ConceptResponse(
                id=concept.id,
                ordinal=concept.ordinal,
                name=concept.name,
                subject=concept.subject,
                setting=concept.setting,
                action_or_symbol=concept.action_or_symbol,
                camera=concept.camera,
                medium=concept.medium,
                palette=concept.palette,
                typography_zone=concept.typography_zone,
                image_prompt=concept.image_prompt,
                scores=concept.scores_json,
                total_score=concept.total_score,
                rank=concept.rank,
                selected_for_render=bool(concept.selected_for_render),
            )
            for concept in item.concepts
        ]
        variations = []
        for variation in item.variations:
            concept = concepts_by_id.get(variation.concept_candidate_id)
            variations.append(
                VariationResponse(
                    id=variation.id,
                    position=variation.position,
                    image_url=f"/media/{variation.image_path}",
                    download_url=f"/api/variations/{variation.id}/download",
                    mime_type=variation.mime_type,
                    width=variation.width,
                    height=variation.height,
                    selected=generation.selected_variation_id == variation.id,
                    concept_id=variation.concept_candidate_id,
                    concept_name=concept.name if concept else None,
                    render_index=variation.render_index,
                    rank=variation.rank,
                    selection_tier=variation.selection_tier or "unranked",
                    cover_score=variation.cover_score,
                    thumbnail_score=variation.thumbnail_score,
                    commercial_score=variation.commercial_score,
                    critic_feedback=variation.cover_feedback_json,
                    platform_scores=variation.platform_scores_json,
                    created_at=variation.created_at,
                )
            )
        sets.append(
            VariationSetResponse(
                id=item.id,
                set_number=item.set_number,
                mood_path=item.mood_path,
                prompt=item.prompt,
                requested_count=item.requested_count,
                concept_count=item.concept_count,
                selected_concept_count=item.selected_concept_count,
                renders_per_concept=item.renders_per_concept,
                concepts=concepts,
                winner_variation_id=item.ai_winner_variation_id,
                runner_up_variation_id=item.ai_runner_up_variation_id,
                critic_status=item.critic_status,
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
