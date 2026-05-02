# Agent Context — Read This First

> This file exists for AI agents starting a fresh session with zero prior context.
> Read this before doing anything. It tells you what exists, where to look, and how to behave.

## What is NoctusAI?

Multi-tenant, multi-product SaaS platform. FastAPI + Supabase backend, React + TypeScript + Vite frontend. **7 products**, 1 seed framework, 1 MCP dev toolkit. (AdConnect is a WIP scaffold at `products/adconnect/`, currently gitignored and not part of the live platform.)

## The Seed (most important concept)

Everything inherits from `seed/`. The seed has two layers:
- `seed/backend/lib/` (`noctusai_lib`) — reusable code: auth, roles, invitations, email, testing
- `seed/backend/framework/` (`noctusai_seed`) — structural framework: `create_product_app()`, `ProductSettings`, standard routers
- `seed/frontend/lib/` (`@noctusai/lib`) — reusable code: api, sso, roles, hooks, design system
- `seed/frontend/framework/` (`@noctusai/seed`) — structural framework: `createProductApp()`, `createProductLayout()`, `createProductInfra()`, `createViteConfig()`

Products IMPORT from the seed. They never duplicate it. Read `seed/README.md` for the full architecture.

## Products

| Product | Schema | Backend | Frontend | Status |
|---------|--------|---------|----------|--------|
| Core | `public` | 8000 | 5173 | Platform hub, auth, billing |
| ERP Imobiliario | `erp` | 8001 | 8080 | Real estate CRM |
| Personal Finance | `personal-finance` | 8002 | 8090 | Financial management |
| Therapy Platform | `therapy` | 8003 | 8095 | Online therapy |
| Seed | `seed` | 8004 | 8100 | Reference implementation (inactive) |
| Daily Life | `daily_life` | 8005 | 8110 | Personal productivity |
| Mailing | `mailing` | 8006 | 8120 | Email marketing & automations |

Products are registered in `public.products` table (Supabase). The Core dashboard reads from this table dynamically.

Each product has: `README.md` + `MASTER-PROMPT.md` (read these before modifying a product).

## How a product is structured

### Backend (10 lines of structural code)
```
products/<name>/backend/app/
  main.py          → create_product_app(name, schema, settings, routers)
  config.py        → MySettings(ProductSettings)
  database.py      → create_database_module(settings, schema)
  dependencies.py  → create_dependencies(db)
  routers/         → domain routers only (health/team/notificacoes come from framework)
  services/        → domain business logic
  schemas/         → Pydantic models
```

### Frontend (zero boilerplate)
```
products/<name>/frontend/src/
  App.tsx           → createProductApp({ routes, Layout, ...infra.appConfig })
  vite.config.ts    → createViteConfig({ port }) — 3 lines
  pages/            → domain pages (hooks import from @noctusai/seed/infra)
  hooks/            → domain hooks (one per entity, NEVER inline in pages)
```

Infrastructure (supabase, auth, api, notifications) comes from `@noctusai/seed/infra`. Products don't create their own.

## Environment

Single root `.env` for everything. Backend vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, etc. Frontend vars: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, etc. Product-specific vars (`VITE_BACKEND_API_URL`, `VITE_PRODUCT_SCHEMA`) are injected by `createViteConfig()` — never in `.env`.

## MCP Dev Toolkit

<!-- kb-counts:start:agent_context_tools -->
50 tools
<!-- kb-counts:end:agent_context_tools --> exposed as an MCP server at `mcp/noctusai/`. CLI wrapper for humans:

```bash
python mcp/noctusai/cli.py --validate   # Check compliance
python mcp/noctusai/cli.py --review     # Observation-only review — LLM-authored proposals, NEVER edits code
python mcp/noctusai/cli.py --analyze    # Find improvements
python mcp/noctusai/cli.py --discover   # AI-powered discovery
python mcp/noctusai/cli.py --metrics    # Platform metrics
python mcp/noctusai/cli.py --test       # Run tests
python mcp/noctusai/cli.py --build      # Build frontends
python mcp/noctusai/cli.py --proposals  # List proposals
```

Keeper/compliance proposals go to `products/<product>/proposals/`. Project-phase proposals go to `projects/<slug>/proposals/` or `products/<product>/projects/<slug>/proposals/`.

## Rules (read CLAUDE.md for full list)

The top rules you MUST follow:
1. **Seed first** — always use the seed framework. Never duplicate structural code.
2. **No incomplete commits** — backend and frontend must be at same maturity.
3. **No quick fixes** — solve root causes in one place, not symptoms in many.
4. **Hooks in dedicated files** — never inline useQuery/useMutation in pages.
5. **MCP toolkit reviews after changes (observation-only)** — run `python mcp/noctusai/cli.py --review` before committing. Never modifies code; files LLM-authored proposals you triage manually.
6. **Extend framework, never go custom** — if the framework can't handle a product's needs, extend it.
7. **Docs stay in sync** — every change updates CLAUDE.md / KNOWLEDGE-BASE / MCP server README.

## Where to find what

For the full catalog, open **`KNOWLEDGE-BASE/INDEX.md`** — it lists every KB file with a one-line description.

Quick pointers:

| Need to know... | Read... |
|-----------------|---------|
| Engineering rules (behavioral) | `CLAUDE.md` |
| Engineering philosophy (elaborated) | `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md` |
| Platform landscape (products, ports, schemas) | `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` |
| Seed architecture (factories, layers) | `KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md` |
| Shared library catalog | `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` |
| Infrastructure (ports, deploy) | `KNOWLEDGE-BASE/CONTEXT/05-INFRASTRUCTURE.md` |
| MCP dev toolkit (observation-only review) | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| Gamification philosophy | `KNOWLEDGE-BASE/CONTEXT/07-GAMIFICATION.md` |
| Backend patterns | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend.md` |
| Frontend patterns | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/frontend.md` |
| Testing discipline | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/testing.md` |
| DB + RLS patterns | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md` |
| Env / `.env` conventions | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/environment.md` |
| Notifications pattern | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/notifications.md` |
| First-time setup | `KNOWLEDGE-BASE/CONTEXT/GUIDES/setup.md` |
| Creating a new product | `KNOWLEDGE-BASE/CONTEXT/GUIDES/new-product.md` |
| Product details | `products/<name>/MASTER-PROMPT.md` |
| Scripts & setup scripts | `scripts/README.md` |

## What NOT to do

- Don't create per-product `.env` files (single root `.env`)
- Don't create authStore.ts, ErrorBoundary.tsx, NotificationBell.tsx, etc. (framework provides via `@noctusai/seed/infra`)
- Don't create health.py, notificacoes.py, team.py routers (framework provides via `create_product_app()`)
- Don't inline hooks in page components (always extract to `hooks/useEntity.ts`)
- Don't commit without running `python mcp/noctusai/cli.py --review` and triaging any new proposals
- Don't add secret keys with `VITE_` prefix (Vite exposes them to the browser)
