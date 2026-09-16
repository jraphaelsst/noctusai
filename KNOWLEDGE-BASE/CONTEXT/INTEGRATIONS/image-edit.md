# Image editing — consume-side reference (`noctusai_lib.integrations.image_edit`)

> **Purpose.** Authoritative consume-side reference for the
> ``noctusai_lib.integrations.image_edit`` seed package. Canonical
> Protocol + Fake + Real + factory shape mirroring `image_gen` (its
> sibling, left completely untouched by this module) /
> `google_calendar` / `youtube`. Folds **what ships** (verified against
> `__all__`), **consume recipe**, **error taxonomy**, **gaps** into one
> durable doc.
>
> **Why this lives in KB.** Built for `projects/edicao-fotos/PROJECT.md`
> Slice S3b; the project is not yet closed, but the module IS the
> durable seed contract the engine slice (S8, not yet built) is written
> against — this doc is the reference S8 (and any future consumer)
> reads instead of re-deriving the shape from the source.

---

## 1. What ships

Package: `seed/lib/backend/noctusai_lib/integrations/image_edit/`.

`__all__`:
- `ImageEditAdapter` — Protocol (async `edit`, sync `capabilities`).
- `ImageEditRequest` — request value object (`images: tuple[bytes, ...]`,
  `prompt`, `size`, `mask`, `n`, `request_id`, `extra`). `images[0]` is
  the primary photo; additional entries are reference images.
- `ImageEditResult` — response value object (`images: tuple[EditedImage,
  ...]`, `model`, `usage`, `latency_ms`, `raw`).
- `EditedImage` — one output image (`image_bytes`, `format`).
- `ImageEditUsage` — token accounting (`prompt_tokens`,
  `image_input_tokens`, `image_output_tokens`, `total_tokens`) — the
  SAME 4-field shape `noctusai_lib.integrations.llm.usage.UsageEvent`
  carries, so a caller feeds it straight into `record_usage(...)` /
  builds a `UsageEvent` without reshaping.
- `ImageEditCapabilities` — per-model capability flags (`model`,
  `supports_batch`, `known`).
- `capabilities_for_model(model)` — the catalog-driven lookup both
  adapters' `.capabilities()` delegate to (module-level free function;
  callable without constructing an adapter).
- `FakeImageEditAdapter` — deterministic in-memory adapter; default
  when no API key resolves. Returns bytes prefixed
  `b"FAKE-IMAGE-EDIT:"` — the loud "not configured" signal per
  [[feedback_gated_capability_honesty]].
- `OpenAIImageEditAdapter` — real OpenAI Images API (`images.edit`)
  backend. SDK import is lazy — adapter construction does NOT require
  `openai` to be importABLE at that exact call site (though it is
  always installed — a hard seed dependency); only `edit(...)` imports
  it. Offline-testable via constructor-injected `client=...` (§4).
- `KeyProvider` — `Callable[..., str | None]` alias, mirrors the LLM
  module's `key_provider` shape.
- `get_image_edit_adapter` — factory; picks Real when a key is
  resolved, Fake otherwise.
- Typed error taxonomy (`exceptions.py`): `ImageEditError` (base,
  `.retryable: bool`) → `ImageEditRetryableError` (429 / 5xx / timeout /
  connection failure: `ImageEditRateLimited`, `ImageEditServerError`,
  `ImageEditTimeout`) and `ImageEditFatalError` (content policy / invalid
  size / not-configured: `ImageEditContentPolicyViolation`,
  `ImageEditInvalidSize`, `ImageEditNotConfigured`).

The Protocol is **async** for `edit` (unlike `image_gen`'s sync
`generate`) — this module is consumed from
`noctusai_lib.domain.jobs.worker`'s async job handlers, the same reason
`integrations.outbound_webhook.OutboundWebhookSender.send` is async, and
its Real backend uses OpenAI's `AsyncOpenAI` client. `capabilities` stays
sync — it is a pure catalog lookup, no IO.

---

## 2. Consume recipe

```python
from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.image_edit import (
    ImageEditRequest,
    get_image_edit_adapter,
)
from noctusai_lib.integrations.imaging import get_imaging_adapter
from noctusai_lib.primitives.image_sizing import compute_edit_size


def _openai_key_provider(org_id: str | None = None) -> str | None:
    return resolve_credential("openai_api_key", org_id)


# 1. Normalize + size the uploaded photo (imaging + image_sizing —
#    Slice S3 organs; this module has no dependency on either, so the
#    caller drives this leg itself).
imaging = get_imaging_adapter()
normalized = imaging.normalize_for_edit(uploaded_bytes)
edit_w, edit_h = compute_edit_size(normalized.width, normalized.height)
edit_input = imaging.resize(normalized.jpeg_bytes, width=edit_w, height=edit_h)

# 2. Per-call factory (the org_id flows in through here so per-tenant
#    keys AND the org's configured image-edit model resolve correctly —
#    v1 has NO built-in default model per org; see § 3 "no model =
#    blocked").
adapter = get_image_edit_adapter(
    key_provider=_openai_key_provider,
    org_id=user.org_id,
    model=org_settings.image_edit_model,
)

result = await adapter.edit(
    ImageEditRequest(
        images=(edit_input,),
        prompt=combined_prompt,  # ALL edit types the org enabled, folded into ONE prompt — the engine's job
        size=f"{edit_w}x{edit_h}",
        request_id=f"{lote_id}:{foto_id}",
    ),
    org_id=user.org_id,
)
# result.images[0].image_bytes   bytes — PNG; re-encode to JPEG via
#                                 imaging.resize/apply_watermark if needed.
# result.usage.image_output_tokens  int | None — feed into cost recording.
# result.model                   "gpt-image-2.5-sunburst" | "fake-image-edit".
# result.latency_ms               int — wire-time + SDK overhead.
```

**Detecting "not configured" without inspecting bytes.** Mirrors
`image_gen`'s pattern — do not branch on the returned bytes; check the
adapter type:

```python
from noctusai_lib.integrations.image_edit import FakeImageEditAdapter

configured = not isinstance(adapter, FakeImageEditAdapter)
```

**Handling retryable vs fatal failures** (job handler shape — S8, not
yet built):

```python
from noctusai_lib.integrations.image_edit import (
    ImageEditFatalError,
    ImageEditRetryableError,
)
from noctusai_lib.domain.jobs.retry_policy import RetryPolicy, next_retry_at

try:
    result = await adapter.edit(request, org_id=org_id)
except ImageEditRetryableError as exc:
    schedule_at = next_retry_at(retries_so_far, policy, now)
    # ... reschedule the job ...
except ImageEditFatalError as exc:
    # dead-letter immediately — content policy / invalid size / not
    # configured will not resolve on retry.
    ...
```

---

## 3. Auth + model resolution

**Per-org OpenAI API key** (the only v1 backend auth shape) — resolved
through `noctusai_lib.config.credentials.resolve_credential("openai_api_key",
org_id)`, identical to the LLM key-resolution shape.

**Model has NO seed-level default per org.** Per the approved plan
(`~/.claude/plans/hey-claude-i-need-gentle-spring.md` §1 "Models"): "image
editor... set per org by agency admin or platform admin; no model = batches
blocked." `OpenAIImageEditAdapter.__init__` DOES carry a constructor
default (`gpt-image-2.5-sunburst`, applied only when the caller omits
`model=`) — that default exists so the adapter is usable standalone (dev,
tests, a script), but a caller enforcing the product's "no model
configured -> refuse" rule must check the org's own settings BEFORE
calling `get_image_edit_adapter`, not rely on the factory to refuse. The
factory itself never inspects org settings.

There is **no OAuth path** — OpenAI's Images API uses an API key.

---

## 4. Offline testing — the DI seam

`OpenAIImageEditAdapter(api_key, *, model=..., client=None)` accepts an
optional pre-built async client. Production never passes it (the real
`openai.AsyncOpenAI` is constructed lazily on first `edit()` call); tests
pass an object that duck-types `client.images.edit(**kwargs) ->
Awaitable[response]` where `response` matches the OpenAI SDK's
`ImagesResponse` shape (`.data[i].b64_json`,
`.usage.{output_tokens,total_tokens,input_tokens_details.
{text_tokens,image_tokens}}`).

This is **constructor injection**, not `sys.modules` patching (the
pattern `StripePaymentGateway`'s tests use — see
`seed/lib/backend/tests/integrations/payments/test_stripe_gateway.py`)
and NOT monkeypatching this module's own code — both are the same class
of DI-on-an-EXTERNAL-dependency the standing protocol carves out from
"no workarounds / no monkey-patching." Error-classification tests raise
REAL `openai.*Error` instances from the injected client (the SDK is an
installed seed dependency) so the assertions exercise the actual classes
`_classify_openai_error` pattern-matches against.

**No live OpenAI call was exercised during S3b** — the account had no
credits (`projects/edicao-fotos/PROJECT.md` § 4c). Every response-field
read in `openai_adapter.py` defensively `getattr`s with a default,
mirroring `OpenAIProvider`'s existing defensive style, precisely because
this path is verified against a scripted double only. **Re-verify the
exact `ImagesResponse.usage` shape against a real account before the
first production edit call.**

Tests: `seed/lib/backend/tests/integrations/image_edit/test_{fake_adapter,
factory,openai_adapter,batch}.py`.

---

## 5. Gaps & follow-ups

**Batch ("Econômico") — built in edicao-fotos W4 (2026-09-16).** The owner
chose to build it before any batch-capable model is priced, so it works the
moment the catalog marks one `supports_batch=True`. Protocol, Fake and Real
all carry:

| method | returns | notes |
|---|---|---|
| `submit_batch(items: Sequence[BatchEditItem], *, org_id, metadata)` | `BatchSubmission` (`batch_id`, `state`, `item_count`, `input_file_id`) | REFUSES `ImageEditBatchUnsupported` (fatal) unless `capabilities(model).supports_batch` — before any network call |
| `poll_batch(batch_id, *, org_id)` | `BatchPollResult` (`state: BatchState`, output/error file ids, request counts) | unknown provider status ⇒ `ImageEditServerError`, never a guess |
| `fetch_batch_results(batch_id, *, org_id)` | `tuple[BatchItemResult, ...]` — per item exactly one of `result: ImageEditResult` / `error: ImageEditError` (carried, not raised) | non-terminal ⇒ `ImageEditBatchNotReady` (retryable); unknown id ⇒ `ImageEditBatchNotFound` (fatal); the Real may OMIT items (expired batch with no files) — the caller treats a missing `custom_id` as a retryable failure |

`BatchState` mirrors the OpenAI status vocabulary 1:1 (`.is_terminal` for
completed/failed/expired/cancelled). Item errors reuse the sync taxonomy:
429 ⇒ `ImageEditRateLimited`, 5xx ⇒ `ImageEditServerError`,
400+policy text ⇒ `ImageEditContentPolicyViolation`, other 4xx ⇒
`ImageEditInvalidSize`, `batch_expired`/`batch_cancelled` ⇒
`ImageEditTimeout` (retryable). `ImageEditResult.usage` is the provider's
RAW token count — the 50% discount is the caller's pricing concern
(`photo_editing.costs.BATCH_API_DISCOUNT`).

**The gate.** `capabilities()` is the only Econômico gate. Both adapters
resolve `capabilities_for_model` at CALL time (module attribute), so a
catalog seam installed after import is honoured; the Real also takes
`capabilities=` (and `photo_editing.openai_image_edit_factory(...,
capabilities=)`) so a consumer whose engine gate is a different lookup can
never have the adapter disagree with it. The Fake takes `batch_models=` —
an explicit test arrangement for "this model is batch-capable" while the
static catalog has none — plus `batch_pending_polls=`,
`batch_item_errors=`, `set_batch_state()`; it records `batch_calls`.

**Real (OpenAI Batch API), offline-verified only** — JSONL upload
(`files.create(purpose="batch")`), `batches.create(endpoint=
"/v1/images/edits", completion_window="24h", metadata=...)`,
`batches.retrieve`, `files.content(output|error file)`. 🔴 UNVERIFIED
against a live account (no credits), flagged in `openai_adapter.py`'s
docstring for the first real smoke run: (1) the JSON image-input shape of
a batch line — `body.images=[{"image_url": "data:<mime>;base64,..."}]`, the
one place to change is `_batch_line` (e.g. to `file_id` references);
(2) `/v1/images/edits` as a batch endpoint; (3) output-line body = the sync
`ImagesResponse` JSON; (4) the 200 MB input-file cap
(`MAX_BATCH_INPUT_BYTES`, refused up front). Tests:
`seed/lib/backend/tests/integrations/image_edit/test_batch.py`.

🔴 **`ImageEditRequest.extra` is forwarded to the provider VERBATIM** (sync
`images.edit(**payload)` and every batch line body). Never put engine
metadata there — the SDK rejects an unknown keyword with `TypeError`. The
engine's sync edit once passed `extra={"prompt_ref": ...}`, which would have
failed every real Urgente edit; fixed in W4, pinned by
`test_sync_edit_sends_only_wire_parameters_to_the_provider`.

**Budget accounting is not yet wired.** `edit()` returns `ImageEditUsage`
but does NOT call `noctusai_lib.integrations.llm.usage.record_usage`
itself (deliberate — mirrors `image_gen`'s adapters, which also don't
autonomously write to a usage sink). The engine (S8) is responsible for
feeding the returned usage into cost recording (`llm_usage` +
`cost_ledger` per the plan §6), same as `OpenAIProvider`'s
`chat_completion` does internally for text calls — but at the point this
module ships, that decision belongs to the consumer, not the adapter.

**No mask-editing UI exists yet.** `ImageEditRequest.mask` is wired
end-to-end through the adapter (forwarded to the OpenAI call when
present) but no v1 flow sets it — every real-estate edit type in the
approved plan (color/light, sky replacement, declutter, virtual staging)
edits the whole photo. The field exists for a future selective-region
edit type without another adapter change.
