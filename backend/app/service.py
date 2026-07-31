from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .audio_analysis import AudioAnalyzer
from .config import Settings
from .database import Database
from .errors import AnalysisError, PipelineError
from .image_client import OpenAIImageClient
from .lyrics_analysis import LyricsAnalyzer
from .models import AuditEvent, Generation, Variation, VariationSet
from .prompts import attach_concept_plan, build_image_prompt
from .retry import with_retry
from .signals import combine_signals, detect_conflict
from .storage import LocalStorage
from .typography import choose_typography_style
from .validation import build_input_hash, sha256_bytes


_COLLECTION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
TERMINAL_STATUSES = {
    "complete", "partial", "analysis_failed", "image_failed", "needs_mood_choice"
}


@dataclass(slots=True)
class CreateResult:
    generation: Generation
    cache_hit: bool


class GenerationService:
    def __init__(
        self,
        *,
        settings: Settings,
        database: Database,
        storage: LocalStorage,
        audio_analyzer: AudioAnalyzer,
        lyrics_analyzer: LyricsAnalyzer,
        image_client: OpenAIImageClient,
        creative_director: object | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.storage = storage
        self.audio_analyzer = audio_analyzer
        self.lyrics_analyzer = lyrics_analyzer
        self.image_client = image_client
        self.creative_director = creative_director

    def create_or_get(
        self,
        db: Session,
        *,
        collection_id: str | None,
        audio_bytes: bytes | None,
        lyrics_text: str | None,
        title: str | None,
        artist: str | None,
        parental_advisory: bool,
    ) -> CreateResult:
        collection_id = self._normalize_collection_id(collection_id)
        audio_hash = sha256_bytes(audio_bytes) if audio_bytes else None
        lyrics_hash = sha256_bytes(lyrics_text.encode("utf-8")) if lyrics_text else None
        input_hash = build_input_hash(
            audio_hash, lyrics_hash, title=title, artist=artist, parental_advisory=parental_advisory
        )

        cached = db.scalar(
            select(Generation)
            .where(
                Generation.collection_id == collection_id,
                Generation.input_hash == input_hash,
            )
            .order_by(Generation.version.desc())
            .limit(1)
        )
        if cached:
            self._audit(db, cached.id, "cache_lookup", 1, "hit", "Identical inputs reused.")
            return CreateResult(self.get(db, cached.id), True)

        latest_version = db.scalar(
            select(func.max(Generation.version)).where(Generation.collection_id == collection_id)
        ) or 0
        generation_id = str(uuid4())
        generation = Generation(
            id=generation_id,
            collection_id=collection_id,
            version=latest_version + 1,
            input_hash=input_hash,
            audio_hash=audio_hash,
            lyrics_hash=lyrics_hash,
            lyrics_text=lyrics_text,
            title=title,
            artist=artist,
            parental_advisory=parental_advisory,
            status="queued",
        )
        if audio_bytes:
            generation.audio_path = self.storage.save_audio(generation_id, audio_bytes)
        db.add(generation)
        db.commit()
        self._audit(
            db,
            generation.id,
            "input_acceptance",
            1,
            "succeeded",
            "Immutable input version created.",
            {
                "has_audio": bool(audio_bytes),
                "has_lyrics": bool(lyrics_text),
                "input_hash": input_hash,
                "version": generation.version,
                "title": title,
                "artist": artist,
                "parental_advisory": parental_advisory,
            },
        )
        return CreateResult(self.get(db, generation.id), False)

    async def process_generation(
        self, generation_id: str, variation_count: int = 4, mood_path: str = "auto"
    ) -> None:
        with self.database.session_factory() as db:
            generation = self.get(db, generation_id)
            try:
                ready = await self._ensure_analysis(db, generation)
                if not ready:
                    return
                generation = self.get(db, generation_id)
                conflict = generation.conflict_json
                if conflict and mood_path == "auto":
                    generation.status = "needs_mood_choice"
                    generation.last_error = None
                    db.commit()
                    self._audit(
                        db,
                        generation.id,
                        "conflict_detection",
                        1,
                        "choice_required",
                        conflict.get("reason"),
                        conflict,
                    )
                    return
                resolved_path = self._resolve_path(generation, mood_path)
                await self._create_and_fill_set(db, generation, variation_count, resolved_path)
            except Exception as exc:
                generation = db.get(Generation, generation_id)
                if generation:
                    generation.status = "image_failed" if generation.analysis_json else "analysis_failed"
                    generation.last_error = self._error_dict(exc)
                    db.commit()
                    self._audit(
                        db,
                        generation.id,
                        "pipeline",
                        1,
                        "failed",
                        str(exc),
                        self._error_dict(exc),
                    )

    async def regenerate(
        self, generation_id: str, variation_count: int, mood_path: str
    ) -> None:
        with self.database.session_factory() as db:
            generation = self.get(db, generation_id)
            if not generation.analysis_json:
                await self.process_generation(generation_id, variation_count, mood_path)
                return
            await self._create_and_fill_set(db, generation, variation_count, mood_path)

    async def retry_failed(self, generation_id: str) -> None:
        with self.database.session_factory() as db:
            generation = self.get(db, generation_id)
            if not self._analysis_complete(generation):
                await self.process_generation(generation_id, 4, "auto")
                return
            incomplete = next(
                (
                    item
                    for item in reversed(generation.variation_sets)
                    if item.status in {"failed", "partial", "generating"}
                ),
                None,
            )
            if incomplete:
                await self._fill_set(db, generation, incomplete)
                return
            if generation.status == "needs_mood_choice":
                return
            await self._create_and_fill_set(db, generation, 4, self._resolve_path(generation, "auto"))

    def get(self, db: Session, generation_id: str) -> Generation:
        generation = db.scalar(
            select(Generation)
            .options(
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
                .options(selectinload(Generation.variation_sets).selectinload(VariationSet.variations))
                .where(Generation.collection_id == collection_id)
                .order_by(Generation.version.desc())
            )
        )

    def select_variation(self, db: Session, variation_id: str) -> Generation:
        variation = db.get(Variation, variation_id)
        if variation is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Variation not found.")
        variation_set = db.get(VariationSet, variation.variation_set_id)
        assert variation_set is not None
        generation = db.get(Generation, variation_set.generation_id)
        assert generation is not None
        generation.selected_variation_id = variation.id
        db.commit()
        self._audit(
            db,
            generation.id,
            "variation_selection",
            1,
            "succeeded",
            f"Variation {variation.id} selected.",
            {"variation_id": variation.id, "variation_set_id": variation_set.id},
        )
        return self.get(db, generation.id)

    def variation_file(self, db: Session, variation_id: str) -> tuple[Path, str]:
        variation = db.get(Variation, variation_id)
        if variation is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Variation not found.")
        return self.storage.absolute(variation.image_path), variation.mime_type

    async def _ensure_analysis(self, db: Session, generation: Generation) -> bool:
        analysis = dict(generation.analysis_json or {})
        generation.status = "analyzing"
        generation.last_error = None
        db.commit()
        errors: list[dict[str, Any]] = []

        if generation.audio_path and not analysis.get("audio"):
            path = self.storage.absolute(generation.audio_path)

            async def audio_operation() -> dict[str, Any]:
                return await asyncio.to_thread(self.audio_analyzer.analyze, path)

            try:
                analysis["audio"] = await with_retry(
                    audio_operation,
                    max_attempts=self.settings.retry_max_attempts,
                    base_delay_seconds=self.settings.retry_base_delay_seconds,
                    on_attempt=lambda attempt, outcome, error: self._retry_audit(
                        db, generation.id, None, "audio_analysis", attempt, outcome, error
                    ),
                )
                generation.analysis_json = dict(analysis)
                db.commit()
            except Exception as exc:
                errors.append(self._error_dict(exc))

        if generation.lyrics_text and not analysis.get("lyrics"):

            async def lyrics_operation() -> dict[str, Any]:
                try:
                    return await asyncio.to_thread(
                        self.lyrics_analyzer.analyze, generation.lyrics_text or ""
                    )
                except Exception as exc:
                    if isinstance(exc, PipelineError):
                        raise
                    raise AnalysisError(f"Lyrics analysis failed: {exc}") from exc

            try:
                analysis["lyrics"] = await with_retry(
                    lyrics_operation,
                    max_attempts=self.settings.retry_max_attempts,
                    base_delay_seconds=self.settings.retry_base_delay_seconds,
                    on_attempt=lambda attempt, outcome, error: self._retry_audit(
                        db, generation.id, None, "lyrics_analysis", attempt, outcome, error
                    ),
                )
                generation.analysis_json = dict(analysis)
                db.commit()
            except Exception as exc:
                errors.append(self._error_dict(exc))

        if errors:
            generation.analysis_json = analysis or None
            generation.status = "analysis_failed"
            generation.last_error = {
                "code": "analysis_failed",
                "message": "One or more analysis steps failed after retries.",
                "steps": errors,
                "retryable": True,
            }
            db.commit()
            return False

        audio_signal = analysis.get("audio")
        lyric_signal = analysis.get("lyrics")
        conflict = detect_conflict(audio_signal, lyric_signal)
        analysis = {
            **analysis,
            "structured_signal": combine_signals(audio_signal, lyric_signal, mood_path="blend"),
        }
        generation.analysis_json = analysis
        generation.conflict_json = conflict
        generation.status = "analyzed"
        generation.last_error = None
        db.commit()
        self._audit(
            db,
            generation.id,
            "signal_combination",
            1,
            "succeeded",
            "Audio and lyrics combined with equal weights when both were present.",
            analysis["structured_signal"].get("source_weights"),
        )
        return True

    async def _create_and_fill_set(
        self, db: Session, generation: Generation, variation_count: int, mood_path: str
    ) -> None:
        if variation_count < 3 or variation_count > 5:
            raise ValueError("variation_count must be between 3 and 5")
        analysis = generation.analysis_json or {}
        signal = combine_signals(analysis.get("audio"), analysis.get("lyrics"), mood_path=mood_path)
        next_number = max((item.set_number for item in generation.variation_sets), default=0) + 1
        # Mix the immutable input fingerprint with the set number. Different songs
        # therefore get different visual DNA, while a Fresh Variations request for
        # the same song deliberately rotates to a new art direction.
        creative_seed = f"{generation.input_hash}:set:{next_number}:path:{mood_path}"
        prompt = build_image_prompt(
            signal,
            mood_path,
            title=generation.title,
            artist=generation.artist,
            parental_advisory=bool(generation.parental_advisory),
            creative_seed=creative_seed,
        )

        # Ask a separate creative-director model to invent the actual visual premises.
        # It sees recent sets for this song so Fresh Variations can explicitly avoid them.
        # If this optional planning step fails, image generation still proceeds with the
        # deterministic rule-based fallback in prompts.variation_prompt.
        if self.creative_director is not None:
            previous_prompts = [item.prompt for item in generation.variation_sets[-3:]]
            try:
                async def concept_operation() -> Any:
                    return await self.creative_director.plan(
                        base_brief=prompt,
                        signal=signal,
                        count=variation_count,
                        creative_seed=creative_seed,
                        title=generation.title,
                        artist=generation.artist,
                        previous_prompts=previous_prompts,
                    )

                plan = await with_retry(
                    concept_operation,
                    max_attempts=self.settings.retry_max_attempts,
                    base_delay_seconds=self.settings.retry_base_delay_seconds,
                    on_attempt=lambda attempt, outcome, error: self._retry_audit(
                        db, generation.id, None, "creative_direction", attempt, outcome, error
                    ),
                )
                if getattr(plan, "concepts", None):
                    prompt = attach_concept_plan(prompt, plan.concepts)
                    self._audit(
                        db,
                        generation.id,
                        "creative_direction_plan",
                        1,
                        "succeeded",
                        f"Created {len(plan.concepts)} mutually distinct visual concepts.",
                        {
                            "model": self.settings.openai_concept_model,
                            "concept_names": [c.get("name") for c in plan.concepts],
                            "request_id": getattr(plan, "request_id", None),
                        },
                    )
            except Exception as exc:
                self._audit(
                    db,
                    generation.id,
                    "creative_direction_plan",
                    1,
                    "fallback",
                    "AI creative director unavailable; using local diversity planner.",
                    self._error_dict(exc),
                )

        variation_set = VariationSet(
            id=str(uuid4()),
            generation_id=generation.id,
            set_number=next_number,
            mood_path=mood_path,
            prompt=prompt,
            requested_count=variation_count,
            status="generating",
        )
        db.add(variation_set)
        generation.status = "generating"
        generation.last_error = None
        db.commit()
        self._audit(
            db,
            generation.id,
            "variation_set_creation",
            1,
            "succeeded",
            f"Variation set {next_number} created.",
            {"variation_set_id": variation_set.id, "mood_path": mood_path, "count": variation_count},
            variation_set.id,
        )
        await self._fill_set(db, generation, variation_set)

    async def _fill_set(
        self, db: Session, generation: Generation, variation_set: VariationSet
    ) -> None:
        existing_positions = {item.position for item in variation_set.variations}
        failure: Exception | None = None
        for position in range(1, variation_set.requested_count + 1):
            if position in existing_positions:
                continue

            async def image_operation() -> Any:
                return await self.image_client.generate(variation_set.prompt, position)

            try:
                generated = await with_retry(
                    image_operation,
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
                relative, width, height = self.storage.save_image(
                    generation.id,
                    variation_set.id,
                    position,
                    generated.content,
                    title=generation.title,
                    artist=generation.artist,
                    parental_advisory=bool(generation.parental_advisory),
                    typography_style=typography_style,
                )
                db.add(
                    Variation(
                        id=str(uuid4()),
                        variation_set_id=variation_set.id,
                        position=position,
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

        db.refresh(variation_set)
        completed = db.scalar(
            select(func.count(Variation.id)).where(Variation.variation_set_id == variation_set.id)
        ) or 0
        if completed == variation_set.requested_count:
            variation_set.status = "complete"
            variation_set.error_json = None
            generation.status = "complete"
            generation.last_error = None
        elif completed > 0:
            variation_set.status = "partial"
            variation_set.error_json = self._error_dict(failure) if failure else None
            generation.status = "partial"
            generation.last_error = variation_set.error_json
        else:
            variation_set.status = "failed"
            variation_set.error_json = self._error_dict(failure) if failure else {
                "code": "image_failed", "message": "No images were generated."
            }
            generation.status = "image_failed"
            generation.last_error = variation_set.error_json
        db.commit()
        self._audit(
            db,
            generation.id,
            "variation_set_completion",
            1,
            variation_set.status,
            f"Generated {completed} of {variation_set.requested_count} requested images.",
            variation_set.error_json,
            variation_set.id,
        )

    def _analysis_complete(self, generation: Generation) -> bool:
        analysis = generation.analysis_json or {}
        return (not generation.audio_path or bool(analysis.get("audio"))) and (
            not generation.lyrics_text or bool(analysis.get("lyrics"))
        )

    @staticmethod
    def _resolve_path(generation: Generation, requested: str) -> str:
        analysis = generation.analysis_json or {}
        has_audio = bool(analysis.get("audio"))
        has_lyrics = bool(analysis.get("lyrics"))
        if requested in {"audio", "lyrics", "blend"}:
            if requested == "audio" and not has_audio:
                raise ValueError("Audio-driven generation requires audio input.")
            if requested == "lyrics" and not has_lyrics:
                raise ValueError("Lyrics-driven generation requires lyrics input.")
            if requested == "blend" and not (has_audio and has_lyrics):
                return "audio" if has_audio else "lyrics"
            return requested
        if has_audio and has_lyrics:
            return "blend"
        return "audio" if has_audio else "lyrics"

    @staticmethod
    def _normalize_collection_id(collection_id: str | None) -> str:
        if not collection_id:
            return uuid4().hex
        collection_id = collection_id.strip()
        if not _COLLECTION_RE.fullmatch(collection_id):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=422,
                detail="collection_id must be 8-64 characters containing letters, numbers, '_' or '-'.",
            )
        return collection_id

    def _retry_audit(
        self,
        db: Session,
        generation_id: str,
        variation_set_id: str | None,
        step: str,
        attempt: int,
        outcome: str,
        error: Exception | None,
    ) -> None:
        details = self._error_dict(error) if error else None
        self._audit(
            db,
            generation_id,
            step,
            attempt,
            outcome,
            str(error) if error else None,
            details,
            variation_set_id,
        )

    @staticmethod
    def _error_dict(error: Exception | None) -> dict[str, Any] | None:
        if error is None:
            return None
        if isinstance(error, PipelineError):
            return error.as_dict()
        return {
            "code": error.__class__.__name__,
            "message": str(error),
            "retryable": bool(getattr(error, "retryable", False)),
        }

    @staticmethod
    def _audit(
        db: Session,
        generation_id: str,
        step: str,
        attempt: int,
        outcome: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        variation_set_id: str | None = None,
    ) -> None:
        db.add(
            AuditEvent(
                generation_id=generation_id,
                variation_set_id=variation_set_id,
                step=step,
                attempt=attempt,
                outcome=outcome,
                message=message,
                details_json=details,
            )
        )
        db.commit()
