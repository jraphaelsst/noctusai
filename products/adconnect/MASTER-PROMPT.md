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
- **auth** -- distributor invitation acceptance + `/me` endpoint. Custom JWT retired (Option A locked in Phase 0); SSO inherited from seed's `make_get_current_user` factory.

## Production state (post-MVP, 2026-05-10)

Backend is 100% Supabase-backed. Single `001_adconnect.sql` builds the full schema (16 tables in topological order: identity → catalog → sellout → orders → rewards → financial). All routers DB-backed with constructor-time `prefix=` (FastAPI 0.115 wildcard-route bug structurally fixed). Frontend ships 9 distributor pages + 5 React Query hooks against live endpoints.

- 208 mock-backed tests passing; realdb suites scaffolded; 9 LGPD flags landed.
- Brand admin V1 operates the marketplace via `/api/admin/*` — V2 (the brand-side UI) is a separate follow-up project.
- NF-e issuance via `FocusNFeProvider` Real adapter (lazy-imported httpx; sandbox vs prod via `ambiente=`); cancel + status round-trip implemented.
- Stripe pattern inherited from `products/core` (cross-product Python import is infeasible; SDK called directly with idempotency keys derived from `fatura.id`).

## Rules

- The seed framework is non-negotiable — all domain routers stay attached through `create_product_app()`'s `routers=[...]` seam. Never re-wire CORS, exception handlers, or middleware locally.
- Single `001_adconnect.sql` is the fresh-start migration. New schema changes edit 001 in-place + ship additive `002+` patches for live DBs (single-001 convention; `KB § PATTERNS/database-rls.md`).
- Constructor-time `APIRouter(prefix=...)` everywhere. NEVER `router.prefix = ...` post-construction (FastAPI 0.115 silently no-ops it — Phase 2-6 structural fix).
- Module-level `from ..database import X` binds at import time and defeats conftest patches. Use `_db.get_client()` lazy attribute access in services.
- Recurrence on rewards/sellout/financial/NF-e primitives must absorb to `noctusai_lib.domain.*` per the recurrence rule if mailing/PF/ERP/etc. grow similar engines.
- LGPD-first: distributor PII (CNPJ, addresses, financial state, NF-e XML) is flagged at every write site via `noctus.dev.lgpd_flag`.

## Testing

```bash
cd products/adconnect/backend && pytest
cd products/adconnect/frontend && npx vite build
```

## Dependencies

- Backend: `noctusai_lib` (code library) + `noctusai_seed` (framework)
- Frontend: `@noctusai/lib` (code library) + `@noctusai/seed` (framework)
