from __future__ import annotations

import hashlib
import json
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
        "Americana record photography with tactile natural materials, honest wardrobe, weathered print character, "
        "open-air light, lived-in detail and human storytelling; avoid genre-stereotype scenery"
    ),
    "acoustic / singer-songwriter": (
        "intimate roots-music photography with natural fabrics, quiet gestures, personal objects, window or outdoor light, "
        "human-scale storytelling and restrained production design"
    ),
    "hip-hop / trap": (
        "premium rap and mixtape photography with confident styling, documentary immediacy, bold silhouette, tactile surfaces, "
        "flash or cinematic practical light and culturally believable detail; genre alone must not determine the setting or props"
    ),
    "R&B / soul": (
        "luxury R&B editorial photography with intimate gesture, elegant wardrobe, reflective materials, warm practical light, "
        "sensual negative space and emotionally specific styling rather than stock luxury props"
    ),
    "rock / alternative": (
        "gritty music-editorial photography with physical texture, documentary flash, expressive movement, worn materials, "
        "performance residue and tactile print character without generic genre scenery"
    ),
    "electronic / dance": (
        "nightlife and movement photography with controlled motion blur, reflective surfaces, practical colored light, crowd energy, "
        "graphic shadows and disciplined futuristic detail without defaulting to stock nightlife scenery"
    ),
    "pop": (
        "major-label pop editorial photography with memorable fashion, clean visual hooks, strong color relationships, playful physical props, "
        "polished lighting and immediately readable silhouettes"
    ),
    "ambient": (
        "atmospheric photography with weather, water, sky, natural texture, scale, distance, stillness and restrained cinematic production design"
    ),
    "cinematic / experimental": (
        "cinematic narrative photography with unusual but believable physical ideas, tactile materials, practical effects, expressive framing, "
        "unexpected human detail and grounded production design"
    ),
}

# These pools intentionally span different subject types and camera languages.  A
# deterministic fingerprint chooses one from each pool using the immutable input
# hash plus variation-set number.  That makes different songs (and fresh sets of
# the same song) start from different visual premises rather than one house style.
_SUBJECT_MODES = [
    "no person at all; use one song-specific physical symbol or natural element as the protagonist",
    "one full-body human subject with expressive posture and no posed headshot",
    "a candid two-person interaction that communicates relationship, tension or celebration",
    "a tactile still-life built from two or three objects that actually connect to the song",
    "a distant human silhouette shaped by weather, landscape, light or negative space",
    "hands, clothing and an action in progress; keep faces outside the typography zone",
    "a documentary moment caught mid-action rather than someone simply looking at camera",
    "a fashion-led character study with a simple non-descriptive background and strong body language",
    "an everyday ritual or private moment made visually specific through gesture and one meaningful prop",
    "a physical installation or practical set piece built around a lyric-derived symbol, photographed as if it really exists",
]

_CAMERA_MODES = [
    "wide 24mm environmental frame from a low viewpoint",
    "compressed 85mm telephoto frame with layered foreground and background",
    "overhead or high-angle frame with graphic real-world geometry",
    "off-center 35mm documentary frame with imperfect candid energy",
    "view through fabric, glass, foliage, smoke, a mirror edge or another foreground obstruction",
    "ground-level frame that makes a person or song-specific object feel monumental",
    "long-distance frame with the focal subject occupying less than one third of the cover",
    "tight object/detail crop with no conventional head-and-shoulders portrait",
    "waist-level candid frame with asymmetry and human movement",
    "diagonal composition with strong depth and a non-centered focal point",
]

_TIME_WEATHER = [
    "blue hour just before night, with subtle practical light beginning to glow",
    "hard midday sun with honest shadows and documentary realism",
    "rainy twilight with wet natural surfaces and restrained color",
    "late golden hour with long directional shadows",
    "overcast morning with soft contrast and subdued color",
    "deep night lit by one believable local light source rather than generic neon",
    "foggy dawn with layers of atmospheric depth",
    "hot dusk after sunset with residual sky color and tungsten warmth",
    "winter-gray daylight with crisp air and minimal saturation",
    "direct-flash night photography with the background falling into darkness",
]

_IMAGE_MAKING = [
    "clean contemporary music-editorial photography with realistic skin and materials",
    "35mm color-negative character with visible but controlled grain",
    "medium-format record-sleeve photography with rich tonal depth",
    "documentary direct-flash photography with intentional imperfection",
    "cinematic still-frame photography with subtle halation and practical light",
    "late-1990s or early-2000s magazine photography translated into a modern release",
    "tactile printed-photo look with subtle paper and ink character, not digital grunge",
    "polished commercial photography with restrained color grading and believable texture",
]

_LAYOUTS = [
    "large negative space in the upper third and visual weight low in frame",
    "visual weight on the left with clean breathing room on the right",
    "visual weight on the right with clean breathing room on the left",
    "low horizon and a large field of sky, color or negative space",
    "foreground texture or object creates depth while the main story happens farther back",
    "strong diagonal movement across the square rather than centered symmetry",
    "small focal subject surrounded by substantial environmental or tonal context",
    "layered foreground, middle ground and background with no dominant face",
]

_VARIATION_ARCHETYPES = [
    "LYRIC-SYMBOL SLEEVE: choose one concrete symbol that is justified by the lyrics and make it unforgettable; no generic music-video props.",
    "DOCUMENTARY MOMENT: capture a believable action that feels observed rather than staged; nobody should simply pose at camera.",
    "TACTILE STILL-LIFE: build the cover around two or three song-specific objects or materials with strong lighting and physical texture.",
    "WIDE EMOTIONAL SCENE: use weather, landscape, people or open space to tell the emotional story without relying on an urban exterior.",
    "CHARACTER COVER: use a believable full- or three-quarter-body subject with expressive wardrobe and posture; never default to a centered face close-up.",
    "FASHION / PORTRAIT SLEEVE: create a striking artist-like character study against a simple or abstracted physical backdrop, with styling carrying the genre.",
    "AFTER-THE-EVENT SCENE: imply that something important just happened through traces, objects, gesture, light or weather; do not use a car or building as shorthand.",
    "UNEXPECTED VIEWPOINT: use overhead, through-glass, reflected, cropped-detail or ground-level framing instead of eye-level portrait framing.",
    "MINIMAL PHYSICAL COVER: use one lyric-relevant object, body detail, natural element or material plus substantial negative space.",
    "ENERGETIC HUMAN COVER: show movement through dance, running, performance residue, fabric, gesture or crowd energy without requiring a vehicle.",
    "INTIMATE DETAIL COVER: crop to hands, clothing, an object, touch or interaction; communicate emotion without relying on a face.",
    "PRACTICAL CONCEPT COVER: stage one surprising but physically believable visual idea derived from the song, with no default architecture or transportation imagery.",
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
    literal_permissions = _literal_permissions(signal)
    scene_cues = _story_cues(signal)

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
            f"Song-specific story cue bank: {scene_cues}.",
            motif_sentence,
            literal_permissions,
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
                "ANTI-TEMPLATE RULE: do not default to a centered person, centered head, close-up face, transportation imagery, architecture-led scenery, generic nightlife exteriors or any repeated stock music-cover location. "
                "Transportation and architecture-led compositions are forbidden unless the song-specific permission rule above explicitly allows them. The cover must be identifiable at thumbnail size by its own subject, gesture, symbol, color field or silhouette."
            ),
            (
                "Use authentic wardrobe, props, natural elements and human behavior. Favor concrete song-specific story over genre stereotypes. A person is optional, not required. "
                "Vary subject count, camera distance, horizon position, dominant shape, material, activity and color relationship from other covers."
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


_PLAN_MARKER = "\n\n[[EZ_AI_CONCEPT_PLAN_V1]]\n"


def attach_concept_plan(base_prompt: str, concepts: list[dict[str, str]]) -> str:
    """Persist the creative-director plan inside VariationSet.prompt without a DB migration."""
    payload = json.dumps({"concepts": concepts}, ensure_ascii=False, separators=(",", ":"))
    return f"{base_prompt}{_PLAN_MARKER}{payload}"


def _split_concept_plan(stored_prompt: str) -> tuple[str, list[dict[str, str]]]:
    if _PLAN_MARKER not in stored_prompt:
        return stored_prompt, []
    base, payload = stored_prompt.split(_PLAN_MARKER, 1)
    try:
        parsed = json.loads(payload)
        concepts = parsed.get("concepts", [])
        if isinstance(concepts, list):
            return base, [item for item in concepts if isinstance(item, dict)]
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return base, []


def variation_prompt(base_prompt: str, position: int) -> str:
    clean_base, concepts = _split_concept_plan(base_prompt)
    if concepts:
        index = (max(position, 1) - 1) % len(concepts)
        concept = concepts[index]
        return (
            f"{clean_base} CREATIVE DIRECTOR CONCEPT {position}: {concept.get('name', 'Untitled concept')}. "
            f"SUBJECT: {concept.get('subject', '')}. SETTING: {concept.get('setting', '')}. "
            f"ACTION OR SYMBOL: {concept.get('action_or_symbol', '')}. CAMERA: {concept.get('camera', '')}. "
            f"MEDIUM: {concept.get('medium', '')}. PALETTE: {concept.get('palette', '')}. "
            f"TYPOGRAPHY SAFE ZONE: {concept.get('typography_zone', '')}. "
            f"FINAL IMAGE DIRECTION: {concept.get('image_prompt', '')}. "
            "Follow this concept as the primary art direction. Do not borrow the subject, setting, camera, or central metaphor from the other variations. "
            "No generated title, artist lettering, logos, or watermarks."
        )

    base_prompt = clean_base
    # Fallback when the creative-director API is unavailable: choose a per-set permutation.
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
    scenes = _scene_pool(signal)
    return {
        "subject": _pick(_SUBJECT_MODES, digest, 0),
        "setting": _pick(scenes, digest, 3),
        "camera": _pick(_CAMERA_MODES, digest, 7),
        "time_weather": _pick(_TIME_WEATHER, digest, 11),
        "image_making": _pick(_IMAGE_MAKING, digest, 15),
        "layout": _pick(_LAYOUTS, digest, 19),
    }


def _pick(options: list[str], digest: bytes, offset: int) -> str:
    value = int.from_bytes(digest[offset:offset + 3], "big")
    return options[value % len(options)]


def _scene_pool(signal: dict[str, Any]) -> list[str]:
    """Return varied scene premises without letting genre inject stock cars/buildings.

    Lyrics can explicitly earn a transportation/architecture cue through
    `_literal_permissions`, but the fallback scene pool remains neutral and human,
    object, nature and action led.
    """
    themes = {str(x).lower() for x in signal.get("themes", [])}
    words = {
        str(x).lower().replace("-", " ")
        for x in [*signal.get("keywords", []), *signal.get("imagery", [])]
    }
    scenes = [
        "a simple studio or seamless backdrop transformed by wardrobe, gesture and lighting rather than scenery",
        "an open natural landscape where weather, body language and color carry the story",
        "a close human-scale moment centered on hands, clothing, touch or an action",
        "a tactile tabletop or floor-level still-life using only song-relevant objects and materials",
        "a sparse practical set with one oversized physical symbol derived from the song",
        "a performance-adjacent moment focused on movement, sweat, fabric, cables, instruments or aftermath rather than a stage pose",
        "a private everyday ritual photographed with documentary intimacy",
        "a water, field, sky, tree-line or other natural setting selected for emotional tone rather than genre stereotype",
        "a monochrome or limited-color physical set where silhouette and texture create the hook",
        "a group or two-person candid moment whose relationship tells the story",
        "a reflective, translucent, fabric, smoke, rain or shadow-based practical setup with no futuristic CGI",
        "an unusual crop of a person or object that turns an ordinary detail into the cover's central icon",
    ]

    if "love and intimacy" in themes:
        scenes.extend([
            "an intimate two-person gesture with faces optional and touch carrying the emotion",
            "a private still-life of flowers, fabric, jewelry, a handwritten note or another lyric-supported keepsake",
        ])
    if "loss and memory" in themes:
        scenes.extend([
            "an empty chair, worn photograph, folded clothing or another believable trace of someone absent",
            "a weathered personal object isolated in quiet light with negative space suggesting memory",
        ])
    if "freedom and escape" in themes:
        scenes.extend([
            "a person moving through open land, shoreline, wind or vast sky with no transportation required",
            "an open path or horizon with strong directional movement and a small human figure",
        ])
    if "nature and seasons" in themes:
        scenes.extend([
            "a shoreline, river edge, forest clearing, rain field or seasonal landscape tied to the lyric imagery",
            "a close natural detail such as water, leaves, flowers, mud, ice or wind-tossed grass used as the visual hook",
        ])
    if "identity and reflection" in themes:
        scenes.extend([
            "a mirror, reflection, shadow or wardrobe transformation used as a physically believable identity motif",
            "a cropped character study where posture, styling and reflection reveal identity without fantasy effects",
        ])
    if "conflict and defiance" in themes:
        scenes.extend([
            "a tense physical gesture, torn material, scuffed floor, smoke, rain or aftermath suggesting conflict without weapons",
            "a defiant full-body stance against a simple backdrop with movement in clothing or weather",
        ])
    if "success and ambition" in themes:
        scenes.extend([
            "a disciplined fashion portrait where tailoring, jewelry or one earned object signals ambition without cars or mansions",
            "a work-in-progress scene centered on hands, notes, equipment or ritual rather than generic luxury",
        ])

    # Literal lyric imagery may add scenes, but only when those words are present.
    if words & {"ocean", "sea", "water", "wave", "river"}:
        scenes.append("a water-edge scene directly justified by the lyrics, with weather and scale carrying the emotion")
    if words & {"forest", "tree", "mountain", "field", "sky", "moon", "sun", "winter", "rain", "storm"}:
        scenes.append("a natural landscape directly built from the lyric imagery rather than a genre stereotype")
    if words & {"mirror", "glass", "window"}:
        scenes.append("a reflection or transparency-based physical composition directly justified by the lyric imagery")
    if words & {"flower", "flowers", "rose", "roses"}:
        scenes.append("a floral physical composition used as a lyric-specific object rather than generic decoration")
    if words & {"car", "cars", "truck", "pickup", "vehicle", "whip"}:
        scenes.append("a contemporary vehicle used because transportation is explicitly named in the lyrics; avoid classic-car nostalgia unless the lyric specifically says classic or vintage")
    if words & {"house", "home", "room", "hotel", "motel", "apartment", "building"}:
        scenes.append("an interior or exterior place directly justified by a named lyrical location; make the human story more important than the architecture")

    return scenes


def _story_cues(signal: dict[str, Any]) -> str:
    pool = _scene_pool(signal)
    # Keep the base prompt concise but give the model multiple directions other
    # than the one deterministic setting selected for visual DNA.
    return " | ".join(pool[:6])


def _literal_permissions(signal: dict[str, Any]) -> str:
    words = {
        str(x).lower().replace("-", " ")
        for x in [*signal.get("keywords", []), *signal.get("imagery", [])]
    }
    vehicle_words = {"car", "cars", "truck", "pickup", "vehicle", "whip"}
    place_words = {"house", "home", "room", "hotel", "motel", "apartment", "building"}
    vehicle_allowed = bool(words & vehicle_words)
    architecture_allowed = bool(words & place_words)

    vehicle_rule = (
        "Vehicle permission: ALLOWED because a vehicle is explicitly present in the lyrical signal; use it only if it strengthens the specific story, and do not automatically make it a classic car."
        if vehicle_allowed
        else "Transportation imagery: FORBIDDEN for this song — do not include any vehicle or transportation-centered composition."
    )
    architecture_rule = (
        "Architecture permission: ALLOWED because a house/room/building-type place is explicitly present in the lyrical signal; keep people, action or a lyric-specific object more important than the structure."
        if architecture_allowed
        else "Architecture-led imagery: FORBIDDEN for this song — do not use a structure, facade, skyline or built environment as the visual subject."
    )
    return vehicle_rule + " " + architecture_rule



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
        cues.append("the attack pattern is assertive, so build directional movement into bodies, fabric, shadows, weather or perspective")

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
