from __future__ import annotations

from dataclasses import dataclass
import base64
from io import BytesIO
from typing import Any

import httpx
from PIL import Image, ImageDraw

from .errors import (
    OpenAIAuthenticationError,
    OpenAIRateLimitError,
    OpenAIRequestError,
    OpenAIServiceError,
)
from .prompts import variation_prompt


@dataclass(slots=True)
class GeneratedImage:
    content: bytes
    request_id: str | None = None


class OpenAIImageClient:
    endpoint = "https://api.openai.com/v1/images/generations"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        quality: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
        allow_mock_images: bool = False,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.quality = quality
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.allow_mock_images = allow_mock_images

    async def generate(self, prompt: str, position: int) -> GeneratedImage:
        """Legacy shared-prompt path."""
        return await self._generate(variation_prompt(prompt, position), position)

    async def generate_exact(self, prompt: str, position: int = 1) -> GeneratedImage:
        """Render one already-complete concept prompt without merging another concept."""
        return await self._generate(prompt, position)

    async def _generate(self, final_prompt: str, position: int) -> GeneratedImage:
        if not self.api_key:
            if self.allow_mock_images:
                return GeneratedImage(self._placeholder(position))
            raise OpenAIAuthenticationError(
                "OPENAI_API_KEY is not configured.", status_code=401
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": final_prompt,
            "n": 1,
            "size": "1024x1024",
        }
        if self.model.startswith("gpt-image"):
            payload.update({"quality": self.quality, "output_format": "png"})
        else:
            payload["response_format"] = "b64_json"
            if self.model == "dall-e-3":
                payload["quality"] = "hd" if self.quality == "high" else "standard"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(self.endpoint, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise OpenAIServiceError(f"OpenAI image request failed: {exc}") from exc

        request_id = response.headers.get("x-request-id")
        if response.status_code in {401, 403}:
            raise OpenAIAuthenticationError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )
        if response.status_code == 429:
            raise OpenAIRateLimitError(
                self._error_message(response), status_code=429, request_id=request_id
            )
        if response.status_code >= 500:
            raise OpenAIServiceError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )
        if response.status_code >= 400:
            raise OpenAIRequestError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )

        try:
            body = response.json()
            image = body["data"][0]
            encoded = image.get("b64_json")
            if encoded:
                return GeneratedImage(base64.b64decode(encoded), request_id=request_id)
            url = image.get("url")
            if url:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    downloaded = await client.get(url)
                    downloaded.raise_for_status()
                    return GeneratedImage(downloaded.content, request_id=request_id)
            raise KeyError("Neither b64_json nor url was returned")
        except Exception as exc:
            if isinstance(exc, OpenAIRequestError):
                raise
            raise OpenAIServiceError(
                f"OpenAI returned an invalid image response: {exc}", request_id=request_id
            ) from exc

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            error = payload.get("error", {})
            return str(error.get("message") or payload)
        except Exception:
            return response.text[:500] or f"OpenAI HTTP {response.status_code}"

    @staticmethod
    def _placeholder(position: int) -> bytes:
        image = Image.new("RGB", (1024, 1024), (28 + position * 12, 34, 54 + position * 20))
        draw = ImageDraw.Draw(image)
        draw.ellipse((180, 180, 844, 844), outline=(235, 235, 235), width=18)
        draw.text((435, 490), f"MOCK {position}", fill=(245, 245, 245))
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
