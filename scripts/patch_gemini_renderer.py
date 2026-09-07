from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    source = file.read_text(encoding="utf-8")
    if old not in source:
        raise RuntimeError(f"Patch target not found in {path}: {old[:80]!r}")
    file.write_text(source.replace(old, new, 1), encoding="utf-8")


# Active provider configuration: Gemini supplies both direction and final image rendering.
replace_once(
    "backend/app/config.py",
    '''    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_image_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
    )
    openai_image_quality: str = field(
        default_factory=lambda: os.getenv("OPENAI_IMAGE_QUALITY", "medium")
    )
    openai_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("OPENAI_TIMEOUT_SECONDS", "150"))
    )

    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
''',
    '''    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_image_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    )
    gemini_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("GEMINI_TIMEOUT_SECONDS", "150"))
    )
''',
)

# Add the Gemini image adapter while retaining the legacy OpenAI class only for backwards-compatible tests.
image_path = Path("backend/app/image_client.py")
image_source = image_path.read_text(encoding="utf-8")
image_source = image_source.replace("from typing import Any\n", "from typing import Any, Protocol\n", 1)
image_source = image_source.replace(
    '''from .errors import (
    OpenAIAuthenticationError,
    OpenAIRateLimitError,
    OpenAIRequestError,
    OpenAIServiceError,
)
''',
    '''from .errors import (
    GeminiAuthenticationError,
    GeminiRateLimitError,
    GeminiRequestError,
    GeminiServiceError,
    OpenAIAuthenticationError,
    OpenAIRateLimitError,
    OpenAIRequestError,
    OpenAIServiceError,
)
''',
    1,
)
marker = "\n\nclass OpenAIImageClient:\n"
if marker not in image_source:
    raise RuntimeError("OpenAIImageClient marker not found")
new_client = r'''

class ImageClient(Protocol):
    async def generate(self, prompt: str, position: int) -> GeneratedImage: ...
    async def generate_exact(self, prompt: str, position: int = 1) -> GeneratedImage: ...


class GeminiImageClient:
    """Gemini Image API adapter used by the production album-cover pipeline."""

    endpoint_root = "https://generativelanguage.googleapis.com/v1/models"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gemini-3.1-flash-image",
        timeout_seconds: float = 150,
        transport: httpx.AsyncBaseTransport | None = None,
        allow_mock_images: bool = False,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.allow_mock_images = allow_mock_images

    async def generate(self, prompt: str, position: int) -> GeneratedImage:
        return await self._generate(variation_prompt(prompt, position), position)

    async def generate_exact(self, prompt: str, position: int = 1) -> GeneratedImage:
        return await self._generate(prompt, position)

    async def _generate(self, final_prompt: str, position: int) -> GeneratedImage:
        if not self.api_key:
            if self.allow_mock_images:
                return GeneratedImage(self._placeholder(position))
            raise GeminiAuthenticationError(
                "GEMINI_API_KEY is not configured.", status_code=401
            )

        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": final_prompt}],
                }
            ],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "responseFormat": {
                    "image": {
                        "aspectRatio": "1:1",
                        "imageSize": "1K",
                    }
                },
            },
        }
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        endpoint = f"{self.endpoint_root}/{self.model}:generateContent"
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise GeminiServiceError(f"Gemini image request failed: {exc}") from exc

        request_id = (
            response.headers.get("x-goog-request-id")
            or response.headers.get("x-request-id")
            or response.headers.get("x-cloud-trace-context")
        )
        if response.status_code in {401, 403}:
            raise GeminiAuthenticationError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )
        if response.status_code == 429:
            raise GeminiRateLimitError(
                self._error_message(response), status_code=429, request_id=request_id
            )
        if response.status_code >= 500:
            raise GeminiServiceError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )
        if response.status_code >= 400:
            raise GeminiRequestError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )

        try:
            body = response.json()
            for candidate in body.get("candidates", []):
                content = candidate.get("content") or {}
                for part in content.get("parts", []):
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"):
                        return GeneratedImage(
                            base64.b64decode(inline["data"]), request_id=request_id
                        )
            raise KeyError("No inline image data was returned")
        except Exception as exc:
            if isinstance(exc, GeminiRequestError):
                raise
            raise GeminiServiceError(
                f"Gemini returned an invalid image response: {exc}",
                request_id=request_id,
            ) from exc

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            error = payload.get("error", {})
            return str(error.get("message") or payload)
        except Exception:
            return response.text[:500] or f"Gemini HTTP {response.status_code}"

    @staticmethod
    def _placeholder(position: int) -> bytes:
        image = Image.new("RGB", (1024, 1024), (28 + position * 12, 34, 54 + position * 20))
        draw = ImageDraw.Draw(image)
        draw.ellipse((180, 180, 844, 844), outline=(235, 235, 235), width=18)
        draw.text((420, 490), f"GEMINI MOCK {position}", fill=(245, 245, 245))
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
'''
image_source = image_source.replace(marker, new_client + marker, 1)
image_path.write_text(image_source, encoding="utf-8")

replace_once(
    "backend/app/service.py",
    "from .image_client import OpenAIImageClient\n",
    "from .image_client import ImageClient\n",
)
replace_once(
    "backend/app/service.py",
    "        image_client: OpenAIImageClient,\n",
    "        image_client: ImageClient,\n",
)

main_path = Path("backend/app/main.py")
main_source = main_path.read_text(encoding="utf-8")
main_source = main_source.replace("from .image_client import OpenAIImageClient\n", "from .image_client import GeminiImageClient\n", 1)
main_source = main_source.replace(
    '''    image_client = dependencies.image_client or OpenAIImageClient(
        api_key=settings.openai_api_key,
        model=settings.openai_image_model,
        quality=settings.openai_image_quality,
        timeout_seconds=settings.openai_timeout_seconds,
        allow_mock_images=settings.allow_mock_images,
    )
''',
    '''    image_client = dependencies.image_client or GeminiImageClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_image_model,
        timeout_seconds=settings.gemini_timeout_seconds,
        allow_mock_images=settings.allow_mock_images,
    )
''',
    1,
)
main_source = main_source.replace("min(settings.openai_timeout_seconds, 90)", "min(settings.gemini_timeout_seconds, 90)")
main_source = main_source.replace("min(settings.openai_timeout_seconds, 120)", "min(settings.gemini_timeout_seconds, 120)")
main_source = main_source.replace(
    '''                "openai_images": {
                    "configured": bool(settings.openai_api_key),
                    "model": settings.openai_image_model,
                },
''',
    '''                "gemini_images": {
                    "configured": bool(settings.gemini_api_key),
                    "model": settings.gemini_image_model,
                },
''',
    1,
)
main_path.write_text(main_source, encoding="utf-8")

# Keep creative-direction wording accurate now that both stages are Gemini-backed.
creative_path = Path("backend/app/creative_director.py")
creative = creative_path.read_text(encoding="utf-8")
creative = creative.replace(
    '''    """Uses Gemini only for cover-concept/prompt enhancement.

    OpenAI remains the image renderer. Keeping the creative-director provider separate
    reduces the tendency for one model family to both invent and render the same visual
    habits. If Gemini is not configured or temporarily unavailable, the service falls
    back to the local high-cardinality prompt planner; it never falls back to OpenAI for
    concept enhancement.
    """
''',
    '''    """Uses Gemini for cover-concept and prompt enhancement.

    Creative direction and final image rendering use separate Gemini model calls while
    sharing the server-side GEMINI_API_KEY. If creative direction is unavailable, the
    service falls back to the local high-cardinality prompt planner.
    """
''',
    1,
)
creative = creative.replace(
    "Another company's image model will render your concepts. Your job is to invent exactly {count}",
    "A separate Gemini image model will render your concepts. Your job is to invent exactly {count}",
    1,
)
creative_path.write_text(creative, encoding="utf-8")

# Environment example: Gemini is the only required provider credential.
env_path = Path(".env.example")
env = env_path.read_text(encoding="utf-8")
env = env.replace(
    '''# Required provider credentials
OPENAI_API_KEY=
GEMINI_API_KEY=

# OpenAI renders final artwork.
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_QUALITY=medium
OPENAI_TIMEOUT_SECONDS=150

# Gemini plans, ranks, and critiques.
''',
    '''# Required provider credential
GEMINI_API_KEY=

# Gemini renders final artwork and also plans, ranks, and critiques.
GEMINI_IMAGE_MODEL=gemini-3.1-flash-image
GEMINI_TIMEOUT_SECONDS=150
''',
    1,
)
env_path.write_text(env, encoding="utf-8")

# Documentation must no longer instruct operators to fund/configure OpenAI.
readme_path = Path("README.md")
readme = readme_path.read_text(encoding="utf-8")
readme = readme.replace("creates 3–5 OpenAI image variations", "creates 3–5 Gemini image variations")
readme = readme.replace("**OpenAI Image API** renderer supporting `gpt-image-1`, `gpt-image-2`, and legacy `dall-e-3`", "**Gemini Image API** renderer using `gemini-3.1-flash-image`")
readme = readme.replace("Input-hash cache reuse without rerunning analysis or OpenAI", "Input-hash cache reuse without rerunning analysis or Gemini image rendering")
readme = readme.replace("image_client.py        # OpenAI Image API adapter", "image_client.py        # Gemini Image API adapter")
readme = readme.replace("Edit `.env` and set both `OPENAI_API_KEY` and `GEMINI_API_KEY`. OpenAI renders artwork; Gemini independently invents/enhances the cover concepts.", "Edit `.env` and set `GEMINI_API_KEY`. Gemini renders artwork and independently invents/enhances the cover concepts using separate model calls.")
readme = readme.replace("**Gemini is the prompt enhancer / creative director; OpenAI is only the image renderer.**", "**Gemini handles both creative direction and image rendering through separate model calls.**")
readme = readme.replace("Before any OpenAI image call", "Before any Gemini image call")
readme = readme.replace("Gemini uses its own `GEMINI_API_KEY`; the OpenAI key is never sent to Google and the Gemini key is never sent to OpenAI.", "Gemini uses the server-side `GEMINI_API_KEY` for both stages; the key is never sent to the browser.")
readme = readme.replace("| `OPENAI_API_KEY` | Yes for real images | none | Server-side OpenAI credential; never sent to the browser |\n", "")
readme = readme.replace("| `OPENAI_IMAGE_MODEL` | No | `gpt-image-2` | Image API model; `gpt-image-1` and legacy `dall-e-3` are also supported |\n", "")
readme = readme.replace("| `OPENAI_IMAGE_QUALITY` | No | `medium` | GPT Image quality; maps to `standard`/`hd` for DALL·E 3 |\n", "")
readme = readme.replace("| `OPENAI_TIMEOUT_SECONDS` | No | `150` | Per-request image generation timeout |\n", "")
readme = readme.replace("| `GEMINI_API_KEY` | Yes for Gemini prompt enhancement | none | Server-side Google Gemini credential; never sent to OpenAI or the browser |", "| `GEMINI_API_KEY` | Yes for real images and Gemini intelligence | none | Server-side Google Gemini credential; never sent to the browser |")
readme = readme.replace("| `GEMINI_CONCEPT_MODEL` | No | `gemini-3.6-flash` | Gemini model used only for creative direction / prompt enhancement |", "| `GEMINI_IMAGE_MODEL` | No | `gemini-3.1-flash-image` | Gemini model used for final square artwork renders |\n| `GEMINI_TIMEOUT_SECONDS` | No | `150` | Per-request Gemini timeout |\n| `GEMINI_CONCEPT_MODEL` | No | `gemini-3.6-flash` | Gemini model used for creative direction / prompt enhancement |")
readme = readme.replace("The OpenAI prompt reserves calm title", "The Gemini image prompt reserves calm title")
readme_path.write_text(readme, encoding="utf-8")

print("Gemini renderer patch applied")
