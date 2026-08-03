from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from .concept_ranking import ConceptRankingResult
from .cover_critic import CoverCriticResult, CoverInput
from .render_prompts import build_render_prompt
from .style_presets import StylePreset


class CreativeDirector(Protocol):
    async def plan(self, **kwargs: Any) -> Any: ...


class ConceptRanker(Protocol):
    async def rank(self, **kwargs: Any) -> ConceptRankingResult: ...


class CoverCritic(Protocol):
    async def evaluate(self, **kwargs: Any) -> CoverCriticResult: ...


@dataclass(frozen=True, slots=True)
class RenderRequest:
    concept_id: str
    concept: dict[str, Any]
    render_index: int
    position: int
    prompt: str


@dataclass(frozen=True, slots=True)
class RenderedCover:
    variation_id: str
    concept_id: str
    render_index: int
    position: int
    prompt: str
    image_bytes: bytes
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class QualityPipelineResult:
    concepts: list[dict[str, Any]]
    ranking: ConceptRankingResult
    rendered_covers: list[RenderedCover]
    critic: CoverCriticResult

    @property
    def winner(self) -> RenderedCover:
        return next(item for item in self.rendered_covers if item.variation_id == self.critic.winner_id)

    @property
    def runner_up(self) -> RenderedCover | None:
        if self.critic.runner_up_id is None:
            return None
        return next(
            item for item in self.rendered_covers if item.variation_id == self.critic.runner_up_id
        )


async def run_quality_pipeline(
    *,
    creative_director: CreativeDirector,
    concept_ranker: ConceptRanker,
    cover_critic: CoverCritic,
    render: Callable[[RenderRequest], Awaitable[RenderedCover]],
    base_brief: str,
    signal: dict[str, Any],
    title: str | None,
    artist: str | None,
    creative_seed: str,
    style_preset: StylePreset,
    previous_prompts: list[str] | None = None,
    concept_count: int = 8,
    selected_concept_count: int = 2,
    renders_per_concept: int = 2,
    max_parallel_renders: int = 2,
    improvement_feedback: list[str] | None = None,
) -> QualityPipelineResult:
    if concept_count < selected_concept_count:
        raise ValueError("concept_count must be at least selected_concept_count")
    plan = await creative_director.plan(
        base_brief=base_brief,
        signal=signal,
        count=concept_count,
        creative_seed=creative_seed,
        title=title,
        artist=artist,
        previous_prompts=previous_prompts or [],
    )
    concepts = [dict(item) for item in getattr(plan, "concepts", [])]
    if len(concepts) != concept_count:
        raise ValueError(f"Creative director returned {len(concepts)} concepts; expected {concept_count}")
    for index, concept in enumerate(concepts, start=1):
        concept.setdefault("id", f"concept-{index}")

    ranking = await concept_ranker.rank(
        concepts=concepts,
        signal=signal,
        title=title,
        artist=artist,
        selected_count=selected_concept_count,
    )
    by_id = {str(item["id"]): item for item in concepts}
    selected = [by_id[concept_id] for concept_id in ranking.selected_concept_ids]

    requests: list[RenderRequest] = []
    position = 1
    for concept in selected:
        for render_index in range(1, renders_per_concept + 1):
            requests.append(
                RenderRequest(
                    concept_id=str(concept["id"]),
                    concept=concept,
                    render_index=render_index,
                    position=position,
                    prompt=build_render_prompt(
                        base_brief=base_brief,
                        concept=concept,
                        render_index=render_index,
                        style_preset=style_preset,
                        improvement_feedback=improvement_feedback,
                    ),
                )
            )
            position += 1

    semaphore = asyncio.Semaphore(max_parallel_renders)

    async def guarded(request: RenderRequest) -> RenderedCover:
        async with semaphore:
            return await render(request)

    rendered = await asyncio.gather(*(guarded(request) for request in requests))
    critic = await cover_critic.evaluate(
        covers=[
            CoverInput(
                variation_id=item.variation_id,
                image_bytes=item.image_bytes,
                concept_name=str(by_id[item.concept_id].get("name", "")),
                concept_prompt=item.prompt,
            )
            for item in rendered
        ],
        signal=signal,
        title=title,
        artist=artist,
    )
    return QualityPipelineResult(concepts, ranking, list(rendered), critic)
