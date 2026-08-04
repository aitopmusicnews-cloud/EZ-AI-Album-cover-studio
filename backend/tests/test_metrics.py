from datetime import datetime, timezone
from types import SimpleNamespace

from app.metrics import summarize_collection


def test_collection_metrics_summarize_quality_and_pipeline_health():
    now = datetime.now(timezone.utc)
    winner = SimpleNamespace(
        id="winner",
        cover_score=91.0,
        thumbnail_score=88.0,
        commercial_score=86.0,
        selection_tier="winner",
        platform_scores_json={
            "spotify": {"score": 92.0},
            "tiktok": {"score": 84.0},
        },
    )
    alternate = SimpleNamespace(
        id="alternate",
        cover_score=73.0,
        thumbnail_score=70.0,
        commercial_score=68.0,
        selection_tier="remaining",
        platform_scores_json={
            "spotify": {"score": 76.0},
            "tiktok": {"score": 72.0},
        },
    )
    variation_set = SimpleNamespace(
        set_number=1,
        status="complete",
        critic_status="complete",
        ai_winner_variation_id="winner",
        variations=[winner, alternate],
        created_at=now,
    )
    generation = SimpleNamespace(
        version=1,
        status="complete",
        selected_variation_id="winner",
        variation_sets=[variation_set],
        audit_events=[
            SimpleNamespace(step="image_generation_1", outcome="succeeded", attempt=2),
            SimpleNamespace(step="cache_lookup", outcome="hit", attempt=1),
        ],
        updated_at=now,
    )

    metrics = summarize_collection("collection-1", [generation])

    assert metrics["versions"] == 1
    assert metrics["variation_sets"] == 1
    assert metrics["covers_generated"] == 2
    assert metrics["success_rate"] == 100.0
    assert metrics["critic_completion_rate"] == 100.0
    assert metrics["average_cover_score"] == 82.0
    assert metrics["best_cover_score"] == 91.0
    assert metrics["release_ready_covers"] == 1
    assert metrics["retries"] == 1
    assert metrics["cache_hits"] == 1
    assert metrics["platform_averages"]["spotify"] == 84.0
    assert metrics["quality_trend"][0]["winner_score"] == 91.0


def test_collection_metrics_handles_empty_collection():
    metrics = summarize_collection("empty", [])

    assert metrics["versions"] == 0
    assert metrics["covers_generated"] == 0
    assert metrics["success_rate"] == 0.0
    assert metrics["average_cover_score"] is None
    assert metrics["quality_trend"] == []
