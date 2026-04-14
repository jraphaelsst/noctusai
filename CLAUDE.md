# CLAUDE.md

## Engineering Philosophy

- **No workarounds.** Always use the real API/SDK/framework. No monkeypatches, shims, or hacks.
- **DRY.** Single authoritative source for every piece of logic. Three similar blocks → extract to shared.
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

**Full catalog**: `KNOWLEDGE-BASE/CONTEXT/07-SHARED-LIBRARY.md` — check before building anything.

**Backend** (`noctusai_shared`): auth (SSO role resolution, context), roles (7-role hierarchy), invitations (token-based team invites), email_templates (Resend-powered), notifications (field mapping), page_status (dev-gated pages), responses, exceptions, middleware, logging, database, config, app_factory, testing (MockSupabaseClient, MockUser, AuthClient).

**Frontend** (`@noctusai/shared`): api (createApiClient + 401 retry), sso (resolveSSORoles, resolveSSOContext), roles (ORG_ROLE_LABELS, isDevOrOwner), page-status (usePageStatus, filterNavByPageStatus), auth, stores, hooks, notifications, supabase (createProductSupabase), components (SSOCallback, createAuthProvider).

**Design System** (`@noctusai/shared/design-system`): AppShell, Sidebar, Header, NotificationBell, LoginForm, AcceptInvitePage, ForgotPasswordPage, PageSkeleton, InactivityWarning, useTheme, useActivityRefresh, tokens.css, tailwind.config.base.ts.

> `get_current_user` is NOT shared — lives in each product's `dependencies.py` for test mock compatibility.

### Product Layout Pattern

One `Layout.tsx` per product. Imports shared AppShell + Sidebar + Header + useTheme. Nav data switched by role (no separate layout files). SSO users get BackToCore link + redirect logout. Page visibility filtered by `usePageStatus` + `filterNavByPageStatus`.

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
