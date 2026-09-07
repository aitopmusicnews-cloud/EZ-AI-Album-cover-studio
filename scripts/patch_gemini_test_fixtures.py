from __future__ import annotations

from pathlib import Path


def replace_all(path: str, replacements: list[tuple[str, str]]) -> None:
    file = Path(path)
    source = file.read_text(encoding="utf-8")
    for old, new in replacements:
        if old not in source:
            raise RuntimeError(f"Patch target not found in {path}: {old!r}")
        source = source.replace(old, new)
    file.write_text(source, encoding="utf-8")


# Pipeline tests inject fake provider implementations, so keep Gemini network access
# disabled by default. Individual provider-configuration tests opt in explicitly.
replace_all(
    "backend/tests/conftest.py",
    [
        (
            "        creative_director: Any | None = None,\n        retry_attempts: int = 3,\n",
            "        creative_director: Any | None = None,\n        retry_attempts: int = 3,\n        gemini_api_key: str | None = None,\n",
        ),
        (
            "            openai_api_key=\"test-key\",\n",
            "            gemini_api_key=gemini_api_key,\n",
        ),
        ("media[i]", "media[i % len(media)]"),
        ("subjects[i]", "subjects[i % len(subjects)]"),
        ("settings[i]", "settings[i % len(settings)]"),
        ("cameras[i]", "cameras[i % len(cameras)]"),
    ],
)

replace_all(
    "backend/tests/test_pipeline.py",
    [
        ("OpenAIAuthenticationError", "GeminiAuthenticationError"),
        ("OpenAIRateLimitError", "GeminiRateLimitError"),
        ("OpenAIServiceError", "GeminiServiceError"),
        ("openai_rate_limit", "gemini_rate_limit"),
        ("openai_service_unavailable", "gemini_service_unavailable"),
        ("openai_authentication_error", "gemini_authentication_error"),
        ("test_openai_errors_surface_cleanly", "test_gemini_errors_surface_cleanly"),
        ("test_same_input_returns_cached_variations_without_openai", "test_same_input_returns_cached_variations_without_rerendering"),
        ("openai_api_key=\"openai-test-key\",", "gemini_api_key=\"gemini-test-key\",") ,
        ('client, *_ = app_factory()\n    body = client.get("/health").json()', 'client, *_ = app_factory(gemini_api_key="gemini-test-key")\n    body = client.get("/health").json()'),
        ('body["providers"]["openai_images"]["configured"] is True', 'body["providers"]["gemini_images"]["configured"] is True'),
        ('body["providers"]["openai_images"]["model"] == "gpt-image-2"', 'body["providers"]["gemini_images"]["model"] == "gemini-3.1-flash-image"'),
        ('all("CREATIVE DIRECTOR CONCEPT" in p for p in images.prompts)', 'all("CONCEPT:" in p for p in images.prompts)'),
        ('assert any("cut-paper collage" in p for p in images.prompts)\n    assert any("screenprint sleeve" in p for p in images.prompts)', 'concept_names = {p.split("CONCEPT:", 1)[1].split(".", 1)[0].strip() for p in images.prompts}\n    assert len(concept_names) >= 2'),
        ('assert "Concept 1-1" in director.previous_prompts_seen[1][0]', 'assert "Create a commercially credible" in director.previous_prompts_seen[1][0]'),
    ],
)

pipeline = Path("backend/tests/test_pipeline.py")
source = pipeline.read_text(encoding="utf-8")
needle = '    assert body["providers"]["gemini_images"]["model"] == "gemini-3.1-flash-image"\n'
if needle not in source:
    raise RuntimeError("Gemini health assertion not found")
source = source.replace(
    needle,
    needle + '    assert "openai_images" not in body["providers"]\n',
    1,
)
pipeline.write_text(source, encoding="utf-8")

print("Gemini provider test fixtures updated")
