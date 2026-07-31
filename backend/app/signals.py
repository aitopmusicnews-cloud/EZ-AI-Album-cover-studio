from __future__ import annotations

from typing import Any


_AUDIO_VISUAL_THEMES = {
    "ambient": ["vast negative space", "mist-like layers", "slow celestial motion"],
    "hip-hop / trap": ["architectural rhythm", "street-scale geometry", "heavy low-end gravity"],
    "electronic / dance": ["neon pulse", "kinetic light trails", "synthetic geometry"],
    "rock / alternative": ["raw material tension", "fractured motion", "high-contrast impact"],
    "acoustic / singer-songwriter": ["tactile natural materials", "human-scale intimacy", "soft daylight"],
    "pop": ["iconic central form", "clean graphic rhythm", "luminous color blocking"],
    "cinematic / experimental": ["surreal scale", "dramatic atmosphere", "unexpected texture"],
}


def detect_conflict(audio: dict[str, Any] | None, lyrics: dict[str, Any] | None) -> dict[str, Any] | None:
    if not audio or not lyrics:
        return None
    audio_mood = audio["mood"]
    lyrics_mood = lyrics["mood"]
    audio_valence = float(audio_mood["valence"])
    lyrics_valence = float(lyrics_mood["valence"])
    audio_energy = float(audio_mood["energy"])
    lyrics_energy = float(lyrics_mood["energy"])
    valence_gap = abs(audio_valence - lyrics_valence)
    opposite_polarity = audio_valence * lyrics_valence < -0.08
    upbeat_dark = audio_valence > 0.25 and audio_energy > 0.55 and lyrics_valence < -0.25
    dark_music_bright_words = audio_valence < -0.25 and lyrics_valence > 0.25
    severity = min(1.0, valence_gap * 0.8 + abs(audio_energy - lyrics_energy) * 0.2)
    if not ((opposite_polarity and valence_gap >= 0.6) or upbeat_dark or dark_music_bright_words):
        return None
    return {
        "detected": True,
        "severity": round(severity, 4),
        "reason": (
            f"Audio reads as '{audio_mood['label']}' while lyrics read as "
            f"'{lyrics_mood['label']}'."
        ),
        "audio_path": {
            "label": "Prioritize the music",
            "mood": audio_mood,
            "description": "Use tempo, tonality, energy, and production style as the dominant visual direction.",
        },
        "lyrics_path": {
            "label": "Prioritize the lyrics",
            "mood": lyrics_mood,
            "description": "Use lyrical sentiment, themes, and imagery as the dominant visual direction.",
        },
    }


def combine_signals(
    audio: dict[str, Any] | None,
    lyrics: dict[str, Any] | None,
    *,
    mood_path: str = "blend",
) -> dict[str, Any]:
    if not audio and not lyrics:
        raise ValueError("At least one signal is required")

    if audio and lyrics:
        weights = {"audio": 0.5, "lyrics": 0.5}
        audio_mood = audio["mood"]
        lyric_mood = lyrics["mood"]
        if mood_path == "audio":
            mood = dict(audio_mood)
            mood["priority"] = "audio"
        elif mood_path == "lyrics":
            mood = dict(lyric_mood)
            mood["priority"] = "lyrics"
        else:
            valence = (float(audio_mood["valence"]) + float(lyric_mood["valence"])) / 2.0
            energy = (float(audio_mood["energy"]) + float(lyric_mood["energy"])) / 2.0
            mood = {
                "label": _label_blended_mood(valence, energy),
                "valence": round(valence, 4),
                "energy": round(energy, 4),
                "priority": "equal blend",
            }
    elif audio:
        weights = {"audio": 1.0, "lyrics": 0.0}
        mood = {**audio["mood"], "priority": "audio"}
    else:
        weights = {"audio": 0.0, "lyrics": 1.0}
        mood = {**lyrics["mood"], "priority": "lyrics"}

    audio_themes: list[str] = []
    if audio:
        audio_themes = _AUDIO_VISUAL_THEMES.get(audio["inferred_genre"], audio.get("style_tags", []))
    lyric_themes = list(lyrics.get("themes", [])) if lyrics else []
    themes = _interleave(audio_themes, lyric_themes, limit=6)

    return {
        "source_weights": weights,
        "mood_path": mood_path,
        "mood": mood,
        "themes": themes,
        "keywords": list(lyrics.get("keywords", []))[:10] if lyrics else [],
        "imagery": list(lyrics.get("imagery", []))[:8] if lyrics else [],
        "tempo_bpm": audio.get("tempo_bpm") if audio else None,
        "key": audio.get("key") if audio else None,
        "scale": audio.get("scale") if audio else None,
        "dominant_frequencies_hz": audio.get("dominant_frequencies_hz", []) if audio else [],
        "inferred_genre": audio.get("inferred_genre") if audio else None,
        "style_tags": audio.get("style_tags", []) if audio else [],
        "audio_signal": audio,
        "lyric_signal": lyrics,
    }


def _interleave(left: list[str], right: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for index in range(max(len(left), len(right))):
        for source in (left, right):
            if index < len(source) and source[index] not in result:
                result.append(source[index])
                if len(result) == limit:
                    return result
    return result


def _label_blended_mood(valence: float, energy: float) -> str:
    if valence >= 0.3 and energy >= 0.58:
        return "radiant and kinetic"
    if valence >= 0.25:
        return "hopeful and spacious"
    if valence <= -0.3 and energy >= 0.58:
        return "brooding and volatile"
    if valence <= -0.3:
        return "melancholic and cinematic"
    if energy >= 0.65:
        return "tense and propulsive"
    if energy <= 0.34:
        return "quiet and dreamlike"
    return "poised and introspective"
