# Commerce

Generic e-commerce + ERP reference store for the NoctusAI **commerce vertical seed**. It is the L1 host product that consumes the `noctusai_lib.domain.commerce` organs (catalog, orders, payments, fulfilment) so the owner can validate the vertical end to end (gate T2) before any market-specific store is cut from it.

- Back office: `commerce.noctusai.com` (staff, license-gated).
- Public storefront: resolved from the request `Host` header via the organ's `commerce_storefront_hosts` table. On `commerce.noctusai.com` itself the storefront shows a "no store on this address" state.
- Scope: `deploy_scope='dev'` until owner validation; going live is a separate, consent-gated step.

## Stack

- **Backend**: FastAPI via `create_product_app()` from `noctusai_seed` (port 8019)
- **Frontend**: React via `createProductApp()` + `createProductLayout()` from `@noctusai/seed` (port 8230)
- **Build**: `createViteConfig()` from the seed framework
- **Database**: Supabase (schema: `commerce`)
- **Auth**: SSO + direct login; license-gated by construction

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8019 --app-dir products/commerce/backend

# Frontend
cd products/commerce/frontend && npm run dev
```

## Status

Backend wired to the commerce organ: `app/commerce.py` (`CommerceConfig` + generated `migrations/012_commerce.sql`, pinned by `tests/test_commerce_wiring.py`), staff / storefront / payment-webhook routers (`app/routers/commerce_routers.py`), per-org Asaas keys (`app/api_keys.py`, `/api/settings/api-keys`, readiness probe `app/key_testers.py`), fake-or-refuse deps (`app/commerce_deps.py`). P4 backend (`projects/commerce-seed-p4/CONTRACT.md` §6/§9): money states + fiscal (`014_commerce_money.sql`, `015_commerce_fiscal.sql`), the seed jobs queue (`016_jobs.sql`), the finance organ (`017_finance.sql`, `/api/finance/*`) and the items organ (`018_items.sql`, `/api/items/*`) — each rendered by `noctus.dev.render_organ_migration` and pinned by `tests/test_commerce_p4_wiring.py` (`012_commerce.sql` is applied in prod and is never rewritten). Fiscal + invoice webhook, order hooks → invoice jobs, scheduler jobs and the invoice worker live in `app/commerce_deps.py` / `app/scheduler.py` (inert without `NOCTUS_SCHEDULERS_ENABLED`). Frontend pages (`/admin/*`, `/financeiro/*`, storefront `/`) follow with the frontend organ. Store settings live at `/admin/configuracoes/{loja,enderecos,integracoes}` (seed `SectionTabsPage`, migration `030_status_pagina_configuracoes.sql`); the old per-page paths redirect. Contract: `projects/commerce-seed-p3/CONTRACT.md` §6.

Env: `ENCRYPTION_KEY` (Fernet, key writes 503 without it), `COMMERCE_LINK_SECRET` (signs e-mailed links; unset => 503), `PAYMENTS_ALLOW_FAKE` (tests/local only), `INVOICES_ALLOW_FAKE` (tests/local only: without a `focusnfe_token` invoices REFUSE with 503).
Platform credentials (resolved org → `platform_settings` → env, `resolve_credential`; never in the repo): `focusnfe_token` (env `FOCUSNFE_TOKEN`), `focusnfe_environment` / `focusnfe_token_environment` (+ env `FOCUSNFE_ALLOW_PRODUCTION=1` for `producao`), `invoice_webhook_token` (per-org invoice webhook secret; unset ⇒ 401), `commerce_installment_interest_bps` (optional card-installment interest override, default 199).
