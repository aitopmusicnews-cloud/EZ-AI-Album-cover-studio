from types import SimpleNamespace

from app.improvement_feedback import build_improvement_context


def test_build_improvement_context_uses_winner_feedback() -> None:
    concept = SimpleNamespace(id="concept-1", name="Midnight Signal")
    winner = SimpleNamespace(
        id="cover-1",
        concept_candidate_id="concept-1",
        rank=1,
        cover_score=88.0,
        cover_feedback_json={
            "strengths": ["memorable central symbol"],
            "weaknesses": ["title competes with the focal point"],
            "improvement_instructions": ["open more negative space above the subject"],
        },
        critic_scores_json={
            "commercial_quality": 8.2,
            "thumbnail_visibility": 6.1,
            "typography_quality": 6.5,
        },
    )
    variation_set = SimpleNamespace(
        ai_winner_variation_id="cover-1",
        concepts=[concept],
        variations=[winner],
    )

    context, source_id = build_improvement_context(variation_set)

    assert source_id == "cover-1"
    assert "Midnight Signal" in context
    assert "memorable central symbol" in context
    assert "open more negative space" in context
    assert "thumbnail visibility" in context
    assert "do not duplicate" in context


def test_build_improvement_context_has_safe_fallback() -> None:
    context, source_id = build_improvement_context(SimpleNamespace(variations=[]))

    assert source_id is None
    assert "thumbnail recognition" in context
    assert "commercial finish" in context
