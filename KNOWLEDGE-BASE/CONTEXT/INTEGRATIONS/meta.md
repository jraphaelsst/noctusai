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
> **Scope.** Posting (FB Page post, IG publish) and ads **SHIP**; the
> Lead-Ads webhook parsing + subscription-management surface **SHIPS**
> (§1, §5) — see `leadgen_webhook.py`.
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
| `LeadgenForm` / `LeadgenQuestion` | A Page's lead-gen (Instant Form) form + its field schema (`list_leadgen_forms` / `get_leadgen_form`) |
| `Lead` / `LeadFieldEntry` | A submitted lead record + one answered field (`list_leads` / `get_lead`) — PII, gated by `leads_retrieval` |
| `PageSubscription` | One app's webhook subscription on a Page (`list_page_subscribed_apps`) |
| `LeadgenEvent` | One `leadgen` webhook-delivery change entry (`leadgen_webhook.parse_leadgen_webhook`) — carries only `leadgen_id` + attribution ids, never PII |

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

**Lead-ads read + webhook surface on `MetaAdapter`** (`get_lead` +
subscription management + the `leadgen_webhook` parsing module are the
additions this doc revision documents; form list/schema/records
predate it):
- `list_leadgen_forms(page_id, *, with_questions=False)` →
  `list[LeadgenForm]`. Form list + field schema — a Page token
  (`pages_show_list`/`pages_read_engagement`) is enough; `leads_count`
  is a form-level metric, NOT lead PII, so it's readable without the
  `leads_retrieval` scope below.
- `get_leadgen_form(form_id, *, page_id=None)` → `LeadgenForm` (with
  `questions`).
- `list_leads(form_id, *, page_id=None, limit=100)` → `list[Lead]` —
  the submitted lead RECORDS. **Production gate:** the distinct
  `leads_retrieval` scope; absent it Graph raises `MetaGraphError`
  `(#200) Requires leads_retrieval permission`, surfaced never faked.
- `get_lead(leadgen_id, *, page_id=None)` → `Lead` — the webhook-driven
  read-back: the Lead-Ads webhook delivers ONLY a `leadgen_id`, never
  the answers, so a receiver calls back here for the actual record.
  Same `leads_retrieval` gate as `list_leads`. **`FakeMetaAdapter`
  RAISES `MetaGraphError` on a miss** — the one exception to "the Fake
  never raises" in this package, because an empty `Lead` on a miss
  would silently upsert a PII-less row into production.
- `subscribe_page_to_leadgen(page_id, *, fields=("leadgen",))` →
  `bool` — `POST /{page_id}/subscribed_apps`, the Page-level opt-in
  Meta requires before it will DELIVER webhook events for that Page.
  **`graph_post` is form-encoded**: `fields` is sent as the
  comma-joined STRING Graph's form parser expects, never a JSON list
  (the single most likely silent Graph-400 / "webhook never fires"
  bug).
- `list_page_subscribed_apps(page_id)` → `list[PageSubscription]` —
  introspection counterpart; confirm a subscription actually took.
- `unsubscribe_page_from_leadgen(page_id)` → `bool` —
  `DELETE /{page_id}/subscribed_apps`.

`leadgen_webhook` module (`meta.leadgen_webhook`) — **pure functions,
zero IO, zero FastAPI**, so any product's webhook router can consume
them directly:
- `parse_leadgen_webhook(payload) -> list[LeadgenEvent]` — parses a
  (possibly batched) `POST /webhooks` delivery. Iterates **every**
  `entry[]` × **every** `changes[]` (Meta batches multiple
  entries/changes into one delivery — the anti-shape to avoid is
  `products/erp-imobiliario/backend/app/services/meta_api_service.py:139`,
  which reads `entry[0].changes[0]` only and silently drops the rest).
  Returns `[]` (never raises) on `object != "page"`, a non-list
  `entry`/`changes`, or any malformed row; skips a change whose
  `field != "leadgen"` or whose `value.leadgen_id` is falsy.
  `LeadgenEvent.raw` carries the `value` object verbatim (lossless —
  the product persists it).
- `leadgen_challenge_response(*, mode, verify_token, challenge,
  expected_token) -> str | None` — the `GET /webhooks` verification
  handshake. Returns `challenge` iff `mode == "subscribe"` AND
  `expected_token` is configured AND `verify_token` matches it via
  `hmac.compare_digest` (constant-time — this is a public
  unauthenticated endpoint guarding a shared secret).

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
(handles the Graph `+0000` offset), `page_subscription_from_body`
(reads an injected `_page_id`, same seam as `leadgen_form_from_body`).

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
| Lead-Ads webhook (Page/IG change events, `leadgen` field) | **SHIPS** — `leadgen_webhook.parse_leadgen_webhook` (batched-delivery-safe parsing) + `leadgen_challenge_response` (verification handshake) + `MetaAdapter.get_lead`/`subscribe_page_to_leadgen`/`list_page_subscribed_apps`/`unsubscribe_page_from_leadgen` (subscription mgmt + webhook-driven read-back) | Router mounting (`POST`/`GET /webhooks` FastAPI endpoint) + persistence is a product-side consumer wiring step — this module ships the parsing + adapter surface only, no FastAPI route |
| Webhook subscriptions for other change events (Page feed / IG comments / …) | out-of-scope | Separate future extension of `leadgen_webhook.py` (or a sibling module) if a non-leadgen field is ever needed |
| Video / Reels publish | **SHIPS** (`publish_instagram_reel` / `publish_facebook_video` — async resumable-upload + `poll_media_status` processing poll) — same App Review scope as image publish (`instagram_content_publish` for IG Reels; `pages_manage_posts` + Reels capability for FB) | Seed extension shipped 2026-05-24 (`projects/meta-video-reels-publish`). **Consumer wiring is the remaining thin step**: `social-wiring/media_creation/services/publish_service.py` extends with `target='instagram_reel'` / `'facebook_video'` / `'facebook_reel'` + widens the `mc_posts.published_target` CHECK constraint — gated on a `format='video'` consumer surfacing |
| TikTok | n/a — different vendor | Separate future `integrations/tiktok/` module |
| OAuth start/callback router | **not duplicated by design** | Consume `noctusai_lib.security.oauth` as-is |

> **WhatsApp is a separate package.** `noctusai_lib.integrations.whatsapp`
> ships its own Meta Cloud API client (`get_meta_cloud_client`) for
> WhatsApp Business — see `CONTEXT/INTEGRATIONS/whatsapp.md`. This doc
> is Facebook-Pages + Instagram-Graph only.

---

## 6. `leadgen_update` — Meta AI-agent lead qualification

**Undocumented by Meta.** Absent from the Page webhook reference and from every
lead-ads guide; four searches across StackOverflow, GitHub and vendor blogs on
2026-08-04 found no substantive public description. Everything below is captured
from Meta's own **"Teste"** sample payload in the App Dashboard — from the wire,
not from prose.

**Full runbook + the unfinished-processor contract: `/META-LEADGEN-UPDATE.md`.**

### The distinction that matters

`leadgen` = "a new lead was **submitted**" — immutable, fires once, `leadgen_id`
is a natural PK. `leadgen_update` = "an existing lead's **qualification
changed**" — mutable, fires repeatedly per lead, so `leadgen_id` alone is *not*
a PK. 🔴 Routing an update down the new-lead path creates a **duplicate lead**;
the two parsers are separate functions returning separate types for that reason.

### What ships

- `parse_leadgen_update_webhook(payload) -> list[LeadgenUpdateEvent]` — sibling
  of `parse_leadgen_webhook`, same batched-`entry[]`×`changes[]` and
  never-raise contract.
- `LeadgenUpdateEvent` — `leadgen_id`, ad context, `updated_time`, `area`,
  `event`, `updated_fields`, `raw` (lossless).

### Three wire facts

1. 🔴 **Ids are INTEGERS in this payload and STRINGS in `leadgen`'s.** Meta is
   inconsistent with itself; everything is coerced through `_stringify`. A `str`
   PK compared against an un-coerced `int` silently never matches.
2. `updated_time` is a **quoted string** unix timestamp; `created_time` is a bare
   number.
3. `updated_fields` names WHICH fields changed and carries **none of their
   values** — reading them needs a Graph call, the same indirection `leadgen`
   uses for PII.

`area` (`ai_agent_updates`) reads as a namespace and `event`
(`qualification_status_change`) as the change within it. Treated as open
vocabulary, never an enum — an unrecognised pair is preserved and surfaced.

### Consumer state

`products/social-wiring` captures these into `meta_webhook_events` as
`upd:<leadgen_id>:<fingerprint>` rows (fingerprint = `updated_time`+`area`+
`event`+`updated_fields`, so distinct changes are a history while a retry is
idempotent). **Applying the qualification to the lead or funnel is deliberately
NOT built** — the Graph response shape has never been observed, and guessing it
yields silently-wrong qualification rather than a visible failure. The trigger to
finish is one real non-test event; `/META-LEADGEN-UPDATE.md` §4 has the query,
the log marker, and the ordered next steps.
