"""Gemini "Nano Banana" image-gen adapter — Google Gemini API path.

Wraps the ``google-genai`` SDK's ``models.generate_images`` /
``models.generate_content`` call for the ``imagen-3.0-generate-001``
(production) and ``gemini-2.0-flash-exp`` (preview) models.

Lazy SDK import — the seed stays importable even on machines that
don't have ``google-genai`` installed (the Fake path is the dev
default).
"""

from __future__ import annotations

import base64
import time
from typing import Any

from noctusai_lib.integrations.image_gen.types import (
    GeneratedImage,
    ImagePromptInput,
)


class GeminiImageGenAdapter:
    """Real Gemini image-gen adapter.

    Accepts an ``api_key`` resolved by the consumer (per-org via the
    LLM ``key_provider``). The SDK is imported lazily so the adapter
    construction itself does NOT require ``google-genai`` to be
    installed; only ``generate(...)`` does.

    ``model`` defaults to ``imagen-3.0-generate-001`` (Gemini's
    production image model — "Nano Banana"). Override via constructor
    when a tenant wants the preview ``gemini-2.0-flash-exp`` model.
    """

    backend = "gemini"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "imagen-3.0-generate-001",
        upload_url_resolver=None,
    ) -> None:
        if not api_key:
            raise ValueError("GeminiImageGenAdapter requires a non-empty api_key")
        self._api_key = api_key
        self._model = model
        self._upload_url_resolver = upload_url_resolver
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google import genai  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError(
                    "google-genai is not installed — install it to use "
                    "GeminiImageGenAdapter, or fall back to FakeImageGenAdapter."
                ) from exc
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def generate(
        self,
        prompt: ImagePromptInput,
        *,
        org_id: str | None = None,
    ) -> GeneratedImage:
        client = self._get_client()
        started_at = time.monotonic()

        response = client.models.generate_images(
            model=self._model,
            prompt=prompt.prompt,
            config={
                "number_of_images": 1,
                "aspect_ratio": prompt.aspect_ratio,
                **({"negative_prompt": prompt.negative_prompt} if prompt.negative_prompt else {}),
            },
        )
        latency_ms = int((time.monotonic() - started_at) * 1000)

        generated = list(getattr(response, "generated_images", []) or [])
        if not generated:
            raise RuntimeError(
                f"Gemini image-gen returned no images (model={self._model}, "
                f"org_id={org_id})"
            )

        first = generated[0]
        image_bytes: bytes | None = None
        image_url: str | None = None

        image_obj = getattr(first, "image", None)
        if image_obj is not None:
            image_bytes = getattr(image_obj, "image_bytes", None) or getattr(
                image_obj, "data", None
            )
            image_url = getattr(image_obj, "uri", None) or getattr(image_obj, "url", None)

        if image_url is None and image_bytes is not None:
            if self._upload_url_resolver is not None:
                image_url = self._upload_url_resolver(image_bytes, prompt)
            else:
                image_url = (
                    "data:image/png;base64,"
                    + base64.b64encode(image_bytes).decode("ascii")
                )

        if image_url is None:
            raise RuntimeError(
                "Gemini image-gen returned an image with neither bytes nor URL"
            )

        return GeneratedImage(
            image_url=image_url,
            renderer=prompt.renderer,
            model=self._model,
            latency_ms=latency_ms,
            raw={
                "request_id": prompt.request_id,
                "has_bytes": image_bytes is not None,
                "negative_prompt": prompt.negative_prompt,
            },
        )
