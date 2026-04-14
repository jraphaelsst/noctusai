# CLAUDE.md

## Engineering Philosophy

- **No workarounds. Ever.** Always use the real API/SDK/framework. Monkeypatches, shims, hacks are never acceptable.
- **DRY.** Every piece of logic has a single authoritative source. If two files need the same function, it belongs in a shared module. Three similar blocks → extract and reuse.
- **Docs stay in sync.** Every commit updates `CLAUDE.md` and `KNOWLEDGE-BASE/` to reflect changes.
- **`KNOWLEDGE-BASE/`** = persistent platform context (architecture, inventories, domain knowledge). `CLAUDE.md` = behavioral rules. See `KNOWLEDGE-BASE/CONTEXT/00-LANDSCAPE.md` for the full overview.

## Architecture

Multi-tenant, multi-product SaaS monorepo. Orgs sign up on Core, get licensed products. Tenant isolation via Supabase RLS on `org_id`. Stack: **FastAPI + Supabase** backend, **React + TypeScript + Vite** frontend.

| Product | Routers | Services | Schema | Ports | Tenant key | Details |
|---------|---------|----------|--------|-------|------------|---------|
| **Core** (`core/`) | 23 | 9 | `public` | 8000/5173 | `org_id` | Auth, orgs, products, licenses, SSO, notifications, webhooks, audit, settings |
| **ERP** (`products/erp-imobiliario/`) | 50 | 42 | `erp` | 8001/8080 | `org_id` | Real estate CRM, sales funnel, AI matching, WhatsApp, digital signatures |
| **PF** (`products/personal-finance/`) | 16 | 14 | `personal-finance` | 8002/8090 | `org_id` | Accounts, transactions, budgets, portfolios, watchlists |
| **Therapy** (`products/therapy-platform/`) | 39 | 38 | `therapy` | 8003/8095 | `clinic_id` | 4 roles (platform_admin, clinic_admin, therapist, patient), video sessions, clinical AI, Stripe Connect. Direct Supabase Auth (NOT NoctusAI SSO) |

Per-product docs: `KNOWLEDGE-BASE/CONTEXT/backend/01-CORE.md`, `02-ERP.md`, `03-PF.md`, `06-THERAPY.md`.

### Backend Layers

```
routers/      → Thin HTTP handlers (auth + validation + delegation)
services/     → Business logic
schemas/      → Pydantic request/response models
dependencies.py → get_current_user, get_user_client, get_admin_client, get_org_id, resolve_sso_role
database.py   → Supabase client singleton
```

`get_user_client(token)` respects RLS; `get_admin_client()` uses service role.

### Frontend Layers

```
pages/ → Route components   components/ → UI (shadcn/ui + domain)   hooks/ → TanStack Query
store/ → Zustand stores     lib/ → API client, utils, constants      types/ → TypeScript defs
```

State: **Zustand** (global UI), **TanStack Query** (server state).

### Shared Packages

**Full catalog with usage examples**: `KNOWLEDGE-BASE/CONTEXT/07-SHARED-LIBRARY.md`. Before building anything, check if it already exists there.

**Backend** (`noctusai_shared`) — `pip install -e shared/backend`:
`auth.py` (resolve_sso_role, get_sso_context, require_role, first_or_none), `notifications.py` (map_notification_to_pt/from_pt), `responses.py`, `exceptions.py`, `middleware.py`, `logging_config.py`, `database.py`, `config.py`, `app_factory.py`, `testing/` (MockSupabaseClient, MockUser, AuthClient — all products import from here).

> `get_current_user` is NOT shared — lives in each product's `dependencies.py` for test mock compatibility.

**Frontend** (`@noctusai/shared`):
`api.ts` (createApiClient), `sso.ts` (resolveSSORoles, resolveSSOContext, isTrial, licenseDaysRemaining), `auth.ts` (useSupabaseAuthInit), `stores.ts` (createAuthStore), `hooks.ts` (createCrudHooks), `notifications.ts` (createNotificationHooks), `supabase.ts` (createProductSupabase), `utils.ts`, `components/` (SSOCallback, createAuthProvider, ErrorBoundary).

**Design System** (`@noctusai/shared/design-system`):
Layout: `AppShell`, `Sidebar`, `Header`. UI: `NotificationBell`, `LoginForm`, `PageSkeleton`, `InactivityWarning`, `HoverCard`. Hooks: `useTheme`, `useActivityRefresh`. Styling: `tokens.css`, `tailwind.config.base.ts`.

Principles: One change affects all products. Products customize via props, not forks. Mobile-first 3-tier responsive (375px → 768px → 1440px).

### Product Layout Pattern (mandatory)

Every product has ONE `components/layout/Layout.tsx`:
1. Imports AppShell + Sidebar + Header + useTheme + useActivityRefresh from shared design-system
2. Imports `resolveSSORoles` from `@noctusai/shared` for SSO admin detection
3. Static NAV_GROUPS switched by user role (no separate layout files)
4. AppShell → Sidebar(brand + navGroups + BackToCore footer) + Header(user + theme + NotificationBell)
5. Products: `logoutBehavior="redirect"` + BackToCore. Core: `logoutBehavior="signout"`.

No local Sidebar/Header wrappers. No AdminLayout/UserLayout split. Role branching via nav data switching inside one file. Exception: `PublicLayout.tsx` for unauthenticated pages.

## Setup & Commands

**Venv**: Single root `venv/` (Python 3.11+). `pip install -r requirements.txt && pip install -e shared/backend`.

**Servers**: `bash start.sh` for everything, or individually:
- Core: `uvicorn app.main:app --reload --port 8000 --app-dir core/backend`
- ERP: `uvicorn app.main:app --reload --port 8001 --app-dir products/erp-imobiliario/backend`
- PF: `uvicorn app.main:app --reload --port 8002 --app-dir products/personal-finance/backend`
- Therapy: `uvicorn app.main:app --reload --port 8003 --app-dir products/therapy-platform/backend`
- Frontends: `cd <product>/frontend && npm run dev`

**Tests**: `cd <product>/backend && pytest` — all mocked via `MockSupabaseClient` in `conftest.py`.
Totals: 394 core, 1636 ERP, 473 PF, 1039 therapy (~3,542). Real-DB tests in `tests/realdb/` (auto-skip without env vars).

## Environment Variables

All backends read from **single root `.env`**. Frontends use `VITE_`-prefixed vars in their own `.env`.

Key vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `JWT_SECRET`, `CORS_ORIGINS`, `DEBUG`, `CORE_API_URL`. Optional: `SENTRY_DSN`, `REDIS_URL`, `OPENAI_API_KEY`, `RESEND_API_KEY`, `CLICKSIGN_API_TOKEN`. Therapy-specific: `THERAPY_LIVEKIT_*`, `THERAPY_GOOGLE_*`, `THERAPY_STRIPE_CONNECT_CLIENT_ID`.

## Backend Patterns

- **Auth**: `authorization: Optional[str] = Header(None)` → `await get_current_user(authorization)` → `(user, token)`. Core admin: `await get_current_admin(authorization)` (verifies `noctus_users.role == "admin"`).
- **SSO role resolution**: Every product's `get_user_role()` calls `resolve_sso_role(user)` from `noctusai_shared.auth` first. Checks `user_metadata.org_role` (owner/admin → `platform_admin`) then `noctus_role` (admin → `platform_admin`), then falls through to product-specific roles. SSO token carries: `sub`, `org_id`, `product`, `email`, `role`, `org_role`. Core `/api/sso/session` syncs both into `user_metadata`. Frontend: `resolveSSORoles(metadata)` → `{ isSSO, isProductAdmin }`.
- **Org ID**: `get_org_id(user)` from `dependencies.py`. Never inline `user.user_metadata.get("org_id")`.
- **Responses**: Lists → `paginated_response(data, total, page, page_size)`. Singles → `success_response(data)`. Deletes → `ok_response(message)`.
- **Pagination**: `page` + `page_size` params via Supabase `.range()`.
- **DELETE pre-checks**: Verify record exists before deletion. 404 if not found.
- **Server-side search**: `busca` param → `.or_()` with `ilike` BEFORE pagination. Never filter in Python.
- **Rate limiting**: `@limiter.limit("30/minute")` from `app.rate_limit` on public/AI endpoints.
- **N+1 zero tolerance**: Every multi-row DB op MUST be batched. Reads: `.in_("id", ids)`. Inserts: `.insert(rows)`. Updates: `.update(data).in_("id", ids)`. Enrichment: `.in_()` + lookup dict. If a loop contains `db.table(...)`, it's almost certainly a bug.
- **Router → Service**: Business logic in services. Routers are thin (auth + validation + delegation).
- **Validation**: Pydantic `Field()` constraints + `Literal` types for enums.
- **Error handling**: `HTTPException` for simple, `AppException` subclasses for structured. `postgrest_exception_handler` catches `PGRST116` → 404.
- **Logging**: Structured JSON (prod) / human-readable (dev). Correlation ID per request.
- **Security defaults**: `debug=False`, `jwt_secret` placeholder triggers prod error. Docs disabled when `not debug`. HaveIBeenPwned leak protection enabled.
- **RLS helpers**: All schemas use STABLE SECURITY DEFINER functions (`current_user_id()`, `current_org_id()`, `therapy.current_user_role()`, etc.). Always `(SELECT auth.uid())` never bare `auth.uid()`. All functions include `SET search_path`.
- **Provisioning**: DB trigger `on_license_change` on `public.licenses` auto-provisions product defaults.
- **Usage reporting**: `product_usage` table + `snapshot_product_usage()` pg_cron daily at 3 AM UTC.

## Frontend Patterns

- **Mobile-first 3-tier**: Base (mobile) → `sm:`/`md:` (tablet) → `lg:`/`xl:` (desktop). `h-10`+ tap targets. Test at 375px, 768px, 1440px.
- **Toasts**: `import { toast } from 'sonner'`. Never `useToast` (deleted).
- **Constants**: Status/type maps in `lib/constants.ts`. Portuguese accents required.
- **Utilities**: `formatCurrency()`, `formatDate()` from `lib/utils.ts`. Never local copies.
- **TanStack Query**: `enabled: !!user` guard, appropriate `staleTime`, correct `invalidateQueries` in mutations.
- **Zustand stores**: Date fields as `string | undefined` (ISO). Convert at component boundaries.
- **Auth init**: `authStore.isInitialized` flag → `<PageSkeleton />` while false.
- **API client**: `safeFetch()` for all methods. Body as `unknown` not `any`.

### Token Refresh & 401 Retry

Two mechanisms for Supabase JWT expiry (~1 hour):
1. **Proactive**: `useActivityRefresh` hook — refreshes every 5min while user is active.
2. **Reactive**: Shared `createApiClient` accepts `onTokenExpired` callback → refresh + retry once on 401.

Every product's `api-client.ts` MUST provide `onTokenExpired`. Raw `fetch` calls (uploads, downloads) MUST implement 401 retry manually. Never skip this pattern.

## Notifications

Platform concern — all products share `public.notifications` table.
- Backend: product router at `/api/notificacoes` proxies to `public.notifications` via `get_core_client()`. Maps English→Portuguese fields.
- Frontend: `createNotificationHooks()` from shared + `<NotificationBell />` in layout header.

## Subscription & Admin

Core admin system: `get_current_admin()` verifies `noctus_users.role == "admin"`.
- Plans CRUD (`/api/plans`), subscriptions (`/api/subscriptions`), API keys (`noctus_k_...`, SHA-256 hashed).
- Admin pages at `/admin/*`: Dashboard, Organizations, Users, Subscriptions, API Keys, Plans, Products, Webhooks, Settings.
- Tables: `plans`, `subscriptions`, `api_keys`, `notifications`, `audit_logs`, `webhook_endpoints`, `webhook_deliveries`, `platform_settings`, `org_settings`, `product_usage`.

## Language

Portuguese (Brazilian) for business domain. English for technical concepts. Error messages in Portuguese.

## Database Security & RLS

129 tables across 4 schemas, all with RLS. Audited 2026-04-09.

| Schema | Tables | Isolation |
|--------|--------|-----------|
| `public` | 15 | `org_id` via `noctus_users` subquery |
| `erp` | 59 | `org_id` from JWT + role+owner scoping |
| `personal-finance` | 16 | `user_org_id()` helper |
| `therapy` | 39 | 4-role system via `current_user_role()` + `current_clinic_id()` |

**Rules**: (1) Always `(SELECT auth.uid())` not bare. (2) All functions: `SET search_path`. (3) Service role bypasses RLS via `get_admin_client()`. (4) HaveIBeenPwned enabled.

**Known gap**: ERP `ativos` SELECT is `USING(true)` — app-layer filtering, candidate for tightening.

## Schema Separation

Products use scoped PostgreSQL schemas. Backend `database.py` uses `ClientOptions(schema="<name>")`. Frontend Supabase client uses `db: { schema: '<name>' }`. All product schemas must be in Supabase "Exposed schemas" list.

Migration files documented in `KNOWLEDGE-BASE/CONTEXT/backend/` per product.

## External Integrations

Credential chain: `org_settings` → `platform_settings` → env vars. Managed via Configurações page.

- **Required** (blocks with 422): `infosimples_token` (certidões), `openai_api_key` (AI/embeddings).
- **Optional** (placeholder when missing): `openai_api_key` (certidão AI analysis), `resend_api_key` (email dry-run), `clicksign_api_token` (mock signing).

Integrations: InfoSimples, OpenAI, Resend, ClickSign/DocuSign/D4Sign, Meta Graph API, WAHA, Supabase Storage, reportlab.

## Creating a New Product

Copy `templates/product-seed/`, replace placeholders (`{{PRODUCT_NAME}}`, `{{PRODUCT_SLUG}}`, `{{SCHEMA_NAME}}`, `{{BACKEND_PORT}}`, `{{FRONTEND_PORT}}`, `{{PRODUCT_ICON}}`), install deps, run migration SQL, register product.

**Seed provides**: FastAPI + shared app_factory, config, database, dependencies (with `resolve_sso_role`), notifications router, test fixtures, React + design system, Layout.tsx, SSO callback, auth store, API client with 401 retry, NotificationBell, useTheme, useActivityRefresh.

**You add**: domain routers/services/schemas, nav items, pages, hooks, migration SQL.

**Seed-Core Sync Rule**: When shared patterns change (design system, auth, layout, notifications), update the seed in the same commit.
