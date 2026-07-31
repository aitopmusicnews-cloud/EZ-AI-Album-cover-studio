from __future__ import annotations

from typing import Any


_PALETTES = {
    "positive_high": "sunlit amber, warm red, denim blue, cream, and crisp white highlights",
    "positive_low": "weathered tan, faded blue, warm cream, dusty rose, and soft gold",
    "negative_high": "deep black, steel gray, blood red accents, cold white highlights, and restrained neon",
    "negative_low": "midnight blue, charcoal, smoke gray, muted burgundy, and dim tungsten light",
    "neutral_high": "graphite, cobalt, hard white, selective red or amber accents, and deep shadow",
    "neutral_low": "washed black, fog gray, desaturated blue, warm brown, and aged paper tones",
    "neutral_mid": "deep indigo, asphalt gray, muted copper, warm skin tones, and balanced shadow",
}

# Real-world album-cover worlds.  The previous prompt leaned heavily on surreal
# sculpture/fragment language, which caused unrelated songs to converge on the
# same cracked-face aesthetic.  These directions intentionally start from
# recognizable music-photo settings and let the song signal choose the details.
_GENRE_WORLDS = {
    "country / americana": (
        "cinematic Americana photography: a roadside bar, open highway, pickup truck, worn denim, "
        "guitar case, motel sign, gas station, desert or small-town landscape; authentic lived-in detail"
    ),
    "acoustic / singer-songwriter": (
        "cinematic roots-music photography: roadside locations, modest interiors, old wood, denim, "
        "guitar, car or pickup, motel or diner light, and intimate human-scale storytelling"
    ),
    "hip-hop / trap": (
        "premium rap/mixtape photography: city streets after dark, cars, storefronts, apartment blocks, "
        "parking lots, studio corridors, concrete, chrome, rain-slick pavement, selective red or neon light"
    ),
    "R&B / soul": (
        "luxury R&B editorial photography: intimate portraiture, hotel rooms, late-night city windows, "
        "classic cars, velvet or leather interiors, warm practical lights, reflective glass, elegant wardrobe"
    ),
    "rock / alternative": (
        "gritty music-editorial photography: rehearsal rooms, garages, roadside stops, industrial backlots, "
        "amplifiers, worn vehicles, stage spill, documentary flash, distressed print texture"
    ),
    "electronic / dance": (
        "nightlife and club photography: warehouse interiors, tunnel lights, night highways, backstage spaces, "
        "crowd silhouettes, reflective surfaces, practical neon, motion blur, disciplined futuristic detail"
    ),
    "pop": (
        "major-label pop editorial photography: strong fashion portrait or cinematic location, memorable prop, "
        "clean production design, polished lighting, bold but believable color, instantly readable silhouette"
    ),
    "ambient": (
        "atmospheric location photography: lonely architecture, shoreline, fog, empty road, distant figure, "
        "large sky, natural haze, practical light, restrained cinematic production design"
    ),
    "cinematic / experimental": (
        "cinematic narrative photography: unusual but believable location, strong character or object, "
        "film-still composition, practical effects, moody production design, tactile real-world materials"
    ),
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
    genre = signal.get("inferred_genre") or "cinematic / experimental"
    genre_world = _genre_world(signal)
    tonal_cue = _tonal_cue(signal.get("scale"), signal.get("key"))
    themes = ", ".join(signal.get("themes", [])[:6]) or "personal identity and atmosphere"
    imagery = ", ".join(signal.get("imagery", [])[:6])
    keywords = ", ".join(signal.get("keywords", [])[:10])

    priority_sentence = {
        "audio": "Let the musical energy, groove, and production character determine the emotional center; lyrical motifs may appear as secondary story details.",
        "lyrics": "Let the lyrical story, sentiment, and imagery determine the emotional center; musical traits should shape pace, lighting, and visual intensity.",
        "blend": "Balance music and lyrics equally: the music determines visual energy while the lyrics supply concrete story and setting clues.",
    }.get(mood_path, "Balance all available signals.")

    motif_sentence = ""
    if imagery or keywords:
        motif_sentence = (
            f"Story clues from the lyrics: {imagery or keywords}. Select only the strongest one or two clues and "
            "turn them into a believable scene, wardrobe, prop, location, weather condition, or background detail."
        )

    release_context = ""
    if title or artist:
        bits = []
        if title:
            bits.append(f"release title is '{title}'")
        if artist:
            bits.append(f"artist name is '{artist}'")
        release_context = (
            "Release context: " + " and ".join(bits) + ". "
            "Use the title as a conceptual clue only; do not draw any words or lettering. Exact typography is composited afterward."
        )

    typography_zone = (
        "Compose like a finished record sleeve and preserve one naturally uncluttered area for bold title/artist typography "
        "that will be added after generation. CRITICAL FACE-SAFE RULE: if a human appears, keep the entire face, eyes, and "
        "important facial features completely outside the typography-safe area. The final title must never cross a face. "
        "Do not force the same text-safe area on every variation. The later typography treatment may be flowing script, arched vintage display, handwritten marker, or editorial italic rather than plain block lettering."
    )
    if parental_advisory:
        typography_zone += " Keep the lower-right corner readable for the explicit-content label."

    return " ".join(
        part.strip()
        for part in [
            "Create a commercially credible, release-ready album or mixtape cover, not generic AI concept art.",
            release_context,
            f"Genre direction: {genre}. Visual world: {genre_world}.",
            f"Emotional direction: {mood['label']}.",
            priority_sentence,
            f"Core themes: {themes}.",
            motif_sentence,
            f"Photographic direction: {composition}; {lighting}; {tonal_cue}.",
            f"Color palette: {palette}.",
            typography_zone,
            (
                "Use a believable camera viewpoint, music-industry editorial styling, authentic wardrobe/props, "
                "layered foreground-midground-background depth, and one memorable focal subject. It should look like a real "
                "album campaign photographed or art-directed for a recording artist."
            ),
            (
                "Avoid the repeated AI-art clichés unless the lyrics explicitly demand them: no cracked marble or metal faces, "
                "no shattered statues, no floating face fragments, no generic disintegrating bust, no glowing cyber mask, "
                "and no random abstract geometry as the main concept."
            ),
            (
                "Square composition. No generated typography, letters, fake logos, fake record-label marks, watermarks, "
                "or recognizable celebrities. Do not imitate a living artist's signature style. Exact release text and "
                "parental-advisory text are composited separately after image generation."
            ),
        ]
        if part.strip()
    )


def variation_prompt(base_prompt: str, position: int) -> str:
    # Each variation uses a materially different album-cover archetype.  This is
    # deliberately concrete so 3-5 requests do not collapse into the same portrait.
    concepts = [
        (
            "CINEMATIC HERO COVER: use a believable artist/character or strong human silhouette in a real location. "
            "Medium or full-body framing, environmental context, dramatic practical lighting, premium music photography. "
            "Do not use a sculpted/statue face. Reserve the UPPER-LEFT area for typography; place any face toward center-right "
            "and keep it completely outside that text-safe area."
        ),
        (
            "NARRATIVE LOCATION COVER: make the setting tell the story. Use a roadside, street, bar, motel, vehicle, room, "
            "warehouse, landscape, or other genre-appropriate location with a person integrated naturally into the scene. "
            "Wide or medium-wide camera; avoid close-up floating faces. Reserve the LOWER-LEFT area for typography and keep "
            "faces and important hands/props above or to the right of that zone."
        ),
        (
            "CLASSIC RECORD-SLEEVE COVER: create a tactile photographed scene with subtle analog print/grain character, "
            "period-aware wardrobe or props when appropriate, strong central hierarchy, and the feel of a collectible physical release. "
            "Reserve the LOWER THIRD for bold typography. If a person is present, keep the head and full face in the upper half so "
            "the title may overlap clothing or foreground but NEVER the face."
        ),
        (
            "MODERN MIXTAPE / POSTER COVER: high-impact photographic composition with a confident central subject, vehicle or architecture, "
            "hard contrast and disciplined color accents. Reserve the TOP-CENTER strip for large exact title typography; position a human "
            "subject lower in frame so the face starts below the title-safe strip and remains fully unobstructed."
        ),
        (
            "ALTERNATE STORY COVER: choose a different location, camera distance, time of day, dominant prop, and subject pose from all earlier "
            "directions. Make it clearly distinct at thumbnail size while staying faithful to the same song and genre. Reserve the BOTTOM-CENTER "
            "area for typography and keep every face in the upper two-thirds, fully clear of the text-safe area."
        ),
    ]
    concept = concepts[(position - 1) % len(concepts)]
    return (
        f"{base_prompt} VARIATION {position} ART DIRECTION: {concept} "
        "This image must not repeat the composition, focal object, or camera setup of another variation."
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
        return "balanced editorial framing with a clear album-cover hierarchy"
    if tempo >= 135 or energy >= 0.72:
        return "dynamic low or eye-level camera, decisive body language, compressed depth, and controlled motion cues"
    if tempo >= 100:
        return "confident eye-level framing, rhythmic environmental detail, and a strong centered-to-offset subject"
    if tempo >= 75:
        return "measured cinematic framing with environmental storytelling and deliberate negative space"
    return "wide or intimate slow-paced framing, substantial negative space, and restrained subject movement"


def _lighting(valence: float, energy: float) -> str:
    if valence > 0.25 and energy > 0.55:
        return "golden-hour or bright practical light with crisp highlights and optimistic contrast"
    if valence < -0.25 and energy > 0.55:
        return "night or storm-light cinematography, hard rim light, selective red/tungsten practicals, and dense blacks"
    if valence < -0.25:
        return "moody dusk, overcast, or low-key practical light with restrained highlights"
    if energy < 0.36:
        return "soft natural or practical light with atmospheric depth and gentle falloff"
    return "cinematic side light with realistic practical sources and controlled contrast"


def _genre_world(signal: dict[str, Any]) -> str:
    genre = signal.get("inferred_genre") or "cinematic / experimental"
    return _GENRE_WORLDS.get(genre, _GENRE_WORLDS["cinematic / experimental"])


def _tonal_cue(scale: str | None, key: str | None) -> str:
    if scale == "major":
        return "the scene should feel emotionally open, resolved, and forward-looking"
    if scale == "minor":
        return "the scene should carry tension, shadow, or introspection without relying on horror clichés"
    return "the scene should feel emotionally balanced and tonally ambiguous"
