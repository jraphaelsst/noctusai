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

**Batch ("Econômico", W4)** follows the documented OpenAI Batch API: one
JSONL file (`files.create(purpose="batch")`), one line per edit
(`{"custom_id", "method": "POST", "url": "/v1/images/edits", "body": {...}}`),
`batches.create(endpoint="/v1/images/edits", completion_window="24h")`,
`batches.retrieve` to poll, `files.content(output_file_id | error_file_id)`
to read the per-line results. The injected `client` must additionally
duck-type `client.files.create(...)`, `client.files.content(file_id)`,
`client.batches.create(...)` and `client.batches.retrieve(batch_id)`.

🔴 UNVERIFIED against a live account (no credits — same reason as above),
flagged so the first real smoke run checks each one:

1. **Image input shape inside a batch line** — the multipart `image=` file
   upload of the synchronous endpoint cannot travel in JSONL, so each line
   carries `body.images = [{"image_url": "data:<mime>;base64,..."}]` (and
   `body.mask = {"image_url": ...}`), the JSON form of the images-edit
   request. `_batch_line` is the ONE place to change if the live API wants
   `file_id` references instead (upload each photo with
   `purpose="vision"`, send `{"file_id": ...}`).
2. **`/v1/images/edits` as a batch endpoint** — plan §3 says `gpt-image-2`
   and older support Batch; the endpoint string is taken from that claim.
3. **Output line body** — assumed to be the same JSON as the synchronous
   `ImagesResponse` (`data[].b64_json`, `usage{...}`), read defensively.
4. **Input-file size** — the Batch API caps one input file at 200 MB;
   base64 inflates each photo ~4/3, so `MAX_BATCH_INPUT_BYTES` refuses an
   oversized file up front (fatal) instead of letting the upload fail.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

from noctusai_lib.integrations.image_edit.exceptions import (
    ImageEditBatchNotFound,
    ImageEditBatchNotReady,
    ImageEditBatchUnsupported,
    ImageEditContentPolicyViolation,
    ImageEditError,
    ImageEditFatalError,
    ImageEditInvalidSize,
    ImageEditNotConfigured,
    ImageEditRateLimited,
    ImageEditServerError,
    ImageEditTimeout,
)
from noctusai_lib.integrations.image_edit.types import (
    BatchEditItem,
    BatchItemResult,
    BatchPollResult,
    BatchState,
    BatchSubmission,
    EditedImage,
    ImageEditCapabilities,
    ImageEditRequest,
    ImageEditResult,
    ImageEditUsage,
)
from noctusai_lib.integrations.image_edit import types as _types

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


#: OpenAI Batch API endpoint for image edits (UNVERIFIED — module docstring §2).
BATCH_ENDPOINT = "/v1/images/edits"
BATCH_COMPLETION_WINDOW = "24h"
#: The Batch API's documented per-input-file ceiling (module docstring §4).
MAX_BATCH_INPUT_BYTES = 200 * 1024 * 1024


def _sniff_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _data_url(data: bytes) -> str:
    return f"data:{_sniff_mime(data)};base64,{base64.b64encode(data).decode('ascii')}"


def _batch_line(model: str, item: BatchEditItem) -> dict[str, Any]:
    """One JSONL request line. The ONLY place that knows the (unverified)
    JSON image-input shape — see module docstring §1."""
    request = item.request
    body: dict[str, Any] = {
        "model": model,
        "prompt": request.prompt,
        "size": request.size,
        "n": request.n,
        "images": [{"image_url": _data_url(img)} for img in request.images],
    }
    if request.mask is not None:
        body["mask"] = {"image_url": _data_url(request.mask)}
    # Wire-level extras only: `request.extra` may carry caller metadata the
    # synchronous path forwards verbatim; the batch path does the same.
    body.update(request.extra)
    return {"custom_id": item.custom_id, "method": "POST", "url": BATCH_ENDPOINT, "body": body}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Attribute-or-key read — SDK objects and plain dicts alike."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _usage_from(usage_obj: Any) -> ImageEditUsage:
    details = _get(usage_obj, "input_tokens_details")
    return ImageEditUsage(
        prompt_tokens=_get(details, "text_tokens"),
        image_input_tokens=_get(details, "image_tokens"),
        image_output_tokens=_get(usage_obj, "output_tokens"),
        total_tokens=_get(usage_obj, "total_tokens"),
    )


def _item_error(status_code: int | None, error: Any) -> ImageEditError:
    """Classify one failed batch line into the typed taxonomy."""
    code = str(_get(error, "code") or "")
    message = str(_get(error, "message") or code or f"status {status_code}")
    text = f"{code} {message}".lower()
    details = {"status_code": status_code, "code": code}
    if code in ("batch_expired", "batch_cancelled"):
        return ImageEditTimeout(message, details=details)
    if status_code == 429:
        return ImageEditRateLimited(message, details=details)
    if status_code is not None and status_code >= 500:
        return ImageEditServerError(message, details=details)
    if status_code is not None and 400 <= status_code < 500:
        if status_code in (401, 403):
            return ImageEditNotConfigured("openai")
        if any(marker in text for marker in _CONTENT_POLICY_MARKERS):
            return ImageEditContentPolicyViolation(message, details=details)
        return ImageEditInvalidSize(message, details=details)
    # No status (line-level `error` without a response): unknown failure
    # mode ⇒ retryable, same default as `_classify_openai_error`.
    return ImageEditServerError(message, details=details)


async def _read_file_text(client: Any, file_id: str) -> str:
    content = await client.files.content(file_id)
    for attr in ("text", "content"):
        value = getattr(content, attr, None)
        if callable(value):
            value = value()
        if isinstance(value, bytes):
            return value.decode("utf-8")
        if isinstance(value, str):
            return value
    if isinstance(content, (bytes, str)):
        return content.decode("utf-8") if isinstance(content, bytes) else content
    raise ImageEditFatalError(f"unreadable content for file {file_id}", provider="openai")


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
        capabilities: Callable[[str], ImageEditCapabilities] | None = None,
    ) -> None:
        if not api_key and client is None:
            raise ImageEditNotConfigured("openai")
        self._api_key = api_key
        self._model = model
        self._client = client
        # None = the catalog, looked up at CALL time (a catalog seam
        # installed after import is honoured). A consumer whose engine gate
        # is a different lookup passes the same callable here, so the
        # adapter's own batch refusal can never disagree with it.
        self._capabilities = capabilities

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
        if self._capabilities is not None:
            return self._capabilities(model)
        return _types.capabilities_for_model(model)

    # --- batch (Econômico) -------------------------------------------------
    async def _call(self, coro: Any, *, batch_id: str | None = None) -> Any:
        try:
            return await coro
        except Exception as exc:
            from openai import NotFoundError, OpenAIError

            if isinstance(exc, NotFoundError):
                raise ImageEditBatchNotFound(str(exc), provider="openai") from exc
            if isinstance(exc, OpenAIError):
                logger.error("OpenAI batch call failed batch_id=%s: %s", batch_id, exc)
                raise _classify_openai_error(exc) from exc
            raise

    async def submit_batch(
        self,
        items: Sequence[BatchEditItem],
        *,
        org_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> BatchSubmission:
        if not self.capabilities(self._model).supports_batch:
            raise ImageEditBatchUnsupported(
                f"model {self._model} does not support the Batch API", provider="openai"
            )
        if not items:
            raise ValueError("submit_batch needs at least one item")
        ids = [item.custom_id for item in items]
        if len(set(ids)) != len(ids):
            raise ValueError("submit_batch: duplicate custom_id")
        jsonl = "".join(
            json.dumps(_batch_line(self._model, item), separators=(",", ":")) + "\n"
            for item in items
        ).encode("utf-8")
        if len(jsonl) > MAX_BATCH_INPUT_BYTES:
            raise ImageEditInvalidSize(
                f"batch input file is {len(jsonl)} bytes (> {MAX_BATCH_INPUT_BYTES})",
                provider="openai",
            )
        client = self._get_client()
        uploaded = await self._call(
            client.files.create(file=("batch.jsonl", jsonl, "application/jsonl"), purpose="batch")
        )
        created = await self._call(
            client.batches.create(
                input_file_id=_get(uploaded, "id"),
                endpoint=BATCH_ENDPOINT,
                completion_window=BATCH_COMPLETION_WINDOW,
                metadata=dict(metadata or {}),
            )
        )
        batch_id = _get(created, "id")
        if not batch_id:
            raise ImageEditFatalError("OpenAI batches.create returned no id", provider="openai")
        return BatchSubmission(
            batch_id=batch_id,
            model=self._model,
            item_count=len(items),
            state=BatchState(_get(created, "status") or BatchState.VALIDATING.value),
            input_file_id=_get(uploaded, "id"),
            raw={"org_id": org_id, "input_bytes": len(jsonl)},
        )

    async def poll_batch(self, batch_id: str, *, org_id: str | None = None) -> BatchPollResult:
        client = self._get_client()
        batch = await self._call(client.batches.retrieve(batch_id), batch_id=batch_id)
        counts = _get(batch, "request_counts")
        try:
            state = BatchState(_get(batch, "status"))
        except ValueError as exc:
            # A status this module does not know: surface it, never guess.
            raise ImageEditServerError(
                f"unknown batch status {_get(batch, 'status')!r}", provider="openai"
            ) from exc
        return BatchPollResult(
            batch_id=batch_id,
            state=state,
            output_file_id=_get(batch, "output_file_id"),
            error_file_id=_get(batch, "error_file_id"),
            total=_get(counts, "total"),
            completed=_get(counts, "completed"),
            failed=_get(counts, "failed"),
        )

    async def fetch_batch_results(
        self, batch_id: str, *, org_id: str | None = None
    ) -> tuple[BatchItemResult, ...]:
        """Per-line results of a TERMINAL batch.

        Items that appear in neither the output nor the error file (an
        expired/cancelled batch may carry no file at all) are simply absent
        from the returned tuple — the caller, who owns the custom_id list,
        treats a missing id as a retryable failure.
        """
        polled = await self.poll_batch(batch_id, org_id=org_id)
        if not polled.state.is_terminal:
            raise ImageEditBatchNotReady(
                f"batch {batch_id} is {polled.state.value}", provider="openai"
            )
        client = self._get_client()
        results: dict[str, BatchItemResult] = {}
        for file_id in (polled.output_file_id, polled.error_file_id):
            if not file_id:
                continue
            text = await self._call(_read_file_text(client, file_id), batch_id=batch_id)
            for raw_line in text.splitlines():
                if not raw_line.strip():
                    continue
                parsed = self._parse_result_line(batch_id, json.loads(raw_line))
                results.setdefault(parsed.custom_id, parsed)
        return tuple(results.values())

    def _parse_result_line(self, batch_id: str, line: dict[str, Any]) -> BatchItemResult:
        custom_id = str(line.get("custom_id") or "")
        if not custom_id:
            raise ImageEditFatalError("batch result line without custom_id", provider="openai")
        response = line.get("response") or {}
        status_code = response.get("status_code")
        body = response.get("body") or {}
        if line.get("error") or status_code != 200:
            error = line.get("error") or (body.get("error") if isinstance(body, dict) else None)
            return BatchItemResult(custom_id=custom_id, error=_item_error(status_code, error))
        images = tuple(
            EditedImage(image_bytes=base64.b64decode(item["b64_json"]), format="png")
            for item in body.get("data") or []
            if item.get("b64_json")
        )
        if not images:
            return BatchItemResult(
                custom_id=custom_id,
                error=ImageEditFatalError(
                    "batch result line carried no b64_json image data", provider="openai"
                ),
            )
        return BatchItemResult(
            custom_id=custom_id,
            result=ImageEditResult(
                images=images,
                model=self._model,
                usage=_usage_from(body.get("usage")),
                latency_ms=0,
                raw={
                    "batch_id": batch_id,
                    "custom_id": custom_id,
                    "request_id": response.get("request_id"),
                },
            ),
        )
