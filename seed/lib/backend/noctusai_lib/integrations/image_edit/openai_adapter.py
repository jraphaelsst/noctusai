"""OpenAI-backed image-edit adapter — the OpenAI Images API `images.edit` call.

Wraps the official `openai` Python SDK's async `images.edit(...)` — the
SAME SDK the seed's `noctusai_lib.integrations.llm.providers.openai_provider
.OpenAIProvider` already uses. This module never issues a raw HTTP request
to OpenAI itself; `openai` is already an unconditional seed dependency
(`seed/lib/backend/pyproject.toml`), so no new dependency was declared for
S3b.

**Offline-testable via constructor injection** (`client=...`) — NOT via
`sys.modules` patching and NOT via monkeypatching this module's own code.
A test passes an object that duck-types the one surface this adapter
touches (`client.images.edit(**kwargs) -> Awaitable[response]`);
production code passes nothing and the adapter lazily constructs a real
`openai.AsyncOpenAI`. This is a narrower seam than the
`sys.modules['stripe']` double `StripePaymentGateway`'s tests use
(`seed/lib/backend/tests/integrations/payments/test_stripe_gateway.py`) —
chosen here because `AsyncOpenAI` is constructed directly inside THIS
module (no shared factory to intercept at import time), so injecting the
already-built client is the narrower, more direct seam. Both are the
same class of DI-on-an-EXTERNAL-dependency the standing protocol carves
out from "no monkeypatching" — neither patches our own code.

**No live verification was possible during S3b** — the OpenAI account had
no credits (every cache refresh that session returned `429 — "You have no
credits remaining"`; see `projects/edicao-fotos/PROJECT.md` § 4c). Every
response-field read below defensively `getattr`s with a default, the same
defensive style `OpenAIProvider` already uses for its own usage fields —
precisely because this path has been verified against a scripted double
only, never a live response. Re-verify the exact `ImagesResponse.usage`
shape (`input_tokens_details.{text_tokens,image_tokens}`) against a real
account before the first production edit call.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

from noctusai_lib.integrations.image_edit.exceptions import (
    ImageEditContentPolicyViolation,
    ImageEditFatalError,
    ImageEditInvalidSize,
    ImageEditNotConfigured,
    ImageEditRateLimited,
    ImageEditServerError,
    ImageEditTimeout,
)
from noctusai_lib.integrations.image_edit.types import (
    EditedImage,
    ImageEditCapabilities,
    ImageEditRequest,
    ImageEditResult,
    ImageEditUsage,
    capabilities_for_model,
)

logger = logging.getLogger(__name__)

#: Content-policy-ish substrings OpenAI's `BadRequestError` message
#: carries when the rejection is about POLICY rather than SHAPE — the SDK
#: exposes no separate typed exception for this distinction, so this is a
#: best-effort text match. It ONLY decides which FATAL subclass to raise
#: (content-policy vs invalid-size); it never flips retryable<->fatal.
_CONTENT_POLICY_MARKERS = ("safety system", "content_policy", "moderation")


def _classify_openai_error(exc: Exception) -> ImageEditFatalError:
    """Translate an `openai.OpenAIError` into the typed taxonomy.

    Imports the SDK's exception classes lazily — this function is only
    reached from inside `OpenAIImageEditAdapter.edit`'s except block,
    after a call that required the SDK to already be importable.
    """
    from openai import (
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        InternalServerError,
        RateLimitError,
    )

    if isinstance(exc, RateLimitError):
        return ImageEditRateLimited(str(exc))
    if isinstance(exc, APITimeoutError):
        return ImageEditTimeout(str(exc))
    if isinstance(exc, APIConnectionError):
        return ImageEditTimeout(str(exc))
    if isinstance(exc, InternalServerError):
        return ImageEditServerError(str(exc))
    if isinstance(exc, AuthenticationError):
        return ImageEditNotConfigured("openai")
    if isinstance(exc, BadRequestError):
        message = str(exc).lower()
        if any(marker in message for marker in _CONTENT_POLICY_MARKERS):
            return ImageEditContentPolicyViolation(str(exc))
        return ImageEditInvalidSize(str(exc))
    # Unrecognized OpenAIError subclass — treat as a transient upstream
    # fault (never silently swallowed, never mis-classified as fatal by
    # default: an unknown failure mode is more likely a new/renamed SDK
    # exception than a permanent one).
    return ImageEditServerError(str(exc))


class OpenAIImageEditAdapter:
    """Real OpenAI image-edit adapter (`images.edit`).

    `client` is an optional pre-built async client (test injection —
    must duck-type `client.images.edit(**kwargs) -> Awaitable[response]`
    where `response` matches the OpenAI SDK's `ImagesResponse` shape:
    `.data[i].b64_json`, `.usage.{input_tokens,output_tokens,
    total_tokens,input_tokens_details.{text_tokens,image_tokens}}`).
    Production callers never pass it — the real
    `openai.AsyncOpenAI(api_key=...)` is constructed lazily on first
    `edit()` call, mirroring `GeminiImageGenAdapter._get_client`'s lazy
    construction (`image_gen/gemini_adapter.py`).

    `model` has NO per-request override on `ImageEditRequest` — v1 wires
    ONE image-edit model per org (per the approved plan §1 "Models":
    "image editor... set per org by agency admin or platform admin; no
    model = batches blocked"), resolved by the caller (S8) and passed
    once at adapter construction via `get_image_edit_adapter(model=...)`.
    """

    backend = "openai"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-image-2.5-sunburst",
        client: Any | None = None,
    ) -> None:
        if not api_key and client is None:
            raise ImageEditNotConfigured("openai")
        self._api_key = api_key
        self._model = model
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def edit(
        self,
        request: ImageEditRequest,
        *,
        org_id: str | None = None,
    ) -> ImageEditResult:
        client = self._get_client()
        started_at = time.monotonic()

        # The SDK accepts either one image or a list of images for
        # multi-reference edits — pass a bare value for the common
        # single-image case rather than always wrapping in a 1-item list,
        # matching how the SDK's own examples shape the call.
        images_arg: Any = list(request.images) if len(request.images) > 1 else request.images[0]
        payload: dict[str, Any] = {
            "model": self._model,
            "image": images_arg,
            "prompt": request.prompt,
            "size": request.size,
            "n": request.n,
        }
        if request.mask is not None:
            payload["mask"] = request.mask
        payload.update(request.extra)

        try:
            response = await client.images.edit(**payload)
        except Exception as exc:
            from openai import OpenAIError

            if isinstance(exc, OpenAIError):
                logger.error("OpenAI images.edit failed: %s", exc)
                raise _classify_openai_error(exc) from exc
            raise

        latency_ms = int((time.monotonic() - started_at) * 1000)

        data = list(getattr(response, "data", []) or [])
        if not data:
            raise ImageEditFatalError("OpenAI images.edit returned no images", provider="openai")

        edited_images = tuple(
            EditedImage(image_bytes=base64.b64decode(item.b64_json), format="png")
            for item in data
            if getattr(item, "b64_json", None)
        )
        if not edited_images:
            raise ImageEditFatalError(
                "OpenAI images.edit response carried no b64_json image data", provider="openai"
            )

        usage_obj = getattr(response, "usage", None)
        details = getattr(usage_obj, "input_tokens_details", None)
        usage = ImageEditUsage(
            prompt_tokens=getattr(details, "text_tokens", None),
            image_input_tokens=getattr(details, "image_tokens", None),
            image_output_tokens=getattr(usage_obj, "output_tokens", None),
            total_tokens=getattr(usage_obj, "total_tokens", None),
        )

        return ImageEditResult(
            images=edited_images,
            model=self._model,
            usage=usage,
            latency_ms=latency_ms,
            raw={"request_id": request.request_id},
        )

    def capabilities(self, model: str) -> ImageEditCapabilities:
        return capabilities_for_model(model)
