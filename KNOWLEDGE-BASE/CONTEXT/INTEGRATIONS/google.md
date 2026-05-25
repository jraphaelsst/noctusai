# Google integrations — consume-side reference (Calendar · Maps · YouTube · Drive · Gmail)

> **Purpose.** Authoritative consume-side reference for the five
> Google seed integration packages:
> `noctusai_lib.integrations.{google_calendar, google_maps, youtube,
> google_drive, gmail}`. Each ships canonical Protocol + Fake + Real +
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

### Upload / Shorts platform facts (durable; verified via a live social-wiring Drive-folder fan-out, 2026-05-21)

- **Shorts max length = 180s** (since 2024-10-15 — the old 60s figure persists in third-party blogs; re-verify off [official YT Help](https://support.google.com/youtube/answer/15424877)). YT **auto-classifies** vertical ∧ ≤180s as a Short on its side — `upload_video()` is the **same call** for long-form and Shorts; the only platform-side signal a consumer adds is a `#Shorts` description tag.
- **Content-ID gotcha**: a Short **>60s** carrying an active Content-ID claim is **globally blocked**. Audio from YT's own library is fine; uploader-supplied licensed audio is the risk.
- **Refresh-token portability (credential insight)**: a Google refresh token is bound to **(client_id, user, scopes)**, NOT to a product. Porting a channel credential across noc products that share one OAuth client is just `decrypt(old_key) → re-encrypt(new_key) → UPSERT` into the target's `CredentialStore`; the redirect-URI registration only matters during the initial consent dance, never on the refresh path.

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

## 5. gmail — Gmail API v1 (send + read, OAuth-only)

Package: `seed/lib/backend/noctusai_lib/integrations/gmail/`.
`__all__`: `GMAIL_MODIFY_SCOPE`, `GMAIL_READONLY_SCOPE`,
`GMAIL_SEND_SCOPE`, `SUBJECT_MAX_LEN`, `FakeGmailClient`, `GmailClient`,
`GmailCredentialResolver`, `GmailLabel`, `GmailListResult`,
`GmailMessage`, `OAuthGmailCredentials`, `RealGmailClient`,
`SendResult`, `make_gmail_client`.

Lifted 2026-05-18 (commit `b881079b`, originating project
`mcp-connector-expansion`) to close the last gap in the Google seed
family. `noctusai_lib.integrations.email` is the **Resend**-backed
digest/invitation module (NOT Gmail) — a product needing "send from
the user's Gmail" or "read the user's inbox" now consumes from here
instead of forking. The consume-side MCP wrapper at
`mcp/google/tools/gmail.py` is the first in-tree adopter.

**Protocol surface** (`GmailClient`):
- `async send_message(*, to, subject, body_text, body_html=None,
  cc=None, bcc=None) → SendResult` — **100 quota units**; requires
  `gmail.send` scope. `subject` is RFC-5322-clipped to
  `SUBJECT_MAX_LEN` (998 octets) by both adapters before MIME-build.
- `async list_messages(*, query=None, label=None, page_token=None)
  → GmailListResult[GmailMessage]` — **5u for the list page + 5u per
  hydrated message** (list returns ids+thread-ids only; both adapters
  hydrate to honour the "return full `GmailMessage`" contract).
  Requires `gmail.readonly`.
- `async get_message(message_id) → GmailMessage | None` — **5u**.
  Returns `None` on 404. Requires `gmail.readonly`.

**Quota model** is per-user-per-second (250u/user/sec burst budget +
1 000 000 000u/day project ceiling), NOT a daily countdown like
YouTube. Consumers size batch loops against the 250/user/sec ceiling;
a naive "list then get each" loop costs `5 + 5·N` (~50 messages/sec
of hydration before throttle).

**Adapters**:
- `FakeGmailClient` — deterministic in-memory; records every send on
  `.sent`; `add_fake_message(...)` fixture seam; `PAGE_SIZE=2` for
  testable paging. Sent messages round-trip via
  `list_messages(label="SENT")`.
- `RealGmailClient(oauth_credentials=...)` — wraps
  `googleapiclient.discovery.build("gmail", "v1", ...)`. **OAuth-only**
  — `users.messages.*` act on a private user mailbox so there is no
  API-key path (unlike YouTube/Drive). Constructing without
  `oauth_credentials` (or with `api_key` only) raises `ValueError`
  at construction time (fail loud, per no-silent-errors). Send builds
  a `multipart/alternative` MIME via the stdlib `EmailMessage` and
  submits the base64url `raw` per the Gmail API contract. Logs HTTP
  errors at WARN+ before re-raising. `get_message` returns `None`
  on 404 (the only swallowed status — every other error re-raises).

**Factory** (`make_gmail_client(use_fake=False, api_key=None,
oauth_credentials=None, fake_seed_data=None)`):
- `use_fake=True` → `FakeGmailClient` (optionally seeded by
  `fake_seed_data={"messages": [...]}`).
- `use_fake=False` ∧ `oauth_credentials` present → `RealGmailClient`.
- `use_fake=False` ∧ NO `oauth_credentials` → `FakeGmailClient`
  (the "tenant not yet connected" fallback; mirrors the Calendar
  resolver pattern — a missing per-tenant OAuth token is the
  *expected* not-connected state, NOT an error). To force a loud
  failure instead, construct `RealGmailClient` directly.
- `api_key` is accepted for factory-shape parity with the
  youtube/drive adapters but is **inert for Gmail** (no API-key path
  for a user mailbox).

**Auth**. Gmail is **OAuth-only** — per-user refresh-token; Workspace
Domain-Wide-Delegation exists but most tenants lack it, so DWD is
out-of-scope for v1. Inject a `GmailCredentialResolver` (per-tenant
OAuth lookup from Supabase or the seed `CredentialStore`); the
resolver returns `OAuthGmailCredentials(refresh_token, client_id,
client_secret, token=None, token_uri=..., scopes=[GMAIL_SEND_SCOPE])`
or `None`. The OAuth dance itself is the generic
`noctusai_lib.security.oauth` router — do NOT duplicate it here
(same rule the Meta + Calendar packages follow). Scopes default to
**send-only**; a read-touching consumer must pass `GMAIL_READONLY_SCOPE`
explicitly (consent must have been granted for it — the seed cannot
widen a scope the user never approved).

**Consume recipe** (cited consumer `mcp/google/tools/gmail.py:48`):
```python
from noctusai_lib.integrations.gmail import (
    GmailClient,
    OAuthGmailCredentials,
    make_gmail_client,
)

# Per-tenant resolver returns OAuthGmailCredentials | None
creds = resolver.get_credentials(tenant_id=org_id)
client = make_gmail_client(oauth_credentials=_to_google_creds(creds))
# creds is None → factory falls back to FakeGmailClient automatically
result = await client.send_message(
    to="user@example.com",
    subject="Hello",
    body_text="plain body",
    body_html="<b>rich body</b>",  # optional
)
```

**Consumer status**: seed-ahead — no in-tree `products/*` consumer
yet (N=0); `mcp/google/tools/gmail.py` is the first thin MCP-tool
wrapper. The next product needing per-user email-send wires
`GmailCredentialResolver` against the seed `CredentialStore` (same
shape as the existing Calendar/Drive resolvers — pattern at
`seed/lib/backend/noctusai_lib/integrations/credential_resolvers.py`,
which already documents `CALENDAR_PROVIDER` / `DRIVE_PROVIDER` /
`META_PROVIDER` constants — extend with `GMAIL_PROVIDER` when N=1
hits, NOT pre-emptively).

**Out-of-scope (v1)**: Gmail push/watch (Pub/Sub) subscriptions,
full thread/label mutation (`gmail.modify` scope is exported but no
methods consume it yet), Workspace DWD, drafts, attachments,
batch-send. Any of these becomes a v2 follow-up filed only when a
consumer surfaces (no seed-ahead beyond send + read; see Gap row
"Gmail v2 surface" in §6).

---

## 6. Gaps / out-of-scope (with destinations)

| Item | Status | Destination |
|---|---|---|
| youtube / google_drive / gmail in-tree `products/*` consumer | seed-ahead-of-consumer (user-authorized) | Wire on the next consuming product; recurrence-rule re-evaluates at N=2 |
| google_calendar Domain-Wide-Delegation setup | supported via `ServiceAccountCalendarCredentials` | Cloud Console drill: `CONTEXT/GUIDES/google-oauth-setup.md` |
| google_maps Static-fallback accuracy | deterministic by design (dev/test) | Set `api_key=` for live Routes API v2 |
| OAuth start/callback router | not duplicated by design | Consume `noctusai_lib.security.oauth` + `google_scopes_router` as-is |
| Drive outbound write (upload to Drive) | out-of-scope — both Protocols are read/download only | Additive Protocol when a consumer needs it |
| Gmail v2 surface (push/watch, threads, drafts, attachments, batch-send, Workspace DWD) | out-of-scope — v1 ships send + list + get only | File `gmail-seed-v2-<feature>` follow-up project when a consumer surfaces; no seed-ahead per user policy |
| Gmail `CredentialStore` resolver bridge (`CredentialStoreGmailResolver` + `GMAIL_PROVIDER` constant) | not yet shipped — extend when N=1 product needs it | Add to `noctusai_lib.integrations.credential_resolvers` mirroring `CredentialStoreCalendarResolver`; pattern is mechanical |
