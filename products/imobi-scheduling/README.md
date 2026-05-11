# Imobi Scheduling

WhatsApp chatbot that schedules real-estate media-crew appointments via Google Calendar. Operators (corretores) chat with the bot in pt-BR; the bot understands the request, deconflicts the crew's schedule + travel time, proposes slots, and on confirmation creates the Calendar event + audits the tool call.

Folded into noc on 2026-05-11 from the sibling repo `whatsapp-google-scheduling/` via `projects/imobi-scheduling-bot-creation/` (deletion-safe — no path dependencies survive).

## Stack

- **Backend**: FastAPI (port 8011) via `create_product_app()` from `noctusai_seed`
- **Frontend**: React + TypeScript + Vite (port 8160) — **DEFERRED** in v1 (WhatsApp-only; admin UI is a follow-up project)
- **Database**: Supabase (schema: `imobi_scheduling`)
- **Tenant key**: `org_id` (single-agency v1; multi-tenant is a refactor when a second agency arrives)
- **Auth**: SSO (from Core) + direct login for any future admin surface
- **WhatsApp transport**: WAHA (self-hosted)
- **LLM**: OpenAI (`gpt-4o-mini` default; tool-calling loop)
- **Calendar**: Google Calendar via OAuth (refresh-token rotation in `oauth_credentials`)
- **Travel**: Google Maps Distance Matrix API
- **Conversation memory**: Redis (TTL-bound; in-memory `FakeRedis` for dev)

## Running

```bash
# From repo root — Docker-first (recommended)
./start.sh                                 # full stack (or: ./start.sh tunnel imobi-scheduling)

# Local (no Docker)
uvicorn app.main:app --reload --port 8011 --app-dir products/imobi-scheduling/backend
```

Production deployment runbook (Compose, ports, env vars, healthcheck, backups, retry policy, smoke test): see [`DEPLOYMENT.md`](./DEPLOYMENT.md).

## Key Features

- **Inbound WhatsApp webhook** — WAHA receiver with HMAC-SHA256 signature verification (5-pin compliance contract; `webhook_router.py` + `whatsapp_router.py`).
- **Conversation framework** — Redis-backed buffer + debounced LLM dispatcher + summary memory (consumes `noctusai_lib.domain.chatbot`).
- **Authorization** — phone → user mapping via `users` + `linked_identities`; unrecognized senders go through `pending_chat_identities` onboarding.
- **Scheduling engine** — `noctusai_lib.domain.scheduling` (`SchedulingEngine` + `DefaultConflict`) wired with a Maps-backed travel adapter. Real-estate vocabulary mapping: `condominium_id` ↔ location, `media_crew_user_id` ↔ assignee, travel-buffer ↔ transition.
- **Working hours** — 09:00-12:00 / 13:30-16:30 (lunch is implicit gap between two `WorkingWindow`s; configurable per agency via `IMOBI_SCHEDULING_*` env).
- **Cancellation + reschedule flows** — `SchedulingService.cancel_appointment` / `.reschedule_appointment` with audit columns on `appointments` (Phase 9, migration 002).
- **Tool-call audit** — every LLM tool dispatch persisted to `tool_call_audits` (LGPD-relevant; redaction at write time).
- **Security hardening** (Phase 11) — output sanitization, Pydantic arg validation, per-conversation rate limiter + tool-dispatch anomaly detector (both Redis-backed; degrade gracefully when Redis unset).
- **Operational readiness** (Phase 10) — `retry_call` on Calendar / WAHA writes, structured JSON logs, `/api/health` endpoint, `NoopCounter` metrics sink with seam ready for the platform-metrics project.

## Tests

```bash
cd products/imobi-scheduling/backend && pytest
```

393 passed (P14 close 2026-05-11). Test layout: `tests/test_001_migration.py` + `tests/test_schemas.py` (structural) · `tests/routers/` (health/team/example/webhook/whatsapp) · `tests/services/` (scheduling/conversation/calendar/maps/tool_audit/tool_registry/anomaly/authorization/retry/sanitization/metrics/conversation_rate_limit) · `tests/lifespan/` · `tests/security/test_prompt_injection.py` · `tests/integration/test_e2e_flows.py`.
