from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StylePresetName(StrEnum):
    MAJOR_LABEL_POP = "MAJOR_LABEL_POP"
    HIPHOP_EDITORIAL = "HIPHOP_EDITORIAL"
    INDIE_ALT = "INDIE_ALT"
    COUNTRY_COMMERCIAL = "COUNTRY_COMMERCIAL"
    RNB_PREMIUM = "RNB_PREMIUM"
    ROCK_PREMIUM = "ROCK_PREMIUM"
    EDM_FESTIVAL = "EDM_FESTIVAL"


@dataclass(frozen=True, slots=True)
class StylePreset:
    name: StylePresetName
    composition: tuple[str, ...]
    camera: tuple[str, ...]
    lighting: tuple[str, ...]
    negative_space: tuple[str, ...]
    color: tuple[str, ...]
    wardrobe: tuple[str, ...]
    prohibited_defaults: tuple[str, ...]

    def prompt_fragment(self) -> str:
        return " ".join(
            [
                f"Composition: {'; '.join(self.composition)}.",
                f"Camera: {'; '.join(self.camera)}.",
                f"Lighting: {'; '.join(self.lighting)}.",
                f"Negative space: {'; '.join(self.negative_space)}.",
                f"Color: {'; '.join(self.color)}.",
                f"Wardrobe: {'; '.join(self.wardrobe)}.",
                f"Avoid defaults: {'; '.join(self.prohibited_defaults)}.",
            ]
        )


PRESETS: dict[StylePresetName, StylePreset] = {
    StylePresetName.MAJOR_LABEL_POP: StylePreset(
        StylePresetName.MAJOR_LABEL_POP,
        ("one immediate visual hook", "clean silhouette", "campaign-ready crop"),
        ("editorial 35mm or 50mm", "confident eye line or expressive full-body gesture"),
        ("polished key light", "controlled specular highlights"),
        ("deliberate title field", "simple edge structure"),
        ("two dominant hues", "one high-energy accent"),
        ("memorable styling", "clean shape language", "no costume clichés"),
        ("generic beauty portrait", "random candy props", "empty neon gradient"),
    ),
    StylePresetName.HIPHOP_EDITORIAL: StylePreset(
        StylePresetName.HIPHOP_EDITORIAL,
        ("documentary immediacy", "bold body language", "tactile foreground"),
        ("direct flash or compressed editorial lens", "non-centered framing"),
        ("hard practical light", "deep controlled blacks"),
        ("poster-ready side field", "face kept outside title zone"),
        ("rich neutrals", "one culturally credible accent"),
        ("premium street tailoring", "personal detail over status symbols"),
        ("cars", "mansions", "parking structures", "generic smoke portrait"),
    ),
    StylePresetName.INDIE_ALT: StylePreset(
        StylePresetName.INDIE_ALT,
        ("unexpected crop", "tactile imperfection", "small narrative detail"),
        ("35mm candid", "overhead", "through-glass viewpoint"),
        ("available light", "subtle flash falloff"),
        ("asymmetric breathing room", "print-like margins"),
        ("muted base", "one surprising color relationship"),
        ("lived-in texture", "individual styling", "anti-fashion allowed"),
        ("fake film damage", "meaningless collage", "default abandoned building"),
    ),
    StylePresetName.COUNTRY_COMMERCIAL: StylePreset(
        StylePresetName.COUNTRY_COMMERCIAL,
        ("human-scale storytelling", "open-air depth", "clear focal gesture"),
        ("natural perspective", "environmental portrait when earned"),
        ("sun, window, or weather-motivated light",),
        ("sky, wall, field, or tonal area reserved for type",),
        ("warm natural materials", "clean commercial contrast"),
        ("honest contemporary wardrobe", "texture without costume"),
        ("truck", "barn", "gas station", "forced rustic nostalgia"),
    ),
    StylePresetName.RNB_PREMIUM: StylePreset(
        StylePresetName.RNB_PREMIUM,
        ("intimate gesture", "luxury through material discipline", "elegant restraint"),
        ("85mm compression or close detail", "graceful negative space"),
        ("warm practical light", "soft highlight rolloff"),
        ("quiet dark or tonal field", "uncluttered title zone"),
        ("deep jewel tones", "skin-faithful grading"),
        ("refined fabric", "jewelry as personal detail", "not generic wealth"),
        ("bedroom cliché", "generic purple neon", "smoke-filled close-up"),
    ),
    StylePresetName.ROCK_PREMIUM: StylePreset(
        StylePresetName.ROCK_PREMIUM,
        ("physical energy", "performance residue", "strong diagonal"),
        ("wide documentary lens", "direct flash", "motion-aware framing"),
        ("hard side light", "practical stage or workshop sources"),
        ("rough but intentional title field",),
        ("restrained palette", "one aggressive accent"),
        ("worn authentic materials", "movement-first styling"),
        ("fire", "skulls", "abandoned warehouse", "generic leather pose"),
    ),
    StylePresetName.EDM_FESTIVAL: StylePreset(
        StylePresetName.EDM_FESTIVAL,
        ("large readable shape", "motion and crowd scale", "graphic rhythm"),
        ("wide dynamic lens", "controlled motion blur", "high viewpoint when useful"),
        ("practical colored sources", "laser or projection only when physically grounded"),
        ("high-contrast clean title field",),
        ("electric accent colors", "deep neutral structure"),
        ("movement-friendly styling", "reflective detail used sparingly"),
        ("anonymous cyberpunk", "random chrome mask", "meaningless neon city"),
    ),
}


def get_style_preset(name: str | StylePresetName) -> StylePreset:
    try:
        key = name if isinstance(name, StylePresetName) else StylePresetName(name)
    except ValueError:
        key = StylePresetName.MAJOR_LABEL_POP
    return PRESETS[key]
