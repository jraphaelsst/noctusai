# 📩 Session findings — Google Calendar + Maps + Drive integrations

> **Date:** 2026-05-12
> **Source workspace:** `noctusai-youtube-crawler`
> **Source branch:** `feat/platform-chat-agent`
> **Source commit:** ports + adaptations live across the latest
> commits of the branch; promotion manifest at
> `noctusai-youtube-crawler/.promotions/google-integrations.md`.
>
> **Reference scope:** historical / read-before-planning. These are
> the first-class Google integrations promoted into a productized
> chatbot environment. Captures what was ported, where it differs
> from the source repo (`whatsapp-google-scheduling`), and a
> specific gotcha that future implementations will hit.

---

## TL;DR

Ported three Google integrations from `whatsapp-google-scheduling`
into `noctusai-youtube-crawler` and wired four new tools onto the
existing chatbot loop:

- **Calendar** — Fake + ServiceAccount + OAuth-user adapters,
  factory-selected. OAuth credential storage adapted onto the
  existing `CredentialStore` (Fernet-encrypted
  `youtube_crawler.credentials` table) so no new table needed.
- **Routes (Maps)** — Routes API v2 via httpx + a static fallback.
  Geocoding via Maps Geocoding API with the same key, kept on the
  intake service as `_geocode()`.
- **Drive-aware inspection** — non-destructive URL parser reusing
  the existing `gdrive_service`.

Four new chatbot tools: `schedule_event`, `list_upcoming_events`,
`travel_estimate`, `inspect_drive_url`. Validated **live** against
real Google APIs with credentials copied from the reference repo.

When this lands in noc, the migration map is
`.promotions/google-integrations.md` in the workspace.

---

## 1 · What was ported, and how it differs from the source

### Calendar package — `app/services/calendar/`

| File | Source | Adaptation |
|------|--------|------------|
| `types.py` | verbatim | none |
| `_google_api.py` | verbatim | none |
| `mappers.py` | verbatim | none |
| `google_adapter.py` | verbatim | none |
| `fake_adapter.py` | verbatim | none |
| `oauth_adapter.py` | restructured | credential storage moved from a SQLAlchemy `OAuthCredential` table to our existing `CredentialStore` (Fernet over `youtube_crawler.credentials`). Keyed by `(org_id, provider='google_calendar')` instead of `(provider, account_email)`. |
| `__init__.py` (factory) | restructured | takes `org_id + credential_store` instead of `session_factory`; same 3-tier resolution (OAuth → service-account → Fake) |

The OAuth flow is identical in shape to the reference, but
credential persistence reuses the same encryption + table the
YouTube OAuth refresh-token uses. No new schema migration.

### Routing package — `app/services/routing/`

Ported verbatim — `types`, `mappers`, `google_maps_adapter`,
`static_adapter`, `__init__`. Routes API v2 (`directions/v2:computeRoutes`)
with `routingPreference: TRAFFIC_UNAWARE` and minimal field mask.

### Drive

The reference repo doesn't ship a Drive integration. We already had
one (`app/services/gdrive_service.py`) for the YouTube-upload
pipeline; the new chatbot tool `inspect_drive_url` reuses its
URL parsers (`is_folder_url`, `parse_folder_id`, `parse_file_id`).

### Chatbot integration

`ChatbotService._build_tools()` gained four entries:
`schedule_event`, `list_upcoming_events`, `travel_estimate`,
`inspect_drive_url`. Handlers delegate to new
`WhatsAppIntakeService` methods.

`SYSTEM_PROMPT` gained:
- Paths 7/8/9 (calendar / maps / drive-inspect) listed alongside
  the existing media + upload capabilities.
- An explicit rule: **"Use returned URLs verbatim — never add
  `/u/0/` prefixes or rewrite domains"**. This was a real bug —
  see §3 below.

### OAuth bootstrap router — `app/routers/calendar_router.py`

- `GET /api/calendar/status` — which adapter would build today
- `GET /api/calendar/oauth/start` — 302 to Google consent
- `GET /api/calendar/oauth/callback` — code exchange + encrypt +
  upsert via `CredentialStore`

Code exchange uses httpx directly (no `google-auth-oauthlib`
dependency) so the import footprint stays minimal.

---

## 2 · Config + secret handling

Same env var names as `whatsapp-google-scheduling` so an operator
who already has the working credentials there copies verbatim:

```
GOOGLE_OAUTH_CLIENT_ID
GOOGLE_OAUTH_CLIENT_SECRET
GOOGLE_OAUTH_REDIRECT_URI
GOOGLE_OAUTH_ACCOUNT_EMAIL
GOOGLE_SERVICE_ACCOUNT_FILE     (path under ./secrets/, gitignored)
GOOGLE_CALENDAR_DEFAULT_ID
GOOGLE_CALENDAR_DEFAULT_TIMEZONE
GOOGLE_MAPS_API_KEY
```

The `secrets/` directory is mounted into the app container at
`/app/secrets:ro`. The service-account JSON + the OAuth-client
JSON live there. Both are listed in `.gitignore`.

---

## 3 · The gotcha: LLM rewriting `htmlLink`

**Symptom:** user clicked the calendar event link the chatbot
sent and got a Google 400 ("solicitação inválida"). Reproduced by
inspecting the URL: it had `/u/0/event?eid=...` instead of the
correct `/event?eid=...`.

**Cause:** the LLM "polished" the `html_link` field returned by
the tool — it inserted `/u/0/` into the URL path because that
pattern is common in Google account-context URLs. Google's UI
doesn't recognize that path for event detail, so the request
returned 400.

**Fix:** explicit `SYSTEM_PROMPT` rule:

> Quando uma ferramenta retornar um link (campo `html_link`,
> `auth_url`, ou `htmlLink`), COPIE-O LITERALMENTE no seu reply.
> Nao adicione prefixos como `/u/0/`, nao mude o dominio, nao
> reformate. URLs do Google so funcionam exatamente como o
> servidor retornou — qualquer modificacao quebra o link e o
> usuario ve um erro 400.

**Recommendation for noc:** any LLM-driven workflow that surfaces
provider-issued URLs back to the user needs this anti-rewriting
rule baked into the system prompt. The seed could ship a generic
fragment like "External URLs are immutable — copy from tool
responses character-for-character" and have products append it
to their own prompts.

Pattern generalizes beyond Google. Same risk exists for: Stripe
checkout URLs, Vista property detail links, WAHA media URLs,
YouTube video URLs.

---

## 4 · The gotcha: SA writer vs. owner

Service-account on a personal-Gmail calendar:

- The user (calendar owner) shares the calendar with the SA email
  with role=writer.
- The SA can `create_event` — the event appears on the user's
  calendar with `organizer.email = <user>, self: true` and
  `creator.email = <SA-email>`.
- The SA CANNOT add real attendees (would silently fail or be
  dropped). For attendees the OAuth-user adapter is required (it
  acts AS the user).

**Recommendation:** the seed factory should expose
`adapter.supports_attendees` as a Protocol attribute so callers
can short-circuit attendee logic when needed. Already done in our
port (carried from the reference repo).

---

## 5 · Live validation evidence

Real Google API calls made during the session, all returning 200:

| Call | Result |
|------|--------|
| Maps Routes v2: Paulista 1000 → Guarulhos | 37 min / 29.4 km |
| Maps Routes v2: Vila Olímpia → Congonhas | 12 min / 4.9 km |
| Maps Geocoding: "Av. Paulista 1000" | resolved to lat/lng |
| Calendar list_events on joaoraphaelsst@gmail.com | 8 events returned |
| Calendar create_event (via SA) | event created, re-fetched, status=confirmed |
| Calendar ACL inspection | confirmed SA has role=writer |
| OAuth /start | consent URL generated with correct scopes |

Backend tests: 190/191 (16 new for the ported modules, same
pre-existing team-list failure as before).

---

## 6 · Recommendation for noc seed-side rollout

These integrations belong in `noctusai_lib.integrations.google.*`
per the seed's six-layer model. Three migration steps:

1. **Verify the seed-side modules exist.** KB hints at
   `noctusai_lib.integrations.google_calendar` and
   `google_maps` but didn't surface in the live tree during this
   session. If they exist, reconcile shapes; if not, lift our port
   as v1.
2. **Make `CredentialStore` part of `noctusai_lib`.** Today it's
   product-side. The OAuth flow (Calendar, YouTube, future
   integrations) consistently needs Fernet-encrypted
   `(org_id, provider) → tokens`. Generalize.
3. **Promote the `ChatbotIntake` Protocol.** When the chatbot
   service lifts (per `platform-chat-agent.md`), these four tool
   handlers (`schedule_calendar_event`, `list_calendar_events`,
   `travel_estimate`, `inspect_drive_url`) become part of the
   contract every consumer's intake implements.

The full migration map is at
`noctusai-youtube-crawler/.promotions/google-integrations.md`
including the seed_first_analysis Q1-Q6 + integration notes.

---

## 7 · Pointers

- Code: `noctusai-youtube-crawler/products/youtube-crawler/backend/app/services/{calendar,routing}/`
- Tests: `tests/services/test_google_integrations.py` (16 cases)
- Router: `app/routers/calendar_router.py`
- Tool handlers: `app/services/whatsapp_intake_service.py`
  (schedule_calendar_event, list_calendar_events,
  travel_estimate, inspect_drive_url, _geocode)
- Chatbot tools: `app/services/chatbot_service.py`
  (4 new entries in `_build_tools()`)
- Reference repo: `../whatsapp-google-scheduling/app/services/{calendar,routing}/`
- Promotion manifest:
  `noctusai-youtube-crawler/.promotions/google-integrations.md`
- Companion docs:
  - `AGENT.md §3.7-3.9` — updated capabilities for the chatbot
  - `SYSTEM-ARCHITECTURE.md §3.9` — new architecture branch
  - This file's sibling
    `SESSION-NOTES_chatbot-multichannel-2026-05-12.md` — the prior
    chatbot-multichannel session that this builds on

— filed by Claude (Opus 4.7) working in `noctusai-youtube-crawler`
  on branch `feat/platform-chat-agent`, 2026-05-12, at the user's
  request as historical reference for future expansion into noc.
