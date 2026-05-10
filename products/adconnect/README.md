# AdConnect

B2B marketplace connecting brands to their distributor network. Distributors browse the brand's catalog at preferential prices, place orders, and earn cashback rewards on qualifying sellout reports.

## Stack

- **Backend**: FastAPI via `create_product_app()` from `noctusai_seed` (port 8007)
- **Frontend**: React via `createProductApp()` + `createProductLayout()` from `@noctusai/seed` (port 8130)
- **Database**: Supabase (schema: `adconnect`)
- **Tenant key**: `org_id`
- **Auth**: SSO + direct login (custom JWT for distributor self-registration is currently scaffolded — final auth model is decided in the implementation project)

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8007 --app-dir products/adconnect/backend

# Frontend
cd products/adconnect/frontend && npm run dev
```

## Domain

Nine routers cover the marketplace surface area:

- **auth** — distributor login and registration
- **products** — brand catalog browsing, filtering, search
- **cart** — shopping cart per distributor
- **orders** — order placement and history
- **rewards** — cashback rules and accrual ledger
- **sellout** — distributor sellout reports (the input that triggers reward accrual)
- **financial** — invoices, payment terms, ledger
- **distributors** — distributor account management
- **admin** — brand-side administration

## Production state

AdConnect is a real, production-shippable B2B marketplace product (post-MVP implementation, 2026-05-10).

- Backend: 100% Supabase-backed. 16 domain tables in `migrations/001_adconnect.sql` (single fresh-start file per platform convention). Per-distributor preferential pricing, three-mode sellout (estruturado / NF-e XML / freeform), pure-function reward accrual engine, lifecycle state-machine for orders, FocusNFe Real adapter for NF-e issuance, Stripe webhook handler (Stripe pattern inherited from products/core).
- Frontend: 9 distributor pages + 5 React Query hooks wired to live endpoints (catalog, cart+checkout, orders+history, sellout submission, rewards ledger).
- Identity: Option A (distributor-as-noc-user) — distributor users live in `noc.noctus_users` with `org_id` = brand's org; per-distributor membership lives in `adconnect.distributor_memberships`. SSO via the seed's `make_get_current_user` factory.
- 208 mock-backed tests passing; realdb suites scaffolded (auto-skip without Supabase credentials).
- LGPD flags at every PII write site (9 entries in `LGPD-WARNINGS.md`).

## Tests

```bash
cd products/adconnect/backend && pytest
```

Currently only framework smoke tests (`tests/routers/test_health.py`, `tests/routers/test_team_router.py`) and the (placeholder) e2e suite. Domain coverage lands as part of the implementation project.
