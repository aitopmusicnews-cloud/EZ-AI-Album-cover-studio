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
        "audio_signal": {
            "dynamic_range_db": 11.0,
            "spectral": {
                "bass_ratio": 0.36,
                "centroid_hz": 2400.0,
                "harmonic_ratio": 0.45,
                "flatness": 0.08,
                "onset_strength": 1.0,
            },
        },
    }


def test_prompt_prioritizes_real_album_photography_and_blocks_cracked_face_cliche():
    prompt = build_image_prompt(
        _signal(),
        "blend",
        title="Cold Signal",
        artist="Night Vault",
        parental_advisory=True,
        creative_seed="cold-signal:set:1",
    )
    assert "commercially credible" in prompt
    assert "premium rap and mixtape photography" in prompt
    assert "MANDATORY UNIQUE VISUAL DNA" in prompt
    assert "ANTI-TEMPLATE RULE" in prompt
    assert "no cracked marble or metal faces" in prompt
    assert "no shattered statues" in prompt
    assert "lower corner" in prompt


def test_variations_are_materially_distinct_album_cover_archetypes():
    base = build_image_prompt(_signal(), "blend", creative_seed="song-a:set:1")
    prompts = [variation_prompt(base, i) for i in range(1, 6)]
    assert len(set(prompts)) == 5
    assert all("SPECIFIC ART DIRECTION" in prompt for prompt in prompts)
    assert all("Changing only pose, clothing color or background light is not enough" in prompt for prompt in prompts)


def test_different_songs_receive_different_visual_dna_even_with_same_genre_and_mood():
    first = build_image_prompt(_signal(), "blend", creative_seed="song-audio-hash-A:set:1")
    second = build_image_prompt(_signal(), "blend", creative_seed="song-audio-hash-B:set:1")
    assert first != second
    marker = "MANDATORY UNIQUE VISUAL DNA FOR THIS RELEASE:"
    assert marker in first and marker in second


def test_fresh_set_rotates_visual_dna_for_same_song():
    first = build_image_prompt(_signal(), "blend", creative_seed="same-song:set:1")
    second = build_image_prompt(_signal(), "blend", creative_seed="same-song:set:2")
    assert first != second
    assert variation_prompt(first, 1) != variation_prompt(second, 1)


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
    prompt = build_image_prompt(signal, "blend", creative_seed="country-song:set:1")
    assert "Americana record photography" in prompt
    assert any(term in prompt for term in ["pickup", "county road", "roadside bar", "motel", "diner", "field"])
