# Google integrations — consume-side reference (Calendar · Maps · YouTube · Drive)

> **Purpose.** Authoritative consume-side reference for the four
> Google seed integration packages:
> `noctusai_lib.integrations.{google_calendar, google_maps, youtube,
> google_drive}`. Each ships canonical Protocol + Fake + Real +
> factory. Folds **what ships** (verified against each `__all__`),
> **consume recipe** (import -> factory -> resolver/credential injection
> via NAMED seams, real consumers cited `path:line`), and **gaps**
> into one durable doc.
>
> **Why this lives in KB.** Project folders
> (`whatsapp-seed-absorption/`, `seed-hardening-from-youtube-crawler/`,
> `youtube-crawler-build/`, `social-wiring-absorption/`) are deleted
> at close; this doc is durable and self-contained. The cross-provider
> OAuth dance / scope-discovery theory is at
> `CONTEXT/INTEGRATIONS/oauth-patterns.md`; the Google Cloud Console
> setup drill is at `CONTEXT/GUIDES/google-oauth-setup.md`; THIS doc
> is the four adapter API surfaces a product imports.

---

## 1. google_calendar — events (Fake + Service-account + OAuth)

Package: `seed/lib/backend/noctusai_lib/integrations/google_calendar/`.
`__all__`: `CalendarAdapter`, `CalendarCredentialResolver`,
`CalendarCredentials`, `CreatedEvent`, `EventAttendee`, `EventInput`,
`FakeCalendarAdapter`, `OAuthCalendarCredentials`,
`ServiceAccountCalendarCredentials`, `event_to_google_body`,
`get_calendar_adapter`, `google_body_to_created_event`,
`parse_google_datetime`.

- **Contract**: `CalendarAdapter` Protocol. Value objects
  `EventInput` / `EventAttendee` / `CreatedEvent`. Mappers
  `event_to_google_body` / `google_body_to_created_event` /
  `parse_google_datetime`.
- **Adapters** (selected by the factory from the resolved
  credentials kind — `*ServiceAccountAdapter` / `*OAuthAdapter` are
  NOT in `__all__`, the factory constructs them lazily):
  - `ServiceAccountCalendarCredentials` -> server-to-server (calendar
    must be owned / shared / DWD-delegated to the SA).
  - `OAuthCalendarCredentials` -> user-delegated, refresh-token based.
  - `None` / no resolver -> `FakeCalendarAdapter` (dev/test default).
- **Credentials seam**: `CalendarCredentialResolver` Protocol —
  product-injected per-tenant lookup; adapters resolve through it,
  they don't know how credentials are stored.

**Consume recipe**

```python
from noctusai_lib.integrations.google_calendar import (
    CalendarAdapter, get_calendar_adapter,
)
adapter: CalendarAdapter = get_calendar_adapter(
    credential_store=store, tenant_id=org,
    oauth_client_id=cid, oauth_client_secret=csecret,
)
```

`credential_store=` is the convenience path — REQUIRES
`oauth_client_id` + `oauth_client_secret` (the product's app
identity, not per-tenant) or it raises `ValueError`. For full control
inject a `CalendarCredentialResolver` via the first positional arg
(`resolver` wins if both given).

**Live consumer (cited):**
`products/social-wiring/backend/app/routers/calendar_router.py:125` —
`adapter = get_calendar_adapter(org_id=resolved_org if store else
None, credential_store=store)`; import at `:46`. Branches
`consent_required` on the `fake` label (the dev/test fallback signal).
Also consumed at
`products/social-wiring/backend/app/services/whatsapp_intake_service.py:1178`.

---

## 2. google_maps — routing (Routes API v2 + Static fallback)

Package: `seed/lib/backend/noctusai_lib/integrations/google_maps/`.
`__all__`: `Coordinates`, `GoogleMapsRoutingAdapter`,
`RoutingAdapter`, `StaticRoutingAdapter`, `TravelEstimate`,
`build_routes_request`, `get_routing_adapter`,
`parse_routes_response`.

- **Contract**: `RoutingAdapter` Protocol. Value objects
  `Coordinates` / `TravelEstimate`. Mappers `build_routes_request` /
  `parse_routes_response`.
- **Factory**: `get_routing_adapter(api_key=)` ->
  `GoogleMapsRoutingAdapter` when `api_key` set, else
  `StaticRoutingAdapter` (deterministic dev/test fallback).
- **Scheduling-engine plug**: to feed
  `noctusai_lib.domain.scheduling.SchedulingEngine`, build a
  `TravelLookup` owning a `location_id -> Coordinates` map and
  delegate `travel_minutes(...)` to
  `RoutingAdapter.travel_estimate(...)`. The map is product-specific
  so it stays consumer-side.

**Live consumer (cited):**
`products/social-wiring/backend/app/services/routing/__init__.py:21`
— `from noctusai_lib.integrations.google_maps import (Coordinates,
GoogleMapsRoutingAdapter, RoutingAdapter, StaticRoutingAdapter,
TravelEstimate)`; `:28` re-exports `get_routing_adapter as
_seed_get_routing_adapter` behind a product `get_routing_adapter(
settings=)` that reads product config — a NAMED product seam over the
byte-identical seed adapters, not a fork.

---

## 3. youtube — Data API v3 (quota-cost-documented)

Package: `seed/lib/backend/noctusai_lib/integrations/youtube/`.
`__all__`: `DESCRIPTION_MAX_LEN`, `TITLE_MAX_LEN`,
`UPLOAD_QUOTA_UNITS`, `Channel`, `FakeYoutubeClient`, `ListResult`,
`Playlist`, `PrivacyStatus`, `RealYoutubeClient`, `Video`,
`VideoUpload`, `YoutubeClient`, `make_youtube_client`.

- **Contract**: `YoutubeClient` Protocol — each async method
  documents its **quota cost** (this is the whole point of the
  lift): `get_channel` 1u · `list_channel_videos` ~2u/50 videos ·
  `get_video` 1u · `search` **100u/page** · `upload_video`
  **1600u** (OAuth-only, resumable, returns `VideoUpload`).
- **Adapters**: `FakeYoutubeClient` (tracks cumulative
  `quota_units_consumed`; `PAGE_SIZE=2` for testable paging) ·
  `RealYoutubeClient(api_key=, oauth_credentials=)` (wraps
  `googleapiclient.discovery.build`; logs HTTP errors at WARN+
  before re-raising — never swallows).
- **Factory**: `make_youtube_client(use_fake=False, api_key=,
  oauth_credentials=, fake_seed_data=None)`.
- **Why the quota math matters**: the default `search.list` strategy
  burns 100u/page (1% of daily quota); `list_channel_videos` is
  ~50x cheaper. Consumers reading the Protocol docstrings pick the
  cheap channel->uploads-playlist->playlistItems path by default.

**Consumer status**: seed lifted ahead of the second consumer
(`seed-hardening-from-youtube-crawler/` Phase 1.3) — no in-tree
`products/*` consumer yet (`youtube-crawler` is the originating N=1).
The seed lands ahead per the user-authorized "spread it soon".

---

## 4. google_drive — download + read/inspect (two Protocols)

Package: `seed/lib/backend/noctusai_lib/integrations/google_drive/`.
`__all__` splits into two surfaces:

- **Download surface**: `DriveDownloader` Protocol · `DriveFile` ·
  `FakeDriveDownloader` · `make_drive_downloader` · `parse_drive_url`
  (pure mapper — accepts `file/d/{id}`, `open?id=`, `uc?id=`,
  `uc?export=download&id=`, bare ids).
- **Read/inspection surface** (added 2026-05-16,
  `social-wiring-absorption` Wave 1.E3): `DriveReader` Protocol ·
  `DriveSearchHit` · `DriveSearchResult` · `DriveFileContent` ·
  `FakeDriveReader` · `make_drive_reader` · `compute_content_stats`.

Two Protocols because they are different operations with different
consumers (chatbot "inspect my Drive" vs upload-pipeline
download-to-disk) — the download contract is NOT overloaded.
`compute_content_stats(...)` is the LLM-counting-trap fix (precompute
aggregates in Python; the tool description forbids the model from
recounting long structured data).

- `RealDriveDownloader(api_key=, oauth_credentials=)` — streams via
  `MediaIoBaseDownload`, logs HTTP errors at WARN before re-raising.
- Auth reach: "anyone-with-link" files need `api_key` (cheaper, no
  consent) OR OAuth `drive.readonly`; private files need OAuth. The
  Protocol is auth-agnostic; the factory routes.

**Consumer status**: `youtube-crawler` is the documented N=1 download
consumer (seed lifted ahead per user authorization,
`youtube-crawler-build/` Phase 0); the read/inspect surface was
reconciled from the social-wiring workspace `drive_api/` package — no
in-tree `products/*` consumer yet.

---

## 5. Gaps / out-of-scope (with destinations)

| Item | Status | Destination |
|---|---|---|
| youtube / google_drive in-tree `products/*` consumer | seed-ahead-of-consumer (user-authorized) | Wire on the next YouTube/Drive-touching product; recurrence-rule re-evaluates at N=2 |
| google_calendar Domain-Wide-Delegation setup | supported via `ServiceAccountCalendarCredentials` | Cloud Console drill: `CONTEXT/GUIDES/google-oauth-setup.md` |
| google_maps Static-fallback accuracy | deterministic by design (dev/test) | Set `api_key=` for live Routes API v2 |
| OAuth start/callback router | not duplicated by design | Consume `noctusai_lib.security.oauth` + `google_scopes_router` as-is |
| Drive outbound write (upload to Drive) | out-of-scope — both Protocols are read/download only | Additive Protocol when a consumer needs it |
| **Gmail** (send/read) | **GAP** — `noctusai_lib.integrations.email` is **Resend**, not Gmail | `projects/gmail-seed-lift/PROJECT.md` (Status=Filed) |
