from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from sqlalchemy.orm import Session

from .improvement_feedback import build_improvement_context
from .major_label_service import MajorLabelGenerationService
from .models import Generation


class FeedbackDrivenGenerationService(MajorLabelGenerationService):
    """Extend the major-label pipeline with a critic-guided refinement pass."""

    _active_improvement_context: ContextVar[str | None] = ContextVar(
        "active_improvement_context", default=None
    )

    async def generate_better(
        self,
        generation_id: str,
        variation_count: int = 4,
        mood_path: str = "blend",
        user_instructions: str | None = None,
    ) -> None:
        with self.database.session_factory() as db:
            generation = self.get(db, generation_id)
            if not generation.analysis_json:
                await self.process_generation(generation_id, variation_count, mood_path)
                return

            source_set = self._latest_scored_set(generation)
            source_variation_id = None
            if source_set is not None:
                context, source_variation_id = build_improvement_context(
                    source_set,
                    preferred_variation_id=generation.selected_variation_id,
                )
            else:
                context = "Create a stronger follow-up with clearer hierarchy, better thumbnail recognition, and a premium commercial finish."

            clean_user_instructions = (user_instructions or "").strip()
            if clean_user_instructions:
                context = (
                    f"{context}\n\n"
                    "USER-REQUESTED COVER EDITS — HIGHEST PRIORITY\n"
                    f"{clean_user_instructions}\n"
                    "Preserve any elements the user explicitly asks to keep. Change the requested elements clearly while producing new original variations."
                )

            token = self._active_improvement_context.set(context)
            try:
                self._audit(
                    db,
                    generation.id,
                    "generate_better",
                    1,
                    "started",
                    "Starting a user-directed cover edit pass." if clean_user_instructions else "Starting a critic-guided improvement pass.",
                    {
                        "source_variation_set_id": source_set.id if source_set is not None else None,
                        "source_variation_id": source_variation_id,
                        "mood_path": mood_path,
                        "variation_count": variation_count,
                        "user_instructions": clean_user_instructions or None,
                        "improvement_context": context,
                    },
                    source_set.id if source_set is not None else None,
                )
                await self._create_and_fill_set(db, generation, variation_count, mood_path)
                refreshed = self.get(db, generation.id)
                created_set = max(refreshed.variation_sets, key=lambda item: item.set_number)
                succeeded = created_set.status in {"complete", "partial"}
                self._audit(
                    db,
                    generation.id,
                    "generate_better",
                    1,
                    "succeeded" if succeeded else "failed",
                    f"Created edited variation set {created_set.set_number}." if clean_user_instructions and succeeded else (
                        f"Created improved variation set {created_set.set_number} from critic feedback." if succeeded
                        else f"Improvement set {created_set.set_number} did not complete."
                    ),
                    {
                        "source_variation_id": source_variation_id,
                        "created_variation_set_id": created_set.id,
                        "created_variation_set_status": created_set.status,
                        "user_instructions": clean_user_instructions or None,
                    },
                    created_set.id,
                )
            finally:
                self._active_improvement_context.reset(token)

    async def _plan_concepts(
        self,
        db: Session,
        generation: Generation,
        signal: dict[str, Any],
        brief: str,
        seed: str,
        count: int | None = None,
    ) -> list[dict[str, Any]]:
        improvement_context = self._active_improvement_context.get()
        if improvement_context:
            brief = (
                f"{brief}\n\n"
                "GENERATE BETTER — CRITIC-GUIDED REFINEMENT BRIEF\n"
                f"{improvement_context}"
            )
        return await super()._plan_concepts(
            db,
            generation,
            signal,
            brief,
            seed,
            count=count,
        )

    @staticmethod
    def _latest_scored_set(generation: Generation):
        candidates = [
            item
            for item in generation.variation_sets
            if item.variations
            and (
                item.ai_winner_variation_id
                or any(row.cover_feedback_json or row.critic_scores_json for row in item.variations)
            )
        ]
        return max(candidates, key=lambda item: item.set_number) if candidates else None
