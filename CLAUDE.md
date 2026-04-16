# CLAUDE.md

## Engineering Philosophy

- **Seed first. Always.** Every product inherits its structural backbone from `seed/`. When creating a new product, import `create_product_app()` (backend) and `createProductApp()` / `createProductLayout()` (frontend) from the seed framework. Do NOT copy-paste structural code. Do NOT re-implement auth, routing, layout, database clients, health checks, team management, or notifications — they come from the seed. This is not optional, not debatable, not a suggestion. The seed is the skeleton. Products are the organs. Read `seed/README.md` before building anything.
- **Keeper heals after every change.** After modifying code, run `python -m agents.keeper --heal` on the affected product. The Keeper detects issues, auto-fixes deterministic ones, creates proposals for non-deterministic ones, re-runs to verify, and repeats until clean. No code ships with known violations. Development loop: change → `python -m agents.keeper --heal --product <name>` → commit.
- **No incomplete commits.** Never commit a product with mismatched maturity between backend and frontend. If the backend has working endpoints, the frontend must have real pages wired to those endpoints — not placeholders. "Scaffolded" is not "complete." Both sides must be at the same level before committing. If one side is incomplete, flag it to the user before committing.
- **No quick fixes.** Never patch symptoms. If your fix requires touching multiple products for the same reason, you're fixing a symptom, not the root cause. Step back. The fix belongs in one place (seed, lib, or a shared config) and propagates automatically. Spend 30 minutes on a proper solution over 5 minutes on a hack that creates future work. Infrastructure before features, root cause before symptoms.
- **No workarounds.** Always use the real API/SDK/framework. No monkeypatches, shims, or hacks.
- **DRY.** Single authoritative source for every piece of logic. Three similar blocks → extract to shared.
- **Componentize everything.** When you build something a product needs, ask: "will another product need this?" If yes (or maybe), build it as a shared component from the start. Check `KNOWLEDGE-BASE/CONTEXT/07-SHARED-LIBRARY.md` before writing anything — it might already exist. The shared library is the platform's validated, reusable code. Every extraction reduces maintenance burden as the platform grows. Duplicate code is tech debt; shared components are assets.
- **Module-scope imports.** All Python imports go at the top of the file (module scope). Never defer imports to inside functions or after object creation unless solving a documented circular dependency. Module-scope imports fail fast at startup, making bugs visible immediately.
- **Docs stay in sync.** Every commit updates `CLAUDE.md` and `KNOWLEDGE-BASE/`. Every agent must have an up-to-date `README.md`. When an agent's behavior changes, its README updates in the same commit. Proposals from all agents live in `agents/proposals/`.
- **`KNOWLEDGE-BASE/`** = platform context (architecture, inventories). `CLAUDE.md` = behavioral rules.
- **Every product has a `README.md` and `MASTER-PROMPT.md`.** README explains what the product does. MASTER-PROMPT is the authoritative development guide (purpose, architecture, domains, testing, dependencies). New products must include both from day one.

## Architecture

Multi-tenant, multi-product SaaS monorepo. Stack: **FastAPI + Supabase** backend, **React + TypeScript + Vite** frontend. Tenant isolation via RLS.

| Product | Schema | Ports | Tenant key | Auth |
|---------|--------|-------|------------|------|
| **Core** (`core/`) | `public` | 8000/5173 | `org_id` | Custom REST API |
| **ERP** (`products/erp-imobiliario/`) | `erp` | 8001/8080 | `org_id` | SSO + direct login |
| **PF** (`products/personal-finance/`) | `personal-finance` | 8002/8090 | `org_id` | SSO + direct login |
| **Therapy** (`products/therapy-platform/`) | `therapy` | 8003/8095 | `clinic_id` | Direct Supabase Auth |
| **Seed** (`products/seed/`) | `seed` | 8004/8100 | `org_id` | SSO + direct login |
| **Daily Life** (`products/daily-life/`) | `daily_life` | 8005/8110 | `org_id` | SSO + direct login |
| **Mailing** (`products/mailing/`) | `mailing` | 8006/8120 | `org_id` | SSO + direct login |

Per-product docs: `KNOWLEDGE-BASE/CONTEXT/backend/01-CORE.md`, `02-ERP.md`, `03-PF.md`, `06-THERAPY.md`, `08-DAILY-LIFE.md`.

### Backend: `routers/ → services/ → schemas/` + `dependencies.py`, `database.py`
### Frontend: `pages/ → components/ → hooks/ → store/ → lib/`

State: **Zustand** (global UI), **TanStack Query** (server state).

### The Seed — Spine of Every Product

**`seed/` is the structural foundation. Every product inherits from it. Change the seed, change all products.**

Read `seed/README.md` for the full architecture. The seed has two layers:

| Layer | Package | Location | Purpose |
|-------|---------|----------|---------|
| **Shared Library** | `noctusai_lib` / `@noctusai/lib` | `seed/lib/` | Reusable code (auth, roles, hooks, components, utils) |
| **Framework** | `noctusai_seed` / `@noctusai/seed` | `seed/framework/` | Structural bones (app factory, database, deps, routing) |

Products import from both. Domain-specific code lives in the product only. **Never duplicate seed code in a product.**

- **Backend framework**: `create_product_app(name, schema, settings, routers)` → fully configured FastAPI app with health, team, notifications, CORS, Sentry, logging, JWT built in.
- **Frontend framework**: `createProductApp(config)` → full App with routing, auth, providers, TooltipProvider. `createProductLayout(config)` → Layout with sidebar, header, page status, SSO.

**Full shared library catalog**: `KNOWLEDGE-BASE/CONTEXT/07-SHARED-LIBRARY.md` — **always check before building anything**.

## Setup

**After cloning**: `bash scripts/setup.sh` — installs git hooks, venv, all deps. Run once.
**Start servers**: `bash start.sh` or `uvicorn app.main:app --reload --port <PORT> --app-dir <backend>`
**Tests**: `cd <product>/backend && pytest`

## Testing Standards

Every product must have three test layers. No product ships without all three.

| Layer | What it tests | Where | When to write |
|-------|-------------|-------|---------------|
| **Unit** (routers) | Individual endpoints — CRUD, auth, validation, error handling | `tests/routers/test_*.py` | One per domain router |
| **Unit** (services) | Business logic in isolation — calculations, transformations, state machines | `tests/services/test_*.py` | One per service with non-trivial logic |
| **Integration** | Cross-service flows — campaign references template + list, automation enrolls contacts | `tests/integration/test_*.py` | When entities reference each other |
| **E2E** | Full user journeys — create contact → template → campaign → send → verify stats | `tests/integration/test_e2e_flows.py` | One per product, covers the golden path |

Rules:
- **Unit tests**: mock the database (`MockSupabaseClient`). Test one endpoint at a time.
- **Integration tests**: mock the database but test multi-step flows where step N depends on step N-1.
- **E2E tests**: simulate a real user journey through multiple endpoints. Each test is a story.
- **All tests must be deterministic**: no hardcoded dates (use `date.today()`), no external API calls, no network.
- **Auth boundary tests**: every product must verify that unauthenticated requests return 401 for all protected endpoints.
**Scripts**: `scripts/README.md` documents all scripts and git hooks. Key: `setup.sh` (first-time), `sync-seed-template.sh` (seed→template auto-sync, runs via post-commit hook).

## Environment

**Single root `.env` for everything** — backends AND frontends. No per-product `.env` files.

Backend vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `JWT_SECRET`, `RESEND_API_KEY`.
Frontend vars: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, `VITE_CORE_URL`, `VITE_CORE_API_URL`.

The `createViteConfig()` factory sets `envDir` to the repo root so all frontends read from the same `.env`. Product-specific vars (`VITE_BACKEND_API_URL`) are injected by the factory based on the port config — never in `.env`.

**Rule: VITE_ prefix = public only.** Vite embeds all VITE_ vars in the client JS bundle. Never add secret keys with the VITE_ prefix. Use non-prefixed vars for secrets (they stay server-side).

## Backend Patterns

- **Auth**: `await get_current_user(authorization)` → `(user, token)`. Core admin: `get_current_admin()`.
- **SSO**: `resolve_sso_role(user)` checks `org_role` (owner/admin → platform_admin) then `noctus_role` (admin → platform_admin). Frontend: `resolveSSORoles()` → `{ isSSO, isProductAdmin }`.
- **7-role hierarchy**: owner, admin, manager, member, viewer, dev, test. Constants in `noctusai_lib/roles.py`. Dev/owner see in-development pages. Admin/owner manage team+billing.
- **Page status**: `status_pagina` table per schema (producao/desenvolvimento/desativado). `usePageStatus()` + `filterNavByPageStatus()` on frontend.
- **Invitations**: `noctusai_lib/invitations.py` — create_invitation, validate, accept, cancel. Email via `send_product_invitation_email()`. Each product has `routers/team.py`. Therapy extends with invite types + binding.
- **Responses**: paginated_response / success_response / ok_response.
- **N+1 zero tolerance**: `.in_("id", ids)` for reads, `.insert(rows)` for batch writes. Never loop `db.table()`.
- **Router → Service**: Business logic in services. Routers are thin.
- **RLS**: All schemas use `(SELECT auth.uid())` pattern. Functions include `SET search_path`. Service role bypasses via `get_admin_client()`.
- **Provisioning**: `on_license_change` trigger auto-provisions product defaults.

## Frontend Patterns

- **Mobile-first 3-tier**: base → `sm:`/`md:` → `lg:`/`xl:`. Test at 375/768/1440px.
- **Toasts**: `sonner` only. **Constants**: `lib/constants.ts`. **Utils**: `lib/utils.ts`.
- **TanStack Query**: `enabled: !!user`, appropriate `staleTime`, correct `invalidateQueries`.
- **Hooks in dedicated files, always.** Every domain entity gets its own hook file (`hooks/useContacts.ts`, `hooks/useCampaigns.ts`). Never inline hooks in page components, even for simple products. Products grow — extracted hooks are ready when a second page needs the same data. No refactoring needed.
- **Token refresh**: `useActivityRefresh` (proactive) + `onTokenExpired` in api-client (reactive 401 retry).

## Notifications

Platform concern — `public.notifications` table. Product routers at `/api/notificacoes` proxy via `get_core_client()` with `map_notification_to_pt()`. Frontend: shared `NotificationBell` component.

## Database & RLS

143+ tables across 5 schemas, all RLS-enabled. Rules: `(SELECT auth.uid())` not bare, `SET search_path` on all functions, HaveIBeenPwned enabled.

## Creating a New Product

Products are born from the seed. The backend `main.py` imports `create_product_app()` from `noctusai_seed`. The frontend `App.tsx` imports `createProductApp()` from `@noctusai/seed`. Products only add domain-specific routers, services, pages, and components.

**New product checklist** (mandatory files from day one):
1. `README.md` — what the product does, stack, ports, features
2. `MASTER-PROMPT.md` — authoritative development guide
3. `frontend/.env.example` — all required `VITE_` vars with placeholders
4. `backend/migrations/001_<schema>.sql` — full schema with RLS
5. Registration in `start.sh` with backend + frontend blocks
6. `backend/app/main.py` — uses `create_product_app()` from seed framework
7. `frontend/src/App.tsx` — uses `createProductApp()` from seed framework

The `products/seed/` directory is the **reference implementation** — the simplest possible product, just the spine with no domain code. The template at `templates/product-seed/` is auto-generated from it via `scripts/sync-seed-template.sh`.
