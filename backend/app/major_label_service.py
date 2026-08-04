from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat
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
        return list(
            db.scalars(
                select(Generation)
                .options(
                    selectinload(Generation.variation_sets).selectinload(VariationSet.concepts),
                    selectinload(Generation.variation_sets).selectinload(VariationSet.variations),
                )
                .where(Generation.collection_id == collection_id)
                .order_by(Generation.version.desc())
            )
        )

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
            signal,
            mood_path,
            title=generation.title,
            artist=generation.artist,
            parental_advisory=bool(generation.parental_advisory),
            creative_seed=seed,
        )
        creative_direction = analysis.get("creative_direction") or {}
        if isinstance(creative_direction, dict) and creative_direction:
            brand_lock = creative_direction.get("brand_lock")
            regular_direction = {
                key: value
                for key, value in creative_direction.items()
                if key != "brand_lock" and value
            }

            if regular_direction:
                direction_text = "; ".join(
                    f"{key.replace('_', ' ')} = {value}"
                    for key, value in regular_direction.items()
                )
                brief = (
                    f"{brief} USER-SELECTED CREATIVE DIRECTION: {direction_text}. "
                    "Treat these choices as firm art-direction preferences while keeping "
                    "the result commercially credible, song-specific, and non-stereotypical."
                )

            if isinstance(brand_lock, dict) and brand_lock:
                lock_text = "; ".join(
                    f"{key.replace('_', ' ')} = {value}"
                    for key, value in brand_lock.items()
                    if value
                )
                brief = (
                    f"{brief} BRAND / STYLE LOCK — NON-NEGOTIABLE SERIES IDENTITY: "
                    f"{lock_text}. Preserve this visual identity across every cover in "
                    "the EP, album, or single series. Subjects and song-specific stories "
                    "may change, but the aesthetic language, palette family, finish, "
                    "lighting character, texture, and recurring signature details must "
                    "remain visibly related."
                )
        concepts = await self._plan_concepts(db, generation, signal, brief, seed)
        ranking: ConceptRankingResult = await self.concept_ranker.rank(
            concepts=concepts,
            signal=signal,
            title=generation.title,
            artist=generation.artist,
            selected_count=min(self.settings.selected_concept_count, len(concepts)),
        )
        selected_total = max(1, len(ranking.selected_concept_ids))
        variation_set = VariationSet(
            id=str(uuid4()),
            generation_id=generation.id,
            set_number=set_number,
            mood_path=mood_path,
            prompt=brief,
            requested_count=variation_count,
            concept_count=len(concepts),
            selected_concept_count=selected_total,
            renders_per_concept=max(1, (variation_count + selected_total - 1) // selected_total),
            concept_ranking_json=ranking.as_dict(),
            critic_status="pending",
            status="rendering",
        )
        db.add(variation_set)
        db.flush()
        ranked = {item.concept_id: item for item in ranking.ranked_concepts}
        selected = set(ranking.selected_concept_ids)
        for ordinal, concept in enumerate(concepts, 1):
            item = ranked[str(concept["id"])]
            db.add(
                ConceptCandidate(
                    id=str(concept["id"]),
                    variation_set_id=variation_set.id,
                    ordinal=ordinal,
                    name=str(concept.get("name", f"Concept {ordinal}")),
                    subject=str(concept.get("subject", "")),
                    setting=str(concept.get("setting", "")),
                    action_or_symbol=str(concept.get("action_or_symbol", "")),
                    camera=str(concept.get("camera", "")),
                    medium=str(concept.get("medium", "")),
                    palette=str(concept.get("palette", "")),
                    typography_zone=str(concept.get("typography_zone", "")),
                    image_prompt=str(concept.get("image_prompt", "")),
                    scores_json=item.scores,
                    total_score=item.total_score,
                    rank=item.rank,
                    selected_for_render=str(concept["id"]) in selected,
                )
            )
        generation.status = "generating"
        generation.last_error = None
        db.commit()
        await self._fill_set(db, generation, variation_set)

    @staticmethod
    def _previous_concept_prompts(
        db: Session,
        generation_id: str,
    ) -> list[str]:
        prompts: list[str] = []

        variation_set_ids = list(
            db.scalars(
                select(VariationSet.id)
                .where(VariationSet.generation_id == generation_id)
                .order_by(VariationSet.set_number.desc())
                .limit(3)
            )
        )

        for variation_set_id in variation_set_ids:
            concepts = list(
                db.scalars(
                    select(ConceptCandidate)
                    .where(
                        ConceptCandidate.variation_set_id
                        == variation_set_id
                    )
                    .order_by(
                        ConceptCandidate.ordinal,
                        ConceptCandidate.id,
                    )
                )
            )

            if not concepts:
                continue

            prompts.append(
                " | ".join(
                    f"{concept.name}: subject={concept.subject}; "
                    f"setting={concept.setting}; "
                    f"medium={concept.medium}; "
                    f"camera={concept.camera}; "
                    f"direction={concept.image_prompt}"
                    for concept in concepts
                )
            )

        return prompts

    async def _plan_concepts(
        self,
        db: Session,
        generation: Generation,
        signal: dict[str, Any],
        brief: str,
        seed: str,
    ) -> list[dict[str, Any]]:
        generation = self.get(db, generation.id)
        count = self.settings.concept_count
        if self.creative_director is not None:
            try:

                async def operation() -> Any:
                    return await self.creative_director.plan(
                        base_brief=brief,
                        signal=signal,
                        count=count,
                        creative_seed=seed,
                        title=generation.title,
                        artist=generation.artist,
                        previous_prompts=self._previous_concept_prompts(db, generation.id),
                    )

                plan = await with_retry(
                    operation,
                    max_attempts=self.settings.retry_max_attempts,
                    base_delay_seconds=self.settings.retry_base_delay_seconds,
                    on_attempt=lambda attempt, outcome, error: self._retry_audit(
                        db, generation.id, None, "creative_direction", attempt, outcome, error
                    ),
                )
                if len(getattr(plan, "concepts", [])) == count:
                    return [{"id": str(uuid4()), **dict(item)} for item in plan.concepts]
            except Exception as exc:
                self._audit(
                    db,
                    generation.id,
                    "creative_direction_plan",
                    1,
                    "fallback",
                    "Using local eight-concept planner.",
                    self._error_dict(exc),
                )
        return self._fallback_concepts(brief, signal, count)

    async def _fill_set(
        self, db: Session, generation: Generation, variation_set: VariationSet
    ) -> None:
        selected = list(
            db.scalars(
                select(ConceptCandidate)
                .where(
                    ConceptCandidate.variation_set_id == variation_set.id,
                    ConceptCandidate.selected_for_render.is_(True),
                )
                .order_by(ConceptCandidate.rank, ConceptCandidate.ordinal)
            )
        )
        if not selected:
            raise ValueError("No ranked concepts available")
        existing = {
            row.position
            for row in db.scalars(
                select(Variation).where(Variation.variation_set_id == variation_set.id)
            )
        }
        preset = get_style_preset(self._style_preset_name(generation, variation_set))
        failure: Exception | None = None
        for position in range(1, variation_set.requested_count + 1):
            if position in existing:
                continue
            concept = selected[(position - 1) % len(selected)]
            render_index = ((position - 1) // len(selected)) + 1
            prompt = build_render_prompt(
                base_brief=variation_set.prompt,
                concept=self._concept_payload(concept),
                render_index=render_index,
                style_preset=preset,
            )
            try:

                async def operation() -> Any:
                    exact = getattr(self.image_client, "generate_exact", None)
                    return (
                        await exact(prompt, position)
                        if exact
                        else await self.image_client.generate(prompt, position)
                    )

                generated = await with_retry(
                    operation,
                    max_attempts=self.settings.retry_max_attempts,
                    base_delay_seconds=self.settings.retry_base_delay_seconds,
                    on_attempt=lambda attempt, outcome, error, p=position: self._retry_audit(
                        db,
                        generation.id,
                        variation_set.id,
                        f"image_generation_{p}",
                        attempt,
                        outcome,
                        error,
                    ),
                )
                signal = combine_signals(
                    (generation.analysis_json or {}).get("audio"),
                    (generation.analysis_json or {}).get("lyrics"),
                    mood_path=variation_set.mood_path,
                )
                typography_style = choose_typography_style(signal, position)
                cover_bytes = self._compose_release_text(
                    generated.content,
                    generation=generation,
                    concept=concept,
                    position=position,
                    typography_style=typography_style,
                )
                relative, width, height = self.storage.save_image(
                    generation.id,
                    variation_set.id,
                    position,
                    cover_bytes,
                )
                db.add(
                    Variation(
                        id=str(uuid4()),
                        variation_set_id=variation_set.id,
                        concept_candidate_id=concept.id,
                        position=position,
                        render_index=render_index,
                        render_prompt=prompt,
                        image_path=relative,
                        mime_type="image/png",
                        width=width,
                        height=height,
                        openai_request_id=generated.request_id,
                    )
                )
                db.commit()
            except Exception as exc:
                failure = exc
                break
        completed = (
            db.scalar(
                select(func.count(Variation.id)).where(
                    Variation.variation_set_id == variation_set.id
                )
            )
            or 0
        )
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
                "code": "image_failed",
                "message": "No images were generated.",
            }
        db.commit()

    def _compose_release_text(
        self,
        raw: bytes,
        *,
        generation: Generation,
        concept: ConceptCandidate,
        position: int,
        typography_style: str,
    ) -> bytes:
        # Apply the locked finish before crisp typography is composited.
        creative_direction = (generation.analysis_json or {}).get("creative_direction") or {}
        brand_lock = (
            creative_direction.get("brand_lock")
            if isinstance(creative_direction, dict)
            else None
        )
        brand_finish = (
            brand_lock.get("finish")
            if isinstance(brand_lock, dict)
            else None
        )

        if (
            not generation.title
            and not generation.artist
            and not generation.parental_advisory
            and not brand_finish
        ):
            return raw

        with Image.open(BytesIO(raw)) as source:
            image = ImageOps.fit(
                source.convert("RGB"),
                (1000, 1000),
                method=Image.Resampling.LANCZOS,
            )

        if brand_finish:
            image = self._apply_brand_finish(image, brand_finish)

        if generation.title or generation.artist or generation.parental_advisory:
            layout = self._typography_layout(image, concept.typography_zone, position)
            composed = self.storage._apply_release_text(
                image,
                title=generation.title,
                artist=generation.artist,
                parental_advisory=bool(generation.parental_advisory),
                position=layout,
                typography_style=typography_style,
            )
        else:
            composed = image

        output = BytesIO()
        composed.save(output, format="PNG", optimize=True)
        return output.getvalue()

    @staticmethod
    def _apply_brand_finish(image: Image.Image, finish: str) -> Image.Image:
        # Repeatable series finish applied before title and artist text.
        value = " ".join((finish or "").lower().split())
        base = image.convert("RGB")

        if value == "warm film":
            warmed = Image.blend(
                base,
                Image.new("RGB", base.size, (244, 176, 112)),
                0.08,
            )
            warmed = ImageEnhance.Color(warmed).enhance(0.94)
            return ImageEnhance.Contrast(warmed).enhance(0.98)

        if value == "cool cinematic":
            cooled = Image.blend(
                base,
                Image.new("RGB", base.size, (78, 116, 166)),
                0.07,
            )
            cooled = ImageEnhance.Color(cooled).enhance(0.92)
            return ImageEnhance.Contrast(cooled).enhance(1.08)

        if value == "vintage print":
            gray = ImageOps.grayscale(base)
            sepia = ImageOps.colorize(gray, "#34251d", "#ead9b7")
            printed = Image.blend(base, sepia, 0.34)
            printed = ImageEnhance.Color(printed).enhance(0.82)
            return ImageEnhance.Contrast(printed).enhance(0.96)

        if value == "high contrast":
            contrasted = ImageEnhance.Contrast(base).enhance(1.2)
            return ImageEnhance.Color(contrasted).enhance(1.06)

        if value == "soft glow":
            glow = base.filter(ImageFilter.GaussianBlur(radius=7))
            softened = Image.blend(base, glow, 0.22)
            return ImageEnhance.Brightness(softened).enhance(1.03)

        if value == "black and white":
            monochrome = ImageOps.grayscale(base).convert("RGB")
            return ImageEnhance.Contrast(monochrome).enhance(1.1)

        if value == "grainy documentary":
            documentary = ImageEnhance.Color(base).enhance(0.72)
            documentary = ImageEnhance.Contrast(documentary).enhance(1.13)
            noise = Image.effect_noise(base.size, 14).convert("RGB")
            return Image.blend(documentary, noise, 0.055)

        clean = ImageEnhance.Contrast(base).enhance(1.045)
        clean = ImageEnhance.Color(clean).enhance(1.02)
        return ImageEnhance.Sharpness(clean).enhance(1.08)

    @classmethod
    def _typography_layout(cls, image: Image.Image, requested_zone: str | None, fallback: int) -> int:
        """Resolve a requested safe zone and reject it when the rendered area is too busy."""
        requested = cls._requested_layout(requested_zone)
        scores = cls._zone_complexity_scores(image)
        best = min(scores, key=scores.get)
        if requested is None:
            return best

        best_score = max(scores[best], 0.01)
        return requested if scores[requested] <= best_score * 1.8 else best

    @staticmethod
    def _requested_layout(zone: str | None) -> int | None:
        value = " ".join((zone or "").lower().replace("_", " ").replace("-", " ").split())
        if not value:
            return None
        if any(term in value for term in ("top center", "upper center", "upper right", "top right")):
            return 4
        if any(term in value for term in ("upper left", "top left", "beside shoulder")):
            return 1
        if any(term in value for term in ("lower left", "bottom left")):
            return 2
        if any(term in value for term in ("bottom center", "lower center", "bottom band", "lower right", "bottom right")):
            return 5
        if any(term in value for term in ("lower third", "bottom third")):
            return 3
        if "upper" in value or "top" in value:
            return 1
        if "lower" in value or "bottom" in value:
            return 3
        if "edge" in value:
            return 1
        return None

    @staticmethod
    def _zone_complexity_scores(image: Image.Image) -> dict[int, float]:
        zones = {
            1: (40, 28, 930, 370),
            2: (38, 620, 925, 955),
            3: (38, 610, 955, 930),
            4: (45, 25, 955, 335),
            5: (45, 635, 955, 950),
        }
        gray = image.convert("L")
        scores: dict[int, float] = {}
        for layout, box in zones.items():
            crop = gray.crop(box).resize((220, 90), Image.Resampling.BILINEAR)
            edges = crop.filter(ImageFilter.FIND_EDGES)
            edge_mean = float(ImageStat.Stat(edges).mean[0])
            tonal_variance = float(ImageStat.Stat(crop).var[0]) ** 0.5
            scores[layout] = edge_mean + tonal_variance * 0.18
        return scores

    async def _critique_set(
        self, db: Session, generation: Generation, variation_set: VariationSet
    ) -> None:
        variations = list(
            db.scalars(
                select(Variation)
                .where(Variation.variation_set_id == variation_set.id)
                .order_by(Variation.position)
            )
        )
        concepts = {
            item.id: item
            for item in db.scalars(
                select(ConceptCandidate).where(
                    ConceptCandidate.variation_set_id == variation_set.id
                )
            )
        }
        variation_set.critic_status = "critiquing"
        db.commit()
        try:
            result = await self.cover_critic.evaluate(
                covers=[
                    CoverInput(
                        variation_id=row.id,
                        image_bytes=Path(self.storage.absolute(row.image_path)).read_bytes(),
                        concept_name=(
                            concepts[row.concept_candidate_id].name
                            if row.concept_candidate_id in concepts
                            else ""
                        ),
                        concept_prompt=row.render_prompt or "",
                    )
                    for row in variations
                ],
                signal=combine_signals(
                    (generation.analysis_json or {}).get("audio"),
                    (generation.analysis_json or {}).get("lyrics"),
                    mood_path=variation_set.mood_path,
                ),
                title=generation.title,
                artist=generation.artist,
            )
            by_id = {item.variation_id: item for item in result.evaluations}
            for row in variations:
                item = by_id[row.id]
                row.critic_scores_json = item.scores
                row.cover_feedback_json = {
                    "strengths": item.strengths,
                    "weaknesses": item.weaknesses,
                    "improvement_instructions": item.improvement_instructions,
                }
                row.platform_scores_json = item.platform_scores
                row.cover_score = item.cover_score
                row.thumbnail_score = round(
                    float(item.scores.get("thumbnail_visibility", 0)) * 10, 2
                )
                row.commercial_score = round(
                    float(item.scores.get("commercial_quality", 0)) * 10, 2
                )
                row.rank = item.rank
                row.selection_tier = (
                    "winner"
                    if row.id == result.winner_id
                    else "runner_up"
                    if row.id == result.runner_up_id
                    else "remaining"
                )
            variation_set.ai_winner_variation_id = result.winner_id
            variation_set.ai_runner_up_variation_id = result.runner_up_id
            variation_set.critic_status = "degraded" if result.degraded else "complete"
            variation_set.critic_error_json = (
                {"message": result.degraded_reason} if result.degraded_reason else None
            )
            db.commit()
        except Exception as exc:
            variation_set.critic_status = "failed"
            variation_set.critic_error_json = self._error_dict(exc)
            db.commit()

    @staticmethod
    def _concept_payload(item: ConceptCandidate) -> dict[str, Any]:
        return {
            name: getattr(item, name)
            for name in (
                "id",
                "name",
                "subject",
                "setting",
                "action_or_symbol",
                "camera",
                "medium",
                "palette",
                "typography_zone",
                "image_prompt",
            )
        }

    def _style_preset_name(
        self, generation: Generation, variation_set: VariationSet
    ) -> StylePresetName:
        signal = combine_signals(
            (generation.analysis_json or {}).get("audio"),
            (generation.analysis_json or {}).get("lyrics"),
            mood_path=variation_set.mood_path,
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
        return next(
            (preset for terms, preset in mappings if any(term in genre for term in terms)),
            StylePresetName.MAJOR_LABEL_POP,
        )

    @staticmethod
    def _fallback_concepts(
        brief: str, signal: dict[str, Any], count: int
    ) -> list[dict[str, Any]]:
        clue = str(
            (signal.get("themes") or signal.get("imagery") or ["the song's emotional turn"])[
                0
            ]
        )
        directions = [
            (
                "Immediate Hook",
                "one unmistakable physical symbol",
                "controlled editorial set",
                "50mm eye-level",
                "premium editorial photography",
                "two tones plus one accent",
                "upper-left",
            ),
            (
                "Tactile Evidence",
                "handmade object still-life",
                "real worktable",
                "overhead macro",
                "tactile still-life photography",
                "warm neutrals",
                "lower-right",
            ),
            (
                "No-Person Horizon",
                "an altered environment with no people",
                "open natural location",
                "wide 28mm",
                "atmospheric location photography",
                "restrained sky tones",
                "top-center",
            ),
            (
                "Character Editorial",
                "one character and one revealing gesture",
                "minimal real interior",
                "85mm off-center",
                "fashion editorial photography",
                "neutrals plus jewel tone",
                "beside shoulder",
            ),
            (
                "Print Campaign",
                "one graphic icon",
                "physical paper field",
                "front-facing",
                "screenprint and collage",
                "three-ink palette",
                "bottom band",
            ),
            (
                "After the Event",
                "one displaced object",
                "believable aftermath location",
                "low 35mm",
                "documentary photography",
                "muted plus luminous accent",
                "upper-right",
            ),
            (
                "Unexpected Viewpoint",
                "reflection or partial silhouette",
                "through glass or water",
                "oblique angle",
                "in-camera experimental photography",
                "deep neutrals",
                "one edge",
            ),
            (
                "Physical Sculpture",
                "one constructed sculptural object",
                "gallery-like practical set",
                "three-quarter medium format",
                "hand-built sculpture photography",
                "monochrome plus contrast",
                "background zone",
            ),
        ]
        output = []
        for index in range(count):
            name, subject, setting, camera, medium, palette, zone = directions[
                index % len(directions)
            ]
            output.append(
                {
                    "id": str(uuid4()),
                    "name": name,
                    "subject": f"{subject} representing {clue}",
                    "setting": setting,
                    "action_or_symbol": "a visible change, tension, or aftermath tells the story",
                    "camera": camera,
                    "medium": medium,
                    "palette": palette,
                    "typography_zone": zone,
                    "image_prompt": (
                        f"Square commercial album cover. {subject} representing {clue}. "
                        f"{setting}. Camera: {camera}. Medium: {medium}. Palette: {palette}. "
                        f"Reserve {zone} for typography. Emotional context: {brief[:900]}. "
                        "No text, logos, or watermarks."
                    ),
                }
            )
        return output
