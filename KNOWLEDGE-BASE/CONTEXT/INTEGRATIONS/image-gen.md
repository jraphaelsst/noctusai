# Image generation — consume-side reference (`noctusai_lib.integrations.image_gen`)

> **Purpose.** Authoritative consume-side reference for the
> ``noctusai_lib.integrations.image_gen`` seed package. Canonical
> Protocol + Fake + Real + factory shape mirroring `google_calendar` /
> `youtube` / `google_drive`. Folds **what ships** (verified against
> `__all__`), **consume recipe**, **gaps** into one durable doc.
>
> **Why this lives in KB.** The project that lifted it
> (`media-creator-w2-4`) is closed + archived at session end; this doc
> is durable and self-contained per [[feedback_absorption_ships_consume_docs]].

---

## 1. What ships

Package: `seed/lib/backend/noctusai_lib/integrations/image_gen/`.

`__all__`:
- `ImageGenAdapter` — Protocol.
- `ImagePromptInput` — request value object (`prompt`, `renderer`,
  `aspect_ratio`, `negative_prompt`, `request_id`, `extra`).
- `GeneratedImage` — response value object (`image_url`, `renderer`,
  `model`, `latency_ms`, `raw`).
- `FakeImageGenAdapter` — deterministic in-memory adapter; default
  when no API key resolves. The fake URL host
  `fake-image-gen.noctusai.local` is the loud "not configured" signal
  per [[feedback_gated_capability_honesty]].
- `GeminiImageGenAdapter` — real Gemini "Nano Banana" backend
  (`imagen-3.0-generate-001` default; `gemini-2.0-flash-exp` override).
  SDK import is lazy — adapter construction does NOT require
  `google-genai` to be installed; only `generate(...)` does.
- `KeyProvider` — `Callable[..., str | None]` alias, mirrors the LLM
  module's `key_provider` shape.
- `get_image_gen_adapter` — factory; picks Real when a key is
  resolved, Fake otherwise.

The Protocol is renderer-agnostic — concrete backends differ in
prompt shape but the consumer contract is uniform:
`generate(ImagePromptInput, *, org_id) -> GeneratedImage`.

---

## 2. Consume recipe

```python
from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.image_gen import (
    ImagePromptInput,
    get_image_gen_adapter,
)


def _gemini_key_provider(org_id: str | None = None) -> str | None:
    return resolve_credential("gemini_api_key", org_id)


# Per-call factory (the org_id flows in through here so per-tenant
# keys resolve correctly):
adapter = get_image_gen_adapter(
    key_provider=_gemini_key_provider,
    org_id=user.org_id,
)

image = adapter.generate(
    ImagePromptInput(
        prompt=slide.prompt_nano_banana,
        renderer="nano_banana",
        aspect_ratio="1:1",
        request_id=f"{post.id}:{slide.slide_n}",
    ),
    org_id=user.org_id,
)
# image.image_url      str — persist to your slide table.
# image.renderer       echo of input renderer label.
# image.model          "imagen-3.0-generate-001" | "fake-image-gen".
# image.latency_ms     int — wire-time + SDK overhead.
# image.raw            dict — request_id, has_bytes flag, etc.
```

**Detecting "not configured" without inspecting URLs.** When the
factory returned the Fake (no key resolved for the org), `image_url`
starts with `https://fake-image-gen.noctusai.local/`. Consumers SHOULD
NOT branch on URL host; instead use `isinstance(adapter,
FakeImageGenAdapter)` or pass the `configured` flag up to the FE:

```python
from noctusai_lib.integrations.image_gen import FakeImageGenAdapter

configured = not isinstance(adapter, FakeImageGenAdapter)
```

The FE then surfaces a "configure your Gemini key" prompt when
`configured=False` — see real consumer:
`products/social-wiring/backend/app/modules/media_creation/services/generation_service.py:render_post`.

---

## 3. Auth modes

**Per-org Gemini API key** (the only v1 backend auth shape) — resolved
through `noctusai_lib.config.credentials.resolve_credential("gemini_api_key", org_id)`,
which walks the 3-tier chain (org → platform → env). Identical to
the LLM key resolution shape ([[feedback_dev_orchestration_codegen_toolkit]]).

There is **no OAuth path** in v1 — Gemini image-gen on the public
`generativelanguage.googleapis.com` endpoint uses an API key. Workspace
DWD / per-user OAuth for image gen would require Vertex AI Imagen
(separate, not in v1 scope).

---

## 4. Real consumer (cite path:line)

`media-creator-w2-4` is the first consumer:

- Service:
  `products/social-wiring/backend/app/modules/media_creation/services/generation_service.py`
  — `_default_gemini_key_provider` + `GenerationService.render_post(post, renderer)`.
- Router:
  `products/social-wiring/backend/app/modules/media_creation/routers/generation.py`
  — `POST /api/media-creation/posts/{post_id}/render`.
- Tests:
  `products/social-wiring/backend/tests/modules/media_creation/test_generation.py`
  — `class TestRender` (6 status-pinned assertions covering 404 / 422 /
  Fake-path / slide-persistence / missing-prompt skip).

Seed tests:
`seed/lib/backend/tests/integrations/image_gen/test_{fake_adapter,factory}.py`
(12 status-pinned assertions covering deterministic-URL / record-calls /
factory-resolution / empty-key-handling / lazy-SDK-import).

---

## 5. Gaps & follow-ups

v1 ships Gemini only. The factory raises `ValueError` on any other
backend name. Adding backends is a 3-step extension:
1. New `<backend>_adapter.py` implementing `ImageGenAdapter`.
2. Branch in `get_image_gen_adapter()` for the new `backend=` value.
3. Tests in `seed/lib/backend/tests/integrations/image_gen/`.

Candidates worth adding when a consumer surfaces a real need (NOT
pre-emptively per the seed-first analysis litmus):
- OpenAI Images (`gpt-image-1`) — for tenants standardizing on OpenAI.
- Stability AI — for SDXL workflows.
- Replicate — for arbitrary HF model passthrough.

**Budget accounting** is not yet wired. Image-gen calls don't record
into the existing `llm_usage` ledger yet — when N=2 consumer wants
per-call cost reporting, extend the ledger with a `kind='image'` column
(one ledger, per the recurrence rule) and inject a usage-sink callback
through the factory (mirror the LLM's `usage_sink` mechanism).

**Durable storage of generated bytes.** When the Gemini API returns
inline bytes (no hosted URL), the adapter falls back to inline
`data:image/png;base64,...` URLs. That's good for dev / small images;
production should pass `upload_url_resolver=` to `get_image_gen_adapter`
— a `(bytes, ImagePromptInput) -> str` callback that uploads to
Supabase Storage and returns the persistent URL. The seed provides the
seam; the consumer implements the upload (the consumer already has the
Supabase client + the bucket).
