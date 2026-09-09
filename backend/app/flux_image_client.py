from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

import httpx
from PIL import Image, ImageDraw

from .errors import (
    FluxAuthenticationError,
    FluxRateLimitError,
    FluxRequestError,
    FluxServiceError,
)
from .image_client import GeneratedImage
from .prompts import variation_prompt


class CloudflareFluxImageClient:
    """Cloudflare Workers AI FLUX adapter for final album-cover rendering."""

    endpoint_root = "https://api.cloudflare.com/client/v4/accounts"

    def __init__(
        self,
        *,
        account_id: str | None,
        api_token: str | None,
        model: str = "@cf/black-forest-labs/flux-1-schnell",
        steps: int = 4,
        timeout_seconds: float = 150,
        transport: httpx.AsyncBaseTransport | None = None,
        allow_mock_images: bool = False,
    ) -> None:
        self.account_id = account_id
        self.api_token = api_token
        self.model = model
        self.steps = steps
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.allow_mock_images = allow_mock_images

    async def generate(self, prompt: str, position: int) -> GeneratedImage:
        return await self._generate(variation_prompt(prompt, position), position)

    async def generate_exact(self, prompt: str, position: int = 1) -> GeneratedImage:
        return await self._generate(prompt, position)

    async def _generate(self, final_prompt: str, position: int) -> GeneratedImage:
        if not self.account_id or not self.api_token:
            if self.allow_mock_images:
                return GeneratedImage(self._placeholder(position))
            raise FluxAuthenticationError(
                "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required.",
                status_code=401,
            )

        endpoint = f"{self.endpoint_root}/{self.account_id}/ai/run/{self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload: dict[str, Any] = {
            "prompt": final_prompt,
            "steps": self.steps,
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise FluxServiceError(f"FLUX image request failed: {exc}") from exc

        request_id = response.headers.get("cf-ray") or response.headers.get("x-request-id")
        if response.status_code in {401, 403}:
            raise FluxAuthenticationError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )
        if response.status_code == 429:
            raise FluxRateLimitError(
                self._error_message(response),
                status_code=429,
                request_id=request_id,
            )
        if response.status_code >= 500:
            raise FluxServiceError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )
        if response.status_code >= 400:
            raise FluxRequestError(
                self._error_message(response),
                status_code=response.status_code,
                request_id=request_id,
            )

        try:
            body = response.json()
            result = body.get("result") or {}
            encoded = result.get("image")
            if not encoded:
                raise KeyError("No result.image was returned")
            return GeneratedImage(base64.b64decode(encoded), request_id=request_id)
        except Exception as exc:
            if isinstance(exc, FluxRequestError):
                raise
            raise FluxServiceError(
                f"FLUX returned an invalid image response: {exc}",
                request_id=request_id,
            ) from exc

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            errors = payload.get("errors") or []
            if errors:
                first = errors[0]
                if isinstance(first, dict):
                    return str(first.get("message") or first)
                return str(first)
            return str(payload.get("message") or payload)
        except Exception:
            return response.text[:500] or f"Cloudflare FLUX HTTP {response.status_code}"

    @staticmethod
    def _placeholder(position: int) -> bytes:
        image = Image.new("RGB", (1024, 1024), (24 + position * 10, 30, 58 + position * 18))
        draw = ImageDraw.Draw(image)
        draw.ellipse((180, 180, 844, 844), outline=(235, 235, 235), width=18)
        draw.text((420, 490), f"FLUX MOCK {position}", fill=(245, 245, 245))
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
