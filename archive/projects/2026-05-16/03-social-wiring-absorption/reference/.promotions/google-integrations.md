---
slug: google-integrations
origin:
  - products/youtube-crawler/backend/app/services/calendar/
  - products/youtube-crawler/backend/app/services/routing/
  - products/youtube-crawler/backend/app/routers/calendar_router.py
intended_noc_destination:
  - noctusai_lib/integrations/google/calendar/
  - noctusai_lib/integrations/google/routing/
  - noctusai_lib/api/calendar_router.py
layer_rationale: |
  Six-layer model: these are integration-adapter modules in the
  `integrations` layer. Belong in `noctusai_lib.integrations.google.*`
  alongside future Sheets / Photos / Translate adapters. The calendar
  OAuth router is in the API layer.

  The structure mirrors `noctusai_lib.integrations.google_calendar` +
  `noctusai_lib.integrations.google_maps` per the seed conventions
  (KB § PATTERNS/whatsapp-chatbot-seed.md mentions both as expected
  seed-side modules).
seed_first_analysis: |
  Q1 — Cross-product candidate? YES. Calendar + Maps are universal:
  mailing (schedule a send), daily-life (agenda), therapy (sessions),
  ERP (visits, vistorias), PF (financial-event reminders), any product
  that talks about "when" or "where".
  Q2 — Variance across consumers? None at the Protocol level — every
  consumer wants Create/Get/List/Delete events + travel-time. Per-
  product variance is at the system-prompt level (which the agent
  branch already isolates).
  Q3 — Existing seed coverage? Partial — KB mentions
  `noctusai_lib.integrations.google_calendar` + `google_maps` but I
  did NOT see them in the live tree at session time. Need to verify
  before promoting (KB § 03-SEED-ARCHITECTURE "verify the seed
  ships it" test).
  Q4 — Fake+Real shape? Already correct — `FakeCalendarAdapter` +
  `StaticRoutingAdapter` ship alongside the real ones. Factory
  selects automatically.
  Q5 — Migration cost? Low. The credential storage already uses
  `CredentialStore` which is product-side but trivially generalizable.
  Q6 — Risk of premature seed lift? Low. The reference repo
  (whatsapp-scheduling) has been running these in production for
  weeks; we just ported them. Two production consumers (WAHA-sched
  + YouTube-Crawler) = N=2 ≥ recurrence threshold.
dependencies_on_other_additions:
  - whatsapp-chatbot-service
  - platform-chat-agent
  - multimodal-stack
promoted_on: not-yet
---

## Why this addition exists

The chatbot's `AGENT.md §4` listed "Agendamento de eventos / Google
Calendar" and "tempo de viagem entre imóveis" as capabilities it
DIDN'T have. Both are universal real-estate operations (visitas,
gravações, deslocamento entre imóveis). The reference repo
`whatsapp-google-scheduling` already had working, production-grade
integrations for both. Porting them in directly is faster than
re-implementing.

Bundle scope:

- **Google Calendar** — 6 files. Protocol + Fake + ServiceAccount +
  OAuth-user adapters + a factory that picks between them based on
  credentials. The OAuth path uses our existing `CredentialStore`
  (Fernet-encrypted `youtube_crawler.credentials` table) keyed by
  `(org_id, provider='google_calendar')`. Same shape the YouTube
  OAuth refresh-token already uses — zero schema migration.
- **Google Maps Routes API v2** — 5 files. Protocol + Static fallback
  + Google adapter (httpx). Plus a private `_geocode` on the intake
  service that hits the Geocoding API with the same Maps key so the
  chatbot can take free-text addresses ("Av Paulista 1000") instead
  of lat/lng pairs.
- **Drive inspection** — leverages the existing `gdrive_service`
  parsers. Pure metadata extraction from a URL, no new download
  path.
- **4 new chatbot tools**: `schedule_event`, `list_upcoming_events`,
  `travel_estimate`, `inspect_drive_url`. Plus an updated
  SYSTEM_PROMPT that documents them in the live system prompt.
- **OAuth bootstrap router** at `/api/calendar/{status,oauth/start,
  oauth/callback}` for the one-time consent flow.

## Integration notes for noc-side

When promoting:

1. Verify the seed-side `noctusai_lib.integrations.google_calendar`
   + `google_maps` modules exist as the KB claims. If not, lift
   our code there as the v1 implementation. If yes, reconcile
   shapes (likely they're closer to ours than divergent).
2. Move `calendar/` → `noctusai_lib/integrations/google/calendar/`.
   The `OAuthCredentialRepo` shape needs the credential-store
   protocol explicit — pass it as a constructor arg so each consumer
   plugs its own.
3. Move `routing/` → `noctusai_lib/integrations/google/routing/`.
4. The OAuth router can stay product-side OR lift into
   `noctusai_lib.api.calendar_router` as a factory like the LLM
   router. Factory makes more sense at N=2+.
5. The 4 chatbot tool handlers live on `WhatsAppIntakeService` (which
   is itself a promotion candidate per platform-chat-agent.md).
   When ChatbotIntake becomes a Protocol, these methods are part of
   the contract.
6. Geocoding cache is a future Redis-backed addition — same address
   geocoded twice costs twice today.
