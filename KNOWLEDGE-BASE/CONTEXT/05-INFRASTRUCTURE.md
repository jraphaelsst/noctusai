# 05 — Infrastructure Context

## Production host (VPS)

- **One VPS** (Hostinger, 8 GB RAM / 2 vCPU) runs the whole product fleet, one container per product, plus the infra and services stacks (`deploy/fleet/`, `deploy/services/`). Single points of failure and their mitigations → `KB § PATTERNS/devops/sre-craft-canon.md` §1.
- **Address and access are not recorded in the KB.** The host is reached through the SSH alias `noctus-vps` (operator `~/.ssh/config`; the default `ssh_host` of the `noctus.vps.*` tools) and, from CI, through the `NOCTUS_VPS_HOST` secret (`KB § PATTERNS/devops/prod-watchdog.md` §6). Look it up there, never paste it into docs.
- **TLS and routing** terminate at Cloudflare: a named Cloudflare tunnel (`noctus-tunnel`) carries every public hostname, with no open inbound web ports. Routes are derived from `deploy/tunnel/ingress.yml` (`KB § PATTERNS/devops/tunnel-ingress-source-of-truth.md`). The earlier Caddy + Let's Encrypt setup is retired.
- `n8n.noctusai.com` — agentic workflow orchestration (`noctus-services` stack, `deploy/services/compose.services.yml`).
- `waha.noctusai.com` — WhatsApp HTTP API (same stack; per-product WAHA instances in `deploy/fleet/compose.waha.yml`).
- Liveness: the off-host watchdog → `KB § PATTERNS/devops/prod-watchdog.md`. Backups / DR → `KB § PATTERNS/devops/sre-craft-canon.md` §5.

## CORS

Each backend configures CORS for its frontend via `CORS_ORIGINS` env var (comma-separated). Default: localhost at the product's frontend port.

## Supabase Schema Configuration

Each backend's `database.py` uses `ClientOptions(schema="<schema>")` to target the correct schema. **Important**: `erp`, `personal-finance`, and `therapy` must be in Supabase Dashboard "Exposed schemas" (Project Settings → API) for PostgREST to accept the schema headers.

## External Service Auth

| Service | Auth Config |
|---------|-------------|
| Supabase | `SUPABASE_URL` + `SUPABASE_ANON_KEY` + `SUPABASE_SERVICE_ROLE_KEY` |
| OpenAI | `OPENAI_API_KEY` (org_settings → platform_settings → env) |
| Stripe | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` |
| Meta Business API | Per-org in `erp.meta_config` table |
| Resend | `RESEND_API_KEY` (org_settings → env fallback) |
| ClickSign/DocuSign/D4Sign | Per-org in `erp.org_settings` → env fallback |
| WAHA | `WAHA_API_URL` + key |
| Sentry | `SENTRY_DSN` (optional) |
| Redis | `REDIS_URL` (optional, production caching) |
