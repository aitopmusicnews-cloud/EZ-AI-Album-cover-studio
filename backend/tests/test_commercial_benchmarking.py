from app.commercial_benchmarking import benchmark_cover


def test_strong_cover_reaches_release_ready_band():
    result = benchmark_cover(
        critic_scores={
            "commercial_quality": 9.0,
            "professional_polish": 8.8,
            "thumbnail_visibility": 8.7,
            "typography_quality": 8.2,
            "originality": 8.0,
            "visual_storytelling": 8.4,
        },
        platform_scores={
            "spotify": {"score": 90},
            "apple_music": {"score": 88},
            "youtube_music": {"score": 87},
            "amazon_music": {"score": 89},
            "tiktok": {"score": 86},
        },
        market_lane="Major-label mainstream",
    )

    assert result["score"] >= 85
    assert result["grade"] in {"A", "A+"}
    assert result["release_readiness"] in {"release-ready", "campaign-ready"}
    assert not result["improvement_gaps"]


def test_developing_cover_returns_actionable_gaps():
    result = benchmark_cover(
        critic_scores={
            "commercial_quality": 5.5,
            "professional_polish": 5.0,
            "thumbnail_visibility": 4.5,
            "typography_quality": 5.2,
            "originality": 6.0,
            "visual_storytelling": 5.8,
        },
        platform_scores={},
    )

    assert result["score"] < result["target_score"]
    assert result["improvement_gaps"]
    assert "refinement" in result["next_action"].lower() or "rework" in result["next_action"].lower()
    assert "no live sales or chart data" in result["basis"].lower()
