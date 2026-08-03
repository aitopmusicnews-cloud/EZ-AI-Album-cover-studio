from __future__ import annotations

from typing import Any

from .style_presets import StylePreset


_RENDER_VARIATIONS = {
    1: "Use the strongest direct execution of the concept with disciplined commercial polish.",
    2: "Preserve the exact concept and metaphor, but change camera distance, crop, and lighting execution.",
    3: "Preserve the exact concept and metaphor, but explore a bolder material and color treatment.",
}


def build_render_prompt(
    *,
    base_brief: str,
    concept: dict[str, Any],
    render_index: int,
    style_preset: StylePreset,
    improvement_feedback: list[str] | None = None,
) -> str:
    feedback = ""
    if improvement_feedback:
        feedback = " Improvements required: " + "; ".join(improvement_feedback[:8]) + "."
    execution = _RENDER_VARIATIONS.get(
        render_index,
        "Preserve the exact concept while changing only execution details, never the central story.",
    )
    return " ".join(
        [
            base_brief.strip(),
            f"CONCEPT: {concept.get('name', 'Untitled')}.",
            f"Subject: {concept.get('subject', '')}.",
            f"Setting: {concept.get('setting', '')}.",
            f"Action or symbol: {concept.get('action_or_symbol', '')}.",
            f"Camera: {concept.get('camera', '')}.",
            f"Medium: {concept.get('medium', '')}.",
            f"Palette: {concept.get('palette', '')}.",
            f"Typography-safe zone: {concept.get('typography_zone', '')}.",
            f"Primary image direction: {concept.get('image_prompt', '')}.",
            style_preset.prompt_fragment(),
            execution,
            feedback,
            "Do not borrow the subject, setting, camera, or central metaphor from another concept.",
            "No generated title, artist text, fake logos, label marks, or watermarks.",
        ]
    ).strip()
