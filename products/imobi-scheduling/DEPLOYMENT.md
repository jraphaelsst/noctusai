# Imobi Scheduling — Deployment

> Phase 10 production-hardening artifact. Folded into the README during Phase 12. Until then this file is the authoritative deployment runbook for the WhatsApp scheduling bot.

## Target — Docker Compose (single-host)

**Why Compose over Kubernetes for v1.** Single-agency deployment (PROJECT.md §7 Q4) → single backend replica is sufficient. The platform's [Containerization pattern](../../KNOWLEDGE-BASE/CONTEXT/PATTERNS/containerization.md) makes Compose the canonical first step — every product ships with a per-product `docker-compose.yml` + a Dockerfile that joins the shared `noctus-net` fabric. K8s is the right destination when multi-tenant lands (a second agency joins) or horizontal scale is needed (>1 backend replica behind a load balancer). Both are future work.

**Build artifacts.**

- `products/imobi-scheduling/backend/Dockerfile` — Python 3.11 slim base + uvicorn entrypoint.
- `products/imobi-scheduling/docker-compose.yml` — backend + frontend + Cloudflare quick-tunnel (profile-gated).

> **Phase 0 leftover (P2).** Today the compose file still carries the seed scaffold's `seed-*` service / container names — the substitution to `imobi-scheduling-*` was deferred at scaffold time. Operator-visible: `docker compose up` works because the fragment is self-contained, but the cosmetic mismatch is a Phase 12 cleanup item (or a follow-up scaffold-tool fix to substitute slugs at copy time). Tracked in PROJECT.md §6 Phase 10 Improvements.

## Ports

| Service               | Port  | Source of truth                  |
|-----------------------|-------|----------------------------------|
| Backend (uvicorn)     | 8011  | `start.sh` registry              |
| Frontend (vite preview)| 8160 | `start.sh` registry              |
| WAHA (external)       | 3000  | WAHA-side default; configurable via `WAHA_BASE_URL` |
| Redis (external)      | 6379  | Compose `redis` service / managed |

The platform's `./start.sh` reads the registry at the top of the script. To bring the stack up: `./start.sh` from the repo root.

## Environment variables

The product reads from a single `.env` at repo root (per `KB § PATTERNS/environment.md`). Required variables for production:

| Variable                                  | Purpose                                            | Notes                                          |
|-------------------------------------------|----------------------------------------------------|------------------------------------------------|
| `SUPABASE_URL`                             | Supabase project URL                               | Single per deployment                          |
| `SUPABASE_SERVICE_ROLE_KEY`                | Admin client; required for the conversation worker | Secret. Encrypt at rest.                       |
| `SUPABASE_ANON_KEY`                        | RLS-bound user paths (frontend, public routes)     |                                                |
| `WAHA_BASE_URL`                            | WAHA HTTP base                                     | e.g. `http://waha:3000` on the shared fabric   |
| `WAHA_API_KEY`                             | WAHA auth (when WAHA is run with auth enabled)     | Secret                                         |
| `WAHA_SESSION_NAME`                        | WAHA session id                                    | Default `imobi_scheduling`                     |
| `IMOBI_WHATSAPP_WEBHOOK_SECRET`            | HMAC-SHA256 secret for inbound signature verification | Unset → verification bypassed + WARN. **Set in prod.** |
| `OPENAI_API_KEY`                           | LLM dispatcher                                     | Secret                                         |
| `OPENAI_MODEL`                             | Model id                                           | Default `gpt-4o-mini`                          |
| `GOOGLE_CALENDAR_OAUTH_CLIENT_ID`          | Google OAuth client id                             | Unset → Fake calendar (dev only)               |
| `GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET`      | Google OAuth client secret                         | Secret. Unset → Fake calendar (dev only)       |
| `GOOGLE_CALENDAR_DEFAULT_CALENDAR_ID`      | Calendar ID events land on                         | e.g. agency shared calendar address            |
| `GOOGLE_MAPS_API_KEY`                      | Distance Matrix API                                | Unset → `StaticRoutingAdapter` (zero travel)   |
| `REDIS_URL`                                | Conversation buffer + idle queue                   | Unset → in-memory `FakeRedis` (dev/test only)  |
| `IMOBI_SCHEDULING_TIMEZONE`                | IANA tz                                            | Default `America/Sao_Paulo`                    |
| `IMOBI_SCHEDULING_MORNING_START` etc.      | Working-hour window bounds                         | See `app/config.py`                            |

**Secrets handling.** Use Docker secrets / a host-side `.env.production` mounted read-only into the backend container. **Never commit `.env`.** The `oauth_credentials.refresh_token` column is flagged LGPD-sensitive — at-rest encryption is currently relying on Supabase's disk encryption (P1 follow-up to fold a `seed/lib crypto envelope` helper; tracked in `LGPD-WARNINGS.md`).

## Health checks

The backend exposes `GET /api/health` via the seed framework (`create_product_app(standard_routers=["health", ...])`). Compose-level healthcheck:

```yaml
healthcheck:
  test: ["CMD", "curl", "-fsS", "http://localhost:8011/api/health"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
```

Expected response: `200 OK` with `{"status": "ok"}`. A `503` indicates the lifespan startup failed (typically a missing `SUPABASE_SERVICE_ROLE_KEY`); check `docker compose logs imobi-scheduling-backend`.

## Logging

Structured JSON logs are configured automatically by `create_product_app(...)` (the seed calls `noctusai_lib.logging_config.configure_logging(...)` during lifespan startup — see `seed/framework/backend/noctusai_seed/app.py:146`). Log format in production:

```json
{"timestamp": "2026-...", "level": "INFO", "logger": "...", "message": "...", "app": "imobi-scheduling"}
```

Ship logs to your preferred sink (Docker logging driver → CloudWatch / Datadog / Loki). Local debugging: `docker compose logs -f imobi-scheduling-backend`.

## DB backup procedure

**Managed: Supabase Daily Backups.** Supabase Pro+ tier ships daily automated backups with point-in-time recovery (PITR). Retention defaults to 7 days; configurable up to 30 days per project settings. Restore path:

1. Supabase Dashboard → Project → Database → Backups.
2. Select backup point + click "Restore".
3. Restoration creates a new project; reconfigure `SUPABASE_URL` / keys in `.env` post-restore.

**Critical tables** for the bot's continuity (loss = re-onboard users + lose conversation memory):

- `imobi_scheduling.appointments` — confirmed bookings + audit columns.
- `imobi_scheduling.appointment_requests` — in-flight bookings (the proposal-to-confirm window).
- `imobi_scheduling.users` + `linked_identities` — authorization mapping.
- `imobi_scheduling.oauth_credentials` — refresh tokens (encrypted at rest by Supabase storage; encryption envelope follow-up filed per LGPD).
- `imobi_scheduling.tool_call_audits` — LLM tool-call audit trail (LGPD-relevant; retention should match the agency's data-retention policy).

**Manual snapshot for local dev / disaster recovery drills.** `pg_dump --schema=imobi_scheduling $DATABASE_URL > imobi-scheduling-$(date +%F).sql`. Restore with `psql $DATABASE_URL < imobi-scheduling-...sql`. **Conversation memory** lives in Redis — it's ephemeral by design (TTL-bound per `CONVERSATION_MEMORY_TTL_SECONDS`); not part of the backup contract.

## Retry semantics

External writes (Google Calendar create/update/delete, future WAHA `send_text`) are wrapped with exponential-backoff retries via `app/services/retry.py`. Default policy for Calendar: 3 retries, 1s base, 2x multiplier, 30s cap. WAHA policy: 3 retries, 0.5s base, 2x, 10s cap. See `KB § PATTERNS/chatbot-operational-readiness.md` for the wider operational-readiness pattern.

## Metrics

**v1 ships with `NoopCounter`** (debug-level logging only). The metrics-sink seam (`app/services/metrics.py`) is wired at call sites — when the platform-metrics project lands, the wire is flipped at lifespan startup with no call-site churn. Operators can grep the JSON logs for `metric.increment` lines today.

## Smoke test (post-deploy)

```bash
curl -fsS http://localhost:8011/api/health      # 200 ok
curl -fsS http://localhost:8011/api/team        # 401 (auth required = wired)
# WhatsApp inbound webhook (with HMAC):
SIG=$(python -c "import hmac, hashlib; print(hmac.new(b'<SECRET>', b'<RAW_BODY>', hashlib.sha256).hexdigest())")
curl -X POST -H "X-Webhook-Hmac-Sha256: $SIG" -d '<RAW_BODY>' \
     http://localhost:8011/api/webhooks/whatsapp
```

Full end-to-end deploy drill: `KB § GUIDES/deploy-workspace-online.md`.
