# 00 — Platform Landscape

> System overview for any AI agent or developer entering this codebase.

---

## What Is NoctusAI?

A **multi-tenant, multi-product SaaS platform**. Organizations sign up once on the core platform and get access to licensed products. Each product is independently deployable but shares authentication, tenant context, and billing through the core.

---

## Products

| Product | Path | Description | Port (BE) | Port (FE) |
|---------|------|-------------|-----------|-----------|
| **Core Platform** | `core/` | Auth, orgs, billing, licenses, SSO, admin | 8000 | 5173 |
| **ERP Imobiliario** | `products/erp-imobiliario/` | Real estate CRM: clients, properties, matching, sales funnel, financial, WhatsApp | 8001 | 8080 |
| **Personal Finance** | `products/personal-finance/` | Personal finance tracker: accounts, transactions, budgets, recurring, portfolios, watchlists, reports | 8002 | 8090 |
| **Therapy Platform** | `products/therapy-platform/` | Online therapy: video sessions (LiveKit), scheduling, clinical AI (dual-track summaries), wallets, messaging, reviews. 4 roles: admin/clinic/therapist/patient. Direct Supabase Auth (not SSO). Schema: `therapy` | 8003 | 8095 |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Core Platform                         │
│  Auth · Orgs · Billing · Licenses · SSO · Admin          │
│  FastAPI :8000          React :5173                      │
└──────────┬──────────────────────────┬───────────────────┘
           │ SSO Token                │ SSO Token
┌──────────▼──────────┐   ┌──────────▼──────────┐
│  ERP Imobiliario     │   │  Personal Finance    │
│  Clients · Properties│   │  Accounts · Budgets  │
│  Matching · AI       │   │  Portfolios · Reports│
│  FastAPI :8001       │   │  FastAPI :8002        │
│  React :8080         │   │  React :8090          │
└──────────┬───────────┘   └──────────┬───────────┘
           │                          │
    ┌──────▼──────────────────────────▼──────┐
    │              Supabase                   │
    │  PostgreSQL · RLS per org · Storage     │
    │  Schemas: public | erp | personal-finance│
    └──────────┬─────────────────────────────┘
               │
    ┌──────────▼──────────────────────────────┐
    │           External Services              │
    │  OpenAI · WAHA · n8n · Stripe · yfinance│
    └─────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI |
| Frontend | React 18 + TypeScript + Vite |
| Database | Supabase (PostgreSQL + RLS) |
| Styling | Tailwind CSS + shadcn/ui |
| Server State | TanStack Query (ERP, PF), React Context (Core) |
| Client State | Zustand (ERP, PF), React Context (Core) |
| Auth | Supabase Auth + JWT + SSO tokens |
| AI | OpenAI GPT-4o-mini + text-embedding-3-small |
| Messaging | WAHA (WhatsApp HTTP API) |
| Orchestration | n8n (self-hosted) |
| Billing | Stripe |

---

## Tenant Isolation

- Every user belongs to exactly one organization (`noctus_users.org_id`)
- Supabase RLS policies scope all data queries to the user's `org_id`
- Admin operations use `get_admin_client()` (service role key, bypasses RLS)
- User operations use `get_user_client(token)` (respects RLS)

---

## Shared Infrastructure

- **Single root `.env`** — All backends read from one `.env` at repo root via absolute path in `config.py`
- **Single root `venv/`** — Shared Python virtual environment, `requirements.txt` at root
- **Shared backend package** (`shared/backend/noctusai_shared/`) — Exceptions, responses, middleware, logging, config, database, app factory (installed via `pip install -e shared/backend`)
- **Shared frontend package** (`shared/frontend/src/`) — API client factory, auth hook, store factories, CRUD hook factory, utilities, shared components (consumed via Vite `@shared/*` alias)
- **Per-backend `requirements.txt`** — Kept for independent Docker deploys
- **Frontend env** — `VITE_`-prefixed vars in per-frontend `.env` files (end up in browser bundles)

---

## External Services

| Service | URL | Purpose |
|---------|-----|---------|
| Supabase | `*.supabase.co` | Database, auth, storage |
| n8n | `n8n.noctusai.com` | Agentic workflow orchestration |
| WAHA | `waha.noctusai.com` | WhatsApp messaging API |
| OpenAI | `api.openai.com` | AI descriptions, embeddings, lead scoring |
| Stripe | `api.stripe.com` | Billing, subscriptions, checkout |

---

## Testing Strategy

**Dual-layer testing**: Mock-based unit tests for speed (2,196 tests: Core 299, ERP 1,432, PF 465) + real-DB integration tests (~25 tests per backend) for confidence. Mock tests use `MockSupabaseClient` and run without credentials. Real-DB tests in `tests/realdb/` hit a live Supabase instance to verify SQL filtering, FK/CHECK constraints, cascade deletes, PostgREST errors, and RLS org isolation — auto-skip without credentials.

## Legacy Data Migration (`migratingDB/`)

SQL scripts for migrating data from the old Django-based permutas platform into the ERP's `erp.ativos`, `erp.clientes`, and `erp.condominios` tables. Run manually in Supabase SQL Editor — not part of application deploys.

| Phase | Files | What it does |
|-------|-------|--------------|
| **Phase 1** (import) | `01_setup_staging.sql` → `04_validate.sql` | Creates staging tables, loads 264 imóveis + 13 permutas + interests, transforms into `erp.ativos` with placeholder clientes/condominios and JSONB interesses, validates |
| **Phase 2** (correct & enrich) | `05_second_migration.sql` | Single-transaction monolith: corrects tipo_imovel/zona mappings on ativos and inside JSONB interesses, replaces placeholder corretor/proprietário/condomínio names with real data from lookup tables, propagates location from condominios to ativos |

**Migrated record markers**: `titulo_anuncio LIKE '[MOCK]%'` (imóveis), `observacoes LIKE '%MIGRADO%'` (clientes/condominios), `[MIGRADO-ENRIQUECIDO]` (Phase 2 enriched records).

**Post-migration TODOs**: Update `titulo_anuncio` (remove `[MOCK]`), add fotos, complete missing emails, generate embeddings for AI matching.

---

## Language Convention

- **Portuguese (Brazilian)** for business domain: clientes, metas, ativos, funil, permutas, comissoes
- **English** for technical/framework concepts: routers, services, hooks, stores
- **Error messages** returned to users are in Portuguese
