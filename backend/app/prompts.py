from __future__ import annotations

import hashlib
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

_GENRE_WORLDS = {
    "country / americana": (
        "Americana record photography with believable rural and small-town life: back roads, roadside bars, "
        "motels, diners, garages, fields, trucks, old wood, denim, instruments, weathered signs and open sky"
    ),
    "acoustic / singer-songwriter": (
        "intimate roots-music photography: modest rooms, porches, diners, roadside stops, old cars, guitar cases, "
        "natural fabrics, window light and human-scale storytelling"
    ),
    "hip-hop / trap": (
        "premium rap and mixtape photography grounded in real environments: apartment blocks, storefronts, studios, "
        "parking structures, cars, convenience stores, rooftops, concrete, chrome and night streets"
    ),
    "R&B / soul": (
        "luxury R&B editorial photography: intimate interiors, late-night windows, hotel corridors, classic cars, "
        "velvet, leather, reflective glass, elegant wardrobe and warm practical light"
    ),
    "rock / alternative": (
        "gritty music-editorial photography: rehearsal rooms, garages, industrial edges, backstage corridors, roadside "
        "stops, amplifiers, worn vehicles, documentary flash and tactile print texture"
    ),
    "electronic / dance": (
        "nightlife photography: warehouses, tunnels, night highways, backstage spaces, crowd silhouettes, reflective "
        "surfaces, practical neon, controlled motion blur and disciplined futuristic detail"
    ),
    "pop": (
        "major-label pop editorial photography: memorable fashion, cinematic locations, strong props, polished practical "
        "lighting, bold believable color and immediately readable silhouettes"
    ),
    "ambient": (
        "atmospheric location photography: lonely architecture, shoreline, fog, empty roads, distant figures, large sky, "
        "natural haze, practical light and restrained cinematic production design"
    ),
    "cinematic / experimental": (
        "cinematic narrative photography: unusual but believable locations, strong physical objects, film-still framing, "
        "practical effects, tactile materials and grounded production design"
    ),
}

# These pools intentionally span different subject types and camera languages.  A
# deterministic fingerprint chooses one from each pool using the immutable input
# hash plus variation-set number.  That makes different songs (and fresh sets of
# the same song) start from different visual premises rather than one house style.
_SUBJECT_MODES = [
    "no person at all; make the environment the protagonist",
    "one full-body human subject small enough that the location remains equally important",
    "a candid two-person interaction rather than a posed portrait",
    "a meaningful vehicle or machine as the principal subject; people may be absent",
    "a still-life of two or three story-specific objects photographed like a record sleeve",
    "a distant human silhouette with identity carried by posture and setting, not facial close-up",
    "hands, clothing and an action in progress; keep faces out of frame",
    "architecture or an interior space as the hero, with only incidental human presence",
    "a documentary moment caught mid-action rather than someone looking at camera",
    "a strong physical symbol from the song placed in a believable real-world scene",
]

_CAMERA_MODES = [
    "wide 24mm environmental frame from a low viewpoint",
    "compressed 85mm telephoto frame with layered foreground and background",
    "overhead or high-angle frame with graphic real-world geometry",
    "off-center 35mm documentary frame with imperfect candid energy",
    "view through a windshield, doorway, window or foreground obstruction",
    "ground-level frame that makes objects and architecture feel monumental",
    "long-distance frame with the subject occupying less than one third of the cover",
    "tight object/detail crop with no conventional head-and-shoulders portrait",
    "symmetrical architectural frame with a deliberately small focal subject",
    "diagonal composition with strong depth and a non-centered focal point",
]

_TIME_WEATHER = [
    "blue hour just before night, with practical lights beginning to glow",
    "hard midday sun with honest shadows and documentary realism",
    "rainy night with wet surfaces but restrained neon",
    "late golden hour with long directional shadows",
    "overcast morning with soft contrast and subdued color",
    "deep night lit mainly by believable storefront, vehicle or room lights",
    "foggy dawn with layers of atmospheric depth",
    "hot dusk after sunset with residual sky color and tungsten practicals",
    "winter-gray daylight with crisp air and minimal saturation",
    "flash-lit night photography with the background falling into darkness",
]

_IMAGE_MAKING = [
    "clean contemporary music-editorial photography with realistic skin and materials",
    "35mm color-negative character with visible but controlled grain",
    "medium-format record-sleeve photography with rich tonal depth",
    "documentary direct-flash photography with intentional imperfection",
    "cinematic still-frame photography with subtle halation and practical light",
    "late-1990s or early-2000s magazine photography translated into a modern release",
    "tactile printed-photo look with subtle paper and ink character, not digital grunge",
    "polished commercial location photography with restrained color grading",
]

_LAYOUTS = [
    "large negative space in the upper third and visual weight low in frame",
    "visual weight on the left with clean breathing room on the right",
    "visual weight on the right with clean breathing room on the left",
    "low horizon and a large field of sky or architecture",
    "foreground object creates depth while the main story happens farther back",
    "strong diagonal movement across the square rather than centered symmetry",
    "small focal subject surrounded by substantial environmental context",
    "layered foreground, middle ground and background with no dominant face",
]

_VARIATION_ARCHETYPES = [
    "ENVIRONMENT-FIRST SLEEVE: no conventional portrait. Let location, weather and one story clue carry the cover.",
    "DOCUMENTARY MOMENT: capture an action that feels observed rather than staged; nobody should simply pose at camera.",
    "OBJECT-LED COVER: build the concept around a vehicle, room, instrument, clothing item, sign, photograph or other concrete story object.",
    "WIDE CINEMATIC STORY: use a wide scene with foreground, middle ground and background; human figures, if present, are secondary to the world.",
    "CHARACTER COVER: use a believable full- or three-quarter-body subject integrated into a real location; never default to a centered face close-up.",
    "PHYSICAL RECORD-SLEEVE IDEA: make the photograph feel like a collectible sleeve with one bold physical idea, practical styling and tactile detail.",
    "AFTER-THE-EVENT SCENE: imply that something important just happened or is about to happen through objects, light, weather and traces of action.",
    "UNEXPECTED VIEWPOINT: use an overhead, through-glass, doorway, windshield, reflected or ground-level viewpoint instead of eye-level portrait framing.",
    "MINIMAL REAL-WORLD COVER: use one place or object, substantial negative space and restrained styling; avoid abstract CGI symbolism.",
    "ENERGETIC LOCATION COVER: show movement in a believable place using body language, vehicle motion, crowd traces or environmental action without turning it into a performance poster.",
    "INTIMATE DETAIL COVER: crop to hands, clothing, an object or an interaction; communicate emotion without relying on a face.",
    "ARCHITECTURE-AS-CHARACTER: use a room, building, street, motel, station, diner, house or industrial space as the dominant visual identity.",
]


def build_image_prompt(
    signal: dict[str, Any],
    mood_path: str,
    *,
    title: str | None = None,
    artist: str | None = None,
    parental_advisory: bool = False,
    creative_seed: str | None = None,
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

    # The seed is derived from the exact input fingerprint and variation-set number
    # in the service layer.  Hashing it again keeps the prompt free of raw hashes
    # while giving us deterministic, extremely high-cardinality art direction.
    seed_material = creative_seed or _fallback_seed(signal, title, artist)
    visual_dna = _visual_dna(seed_material, signal)

    priority_sentence = {
        "audio": "Let musical energy, groove and production character determine the emotional center; lyrical motifs may appear only as secondary story details.",
        "lyrics": "Let the lyrical story, sentiment and imagery determine the emotional center; musical traits should shape pace, lighting and visual intensity.",
        "blend": "Balance music and lyrics equally: music determines visual energy while lyrics supply concrete story and setting clues.",
    }.get(mood_path, "Balance all available signals.")

    motif_sentence = ""
    if imagery or keywords:
        motif_sentence = (
            f"Concrete story clues available from the lyrics: {imagery or keywords}. Choose one or two only. "
            "Translate them into a believable location, action, prop, weather condition, wardrobe detail or background clue; do not simply illustrate every keyword."
        )

    release_context = ""
    if title or artist:
        bits = []
        if title:
            bits.append(f"release title is '{title}'")
        if artist:
            bits.append(f"artist name is '{artist}'")
        release_context = (
            "Release context: " + " and ".join(bits) + ". Treat the title as a conceptual clue, not as text to render. "
            "Do not draw words or lettering; exact typography is composited afterward."
        )

    typography_zone = (
        "Compose like a finished record sleeve and preserve one naturally uncluttered typography-safe area. "
        "Do not put a face in that text-safe area, and do not use the same text-safe location by habit."
    )
    if parental_advisory:
        typography_zone += " Keep a small lower corner readable for the explicit-content label."

    audio_identity = _audio_visual_cues(signal)

    return " ".join(
        part.strip()
        for part in [
            "Create a commercially credible, release-ready album or mixtape cover, not generic AI concept art.",
            release_context,
            f"Genre direction: {genre}. Broad visual vocabulary: {genre_world}.",
            f"Emotional direction: {mood['label']}.",
            priority_sentence,
            f"Core themes: {themes}.",
            motif_sentence,
            audio_identity,
            (
                "MANDATORY UNIQUE VISUAL DNA FOR THIS RELEASE: "
                f"subject strategy = {visual_dna['subject']}; setting direction = {visual_dna['setting']}; "
                f"camera = {visual_dna['camera']}; time/weather = {visual_dna['time_weather']}; "
                f"image-making language = {visual_dna['image_making']}; layout = {visual_dna['layout']}. "
                "Treat this combination as the starting premise, not optional flavor."
            ),
            f"Supporting photographic direction: {composition}; {lighting}; {tonal_cue}.",
            f"Supporting color palette: {palette}.",
            typography_zone,
            (
                "ANTI-TEMPLATE RULE: do not default to a centered person, centered head, close-up face, luxury car, city-at-night scene or the same composition just because it is a music cover. "
                "If the selected subject strategy says no person, environment, object, hands or architecture, obey it. The cover must be identifiable at thumbnail size by its own scene and silhouette."
            ),
            (
                "Use authentic wardrobe, props and locations. Favor concrete story over generic mood. A person is optional, not required. "
                "Vary subject count, camera distance, horizon position, location type and dominant object from other covers."
            ),
            (
                "Avoid repeated AI-art clichés unless the lyrics explicitly demand them: no cracked marble or metal faces, no shattered statues, "
                "no floating face fragments, no generic disintegrating bust, no glowing cyber mask, and no random abstract geometry as the main concept."
            ),
            (
                "Square composition. No generated typography, letters, fake logos, fake record-label marks, watermarks or recognizable celebrities. "
                "Do not imitate a living artist's signature style. Exact release text and parental-advisory text are composited separately after image generation."
            ),
        ]
        if part.strip()
    )


def variation_prompt(base_prompt: str, position: int) -> str:
    # Choose a per-set permutation from the base prompt itself.  Because the base
    # contains the input/set-specific visual DNA, different songs and fresh sets do
    # not receive the same five archetypes in the same order.
    digest = hashlib.sha256(base_prompt.encode("utf-8")).digest()
    start = int.from_bytes(digest[:2], "big") % len(_VARIATION_ARCHETYPES)
    step_candidates = (1, 5, 7, 11)  # all coprime to 12, preventing repeats in first five
    step = step_candidates[digest[2] % len(step_candidates)]
    index = (start + (max(position, 1) - 1) * step) % len(_VARIATION_ARCHETYPES)
    archetype = _VARIATION_ARCHETYPES[index]

    # Add a second orthogonal rotation so even archetypes that recur across songs
    # use a different framing emphasis.
    framing = _CAMERA_MODES[(digest[(position + 3) % len(digest)] + position) % len(_CAMERA_MODES)]
    layout = _LAYOUTS[(digest[(position + 11) % len(digest)] + position * 3) % len(_LAYOUTS)]

    return (
        f"{base_prompt} VARIATION {position} SPECIFIC ART DIRECTION: {archetype} "
        f"For this variation specifically, emphasize {framing}; use {layout}. "
        "Make this variation materially different from the others in subject type, camera distance, viewpoint and dominant shape. "
        "Changing only pose, clothing color or background light is not enough."
    )


def _visual_dna(seed: str, signal: dict[str, Any]) -> dict[str, str]:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    genre = signal.get("inferred_genre") or "cinematic / experimental"
    locations = _genre_locations(genre)
    return {
        "subject": _pick(_SUBJECT_MODES, digest, 0),
        "setting": _pick(locations, digest, 3),
        "camera": _pick(_CAMERA_MODES, digest, 7),
        "time_weather": _pick(_TIME_WEATHER, digest, 11),
        "image_making": _pick(_IMAGE_MAKING, digest, 15),
        "layout": _pick(_LAYOUTS, digest, 19),
    }


def _pick(options: list[str], digest: bytes, offset: int) -> str:
    value = int.from_bytes(digest[offset:offset + 3], "big")
    return options[value % len(options)]


def _genre_locations(genre: str) -> list[str]:
    pools = {
        "country / americana": [
            "an empty county road beside fields and utility poles",
            "a weathered roadside bar or honky-tonk exterior",
            "a small-town gas station or service garage",
            "a motel walkway with an old pickup nearby",
            "a diner, porch or modest kitchen with lived-in details",
            "a river crossing, fence line or wide rural landscape",
            "a fairground, parking lot or backroad gathering after hours",
            "a barn, workshop or dusty rehearsal space",
        ],
        "acoustic / singer-songwriter": [
            "a quiet apartment or rented room near a window",
            "a diner booth or late-night cafe",
            "a roadside pull-off with an old car",
            "a porch, backyard or modest neighborhood street",
            "an empty rehearsal room with an instrument case",
            "a train platform, bus stop or transitional public space",
            "a motel room with personal objects left in place",
            "a lakeside or wooded road with subdued human detail",
        ],
        "hip-hop / trap": [
            "a convenience-store forecourt or gas station",
            "an apartment-block courtyard or stairwell",
            "a parking garage with strong concrete geometry",
            "a recording-studio hallway or loading area",
            "a residential street with parked cars and porch lights",
            "a rooftop, fire escape or elevated city edge",
            "a laundromat, barbershop frontage or late-night storefront",
            "an underpass, basketball court or fenced lot",
        ],
        "R&B / soul": [
            "a hotel room or corridor after midnight",
            "a classic-car interior or curbside arrival",
            "a quiet restaurant after closing",
            "an apartment window overlooking city lights",
            "a velvet lounge or intimate rehearsal room",
            "a stairwell, elevator lobby or reflective hallway",
            "a bedroom with warm practical lamps and personal objects",
            "a poolside or terrace space at blue hour",
        ],
        "rock / alternative": [
            "a rehearsal garage with cables, cases and worn walls",
            "an industrial service road or loading dock",
            "a backstage corridor after a show",
            "a roadside motel or parking lot",
            "a basement, workshop or practice room",
            "a windswept field beside an old vehicle",
            "a fluorescent convenience store or all-night diner",
            "a concrete drainage channel, rail edge or warehouse exterior",
        ],
        "electronic / dance": [
            "an empty warehouse before doors open",
            "a tunnel, pedestrian passage or underground platform",
            "a night highway seen from inside a moving car",
            "a backstage loading area with practical work lights",
            "an empty club floor after closing",
            "a parking structure with repeated lights and concrete lines",
            "a rooftop mechanical area or city service corridor",
            "an airport, station or anonymous late-night transit space",
        ],
        "pop": [
            "a bold but believable domestic interior with one memorable prop",
            "a colorful roadside location or motel pool",
            "a clean architectural plaza or stairway",
            "a studio-built room that still feels physically real",
            "a convertible, bus stop or street corner in strong daylight",
            "a grocery aisle, diner or laundromat used as fashion editorial space",
            "a beach, parking lot or suburban street with graphic natural color",
            "a theater, dressing room or backstage environment without performance clichés",
        ],
        "ambient": [
            "an empty shoreline or breakwater",
            "a fog-covered road or bridge approach",
            "a sparse room with large windows",
            "a distant industrial landscape",
            "a snowy field or winter parking area",
            "a quiet concrete structure beside water",
            "an empty station platform at dawn",
            "a large sky above minimal architecture",
        ],
        "cinematic / experimental": [
            "an unusual but believable motel, house or institutional room",
            "an empty road intersection with one concrete story clue",
            "a service corridor, tunnel or stairwell",
            "a landscape altered by weather rather than fantasy CGI",
            "a workshop or storage space filled with tactile objects",
            "a parked vehicle in a visually distinctive real location",
            "an ordinary domestic room framed in an unexpected way",
            "a public space after hours with traces of recent activity",
        ],
    }
    return pools.get(genre, pools["cinematic / experimental"])


def _audio_visual_cues(signal: dict[str, Any]) -> str:
    audio = signal.get("audio_signal") or {}
    spectral = audio.get("spectral") or {}
    cues: list[str] = []

    bass_ratio = _float_or_none(spectral.get("bass_ratio"))
    centroid = _float_or_none(spectral.get("centroid_hz"))
    harmonic_ratio = _float_or_none(spectral.get("harmonic_ratio"))
    flatness = _float_or_none(spectral.get("flatness"))
    dynamic_range = _float_or_none(audio.get("dynamic_range_db"))
    onset = _float_or_none(spectral.get("onset_strength"))

    if bass_ratio is not None:
        if bass_ratio >= 0.34:
            cues.append("the low-end feels weighty, so favor grounded foreground mass, low horizons and tactile heavy objects")
        elif bass_ratio <= 0.18:
            cues.append("the low-end feels light, so allow more open space, air and vertical separation")
    if centroid is not None:
        if centroid >= 3200:
            cues.append("the upper spectrum is bright, suggesting crisp highlights, reflective detail and sharper edges")
        elif centroid <= 1800:
            cues.append("the timbre is dark, suggesting softer edges, deeper material texture and lower-key surfaces")
    if harmonic_ratio is not None:
        if harmonic_ratio >= 0.62:
            cues.append("the sound is strongly tonal, favoring stable geometry and organic or resonant materials")
        elif harmonic_ratio <= 0.42:
            cues.append("the sound is percussion-forward, favoring interrupted lines, motion traces and harder physical texture")
    if flatness is not None and flatness >= 0.12:
        cues.append("the texture is noisy or dense, so subtle grain, weather and imperfect surfaces fit better than pristine CGI")
    if dynamic_range is not None and dynamic_range >= 10:
        cues.append("the dynamics breathe, so use meaningful negative space with concentrated areas of visual intensity")
    if onset is not None and onset >= 1.3:
        cues.append("the attack pattern is assertive, so build directional movement into bodies, vehicles, shadows or perspective")

    if not cues:
        return "Audio-to-visual cue: keep the scene physically believable and let rhythm determine pacing rather than inventing abstract symbols."
    return "Audio-to-visual cues: " + "; ".join(cues[:3]) + "."


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fallback_seed(signal: dict[str, Any], title: str | None, artist: str | None) -> str:
    parts = [
        title or "",
        artist or "",
        str(signal.get("inferred_genre") or ""),
        str(signal.get("tempo_bpm") or ""),
        str(signal.get("key") or ""),
        str(signal.get("scale") or ""),
        "|".join(signal.get("themes", [])[:6]),
        "|".join(signal.get("keywords", [])[:10]),
    ]
    return "::".join(parts)


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
        return "energetic spatial rhythm, decisive body or object language, compressed moments and controlled motion cues"
    if tempo >= 100:
        return "confident framing, rhythmic environmental detail and clear directional movement"
    if tempo >= 75:
        return "measured cinematic pacing, environmental storytelling and deliberate negative space"
    return "slow visual pacing, substantial negative space and restrained subject movement"


def _lighting(valence: float, energy: float) -> str:
    if valence > 0.25 and energy > 0.55:
        return "golden-hour or bright practical light with crisp highlights and optimistic contrast"
    if valence < -0.25 and energy > 0.55:
        return "night or storm-light cinematography, hard rim light, selective red or tungsten practicals and dense blacks"
    if valence < -0.25:
        return "moody dusk, overcast or low-key practical light with restrained highlights"
    if energy < 0.36:
        return "soft natural or practical light with atmospheric depth and gentle falloff"
    return "cinematic side light with realistic practical sources and controlled contrast"


def _genre_world(signal: dict[str, Any]) -> str:
    genre = signal.get("inferred_genre") or "cinematic / experimental"
    return _GENRE_WORLDS.get(genre, _GENRE_WORLDS["cinematic / experimental"])


def _tonal_cue(scale: str | None, key: str | None) -> str:
    if scale == "major":
        return "the scene should feel emotionally open, resolved and forward-looking"
    if scale == "minor":
        return "the scene should carry tension, shadow or introspection without relying on horror clichés"
    return "the scene should feel emotionally balanced and tonally ambiguous"
