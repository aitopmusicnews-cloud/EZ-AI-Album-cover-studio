from __future__ import annotations

from typing import Any


_PALETTES = {
    "positive_high": "electric coral, luminous gold, saturated cyan, and clean white highlights",
    "positive_low": "sun-washed amber, soft peach, pale turquoise, and warm cream",
    "negative_high": "charcoal black, bruised crimson, ultraviolet, and hard silver highlights",
    "negative_low": "midnight blue, smoke gray, muted wine, and a faint cold glow",
    "neutral_high": "high-contrast cobalt, acid green accents, graphite, and strobing white",
    "neutral_low": "fog gray, desaturated blue, dusty mauve, and soft pearl",
    "neutral_mid": "deep indigo, mineral teal, muted copper, and balanced shadow",
}


def build_image_prompt(signal: dict[str, Any], mood_path: str) -> str:
    mood = signal["mood"]
    valence = float(mood.get("valence", 0.0))
    energy = float(mood.get("energy", 0.5))
    palette = _palette(valence, energy)
    composition = _composition(signal.get("tempo_bpm"), energy)
    lighting = _lighting(valence, energy)
    genre_style = _genre_style(signal.get("inferred_genre"))
    tonal_cue = _tonal_cue(signal.get("scale"), signal.get("key"))
    themes = ", ".join(signal.get("themes", [])[:6]) or "abstract emotional symbolism"
    imagery = ", ".join(signal.get("imagery", [])[:6])
    keywords = ", ".join(signal.get("keywords", [])[:8])

    priority_sentence = {
        "audio": "Let the musical energy and production character determine the emotional center; lyrical motifs may appear only as subtle secondary symbols.",
        "lyrics": "Let the lyrical sentiment and imagery determine the emotional center; musical traits should shape rhythm and texture without changing that mood.",
        "blend": "Balance music and lyrics equally so neither source dominates the emotional direction.",
    }.get(mood_path, "Balance all available signals.")

    motif_sentence = ""
    if imagery or keywords:
        motif_sentence = f"Possible symbolic motifs: {imagery or keywords}. Use them metaphorically, not as a literal checklist."

    return " ".join(
        part.strip()
        for part in [
            "Create a unique, premium album cover artwork for a fictional release.",
            f"Emotional direction: {mood['label']}.",
            priority_sentence,
            f"Core themes: {themes}.",
            motif_sentence,
            f"Visual language: {genre_style}; {composition}; {lighting}; {tonal_cue}.",
            f"Color palette: {palette}.",
            "Use one memorable focal idea, strong silhouette readability at thumbnail size, layered depth, intentional negative space, and gallery-quality detail.",
            "Square composition. No typography, no letters, no logos, no watermarks, no recognizable celebrities, and no imitation of a living artist's signature style.",
        ]
        if part.strip()
    )


def variation_prompt(base_prompt: str, position: int) -> str:
    concepts = [
        "Build the concept around a single surreal object with restrained background detail.",
        "Use an environmental scene with cinematic scale and a small but unmistakable focal subject.",
        "Use bold abstract geometry and tactile material textures rather than a literal scene.",
        "Use an intimate close-up composition with symbolic reflections, shadows, or translucent layers.",
        "Use a graphic, poster-like composition driven by shape, depth, and controlled visual rhythm.",
    ]
    return f"{base_prompt} Variation direction {position}: {concepts[(position - 1) % len(concepts)]}"


def _palette(valence: float, energy: float) -> str:
    if valence > 0.25:
        return _PALETTES["positive_high" if energy > 0.55 else "positive_low"]
    if valence < -0.25:
        return _PALETTES["negative_high" if energy > 0.55 else "negative_low"]
    if energy > 0.62:
        return _PALETTES["neutral_high"]
    if energy < 0.35:
        return _PALETTES["neutral_low"]
    return _PALETTES["neutral_mid"]


def _composition(tempo: float | None, energy: float) -> str:
    if tempo is None:
        return "a balanced visual rhythm with a clear central hierarchy"
    if tempo >= 135 or energy >= 0.72:
        return "diagonal movement, compressed perspective, and energetic repetition"
    if tempo >= 100:
        return "rhythmic modular forms and a confident centered-to-offset composition"
    if tempo >= 75:
        return "measured symmetry with gentle directional flow"
    return "wide negative space, slow visual pacing, and a suspended focal element"


def _lighting(valence: float, energy: float) -> str:
    if valence > 0.25 and energy > 0.55:
        return "radiant directional light with crisp luminous edges"
    if valence < -0.25 and energy > 0.55:
        return "hard chiaroscuro, sharp rim light, and dense shadow"
    if energy < 0.36:
        return "diffuse atmospheric light with soft depth transitions"
    return "cinematic side light with controlled contrast"


def _genre_style(genre: str | None) -> str:
    return {
        "ambient": "minimal surrealism with atmospheric gradients and organic haze",
        "hip-hop / trap": "monumental urban surrealism with polished mixed-media texture",
        "electronic / dance": "precision digital abstraction, refracted light, and kinetic geometry",
        "rock / alternative": "raw editorial collage, distressed surfaces, and sculptural impact",
        "acoustic / singer-songwriter": "tactile photographic realism with natural materials and intimate framing",
        "pop": "iconic contemporary art direction with polished color blocking and a clean focal symbol",
        "cinematic / experimental": "cinematic surrealism with unusual scale, rich atmosphere, and ambiguous narrative",
    }.get(genre, "contemporary cinematic surrealism with refined editorial art direction")


def _tonal_cue(scale: str | None, key: str | None) -> str:
    if scale == "major":
        return "harmonic shapes should feel open, resolved, and luminous"
    if scale == "minor":
        return "harmonic shapes should feel unresolved, inward, and shadowed"
    return "harmonic shapes should feel balanced and tonally ambiguous"
