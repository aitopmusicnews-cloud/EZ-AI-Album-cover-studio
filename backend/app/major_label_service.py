from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .concept_ranking import ConceptRankingResult
from .cover_critic import CoverInput
from .models import ConceptCandidate, Generation, Variation, VariationSet
from .prompts import build_image_prompt
from .render_prompts import build_render_prompt
from .retry import with_retry
from .service import GenerationService
from .signals import combine_signals
from .style_presets import StylePresetName, get_style_preset
from .typography import choose_typography_style


class MajorLabelGenerationService(GenerationService):
    """Eight concepts -> top two -> four covers -> critic ranking."""

    def __init__(self, *, concept_ranker: object, cover_critic: object, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.concept_ranker = concept_ranker
        self.cover_critic = cover_critic

    def get(self, db: Session, generation_id: str) -> Generation:
        generation = db.scalar(
            select(Generation)
            .options(
                selectinload(Generation.variation_sets).selectinload(VariationSet.concepts),
                selectinload(Generation.variation_sets).selectinload(VariationSet.variations),
                selectinload(Generation.audit_events),
            )
            .where(Generation.id == generation_id)
            .execution_options(populate_existing=True)
        )
        if generation is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Generation not found.")
        return generation

    def history(self, db: Session, collection_id: str) -> list[Generation]:
        return list(db.scalars(
            select(Generation)
            .options(
                selectinload(Generation.variation_sets).selectinload(VariationSet.concepts),
                selectinload(Generation.variation_sets).selectinload(VariationSet.variations),
            )
            .where(Generation.collection_id == collection_id)
            .order_by(Generation.version.desc())
        ))

    async def _create_and_fill_set(
        self, db: Session, generation: Generation, variation_count: int, mood_path: str
    ) -> None:
        if not 3 <= variation_count <= 8:
            raise ValueError("variation_count must be between 3 and 8")
        analysis = generation.analysis_json or {}
        signal = combine_signals(analysis.get("audio"), analysis.get("lyrics"), mood_path=mood_path)
        set_number = max((item.set_number for item in generation.variation_sets), default=0) + 1
        seed = f"{generation.input_hash}:set:{set_number}:path:{mood_path}"
        brief = build_image_prompt(
            signal, mood_path, title=generation.title, artist=generation.artist,
            parental_advisory=bool(generation.parental_advisory), creative_seed=seed,
        )
        concepts = await self._plan_concepts(db, generation, signal, brief, seed)
        ranking: ConceptRankingResult = await self.concept_ranker.rank(
            concepts=concepts, signal=signal, title=generation.title, artist=generation.artist,
            selected_count=min(self.settings.selected_concept_count, len(concepts)),
        )
        selected_total = max(1, len(ranking.selected_concept_ids))
        variation_set = VariationSet(
            id=str(uuid4()), generation_id=generation.id, set_number=set_number,
            mood_path=mood_path, prompt=brief, requested_count=variation_count,
            concept_count=len(concepts), selected_concept_count=selected_total,
            renders_per_concept=max(1, (variation_count + selected_total - 1) // selected_total),
            concept_ranking_json=ranking.as_dict(), critic_status="pending", status="rendering",
        )
        db.add(variation_set)
        db.flush()
        ranked = {item.concept_id: item for item in ranking.ranked_concepts}
        selected = set(ranking.selected_concept_ids)
        for ordinal, concept in enumerate(concepts, 1):
            item = ranked[str(concept["id"])]
            db.add(ConceptCandidate(
                id=str(concept["id"]), variation_set_id=variation_set.id, ordinal=ordinal,
                name=str(concept.get("name", f"Concept {ordinal}")),
                subject=str(concept.get("subject", "")), setting=str(concept.get("setting", "")),
                action_or_symbol=str(concept.get("action_or_symbol", "")),
                camera=str(concept.get("camera", "")), medium=str(concept.get("medium", "")),
                palette=str(concept.get("palette", "")), typography_zone=str(concept.get("typography_zone", "")),
                image_prompt=str(concept.get("image_prompt", "")), scores_json=item.scores,
                total_score=item.total_score, rank=item.rank,
                selected_for_render=str(concept["id"]) in selected,
            ))
        generation.status = "generating"
        generation.last_error = None
        db.commit()
        await self._fill_set(db, generation, variation_set)

    async def _plan_concepts(
        self, db: Session, generation: Generation, signal: dict[str, Any], brief: str, seed: str
    ) -> list[dict[str, Any]]:
        count = self.settings.concept_count
        if self.creative_director is not None:
            try:
                async def operation() -> Any:
                    return await self.creative_director.plan(
                        base_brief=brief, signal=signal, count=count, creative_seed=seed,
                        title=generation.title, artist=generation.artist,
                        previous_prompts=[item.prompt for item in generation.variation_sets[-3:]],
                    )
                plan = await with_retry(
                    operation, max_attempts=self.settings.retry_max_attempts,
                    base_delay_seconds=self.settings.retry_base_delay_seconds,
                    on_attempt=lambda attempt, outcome, error: self._retry_audit(
                        db, generation.id, None, "creative_direction", attempt, outcome, error
                    ),
                )
                if len(getattr(plan, "concepts", [])) == count:
                    return [{"id": str(uuid4()), **dict(item)} for item in plan.concepts]
            except Exception as exc:
                self._audit(db, generation.id, "creative_direction_plan", 1, "fallback",
                            "Using local eight-concept planner.", self._error_dict(exc))
        return self._fallback_concepts(brief, signal, count)

    async def _fill_set(self, db: Session, generation: Generation, variation_set: VariationSet) -> None:
        selected = list(db.scalars(
            select(ConceptCandidate)
            .where(ConceptCandidate.variation_set_id == variation_set.id,
                   ConceptCandidate.selected_for_render.is_(True))
            .order_by(ConceptCandidate.rank, ConceptCandidate.ordinal)
        ))
        if not selected:
            raise ValueError("No ranked concepts available")
        existing = {row.position for row in db.scalars(
            select(Variation).where(Variation.variation_set_id == variation_set.id)
        )}
        preset = get_style_preset(self._style_preset_name(generation, variation_set))
        failure: Exception | None = None
        for position in range(1, variation_set.requested_count + 1):
            if position in existing:
                continue
            concept = selected[(position - 1) % len(selected)]
            render_index = ((position - 1) // len(selected)) + 1
            prompt = build_render_prompt(
                base_brief=variation_set.prompt, concept=self._concept_payload(concept),
                render_index=render_index, style_preset=preset,
            )
            try:
                async def operation() -> Any:
                    exact = getattr(self.image_client, "generate_exact", None)
                    return await exact(prompt, position) if exact else await self.image_client.generate(prompt, position)
                generated = await with_retry(
                    operation, max_attempts=self.settings.retry_max_attempts,
                    base_delay_seconds=self.settings.retry_base_delay_seconds,
                    on_attempt=lambda attempt, outcome, error, p=position: self._retry_audit(
                        db, generation.id, variation_set.id, f"image_generation_{p}", attempt, outcome, error
                    ),
                )
                signal = combine_signals(
                    (generation.analysis_json or {}).get("audio"),
                    (generation.analysis_json or {}).get("lyrics"), mood_path=variation_set.mood_path,
                )
                relative, width, height = self.storage.save_image(
                    generation.id, variation_set.id, position, generated.content,
                    title=generation.title, artist=generation.artist,
                    parental_advisory=bool(generation.parental_advisory),
                    typography_style=choose_typography_style(signal, position),
                )
                db.add(Variation(
                    id=str(uuid4()), variation_set_id=variation_set.id,
                    concept_candidate_id=concept.id, position=position, render_index=render_index,
                    render_prompt=prompt, image_path=relative, mime_type="image/png",
                    width=width, height=height, openai_request_id=generated.request_id,
                ))
                db.commit()
            except Exception as exc:
                failure = exc
                break
        completed = db.scalar(select(func.count(Variation.id)).where(
            Variation.variation_set_id == variation_set.id
        )) or 0
        if completed >= 2:
            await self._critique_set(db, generation, variation_set)
        if completed == variation_set.requested_count:
            variation_set.status, generation.status = "complete", "complete"
            variation_set.error_json = generation.last_error = None
        elif completed:
            variation_set.status, generation.status = "partial", "partial"
            variation_set.error_json = generation.last_error = self._error_dict(failure)
        else:
            variation_set.status, generation.status = "failed", "image_failed"
            variation_set.error_json = generation.last_error = self._error_dict(failure) or {
                "code": "image_failed", "message": "No images were generated."
            }
        db.commit()

    async def _critique_set(self, db: Session, generation: Generation, variation_set: VariationSet) -> None:
        variations = list(db.scalars(select(Variation).where(
            Variation.variation_set_id == variation_set.id
        ).order_by(Variation.position)))
        concepts = {item.id: item for item in db.scalars(select(ConceptCandidate).where(
            ConceptCandidate.variation_set_id == variation_set.id
        ))}
        variation_set.critic_status = "critiquing"
        db.commit()
        try:
            result = await self.cover_critic.evaluate(
                covers=[CoverInput(
                    variation_id=row.id, image_bytes=Path(self.storage.absolute(row.image_path)).read_bytes(),
                    concept_name=concepts[row.concept_candidate_id].name if row.concept_candidate_id in concepts else "",
                    concept_prompt=row.render_prompt or "",
                ) for row in variations],
                signal=combine_signals(
                    (generation.analysis_json or {}).get("audio"),
                    (generation.analysis_json or {}).get("lyrics"), mood_path=variation_set.mood_path,
                ), title=generation.title, artist=generation.artist,
            )
            by_id = {item.variation_id: item for item in result.evaluations}
            for row in variations:
                item = by_id[row.id]
                row.critic_scores_json = item.scores
                row.cover_feedback_json = {
                    "strengths": item.strengths, "weaknesses": item.weaknesses,
                    "improvement_instructions": item.improvement_instructions,
                }
                row.platform_scores_json = item.platform_scores
                row.cover_score = item.cover_score
                row.thumbnail_score = round(float(item.scores.get("thumbnail_visibility", 0)) * 10, 2)
                row.commercial_score = round(float(item.scores.get("commercial_quality", 0)) * 10, 2)
                row.rank = item.rank
                row.selection_tier = "winner" if row.id == result.winner_id else "runner_up" if row.id == result.runner_up_id else "remaining"
            variation_set.ai_winner_variation_id = result.winner_id
            variation_set.ai_runner_up_variation_id = result.runner_up_id
            variation_set.critic_status = "degraded" if result.degraded else "complete"
            variation_set.critic_error_json = {"message": result.degraded_reason} if result.degraded_reason else None
            db.commit()
        except Exception as exc:
            variation_set.critic_status = "failed"
            variation_set.critic_error_json = self._error_dict(exc)
            db.commit()

    @staticmethod
    def _concept_payload(item: ConceptCandidate) -> dict[str, Any]:
        return {name: getattr(item, name) for name in (
            "id", "name", "subject", "setting", "action_or_symbol", "camera",
            "medium", "palette", "typography_zone", "image_prompt"
        )}

    def _style_preset_name(self, generation: Generation, variation_set: VariationSet) -> StylePresetName:
        signal = combine_signals(
            (generation.analysis_json or {}).get("audio"),
            (generation.analysis_json or {}).get("lyrics"), mood_path=variation_set.mood_path,
        )
        genre = str(signal.get("inferred_genre") or "").lower()
        mappings = (
            (("hip-hop", "hip hop", "rap", "trap"), StylePresetName.HIPHOP_EDITORIAL),
            (("r&b", "rnb", "soul"), StylePresetName.RNB_PREMIUM),
            (("country", "americana", "folk"), StylePresetName.COUNTRY_COMMERCIAL),
            (("rock", "metal", "punk"), StylePresetName.ROCK_PREMIUM),
            (("edm", "electronic", "dance", "house"), StylePresetName.EDM_FESTIVAL),
            (("indie", "alternative", "alt"), StylePresetName.INDIE_ALT),
        )
        return next((preset for terms, preset in mappings if any(term in genre for term in terms)),
                    StylePresetName.MAJOR_LABEL_POP)

    @staticmethod
    def _fallback_concepts(brief: str, signal: dict[str, Any], count: int) -> list[dict[str, Any]]:
        clue = str((signal.get("themes") or signal.get("imagery") or ["the song's emotional turn"])[0])
        directions = [
            ("Immediate Hook", "one unmistakable physical symbol", "controlled editorial set", "50mm eye-level", "premium editorial photography", "two tones plus one accent", "upper-left"),
            ("Tactile Evidence", "handmade object still-life", "real worktable", "overhead macro", "tactile still-life photography", "warm neutrals", "lower-right"),
            ("No-Person Horizon", "an altered environment with no people", "open natural location", "wide 28mm", "atmospheric location photography", "restrained sky tones", "top-center"),
            ("Character Editorial", "one character and one revealing gesture", "minimal real interior", "85mm off-center", "fashion editorial photography", "neutrals plus jewel tone", "beside shoulder"),
            ("Print Campaign", "one graphic icon", "physical paper field", "front-facing", "screenprint and collage", "three-ink palette", "bottom band"),
            ("After the Event", "one displaced object", "believable aftermath location", "low 35mm", "documentary photography", "muted plus luminous accent", "upper-right"),
            ("Unexpected Viewpoint", "reflection or partial silhouette", "through glass or water", "oblique angle", "in-camera experimental photography", "deep neutrals", "one edge"),
            ("Physical Sculpture", "one constructed sculptural object", "gallery-like practical set", "three-quarter medium format", "hand-built sculpture photography", "monochrome plus contrast", "background zone"),
        ]
        output = []
        for index in range(count):
            name, subject, setting, camera, medium, palette, zone = directions[index % len(directions)]
            output.append({
                "id": str(uuid4()), "name": name,
                "subject": f"{subject} representing {clue}", "setting": setting,
                "action_or_symbol": "a visible change, tension, or aftermath tells the story",
                "camera": camera, "medium": medium, "palette": palette,
                "typography_zone": zone,
                "image_prompt": f"Square commercial album cover. {subject} representing {clue}. {setting}. Camera: {camera}. Medium: {medium}. Palette: {palette}. Reserve {zone} for typography. Emotional context: {brief[:900]}. No text, logos, or watermarks.",
            })
        return output
