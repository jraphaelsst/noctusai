# Meta (Facebook + Instagram) Graph adapter — consume-side reference

> **Purpose.** Authoritative consume-side reference for
> `noctusai_lib.integrations.meta` — the seed's canonical
> Protocol + Fake + Real(dual-auth OAuth) + factory + introspection
> seam for the Meta Graph API (Facebook Pages + Instagram Business).
> Folds **what ships** (verified against `__all__`), **how a product
> consumes it** (import -> factory -> resolver injection -> router mount
> via NAMED seams, with a real consumer cited `path:line`), **auth
> modes**, and **gaps / out-of-scope** into one durable doc.
>
> **Why this lives in KB.** Project folders
> (`projects/social-wiring-absorption/`) are deleted at close; this
> doc is durable and self-contained — it is the single entry for any
> agent wiring a product to Meta, and the consume-side companion to
> the cross-provider `CONTEXT/INTEGRATIONS/oauth-patterns.md` (which
> documents the OAuth dance / token-chain / scope-discovery theory;
> THIS doc documents the adapter API a product actually calls).
>
> **Scope: read-only v1.** Posting (FB Page post, IG publish), ads,
> and webhook subscriptions are out-of-scope-with-destination — see §5.
>
> Provenance: lifted into seed 2026-05-16 (`social-wiring-absorption`
> Wave 1.E4) from the live-validated `noctusai-youtube-crawler`
> `feat/meta-integrations` + `integration/oauth-discovery` branches
> (end-to-end validated against a real One Consultoria FB Page + IG
> account). Sibling to `google_calendar/`, `google_maps/`, `vista/`.

---

## 1. What ships — exact `__all__`

Package: `seed/lib/backend/noctusai_lib/integrations/meta/`. Every
symbol below is exported from `meta/__init__.py.__all__`
(verify-the-seed-ships-it: this list IS the runtime surface — read it,
don't infer from the Protocol).

### Value objects (`meta.types`)
| Symbol | Role |
|---|---|
| `FacebookPage` | A Page the connected identity manages |
| `InstagramAccount` | IG Business account linked to a Page |
| `FacebookPost` | A published Page post (read) |
| `InstagramMedia` | An IG media item (read) |
| `PostInsights` | Per-post engagement metrics |
| `MetaConnectionStatus` | `status()` return — `auth_mode` discriminator surfaced here |
| `PublishedMedia` / `PublishedPost` | Publish results; `processing_duration_ms` populated on the video / Reel path |
| `MediaProcessingStatus` | One reading of a video / Reel container's async processing state (`is_finished` / `is_error`); returned by `poll_media_status` |

### Contract + adapters
| Symbol | Role |
|---|---|
| `MetaAdapter` | Protocol — read surface + publish/ads write surface (additive; pre-existing read callers unaffected) |
| `FakeMetaAdapter` | Deterministic in-memory; dev/test default. Publish methods deterministic-record on `published_posts` / `published_media` |
| `get_meta_adapter(...)` | **Factory** — auth-resolution priority (§3) |

**Publish methods on `MetaAdapter`** (added 2026-05-16, carousel added
2026-05-20, video / Reels added 2026-05-24):
- `publish_facebook_post(page_id, message, link=None, photo_url=None)` →
  `PublishedPost`. Single-step `POST /{page-id}/feed` (text) or
  `POST /{page-id}/photos` (when `photo_url` given). Production needs
  `pages_manage_posts` scope through Meta App Review.
- `publish_instagram_media(ig_user_id, image_url, caption=None)` →
  `PublishedMedia`. 2-step `media` container → `media_publish`. Production
  needs `instagram_content_publish`.
- `publish_instagram_carousel(ig_user_id, image_urls, caption=None)` →
  `PublishedMedia`. N+1+1-step: N child `media` containers (each
  `media_type=IMAGE`, `is_carousel_item=true`) → parent `media` container
  (`media_type=CAROUSEL`, `children=<csv>`) → `media_publish`. 2-10
  children enforced client-side (loud `ValueError` outside bounds). Same
  scope as single-publish.
- `publish_instagram_reel(ig_user_id, video_url, caption=None)` →
  `PublishedMedia`. **Asynchronous** 3-step: `POST /{ig-user}/media`
  with `media_type=REELS` + `video_url` → container; poll
  `poll_media_status(creation_id)` until `FINISHED` (hard-capped 90s,
  raises on `ERROR` / `EXPIRED` / timeout); `media_publish`.
  `processing_duration_ms` records the transcode wait. Same
  `instagram_content_publish` scope as image publish.
- `publish_facebook_video(page_id, video_url, description=None, *, as_reel=False)` →
  `PublishedPost`. `as_reel=False` → `POST /{page-id}/videos` (`file_url`,
  synchronous unless Graph returns an `IN_PROGRESS` container, then it
  polls); `as_reel=True` → `POST /{page-id}/video_reels` start → poll →
  finish (`video_state=PUBLISHED`). Production needs the Page write scope
  (`pages_manage_posts`, plus the Reels-publishing capability for
  `as_reel=True`) through Meta App Review.

`poll_media_status(creation_id, *, access_token, version=..., timeout_seconds=90, poll_interval_seconds=2, transient_retries=3, sleep=time.sleep)`
(in `meta._meta_api`) is the resumable-upload status poll the video /
Reel methods share: polls `GET /{creation-id}?fields=status,status_code`
until `FINISHED`, raises `MetaGraphError` on `ERROR` / `EXPIRED` /
timeout (`video_processing_timeout`), retries transient 5xx within the
budget, and re-raises permission / auth errors immediately (an
unapproved scope will not recover by polling). `sleep` is injected so
tests drive the loop with zero wall-clock wait.

When the active token lacks the gated scope, the live adapter raises
`MetaGraphError` with `requires_app_review=True` — never a silent or
faked success. The Fake does NOT raise the App-Review gate (it is the
"scope already approved" path), so dev/test paths run end-to-end.

> `MetaOAuthAdapter` (the live Graph adapter) is **not** in `__all__` —
> it is constructed only by the factory (`get_meta_adapter`). Consumers
> never import it directly; they depend on the `MetaAdapter` Protocol
> and let the factory pick. (The social-wiring product re-exports its
> own thin `MetaOAuthAdapter` wrapper for label/introspection — that is
> a product seam, not the seed surface.)

### Credentials seam (`meta.credentials`)
| Symbol | Role |
|---|---|
| `MetaCredentialResolver` | Protocol — product-injected per-tenant OAuth token lookup (mirrors `CalendarCredentialResolver`) |
| `OAuthMetaCredentials` | Resolver return shape (long-lived token + meta) |

### Scope auto-discovery + Graph helpers (`meta._meta_api`)
| Symbol | Role |
|---|---|
| `META_KITCHEN_SINK_SCOPES` | The full read-only scope set |
| `resolve_oauth_scopes` | Narrow the kitchen-sink to what the app is actually granted |
| `discover_app_permissions` | Post-consent introspection of granted permissions |
| `exchange_code_for_token` | OAuth code -> short-lived token (string) |
| `exchange_for_long_lived` | Short-lived -> 60-day long-lived token (string) |
| `exchange_code_for_token_bundle` | As above, returns `TokenBundle` (token + `expires_in` + `token_type`) |
| `exchange_for_long_lived_bundle` | As above, returns `TokenBundle` — use when a caller needs the ~60d refresh deadline |
| `TokenBundle` | Frozen value object: `access_token` + optional `expires_in` / `token_type`. The string fns delegate to the bundle variants and unwrap `.access_token` (back-compat). |
| `MetaGraphError` | Typed error — `.is_auth_error` / `.is_rate_limited` |

### Pure mappers (`meta.mappers`)
`page_from_body`, `ig_account_from_body`, `post_from_body`,
`ig_media_from_body`, `insights_from_body`, `parse_graph_datetime`
(handles the Graph `+0000` offset).

### FastAPI seam (`meta.router`)
`make_meta_router(...)` -> mounts `/api/meta/{status,scopes}` (read-only
introspection endpoints). OAuth start/callback is **not** here — that
is the generic `noctusai_lib.security.oauth` router's job; this package
does not duplicate the dance.

---

## 2. Consume recipe

The seed factory + Protocol mean a product NEVER hand-rolls a Graph
client. Wiring is import -> factory -> resolver/store injection -> router
mount via NAMED seams.

```python
from noctusai_lib.integrations.meta import (
    MetaAdapter, get_meta_adapter, make_meta_router,
)

# Per-request / per-tenant — the factory picks the adapter kind.
adapter: MetaAdapter = get_meta_adapter(
    org_id=resolved_org if store else None,
    credential_store=store,        # CredentialStore convenience path
)
status = await adapter.status()    # MetaConnectionStatus, has auth_mode
```

`credential_store=` is the convenience path — pass a
`noctusai_lib.security.token_store.CredentialStore` and the factory
builds a `CredentialStoreMetaResolver` internally (no per-product
resolver bridge). For full control inject a `MetaCredentialResolver`
via `resolver=` instead (`resolver` wins if both given).

**Router mount via the standard-routers NAMED seam** — the product's
`create_product_app(...)` mounts `make_meta_router(...)`; the
introspection router is not hand-registered.

**Live consumer (cited):**

- `products/social-wiring/backend/app/routers/meta_router.py:146` —
  `adapter = get_meta_adapter(org_id=resolved_org if store else None,
  credential_store=store)`; import at `:46`. The router reads
  `adapter.auth_mode` (`:153`) to surface the active auth mode and
  computes `consent_required` only for the `user_oauth` path
  (`system_user` mode bypasses consent).
- `products/social-wiring/backend/app/services/whatsapp_intake_service.py:1730`
  — second consumer: `get_meta_adapter(org_id=self._org_id,
  credential_store=store)` inside the WhatsApp intake flow.

Social-wiring keeps a thin `app/services/meta/` product wrapper
(`app.services.meta.get_meta_adapter`) that re-exports the seed factory
plus a label/`MetaOAuthAdapter` introspection shim — a NAMED product
seam over the seed surface, not a fork.

---

## 3. Auth modes

Source of truth: the `meta/__init__.py` factory docstring + the
`get_meta_adapter` docstring. Selection priority is
**`system_user` -> `user_oauth` -> `Fake`**:

| Mode | Trigger | Needs `org_id`/resolver? | Use |
|---|---|---|---|
| `system_user` | `system_user_token=` set | NO — token is workspace-global, one System User serves every consumer | **Production** for Business-Portfolio-owned assets |
| `user_oauth` | `resolver` present (or `credential_store=`) AND `resolver.get_credentials(org_id)` non-None | YES — per-tenant stored long-lived token | End-user delegated path |
| `Fake` | neither a System User Token NOR a resolver | n/a | Safe dev/test fallback |

Notes:
- Even on the `user_oauth` path the adapter is still **constructed**
  when a resolver is present but returns `None` — so `status()` can
  report a useful error rather than silently degrading. Fallback to
  `FakeMetaAdapter` happens ONLY when there is neither token nor
  resolver.
- `auth_mode` is surfaced on `MetaConnectionStatus` (the `status()`
  return) — consumers branch UI/consent on it (see social-wiring
  `meta_router.py:153`).
- The cross-provider token-chain (short -> long-lived, system-user vs
  OAuth matrix, Google<->Meta scope-discovery diff) is documented in
  `CONTEXT/INTEGRATIONS/oauth-patterns.md`; this doc is the adapter API.

---

## 4. Errors

`MetaGraphError` is the single typed error. Branch on
`.is_auth_error` (re-consent / token-refresh path) vs
`.is_rate_limited` (back-off path). It is raised at request time, not
import time — the router stays import-safe (FastAPI dep-factory
pattern, `CONTEXT/PATTERNS/backend/backend.md`).

---

## 5. Gaps / out-of-scope (with destinations)

| Item | Status | Destination |
|---|---|---|
| FB Page **post** / IG **publish** (write scopes) | **SHIPS** (`publish_facebook_post` / `publish_instagram_media` / `publish_instagram_carousel`) — live behind Meta App Review for production | First consumer: `products/social-wiring/backend/app/modules/media_creation/services/publish_service.py` (carousel + single + FB photo). Surfaces 422 + `meta_scope_pending_app_review` when the App Review gate trips at request time |
| Ads / Insights beyond per-post `PostInsights` | **SHIPS** — read campaigns + ad-insights; full management surface (campaign create/update) ships separately via `meta.ads_management` | See `tests/integrations/meta/test_meta_ads_management.py` |
| Webhook subscriptions (Page/IG change events) | out-of-scope | Separate future `integrations/meta/webhooks/` module |
| Video / Reels publish | **SHIPS** (`publish_instagram_reel` / `publish_facebook_video` — async resumable-upload + `poll_media_status` processing poll) — same App Review scope as image publish (`instagram_content_publish` for IG Reels; `pages_manage_posts` + Reels capability for FB) | Seed extension shipped 2026-05-24 (`projects/meta-video-reels-publish`). **Consumer wiring is the remaining thin step**: `social-wiring/media_creation/services/publish_service.py` extends with `target='instagram_reel'` / `'facebook_video'` / `'facebook_reel'` + widens the `mc_posts.published_target` CHECK constraint — gated on a `format='video'` consumer surfacing |
| TikTok | n/a — different vendor | Separate future `integrations/tiktok/` module |
| OAuth start/callback router | **not duplicated by design** | Consume `noctusai_lib.security.oauth` as-is |

> **WhatsApp is a separate package.** `noctusai_lib.integrations.whatsapp`
> ships its own Meta Cloud API client (`get_meta_cloud_client`) for
> WhatsApp Business — see `CONTEXT/INTEGRATIONS/whatsapp.md`. This doc
> is Facebook-Pages + Instagram-Graph only.
