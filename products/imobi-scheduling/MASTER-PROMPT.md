# Imobi Scheduling -- Master Prompt

## Purpose

WhatsApp scheduling bot for real-estate **media crews**: a real-estate agency's photographers / videographers / drone operators visit properties to produce listing media. Corretores message the agency's WhatsApp number in pt-BR; the bot (OpenAI tool-loop) parses the request, asks for missing fields, deconflicts the crew's calendar + travel time between condominiums, proposes 1-3 candidate slots, and on confirmation creates the Google Calendar event + persists an `appointments` row + a `tool_call_audits` row.

Folded into noc on 2026-05-11 from sibling repo `whatsapp-google-scheduling/` (deletion-safe). The product is the first chatbot consumer of `noctusai_lib.integrations.whatsapp` + `noctusai_lib.domain.chatbot` + `noctusai_lib.domain.scheduling` and the first adopter of the chatbot-operational-readiness pattern.

## Architecture

- Schema: `imobi_scheduling`
- Backend port: 8011 | Frontend port: 8160 (frontend deferred in v1)
- Tenant key: `org_id` (single-agency v1 — one row in `auth.jwt() ->> 'org_id'`)
- Auth: SSO (Core) for any future admin UI; WhatsApp inbound uses HMAC + phone-mapping authorization
- Backend path: `products/imobi-scheduling/backend/app/`
- Frontend path: `products/imobi-scheduling/frontend/src/` (placeholder; no admin UI in v1)

## Key Domains

### Identity
- **users** -- agency operators (corretores) + media crew; role-tagged
- **linked_identities** -- (channel, phone, user_id) mapping for WhatsApp → user authorization
- **pending_chat_identities** -- unrecognized senders awaiting onboarding (phone + first message; clears on identity link)
- **oauth_credentials** -- Google OAuth refresh tokens (LGPD-sensitive; encryption envelope follow-up filed)

### Real-Estate Inventory
- **condominiums** -- buildings + geocoded coords (Maps travel-matrix anchor)
- **properties** -- units within a condominium
- **services** -- photo / video / drone packages with default duration

### Scheduling
- **appointment_requests** + **appointment_request_services** -- in-flight booking (proposal window before confirmation)
- **appointments** -- confirmed bookings; carries `google_calendar_event_id` + audit columns (`cancelled_at`, `rescheduled_at`, `cancellation_reason`, etc. — Phase 9 migration 002)
- **route_groups** + **routes** -- back-to-back same-condo grouping (shorter slot duration when chained)
- **crew_skills** -- per-user service competencies

### Conversation
- **conversation_messages** -- append-only inbound/outbound transcript (PII: phone, name)
- **conversation_summaries** -- LLM-condensed long-term memory (window-rotated)
- **tool_call_audits** -- every LLM tool dispatch, args + result + latency (LGPD-relevant; redaction at write time)

## Services (13)

`scheduling` · `conversation` · `calendar` (Google Calendar adapter wiring + wrappers) · `maps` (Distance Matrix adapter wiring + condominium coord loader) · `tool_registry` (3 OpenAI tool descriptors + dispatcher) · `tool_audit` (Supabase adapter to seed's `AuditRecord`) · `authorization` (phone → user_id via `linked_identities`) · `retry` (Calendar / WAHA exponential-backoff wrappers) · `sanitization` (Phase 11 output sanitizer) · `metrics` (`NoopCounter` seam) · `anomaly` (Phase 11 tool-dispatch anomaly detector) · `conversation_rate_limit` (Phase 11 per-conversation Redis limiter) · `example_service` (scaffolded placeholder, kept until N=2 router-shape lift)

## Seed Consumption (the inheritance map)

- **`noctusai_lib.integrations.whatsapp`** — WAHA inbound parser + outbound sender + the `create_whatsapp_webhook_router` factory consumed in `app/routers/whatsapp_router.py`.
- **`noctusai_lib.domain.chatbot`** — Redis buffer + polling worker + LLM dispatcher; wired by `app/services/conversation.py::configure_conversation_module(...)` (consumer-side factory; lift-to-seed candidate at N=2).
- **`noctusai_lib.domain.scheduling`** — `SchedulingEngine` + `SchedulingRules` + `DefaultConflict` + `TravelLookup` Protocol. Wired by `app/services/scheduling.py::build_engine(...)` over a `GoogleMapsTravelLookup` adapter.
- **`noctusai_lib.integrations.google_calendar`** + **`google_maps`** — Real + Fake + factory shape; product wires both via `app/services/calendar.py::configure_calendar_module(...)` + `app/services/maps.py::configure_maps_module(...)`.
- **`noctusai_lib.domain.ai.tool_audit`** — `AuditRecord` value object. Product ships a Supabase adapter (`make_supabase_audit_writer`) because the seed `make_audit_writer` is SQLAlchemy-only (filed as P1 seed follow-up).
- **`noctusai_seed.create_product_app`** — standard routers `["health", "notificacoes", "team"]` + lifespan startup/shutdown wiring + structured logs + LLM credential resolution.

## Phase 0 stamped decisions (PROJECT.md §7, resolved 2026-05-10)

- **Slug:** `imobi-scheduling`.
- **Ports:** backend `8011`, frontend `8160` (next contiguous slot per `RESERVED_RANGES`).
- **Frontend in v1:** ⏳ DEFER (WhatsApp-only; admin UI ≡ follow-up project).
- **Single-agency RLS:** single-agency v1; multi-tenant when a second agency arrives.
- **Standalone:** shares conventions with `erp-imobiliario` but no cross-product data dep.
- **Locale:** pt-BR only in v1.
- **LGPD:** `conversation_messages` + `tool_call_audits` carry PII (phone, name, possibly location). Retention follows agency policy; redaction at audit write time.

## Imobi-Specific Patterns

- **WhatsApp 5-pin compliance.** `webhook_router.py` + `whatsapp_router.py` enforce HMAC-SHA256 verification before any side effect. Empty `IMOBI_WHATSAPP_WEBHOOK_SECRET` ⇒ bypass-mode + WARN (early dev only).
- **Working hours.** Morning 09:00-12:00, afternoon 13:30-16:30; lunch (12:00-13:30) is the implicit gap between two `WorkingWindow` objects, ≠ `BlockedInterval`. Configurable via `IMOBI_SCHEDULING_*` env vars.
- **Real-estate vocabulary mapping.** `condominium_id` ↔ scheduling-engine `location_id`, `media_crew_user_id` ↔ `assignee_id`, `travel_buffer_minutes` ↔ transition cost. Kept consumer-side so seed scheduling primitive stays domain-neutral.
- **Lifespan idempotence.** `app/lifespan.py::on_startup` short-circuits when `SUPABASE_SERVICE_ROLE_KEY` unset; logs WARN, skips worker start. WhatsApp inbounds drop with WARN in that mode.
- **Worktree-local schema cache.** `tests/conftest.py::_prime_schema_cache_from_worktree` walks from the conftest's own `__file__` to find the worktree's migrations, then calls `set_cache_for_tests(...)` at import time. Closes a `_find_repo_root` slip surfaced by DDD → DDD2 in Phase 9 (filed as seed-level P0 — `NOCTUSAI_REPO_ROOT` env should win the tie).
- **Single 001 migration + additive 002.** `001_imobi_scheduling.sql` builds the full 17-table schema. `002_appointment_audit_columns.sql` ≡ additive Phase 9 patch (cancellation ∨ reschedule columns). `002_invitations_accepted_columns.sql` ≡ parallel additive patch for invitations. Phase numbering may pile up additive `00X_*.sql` patches; greenfield rewrites of `001` ¬ allowed post-go-live.
- **Tool registry.** 3 OpenAI tool descriptors (lookup_property / propose_appointment / confirm_appointment) registered in `app/services/tool_registry.py`. Stub impls run when no `SchedulingService` injected (preserves dispatch-loop tests); live impls dispatched via `_LIVE_IMPLEMENTATIONS` when conversation module configured.

## Standard Routers Mounted

`["health", "notificacoes", "team"]` — health unauthenticated; `notificacoes` proxies to core; `team` enables future admin invitations. Product also mounts three custom routers via `routers=[...]`: `example_router` (CRUD scaffold placeholder; lift-or-delete at N=2), `webhook_router` (signed-receiver scaffold; canonical 5-pin reference), `whatsapp_router` (WAHA inbound via seed factory). `whatsapp_webhook` promotion to standard-router shape deferred until N=2 (mailing ∨ therapy adopting WhatsApp).

## Frontend (deferred)

Scaffold tool always emits a frontend folder. v1 folder ≡ placeholder — no admin UI built. Future "v1 admin UI" follow-up project will populate (operators / condominiums / properties / services / crew) ∨ formally delete. Tracked as [A] (PROJECT.md Phase 0 close).

## Development Guidelines

- Follow shared patterns from `noctusai_lib` (auth, roles, invitations, responses, exceptions); → `CLAUDE/backend.md` + `KB § PATTERNS/backend.md`.
- Router → Service → Schema split; routers thin, business logic in services.
- RLS policies use `((SELECT auth.jwt()) ->> 'org_id')::uuid` subquery form (Phase 3 baseline).
- Portuguese for business domain names (corretor, condominio, agendamento); English for technical/framework code.
- N+1 zero tolerance: batch all reads ∧ writes; scheduling engine pre-fetches condominium coords on lifespan startup.
- LGPD: every conversation_message ∧ tool_call_audit row is PII-bearing; redaction at write time + retention follows agency policy.
- Worktree tests: when running pytest under `.claude/worktrees/...`, `conftest.py` self-primes the schema cache from worktree migrations (¬ bypass).

## Testing

```bash
cd products/imobi-scheduling/backend && pytest
```

393 passed (P14 close 2026-05-11). Breakdown: 89 migration parse + 36 schema validation + ~268 router/service/lifespan/security/integration. Test inventory under `tests/` is split by surface (`routers/`, `services/`, `lifespan/`, `security/`, `integration/`).

## Contract Notes (Phases 0-14 — 2026-05-10 to 2026-05-11)

- **Single agency v1**: every RLS policy scopes on `((SELECT auth.jwt()) ->> 'org_id')::uuid`. Second agency ⇒ refactor (per-row `agency_id`); ¬ a per-product code change.
- **`SchedulingService.AuditWriter` adapter**: seed `AuditWriter` signature ≠ `AuditRecord`'s 1-arg callable shape; product ships the bridging adapter consumer-side. P1 seed follow-up filed.
- **`configure_conversation_module` carve-out**: seed chatbot module is constructor-based; we ship a consumer-side factory. Lift-to-seed at N=2 when therapy ∨ mailing adopt.
- **Calendar / Maps as Fake by default**: empty Google env vars ⇒ Fake adapters. Production deployment MUST set `GOOGLE_CALENDAR_OAUTH_*` + `GOOGLE_MAPS_API_KEY` + `GOOGLE_CALENDAR_DEFAULT_CALENDAR_ID`.
- **Redis as Fake by default**: empty `REDIS_URL` ⇒ in-memory `FakeRedis`. OK for dev; production MUST set a managed Redis URL (conversation memory + rate-limit + anomaly counters all consume it).
- **Frontend deferred**: scaffolded frontend folder is a placeholder; follow-up "v1 admin UI" project will populate ∨ delete it.
- **Migration 002 additive convention**: future schema changes post-go-live land as additive `00N_*.sql` patches; greenfield rewrites of `001` ¬ allowed.

## Dependencies

- Backend: `noctusai_lib` (code library) + `noctusai_seed` (framework)
- Frontend: `@noctusai/lib` + `@noctusai/seed` (placeholder — no admin UI in v1)
- WAHA: WhatsApp HTTP API (self-hosted at the platform's WAHA endpoint)
- Google: Calendar API + Maps Distance Matrix API
- Redis: conversation buffer + idle queue + Phase 11 security counters
- Supabase: Auth, database, RLS, daily backups (managed)
