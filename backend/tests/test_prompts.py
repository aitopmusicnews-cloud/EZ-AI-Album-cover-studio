from app.prompts import build_image_prompt, variation_prompt
from app.signals import combine_signals


def _signal(genre="hip-hop / trap"):
    return {
        "mood": {"label": "dark and intense", "valence": -0.6, "energy": 0.8},
        "themes": ["success and ambition", "nightlife and motion"],
        "keywords": ["city", "street", "car", "money"],
        "imagery": ["city", "night"],
        "tempo_bpm": 82.0,
        "key": "C",
        "scale": "minor",
        "inferred_genre": genre,
    }


def test_prompt_prioritizes_real_album_photography_and_blocks_cracked_face_cliche():
    prompt = build_image_prompt(_signal(), "blend", title="Cold Signal", artist="Night Vault", parental_advisory=True)
    assert "commercially credible" in prompt
    assert "premium rap/mixtape photography" in prompt
    assert "city streets after dark" in prompt
    assert "no cracked marble or metal faces" in prompt
    assert "no shattered statues" in prompt
    assert "lower-right" in prompt


def test_variations_are_materially_distinct_album_cover_archetypes():
    base = build_image_prompt(_signal(), "blend")
    prompts = [variation_prompt(base, i) for i in range(1, 6)]
    assert len(set(prompts)) == 5
    assert "CINEMATIC HERO COVER" in prompts[0]
    assert "NARRATIVE LOCATION COVER" in prompts[1]
    assert "CLASSIC RECORD-SLEEVE COVER" in prompts[2]
    assert "MODERN MIXTAPE / POSTER COVER" in prompts[3]
    assert "ALTERNATE STORY COVER" in prompts[4]


def test_country_lyrics_refine_adjacent_audio_genre_to_country_americana():
    audio = {
        "inferred_genre": "acoustic / singer-songwriter",
        "style_tags": ["organic"],
        "tempo_bpm": 98.0,
        "key": "G",
        "scale": "major",
        "dominant_frequencies_hz": [],
        "mood": {"label": "warm", "valence": 0.3, "energy": 0.5},
    }
    lyrics = {
        "themes": ["freedom and escape"],
        "keywords": ["truck", "whiskey", "highway", "home"],
        "imagery": ["highway"],
        "mood": {"label": "hopeful", "valence": 0.2, "energy": 0.4},
    }
    signal = combine_signals(audio, lyrics)
    assert signal["inferred_genre"] == "country / americana"
    prompt = build_image_prompt(signal, "blend")
    assert "cinematic Americana photography" in prompt
    assert "pickup truck" in prompt
