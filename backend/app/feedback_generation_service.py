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
    ) -> None:
        with self.database.session_factory() as db:
            generation = self.get(db, generation_id)
            if not generation.analysis_json:
                await self.process_generation(generation_id, variation_count, mood_path)
                return

            source_set = self._latest_scored_set(generation)
            if source_set is None:
                await self._create_and_fill_set(db, generation, variation_count, mood_path)
                return

            context, source_variation_id = build_improvement_context(source_set)
            token = self._active_improvement_context.set(context)
            try:
                self._audit(
                    db,
                    generation.id,
                    "generate_better",
                    1,
                    "started",
                    "Starting a critic-guided improvement pass.",
                    {
                        "source_variation_set_id": source_set.id,
                        "source_variation_id": source_variation_id,
                        "mood_path": mood_path,
                        "variation_count": variation_count,
                        "improvement_context": context,
                    },
                    source_set.id,
                )
                await self._create_and_fill_set(db, generation, variation_count, mood_path)
                refreshed = self.get(db, generation.id)
                created_set = max(refreshed.variation_sets, key=lambda item: item.set_number)
                self._audit(
                    db,
                    generation.id,
                    "generate_better",
                    1,
                    "succeeded",
                    f"Created improved variation set {created_set.set_number} from critic feedback.",
                    {
                        "source_variation_id": source_variation_id,
                        "created_variation_set_id": created_set.id,
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
    ) -> list[dict[str, Any]]:
        improvement_context = self._active_improvement_context.get()
        if improvement_context:
            brief = (
                f"{brief}\n\n"
                "GENERATE BETTER — CRITIC-GUIDED REFINEMENT BRIEF\n"
                f"{improvement_context}"
            )
        return await super()._plan_concepts(db, generation, signal, brief, seed)

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
