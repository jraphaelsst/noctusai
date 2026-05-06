# AdConnect -- Master Prompt

## Purpose

B2B marketplace connecting a brand to its distributor network. Distributors log in, browse the brand's catalog at preferential prices, build a cart, place orders, file sellout reports, and earn cashback on qualifying sellout. The brand-side admin manages catalog, distributors, reward rules, and reviews sellout/financial state.

## Architecture

- Schema: `adconnect`
- Backend port: 8007 | Frontend port: 8130
- Tenant key: `org_id`
- Auth: TBD by implementation project — current scaffold ships custom JWT for distributor self-registration; the production auth model (single-org SSO vs. distributor-as-external-org) is one of the questions the implementation project resolves.
- Backend path: `products/adconnect/backend/app/`
- Frontend path: `products/adconnect/frontend/src/`

## Key Domains

### Catalog and ordering
- **products** -- brand catalog browsing with category, search, sort, in-stock filtering. Today reads from `app/data/products.json`.
- **cart** -- per-distributor cart, line-level quantity edits, totals. Today in-memory in `store.users` / `store.orders`.
- **orders** -- order placement (cart → order), order history, status lifecycle.

### Rewards and sellout
- **sellout** -- distributors file sellout reports (the input that proves resale to end-customer). Today reads `app/data/sellout-reports.json`.
- **rewards** -- cashback rules + accrual ledger; reward rules live in `app/data/reward-rules.json`. The accrual logic is a candidate for `noctusai_lib.domain.rewards` extraction once it stabilises (recurrence rule will fire on N=2 if mailing/PF use a similar engine).

### Brand-side operations
- **financial** -- invoices, payment terms, ledger of charges/payments. Today reads `app/data/invoices.json`.
- **distributors** -- distributor account list and detail; brand admin views and manages.
- **admin** -- brand-side administration surface.

### Auth
- **auth** -- login + registration for distributors. Custom JWT scaffolded; password hashing in `app/security.py`; current state seeds in-memory users via `_seed_users()`.

## Current state — pre-implementation

The backend routers and JSON-backed store are **scaffolded mock state from an early absorption**. They demonstrate the intended shape of the domain but are not production. Specifically:

- All 9 routers route through `app/data/store.py` (JSON files loaded once at process start, mutations held in process memory — lost on restart).
- Migration `001_adconnect.sql` creates only the framework tables (`status_pagina`, `invitations`); **zero domain tables exist in Supabase yet**.
- The frontend has no domain pages — only the seed-provided Dashboard, Equipe, Login, Landing, etc. No catalog UI, cart UI, order history UI, rewards UI, sellout UI.
- Tests cover only the framework (health, team) — no domain test coverage.

The implementation project replaces the mock routers with Supabase-backed services, adds RLS, ships the domain frontend, and lands tests. **See `products/adconnect/projects/<slug>/PROJECT.md` once filed for the full scope and phase plan.**

## Rules

- The seed framework is non-negotiable — all domain routers stay attached through `create_product_app()`'s `routers=[...]` seam (already correct in `main.py`). Never re-wire CORS, exception handlers, or middleware locally.
- Mock JSON state is throwaway — the implementation project is responsible for deriving DB schema FROM the mock shapes (don't ossify the mock shapes; treat them as informative, not authoritative).
- Recurrence on rewards/sellout/financial primitives must absorb to `noctusai_lib.domain.*` per the recurrence rule if mailing/PF/ERP grow similar engines.
- LGPD-first applies to distributor data (CNPJ, addresses, financial state) — the implementation project owns the data-class flagging.

## Testing

```bash
cd products/adconnect/backend && pytest
cd products/adconnect/frontend && npx vite build
```

## Dependencies

- Backend: `noctusai_lib` (code library) + `noctusai_seed` (framework)
- Frontend: `@noctusai/lib` (code library) + `@noctusai/seed` (framework)
