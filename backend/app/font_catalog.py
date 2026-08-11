from __future__ import annotations

import hashlib
from pathlib import Path


FONT_ROOT = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Every entry points to a font shipped with its license under assets/fonts.
# Categories intentionally overlap: a strong display face can serve more than
# one art direction, while seeded ordering prevents the same face recurring.
BUNDLED_FONTS: dict[str, tuple[str, ...]] = {
    "script": (
        "allura/Allura-Regular.ttf",
        "chopin-script/ChopinScript.ttf",
        "magnolia-script/Magnolia Script.otf",
        "ranch-mails/Ranch Mails.otf",
        "armadillo/Armadillo.ttf",
        "butflow/Butflow.otf",
    ),
    "hand": (
        "punk-kid/punk kid.ttf",
        "baksoap/Baksoap.otf",
        "the-battle-continuez/TheBattleCont.ttf",
        "chainsaw-carnage/ChainsawCarnage.otf",
        "heart-breaking-bad/Heart Breaking Bad.otf",
        "ranch-mails/Ranch Mails.otf",
    ),
    "condensed": (
        "league-gothic/LeagueGothic-CondensedRegular.otf",
        "league-gothic/LeagueGothic-CondensedItalic.otf",
        "montserrat/Montserrat-Black.otf",
        "poppins/Poppins-Black.ttf",
        "ferro-rosso/FerroRosso.ttf",
        "underground/UndergroundNF.otf",
    ),
    "editorial": (
        "libre-baskerville/LibreBaskerville-Italic.ttf",
        "libre-baskerville/LibreBaskerville-Bold.ttf",
        "league-gothic/LeagueGothic-Italic.otf",
        "montserrat/Montserrat-Italic.otf",
        "poppins/Poppins-Italic.ttf",
        "allura/Allura-Regular.ttf",
    ),
    "modern": (
        "montserrat/Montserrat-Regular.otf",
        "montserrat/Montserrat-Bold.otf",
        "poppins/Poppins-Regular.ttf",
        "poppins/Poppins-Bold.ttf",
        "league-gothic/LeagueGothic-Regular.otf",
        "contour-generator/Contour Generator.otf",
    ),
    "display": (
        "pixemon/Pixemon.otf",
        "corleone/Corleone.ttf",
        "corleone/CorleoneDue.ttf",
        "dystopian-canticle/Dystopian-Canticle-Regular.otf",
        "homoarakhn/HOMOARAK.TTF",
        "if/If.ttf",
        "marlboro/Marlboro.ttf",
        "miltown/Miltown_.ttf",
        "the-rave-is-in-your-pants/The Rave Is In Your Pants.otf",
        "underground/UndergroundNF.otf",
        "ferro-rosso/FerroRosso.ttf",
        "heart-breaking-bad/Heart Breaking Bad.otf",
    ),
}


def bundled_font_candidates(category: str, token: str) -> list[str]:
    """Return real bundled faces in deterministic, generation-specific order."""
    entries = BUNDLED_FONTS.get(category, BUNDLED_FONTS["display"])
    available = [str(FONT_ROOT / relative) for relative in entries if (FONT_ROOT / relative).is_file()]
    return sorted(
        available,
        key=lambda path: hashlib.sha256(f"{token}|bundled|{path}".encode("utf-8")).digest(),
    )


def all_bundled_font_paths() -> tuple[Path, ...]:
    return tuple(sorted({FONT_ROOT / item for entries in BUNDLED_FONTS.values() for item in entries}))
