# CLAUDE.md

## Engineering Philosophy

- **No workarounds.** Always use the real API/SDK/framework. No monkeypatches, shims, or hacks.
- **DRY.** Single authoritative source for every piece of logic. Three similar blocks → extract to shared.
- **Componentize everything.** When you build something a product needs, ask: "will another product need this?" If yes (or maybe), build it as a shared component from the start. Check `KNOWLEDGE-BASE/CONTEXT/07-SHARED-LIBRARY.md` before writing anything — it might already exist. The shared library is the platform's validated, reusable code. Every extraction reduces maintenance burden as the platform grows. Duplicate code is tech debt; shared components are assets.
- **Module-scope imports.** All Python imports go at the top of the file (module scope). Never defer imports to inside functions or after object creation unless solving a documented circular dependency. Module-scope imports fail fast at startup, making bugs visible immediately.
- **Docs stay in sync.** Every commit updates `CLAUDE.md` and `KNOWLEDGE-BASE/`.
- **`KNOWLEDGE-BASE/`** = platform context (architecture, inventories). `CLAUDE.md` = behavioral rules.

## Architecture

Multi-tenant, multi-product SaaS monorepo. Stack: **FastAPI + Supabase** backend, **React + TypeScript + Vite** frontend. Tenant isolation via RLS.

| Product | Schema | Ports | Tenant key | Auth |
|---------|--------|-------|------------|------|
| **Core** (`core/`) | `public` | 8000/5173 | `org_id` | Custom REST API |
| **ERP** (`products/erp-imobiliario/`) | `erp` | 8001/8080 | `org_id` | SSO + direct login |
| **PF** (`products/personal-finance/`) | `personal-finance` | 8002/8090 | `org_id` | SSO + direct login |
| **Therapy** (`products/therapy-platform/`) | `therapy` | 8003/8095 | `clinic_id` | Direct Supabase Auth |

Per-product docs: `KNOWLEDGE-BASE/CONTEXT/backend/01-CORE.md`, `02-ERP.md`, `03-PF.md`, `06-THERAPY.md`.

### Backend: `routers/ → services/ → schemas/` + `dependencies.py`, `database.py`
### Frontend: `pages/ → components/ → hooks/ → store/ → lib/`

State: **Zustand** (global UI), **TanStack Query** (server state).

### Shared Packages

**Full catalog**: `KNOWLEDGE-BASE/CONTEXT/07-SHARED-LIBRARY.md` — **always check before building anything**.

- **Backend** (`noctusai_shared`): auth, roles, invitations, email_templates, notifications, page_status, responses, exceptions, middleware, logging, database, config, app_factory, testing.
- **Frontend** (`@noctusai/shared`): api, sso, roles, page-status, auth, stores, hooks, notifications, supabase, components.
- **Design System** (`@noctusai/shared/design-system`): AppShell, Sidebar, Header, NotificationBell, LoginForm, AcceptInvitePage, ForgotPasswordPage, PageSkeleton, InactivityWarning, useTheme, tokens.css.

> `get_current_user` is NOT shared — lives in each product's `dependencies.py` for test mock compatibility.

### Product Layout Pattern

One `Layout.tsx` per product using shared AppShell + Sidebar + Header. Nav switched by role. SSO users get BackToCore + redirect logout. Pages filtered by `usePageStatus` + `filterNavByPageStatus`.

## Setup

**Venv**: `python3.11 -m venv venv && pip install -r requirements.txt && pip install -e shared/backend`
**Servers**: `bash start.sh` or `uvicorn app.main:app --reload --port <PORT> --app-dir <backend>`
**Tests**: `cd <product>/backend && pytest` — 3,653 total (410 core, 1661 ERP, 502 PF, 1080 therapy). Integration e2e tests in `tests/integration/`.

## Environment

Single root `.env` for all backends. `VITE_`-prefixed vars per frontend.
Key: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `JWT_SECRET`, `RESEND_API_KEY`.

## Backend Patterns

- **Auth**: `await get_current_user(authorization)` → `(user, token)`. Core admin: `get_current_admin()`.
- **SSO**: `resolve_sso_role(user)` checks `org_role` (owner/admin → platform_admin) then `noctus_role` (admin → platform_admin). Frontend: `resolveSSORoles()` → `{ isSSO, isProductAdmin }`.
- **7-role hierarchy**: owner, admin, manager, member, viewer, dev, test. Constants in `noctusai_shared/roles.py`. Dev/owner see in-development pages. Admin/owner manage team+billing.
- **Page status**: `status_pagina` table per schema (producao/desenvolvimento/desativado). `usePageStatus()` + `filterNavByPageStatus()` on frontend.
- **Invitations**: `noctusai_shared/invitations.py` — create_invitation, validate, accept, cancel. Email via `send_product_invitation_email()`. Each product has `routers/team.py`. Therapy extends with invite types + binding.
- **Responses**: paginated_response / success_response / ok_response.
- **N+1 zero tolerance**: `.in_("id", ids)` for reads, `.insert(rows)` for batch writes. Never loop `db.table()`.
- **Router → Service**: Business logic in services. Routers are thin.
- **RLS**: All schemas use `(SELECT auth.uid())` pattern. Functions include `SET search_path`. Service role bypasses via `get_admin_client()`.
- **Provisioning**: `on_license_change` trigger auto-provisions product defaults.

## Frontend Patterns

- **Mobile-first 3-tier**: base → `sm:`/`md:` → `lg:`/`xl:`. Test at 375/768/1440px.
- **Toasts**: `sonner` only. **Constants**: `lib/constants.ts`. **Utils**: `lib/utils.ts`.
- **TanStack Query**: `enabled: !!user`, appropriate `staleTime`, correct `invalidateQueries`.
- **Token refresh**: `useActivityRefresh` (proactive) + `onTokenExpired` in api-client (reactive 401 retry).

## Notifications

Platform concern — `public.notifications` table. Product routers at `/api/notificacoes` proxy via `get_core_client()` with `map_notification_to_pt()`. Frontend: shared `NotificationBell` component.

## Database & RLS

129+ tables across 4 schemas, all RLS-enabled. Rules: `(SELECT auth.uid())` not bare, `SET search_path` on all functions, HaveIBeenPwned enabled.

## Creating a New Product

Copy `templates/product-seed/`, replace placeholders, install deps, run migrations, register product. Seed provides: shared app_factory, config, database, dependencies with SSO role resolution, notifications, team invitations template, Layout with page status, LoginForm, AcceptInvite, ForgotPassword, NotificationBell, tests.
