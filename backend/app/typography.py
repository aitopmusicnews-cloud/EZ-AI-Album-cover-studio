from __future__ import annotations

import hashlib
import json
from math import gcd
from typing import Any


TYPOGRAPHY_TOKEN_SEPARATOR = "::"

# A style is a design system, not merely a font filename.  The compositor uses
# the suffix in the returned token to vary the installed typeface, ink treatment
# and rotation while keeping exact title spelling deterministic.
STYLE_DESCRIPTIONS: dict[str, str] = {
    "street_script": "expressive street-script lettering with energetic hand-painted motion",
    "luxury_script": "elegant flowing script-signature lettering with editorial restraint",
    "heritage_script": "warm heritage script inspired by vintage record sleeves and painted signage",
    "marker_signature": "raw handwritten marker lettering with natural irregularity",
    "vintage_arc": "arched vintage display lettering with individual character rotation",
    "editorial_italic": "high-fashion italic lettering with an offset editorial composition",
    "slanted_serif": "dramatic slanted serif lettering with layered shadow and print depth",
    "condensed_poster": "tall condensed poster lettering with oversized scale and tight rhythm",
    "geometric_modern": "clean geometric display lettering with controlled spacing and asymmetry",
    "psychedelic_display": "curved psychedelic display lettering with playful baseline movement",
    "gothic_blackletter": "ornamental blackletter-inspired display type used with modern restraint",
    "stencil_cutout": "stenciled cut-paper lettering with physical gaps and rough ink edges",
    "typewriter_grunge": "typewriter-inspired lettering with imperfect print registration",
    "art_deco": "elegant Art Deco display lettering with architectural rhythm",
    "minimal_spaced": "minimal wide-tracked lettering with premium negative space",
    "retro_bubble": "rounded retro display lettering with buoyant scale changes",
    "newspaper_collage": "editorial collage lettering with contrasting scale and print texture",
    "cinematic_title": "cinematic title lettering with elegant proportions and subtle depth",
}

_GENRE_STYLE_POOLS: dict[str, tuple[str, ...]] = {
    "hip-hop / trap": (
        "street_script", "marker_signature", "condensed_poster", "stencil_cutout",
        "newspaper_collage", "gothic_blackletter", "slanted_serif", "typewriter_grunge",
        "geometric_modern", "vintage_arc", "retro_bubble", "editorial_italic",
    ),
    "R&B / soul": (
        "luxury_script", "editorial_italic", "cinematic_title", "art_deco",
        "heritage_script", "minimal_spaced", "vintage_arc", "slanted_serif",
        "geometric_modern", "marker_signature", "psychedelic_display", "retro_bubble",
    ),
    "country / americana": (
        "heritage_script", "vintage_arc", "typewriter_grunge", "slanted_serif",
        "marker_signature", "condensed_poster", "cinematic_title", "stencil_cutout",
        "editorial_italic", "newspaper_collage", "art_deco", "minimal_spaced",
    ),
    "acoustic / singer-songwriter": (
        "heritage_script", "marker_signature", "typewriter_grunge", "editorial_italic",
        "minimal_spaced", "vintage_arc", "luxury_script", "newspaper_collage",
        "cinematic_title", "slanted_serif", "geometric_modern", "art_deco",
    ),
    "rock / alternative": (
        "marker_signature", "stencil_cutout", "condensed_poster", "typewriter_grunge",
        "gothic_blackletter", "newspaper_collage", "slanted_serif", "street_script",
        "psychedelic_display", "vintage_arc", "geometric_modern", "editorial_italic",
    ),
    "electronic / dance": (
        "geometric_modern", "minimal_spaced", "condensed_poster", "art_deco",
        "editorial_italic", "retro_bubble", "psychedelic_display", "stencil_cutout",
        "cinematic_title", "slanted_serif", "vintage_arc", "street_script",
    ),
    "pop": (
        "luxury_script", "retro_bubble", "editorial_italic", "geometric_modern",
        "art_deco", "marker_signature", "minimal_spaced", "psychedelic_display",
        "cinematic_title", "vintage_arc", "condensed_poster", "newspaper_collage",
    ),
    "ambient": (
        "minimal_spaced", "editorial_italic", "cinematic_title", "heritage_script",
        "geometric_modern", "art_deco", "typewriter_grunge", "vintage_arc",
        "luxury_script", "slanted_serif", "condensed_poster", "marker_signature",
    ),
    "cinematic / experimental": tuple(STYLE_DESCRIPTIONS),
}

# Each style can be paired with many installed faces, twelve ink/treatment
# recipes and five face-safe layouts.  This conservative capacity figure does
# not count title-length-specific wrapping or color variation.
FONT_VARIANTS_PER_STYLE = 20
TREATMENT_VARIANTS = 12
FACE_SAFE_LAYOUTS = 5


def typography_idea_capacity() -> int:
    return len(STYLE_DESCRIPTIONS) * FONT_VARIANTS_PER_STYLE * TREATMENT_VARIANTS * FACE_SAFE_LAYOUTS


def split_typography_token(token: str | None) -> tuple[str, str]:
    raw = token or "cinematic_title"
    style, separator, variation_seed = raw.partition(TYPOGRAPHY_TOKEN_SEPARATOR)
    if style not in STYLE_DESCRIPTIONS:
        style = "cinematic_title"
    return style, variation_seed if separator else style


def choose_typography_style(
    signal: dict[str, Any] | None,
    position: int,
    *,
    creative_seed: str | None = None,
) -> str:
    """Return a genre-aware typography token with high-cardinality variation.

    The optional creative seed must identify the variation set.  It prevents a
    regenerated set from restarting at the same style/font/treatment sequence.
    Calls without a seed retain the simple style name for backwards compatibility.
    """
    clean_signal = signal or {}
    genre = str(clean_signal.get("inferred_genre") or "cinematic / experimental")
    pool = _GENRE_STYLE_POOLS.get(genre, _GENRE_STYLE_POOLS["cinematic / experimental"])
    slot = max(1, position) - 1

    if creative_seed is None:
        return pool[slot % len(pool)]

    material = json.dumps(clean_signal, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(f"{creative_seed}|{material}".encode("utf-8")).digest()
    start = int.from_bytes(digest[:4], "big") % len(pool)
    step_options = [value for value in range(1, len(pool)) if gcd(value, len(pool)) == 1]
    step = step_options[digest[4] % len(step_options)]
    style = pool[(start + slot * step) % len(pool)]
    variant = hashlib.sha256(
        f"{creative_seed}|{material}|{position}|{style}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{style}{TYPOGRAPHY_TOKEN_SEPARATOR}{variant}"


def typography_direction(
    signal: dict[str, Any] | None,
    position: int,
    *,
    creative_seed: str | None = None,
) -> str:
    token = choose_typography_style(signal, position, creative_seed=creative_seed)
    style, _ = split_typography_token(token)
    return STYLE_DESCRIPTIONS[style]
