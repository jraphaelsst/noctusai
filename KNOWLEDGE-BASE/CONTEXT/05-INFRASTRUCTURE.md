# 06 — Infrastructure Context

## VPS (Hostinger)

- **Server**: `72.61.28.36` — Docker containers with Let's Encrypt SSL
- `n8n.noctusai.com` — Agentic workflow orchestration
- `waha.noctusai.com` — WhatsApp HTTP API

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
