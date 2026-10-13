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

Part 1 (host shell): seed spine registered (`start.sh`, catalog row, schema exposure). Part 2 (wiring the commerce organ: `app/commerce.py`, generated migration + parity test, router mounts, Asaas key spec) follows once the organ lands on `dev`. Contract: `projects/commerce-seed-p3/CONTRACT.md` §6.
