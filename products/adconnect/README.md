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

## Current state — pre-implementation

> **AdConnect is scaffolded, not implemented.** The backend routers are wired against an in-memory store backed by JSON files in `app/data/` (`products.json`, `distributors.json`, `reward-rules.json`, etc.). The frontend has no domain pages yet — only the framework-provided ones (Dashboard, Equipe, Login, Landing).
>
> The mock-backed routers expose the intended shape of the domain. The implementation project replaces them with Supabase-backed services, ships the domain frontend, and adds proper RLS + tests. See `products/adconnect/projects/<implementation-slug>/PROJECT.md` once the project is filed.

What is actually wired today:

- `app/main.py` correctly inherits from `create_product_app()` (the seed framework provides health, team, notifications, CORS, Sentry, exception handlers, rate limiting, sidebar, header, AppShell, page-status filtering, SSO context).
- 9 domain routers attached at `/auth`, `/products`, `/cart`, `/orders`, `/rewards`, `/sellout`, `/financial`, `/distributors`, `/admin` — all reading from `app/data/store.py`'s JSON-backed in-memory store.
- Migration `001_adconnect.sql` creates `adconnect.status_pagina` + `adconnect.invitations` only. **No domain tables exist yet.**

## Tests

```bash
cd products/adconnect/backend && pytest
```

Currently only framework smoke tests (`tests/routers/test_health.py`, `tests/routers/test_team_router.py`) and the (placeholder) e2e suite. Domain coverage lands as part of the implementation project.
