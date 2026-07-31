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


def build_image_prompt(
    signal: dict[str, Any],
    mood_path: str,
    *,
    title: str | None = None,
    artist: str | None = None,
    parental_advisory: bool = False,
) -> str:
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

    release_context = ""
    if title or artist:
        bits = []
        if title:
            bits.append(f"release title is '{title}'")
        if artist:
            bits.append(f"artist name is '{artist}'")
        release_context = (
            "Metadata context only: " + " and ".join(bits) + ". "
            "Use the title only as a subtle conceptual cue; do not draw any words or lettering."
        )

    safe_zone = (
        "Keep the upper-left area visually calm for exact title/artist typography that will be added after generation."
    )
    if parental_advisory:
        safe_zone += " Also keep the lower-right corner readable for a small parental-advisory label."

    return " ".join(
        part.strip()
        for part in [
            "Create a unique, premium album cover artwork for a fictional release.",
            release_context,
            f"Emotional direction: {mood['label']}.",
            priority_sentence,
            f"Core themes: {themes}.",
            motif_sentence,
            f"Visual language: {genre_style}; {composition}; {lighting}; {tonal_cue}.",
            f"Color palette: {palette}.",
            safe_zone,
            "Use one memorable focal idea, strong silhouette readability at thumbnail size, layered depth, intentional negative space, and gallery-quality detail.",
            "Square composition. No typography, no letters, no logos, no watermarks, no recognizable celebrities, and no imitation of a living artist's signature style. Exact release text is composited separately after image generation.",
        ]
        if part.strip()
    )


def variation_prompt(base_prompt: str, position: int) -> str:
    concepts = [
        (
            "PHOTOGRAPHIC ENVIRONMENTAL COVER: create a cinematic real-world or dreamlike "
            "environment with strong atmosphere, depth, architecture, landscape, weather, "
            "light, or location as the main visual idea. Do not use a portrait, face, bust, "
            "statue, mannequin, or mask as the focal subject."
        ),
        (
            "GRAPHIC DESIGN COVER: create bold two-dimensional album artwork using geometric "
            "forms, negative space, color blocking, pattern, visual rhythm, and modern editorial "
            "design. Avoid photorealistic people, faces, statues, and fantasy portrait imagery."
        ),
        (
            "ANALOG COLLAGE COVER: create tactile mixed-media artwork using torn paper, print "
            "textures, ink, grain, halftone, paint, photography fragments, and unexpected symbolic "
            "objects. It should feel handmade and materially different from polished 3D CGI."
        ),
        (
            "SYMBOLIC STILL-LIFE COVER: build the cover around one memorable NON-HUMAN object or "
            "small collection of objects tied metaphorically to the song themes. Use unusual scale, "
            "lighting, materials, shadows, reflections, or placement. No human head, bust, mask, "
            "mannequin, or cracked-face imagery."
        ),
        (
            "WORLD-BUILDING COVER: create an expansive scene based on landscape, architecture, "
            "nature, surreal geography, interiors, streets, sky, water, or abstract space. Make "
            "the location itself the subject. Avoid centered portraits and sculpted human faces."
        ),
    ]

    concept = concepts[(position - 1) % len(concepts)]

    diversity_rule = (
        "IMPORTANT DIVERSITY RULE: each image in this variation set must look like it came from "
        "a completely different creative campaign. Do not repeat the subject, camera framing, "
        "material, visual metaphor, or composition used by another variation. Do not default to "
        "cracked faces, fragmented heads, human busts, statues, masks, mannequins, melting faces, "
        "or disintegrating portraits unless the supplied lyrics explicitly require that imagery."
    )

    return (
        f"{base_prompt} "
        f"Variation direction {position}: {concept} "
        f"{diversity_rule}"
    )

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
        "R&B / soul": "luxurious nocturnal editorial imagery with soft glow, reflective surfaces, and intimate depth",
        "electronic / dance": "precision digital abstraction, refracted light, and kinetic geometry",
        "rock / alternative": "raw editorial collage, distressed surfaces, and sculptural impact",
        "acoustic / singer-songwriter": "tactile photographic realism with natural materials and intimate framing",
        "pop": "iconic contemporary art direction with polished color blocking and a clean focal symbol",
        "cinematic / experimental": "cinematic surrealism with unusual scale, rich atmosphere, and ambiguous narrative",
    }.get(genre, "contemporary album-art direction chosen specifically from the supplied music and lyric signals; avoid generic fantasy portrait and cracked-statue imagery")


def _tonal_cue(scale: str | None, key: str | None) -> str:
    if scale == "major":
        return "harmonic shapes should feel open, resolved, and luminous"
    if scale == "minor":
        return "harmonic shapes should feel unresolved, inward, and shadowed"
    return "harmonic shapes should feel balanced and tonally ambiguous"
