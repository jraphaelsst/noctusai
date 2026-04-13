# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Engineering Philosophy

**No workarounds. Ever.** Always implement the correct solution using the real API, SDK, or framework behavior — even when it adds complexity. Monkeypatches, shims, hacks, and "temporary" fixes are not acceptable. If the proper solution requires touching more files, adding abstractions, or refactoring existing code, that is the right path. Complexity in service of correctness and solidity is a worthwhile trade-off; fragile shortcuts are not.

**DRY — Don't Repeat Yourself.** Every piece of knowledge, logic, or configuration must have a single authoritative source. Never duplicate code, constants, utilities, validation rules, or business logic across files. Extract shared helpers, reuse existing services, import from centralized modules. If two files need the same function, it belongs in a shared module. If three routers do the same org_id lookup, it belongs in `dependencies.py`. Three similar lines are acceptable; three similar blocks are not — extract and reuse. This applies to backend (services, helpers, schemas) and frontend (hooks, utils, constants, shared components) equally.

**Docs stay in sync with code.** Every commit must include documentation updates. When committing changes, update `CLAUDE.md` and `KNOWLEDGE-BASE/` files to reflect what changed: router/service/page/hook counts, new modules, deleted modules, new patterns, test counts, migration files, infrastructure changes. Documentation is part of the changeset, not a separate task. The user should never have to ask "are the docs up to date?" — they always are.

**Knowledge Base (`KNOWLEDGE-BASE/`)** is the platform's persistent context — architecture docs, domain knowledge, and design rationale that survives across conversations and context window limits. `CLAUDE.md` defines *how to behave* (rules, patterns); `KNOWLEDGE-BASE/` defines *what this platform is* (architecture, inventories, domain knowledge). When adding new platform knowledge (product docs, database changes, integration details), create or update files in `KNOWLEDGE-BASE/CONTEXT/`. See `KNOWLEDGE-BASE/CONTEXT/00-LANDSCAPE.md` for the full platform overview.

## Architecture

This is a **multi-tenant, multi-product SaaS monorepo**. Each organization (tenant) signs up once on the core platform and gets access to licensed products. Tenant isolation is enforced at the database level via Supabase RLS policies scoped to `org_id`, so data from one organization is never visible to another. Products are independently deployable but share authentication and tenant context through SSO.

- **`core/`** — NoctusAI Platform foundation (23 routers, 9 services): authentication, organizations, products, licenses, SSO, notifications, webhooks, audit logs, settings, usage reporting, users, templates. Manages tenants, user-to-org mapping, and cross-product access. Every user belongs to an organization; every product access requires an active license for that org. License grants trigger automatic provisioning via database trigger. See `KNOWLEDGE-BASE/CONTEXT/backend/01-CORE.md`.
- **`products/erp-imobiliario/`** — Real estate CRM product with 50 routers and 42 services: client management, property listings (ativos), sales funnel, AI matching, financial operations, WhatsApp messaging, digital signatures, PDF generation, notifications, Meta Ads integration, and compliance reporting. All data is scoped to the user's organization. See `KNOWLEDGE-BASE/CONTEXT/backend/02-ERP.md`.
- **`products/personal-finance/`** — Personal finance tracker product with 16 routers and 14 services: multi-account transaction management, budgets (orcamentos), recurring transactions, investment portfolio tracking (carteiras), stock watchlists with real-time quotes (yfinance), reports, and dashboard analytics. See `KNOWLEDGE-BASE/CONTEXT/backend/03-PF.md`.
- **`products/therapy-platform/`** — Online therapy platform with 39 routers and 38 services: therapist/patient/clinic profiles, scheduling, video sessions (LiveKit), clinical AI (transcription, summaries, longitudinal analysis, crisis detection), wallets, payments (Stripe Connect), messaging, reviews. 4 user roles (platform_admin, clinic_admin, therapist, patient) with role-based layouts. Auth is direct Supabase Auth (NOT NoctusAI SSO). Multi-tenant via `clinic_id` (not `org_id`). Schema: `therapy`. Backend port 8003, frontend port 8095. See `KNOWLEDGE-BASE/CONTEXT/backend/06-THERAPY.md`.

All layers follow the same stack: **FastAPI + Supabase** backend, **React + TypeScript + Vite** frontend. Each has independent backend and frontend directories.

### Backend Layers (FastAPI)

```
routers/     → HTTP handlers (thin: auth + validation + delegation)
services/    → Business logic (matching algorithm, CRUD orchestration)
schemas/     → Pydantic models for request/response
dependencies.py → Auth helpers (get_current_user, get_user_client, get_admin_client, get_org_id)
database.py  → Supabase client singleton
exceptions.py → Centralized error handling (AppException hierarchy)
middleware.py → Correlation IDs, request logging
rate_limit.py → Shared slowapi Limiter instance (avoids circular imports)
```

**Supabase client pattern**: `get_user_client(token)` respects RLS; `get_admin_client()` uses service role (admin-only operations).

### Frontend Layers (React)

```
pages/       → Route-level components
components/  → UI components (shadcn/ui base + domain-specific + shared/)
hooks/       → TanStack Query hooks per domain (useMetas, useClientes, etc.)
store/       → Zustand stores (authStore, filtrosStore, funilFiltrosStore)
lib/         → API client, validation schemas, utilities, constants
types/       → TypeScript definitions
```

State management: **Zustand** for global UI state, **TanStack Query** for server state.

### Shared Packages

Cross-cutting code lives in `shared/` to avoid duplication across products:

**Backend** (`shared/backend/noctusai_shared/`) — Python package installed via `pip install -e shared/backend`:
- `exceptions.py` — `AppException` hierarchy + all FastAPI exception handlers
- `responses.py` — `success_response`, `paginated_response`, `ok_response`, `deleted_response`
- `middleware.py` — `CorrelationIdMiddleware`, `RequestLoggingMiddleware`
- `logging_config.py` — JSON/human-readable formatters, `configure_logging()`
- `auth.py` — `first_or_none` Supabase helper
- `database.py` — `make_supabase_client` factory
- `config.py` — `BaseAppSettings` base class for Pydantic Settings
- `app_factory.py` — `configure_app()` shared FastAPI bootstrap (exception handlers, middleware, CORS, docs toggle)

**Important**: `get_current_user` is NOT shared — it lives in each product's `dependencies.py` and calls `get_supabase_client` at runtime. This is required for test mocks to work (`unittest.mock.patch` patches module attributes, but closures capture references at import time).

**Frontend** (`shared/frontend/src/`) — TypeScript source consumed via Vite path aliases (`@shared/*`), no build step:
- `api.ts` — `createApiClient` factory with `safeFetch`, `extractErrorMessage`, `onTokenExpired` 401-retry
- `utils.ts` — `cn`, `formatCurrency`, `formatDate`, `getTodayAtMidnight`, `stripTime`
- `auth.ts` — `useSupabaseAuthInit` hook
- `stores.ts` — `createAuthStore`, `createFiltrosStore` factories
- `hooks.ts` — `createCrudHooks` factory for TanStack Query CRUD patterns
- `query-client.ts` — `createQueryClient` with shared defaults
- `notifications.ts` — `createNotificationHooks` factory + `Notificacao`, `ContagemNaoLidas` types
- `components/ErrorBoundary.tsx`, `components/SSOCallback.tsx`
- `design-system/tokens.css` — **Single source of truth** for CSS custom properties (colors, radii, sidebar tokens, dark mode). All product `index.css` files import this instead of defining their own tokens.
- `design-system/tailwind.config.base.ts` — Shared Tailwind theme config. Products extend via `{ presets: [base] }`. Registers all color tokens: primary (light/dark), success, warning, danger, info, sidebar, and status colors.
- `design-system/components/AppShell.tsx` — Unified layout shell: dark sidebar + header + content. Handles responsive off-canvas sidebar on mobile.
- `design-system/components/Sidebar.tsx` — Generic, prop-driven sidebar with collapsible `NavGroup`s. Products pass their own nav data.
- `design-system/components/Header.tsx` — Full-featured header: HoverCard user card (avatar, name, role), edit profile form, password change form, dark/light theme toggle, logout. Products pass user data and callbacks via props. Responsive: mobile-first with touch-friendly tap targets.
- `design-system/ui/hover-card.tsx` — Shared Radix HoverCard primitive with fade/zoom animations.
- `design-system/useTheme.ts` — Dark/light theme hook with localStorage + DOM sync + optional DB persistence callback.
- `design-system/useActivityRefresh.ts` — Proactive token refresh hook: monitors user activity, refreshes token every 5 minutes while active, lets token expire on inactivity.
- `design-system/index.ts` — Barrel export for all design system components, hooks, and types.

**Design system principles**:
- One change to `tokens.css`, `tailwind.config.base.ts`, or shared components affects all products simultaneously.
- Products customize via nav data props and callbacks, not by forking components.
- **Mobile-first, 3-tier responsive**: All shared components are designed for mobile first (`h-10` tap targets, fluid widths), then tablet (`sm:`/`md:` — 2-col grids, compact inputs), then desktop (`lg:`/`xl:` — full layouts). Every component must look correct at 375px, 768px, and 1440px.

**THE Product Layout Pattern (mandatory for all products, including core):**

Every product (including the core platform) MUST have a single `components/layout/Layout.tsx` that follows this exact structure:

```
1. Imports: AppShell, Sidebar, Header, useTheme, useActivityRefresh from @noctusai/shared/design-system
2. Constants: NAV_GROUPS (static NavGroup[]), BRAND config, ROLE_LABELS, BackToCore footer
3. For role-based products: switch NAV_GROUPS based on user role (still ONE file, no separate layouts)
4. For feature-flagged products: filter NAV_GROUPS inline (e.g., ERP's status_pagina query)
5. Layout function: AppShell → Sidebar(brand + navGroups) + SharedHeader(user + theme + actions)
6. Content wrapper: <div className="p-4 sm:p-6 lg:p-8">{children}</div>
7. Products (not core): logoutBehavior="redirect" + BackToCore footer in sidebar
8. Core: logoutBehavior="signout" + no BackToCore
9. All products: useTheme() + useActivityRefresh() + NotificationBell in header actions
```

No product may create local Sidebar or Header wrapper components. No product may have multiple layout files (AdminLayout, UserLayout, etc.) — role branching happens inside the single Layout.tsx via nav data switching. The only exception is `PublicLayout.tsx` for unauthenticated pages (landing, directory, login).

All shared backend modules use `from __future__ import annotations` for Python 3.9 compatibility.

## Python Virtual Environment

A **single root-level venv** (`venv/`) is shared by all backends, running **Python 3.11+**. The root `requirements.txt` is the merged superset of all per-backend files. Per-backend `requirements.txt` files are kept for independent Docker deploys.

```bash
# First-time setup (or after pulling new deps)
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e shared/backend
```

## Product Seed Template

New products are bootstrapped from `templates/product-seed/`. Copy it, find-and-replace the placeholders, and start building.

```bash
cp -r templates/product-seed products/my-product
# Replace: {{PRODUCT_NAME}}, {{PRODUCT_SLUG}}, {{SCHEMA_NAME}}, {{BACKEND_PORT}}, {{FRONTEND_PORT}}, {{PRODUCT_ICON}}
```

The seed includes pre-wired: FastAPI backend (shared app factory, config, database, dependencies, notifications router, test fixtures), React frontend (shared design system, AppShell + Sidebar + Header, auth store, API client, SSO callback, theme toggle), and a migration template with RLS helpers. All shared infrastructure is consumed, not duplicated.

## Commands

### ERP Backend (primary development target)

```bash
source venv/bin/activate

# Run server
uvicorn app.main:app --reload --port 8001 --app-dir products/erp-imobiliario/backend

# Run all tests
cd products/erp-imobiliario/backend
pytest

# Run specific test file
pytest tests/routers/test_clientes_router.py -v

# Run single test
pytest tests/services/test_matching_service.py::TestCompatibilidadeRegiao::test_exact_city_state_bairro_match -v
```

### Core Backend

```bash
source venv/bin/activate
uvicorn app.main:app --reload --port 8000 --app-dir core/backend
```

### ERP Frontend

```bash
cd products/erp-imobiliario/frontend

npm run dev      # Vite dev server on port 8080
npm run build    # Production build
npm run lint     # ESLint
```

### Core Frontend

```bash
cd core/frontend
npm run dev      # Vite dev server on port 5173
```

### Therapy Backend

```bash
source venv/bin/activate
uvicorn app.main:app --reload --port 8003 --app-dir products/therapy-platform/backend
```

### Therapy Frontend

```bash
cd products/therapy-platform/frontend

npm run dev      # Vite dev server on port 8095
npm run build    # Production build
npm run lint     # ESLint
```

### Full Stack

```bash
bash start.sh    # Creates root venv, installs deps, starts all backends + frontends
```

## Testing

Tests use **pytest** with a fully mocked Supabase layer (389 core tests, 1,634 ERP tests, 473 PF tests, 1,021 therapy tests — 3,517 total). Key fixtures are in `tests/conftest.py`:

- `MockSupabaseClient` / `MockQueryBuilder` — Chainable query builder that simulates Supabase PostgREST
- `AuthClient` — Wraps FastAPI `TestClient` with automatic `Authorization: Bearer` headers
- `client` fixture — Fully wired test client with mocked auth and logging
- Core also has `admin_client` (admin role) and `unauth_client` (no auth) fixtures

Integration tests in `tests/integration/` use `StatefulMockClient` that persists data across operations for CRUD cycle testing.

Test naming convention: `test_{router_name}_router.py` for router tests, `test_{service_name}_service.py` for service tests.

### Real-DB Integration Tests

A small suite (~25 tests) in `tests/realdb/` per backend hits a **real Supabase instance** to verify things mocks cannot: SQL filtering (`ilike`, `range`), FK/CHECK constraints, cascade deletes, unique violations, PostgREST errors (`PGRST116`), and RLS org isolation.

```bash
# Run real-DB tests for one backend
cd products/erp-imobiliario/backend
pytest tests/realdb/ -v

# Run all real-DB tests across all backends
pytest core/backend/tests/realdb/ \
       products/erp-imobiliario/backend/tests/realdb/ \
       products/personal-finance/backend/tests/realdb/ -v
```

- **Auto-skip**: Tests skip when `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY` are not set, so normal `pytest` runs are unaffected.
- **Cleanup**: Every test cleans up its data via `cleanup` fixture (collects `(table, id)` tuples, deletes in reverse order).
- **Convention**: Test orgs use `category: "test"` for easy identification.
- **Schema targeting**: Core tests use `public`, ERP uses `ClientOptions(schema="erp")`, PF uses `ClientOptions(schema="personal-finance")`, Therapy uses `ClientOptions(schema="therapy")`.

## Environment Variables

All backends read from a **single `.env` at the repo root**. Each backend's `config.py` resolves the root `.env` via an absolute path computed from `__file__`, so it works regardless of CWD. Pydantic Settings silently ignores a missing `.env` file, so CI/Docker environments that inject env vars directly are unaffected.

Create the root `.env` file with the following key variables:

```
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
JWT_SECRET=...
CORS_ORIGINS=http://localhost:5173,http://localhost:8080
DEBUG=true
CORE_API_URL=http://localhost:8000
SENTRY_DSN=          # Optional
REDIS_URL=           # Optional
OPENAI_API_KEY=      # Optional (ERP + Therapy products)
RESEND_API_KEY=      # Optional (email delivery)
CLICKSIGN_API_TOKEN= # Optional (digital signatures)
THERAPY_LIVEKIT_URL=           # Therapy product only
THERAPY_LIVEKIT_API_KEY=       # Therapy product only
THERAPY_LIVEKIT_API_SECRET=    # Therapy product only
THERAPY_GOOGLE_CLIENT_ID=      # Therapy product only (Google OAuth + Calendar)
THERAPY_GOOGLE_CLIENT_SECRET=  # Therapy product only
THERAPY_STRIPE_CONNECT_CLIENT_ID= # Therapy product only (Stripe Connect marketplace)
```

Frontend uses `VITE_`-prefixed vars in their own `.env` files (security boundary — frontend vars end up in browser bundles).

## Key Patterns

### Backend Patterns

- **Auth in routers**: Every protected endpoint takes `authorization: Optional[str] = Header(None)` and calls `await get_current_user(authorization)` which returns `(user, token)`. In the Core backend, admin-only endpoints use `await get_current_admin(authorization)` (defined in `core/backend/app/dependencies.py`) which additionally verifies `noctus_users.role == "admin"`. This dependency is Core-only and does not exist in product backends.
- **Org ID extraction**: Use `get_org_id(user)` from `dependencies.py` to extract `org_id` from user metadata. Never inline `user.user_metadata.get("org_id")` — use the shared helper.
- **Responses**: List endpoints return `paginated_response(data, total, page, page_size)`. Single items return `success_response(data)`. Deletes return `ok_response(message)`.
- **Pagination**: All list endpoints accept `page` and `page_size` query params. Pagination is implemented via Supabase `.range()`.
- **DELETE pre-checks**: All DELETE endpoints must verify the record exists before deletion: `check = db.table("x").select("id").eq("id", id).execute()` → `if not check.data: raise HTTPException(404)`.
- **Server-side search**: List endpoints with `busca` param use Supabase `.or_()` with `ilike` for server-side filtering BEFORE pagination. Never filter in Python after fetching all records.
- **Rate limiting**: Public and AI endpoints use `@limiter.limit("30/minute")` from `app.rate_limit`. Import the shared `limiter` instance, add `request: Request` parameter. Applied to: AI endpoints, WhatsApp `/send`, portal externo public endpoints.
- **Webhook security**: WhatsApp webhook verifies HMAC-SHA256 signatures via `x-hub-signature` header when `webhook_secret` is configured.
- **N+1 prevention (zero tolerance)**: Every DB operation that touches multiple rows MUST be batched. No workarounds, no exceptions. Specifically:
  - **Reads**: Use `.in_("id", ids)` to fetch multiple records in one query. Never loop `.eq("id", id).single()` per item.
  - **Writes (INSERT)**: Build a list of dicts and call `.insert(rows)` once. Never loop `.insert(single_row)` per item.
  - **Writes (UPDATE)**: Use `.update(data).in_("id", ids)` for same-value updates. For different-value updates, group by value and batch each group.
  - **Writes (UPSERT)**: Pass the full list to `.upsert(rows, on_conflict=...)` in one call.
  - **Enrichment**: When enriching a list with related data (e.g., adding consulta info to resultados), fetch all related records with `.in_()` and build a lookup dict — never query per item in a loop.
  - If a loop contains `db.table(...)`, it's almost certainly an N+1 bug. The only exception is when each iteration requires genuinely unique logic (e.g., different RPC calls with unique parameters).
- **Router → Service delegation**: Business logic and aggregation belong in services, not routers. Routers are thin (auth + validation + delegation). Examples: `BIService.get_dashboard_resumo()`, `whatsapp_service.send_via_waha()`.
- **Validation**: Pydantic models use `Field()` constraints (ge, le, max_length). Use `Literal` types for enum-like fields.
- **Error handling**: Raise `HTTPException` for simple cases. Use custom `AppException` subclasses for structured errors. All exceptions are caught by centralized handlers in `main.py`. Both backends register a `postgrest_exception_handler` that catches Supabase PostgREST `APIError` with code `PGRST116` (`.single()` returning 0 rows) and converts it to a 404 response.
- **Logging**: Structured JSON in production, human-readable in dev. Every request gets a correlation ID via middleware.
- **Security defaults**: `debug` defaults to `False` across all backends (core, ERP, personal-finance, therapy). `jwt_secret` defaults to a dev-only placeholder that triggers a validation error in production. Docs endpoints are disabled when `not debug`. Leaked password protection is enabled in Supabase Auth (checks passwords against HaveIBeenPwned.org).
- **RLS helper functions (unified pattern)**: All schemas use STABLE SECURITY DEFINER helper functions to extract identity from JWT, evaluated once per query. For new RLS policies, prefer helpers over raw `auth.uid()`/`auth.jwt()`:
  - **`public`**: `current_user_id()`, `current_org_id()`, `is_platform_admin()`
  - **`erp`**: `erp.current_user_id()`, `erp.current_org_id()` + `has_role(uid, role)` for ERP-specific roles
  - **`personal-finance`**: `"personal-finance".user_org_id()` (pre-existing)
  - **`therapy`**: `therapy.current_user_role()`, `therapy.current_clinic_id()`
  - Existing policies still use `(SELECT auth.uid())` subselect pattern (equivalent performance). New policies should prefer the helper functions for readability.
- **Function search_path**: All PostgreSQL functions must include `SET search_path = <schema>, public` to prevent search path injection. This applies to all product schemas.
- **Provisioning lifecycle**: A database trigger (`on_license_change`) on `public.licenses` automatically provisions product-specific defaults when a license is granted and sends notifications on revocation. Product-specific functions: `provision_erp()`, `provision_personal_finance()`, `provision_therapy()`.
- **Usage reporting**: `public.product_usage` table tracks per-org, per-product metrics (active_users_30d, total_records). `snapshot_product_usage()` function computes metrics across all schemas. Runs daily via pg_cron at 3 AM UTC. Admin endpoint: `GET /api/admin/usage`. Manual trigger: `POST /api/admin/usage/snapshot`.

### Frontend Patterns

- **Mobile-first responsive design (3-tier)**: All UI must be designed mobile-first, then enhanced for tablet, then desktop. Use Tailwind breakpoints progressively — base styles are mobile, then layer `sm:` (640px), `md:` (768px), `lg:` (1024px), `xl:` (1280px). The three tiers:
  - **Mobile** (base, <640px): Single column, `h-10`+ tap targets (44px min), full-width cards (`w-[calc(100vw-2rem)]`), collapsible sidebars, hamburger nav.
  - **Tablet** (`sm:`/`md:`, 640-1024px): 2-column grids (`sm:grid-cols-2`), sidebar visible (`md:block`), compact inputs (`md:h-9`), medium card widths (`sm:w-80 md:w-96`).
  - **Desktop** (`lg:`/`xl:`, 1024px+): 3-4 column grids (`lg:grid-cols-3 xl:grid-cols-4`), full sidebar, relaxed spacing.
  - Test at: 375px (iPhone SE), 768px (iPad), 1024px (iPad landscape), 1440px (desktop).
- **Toasts**: Use `import { toast } from 'sonner'`. Pattern: `toast.success("Msg")`, `toast.error("Msg", { description: "Details" })`. Never use the old `useToast` hook (deleted).
- **Centralized constants**: Status/type label maps live in `lib/constants.ts` (e.g., `PROPOSTA_STATUS_CONFIG`, `CONTRATO_STATUS_CONFIG`). All labels use proper Portuguese accents ("Concluído", "Locação", "Reunião"). Import from `@/lib/constants` — never define local copies.
- **Centralized utilities**: `formatCurrency()`, `formatDate()`, `getTodayAtMidnight()` live in `lib/utils.ts`. Never define local `formatCurrency` or inline `Intl.NumberFormat`.
- **Shared components**: Reusable cross-entity components live in `components/shared/` (e.g., `DocumentosTab` accepting `{ entityType, entityId }`). Prefer thin wrappers over copy-pasting.
- **TanStack Query hooks**: Every query hook must have: (1) `enabled: !!user` guard to prevent unauthenticated requests, (2) appropriate `staleTime` (reference data: 10min, active data: 2-3min, real-time: 30s), (3) correct `invalidateQueries` in related mutations (e.g., creating a locação must invalidate `['imoveis']`).
- **Zustand stores**: Date fields use `string | undefined` (ISO strings), not `Date`. Convert at component boundaries: `selected={dataInicio ? new Date(dataInicio) : undefined}`, `onSelect={(date) => setDataInicio(date?.toISOString())}`.
- **Auth initialization**: `authStore` has `isInitialized` flag. `AuthProvider` calls `setInitialized()` after `getSession()`. `AppContent` shows `<PageSkeleton />` while `!isInitialized` to prevent login form flash.
- **API client** (`lib/api-client.ts`): Handles 204 No Content, uses `safeFetch()` for all methods (not raw `fetch`). Body params typed as `unknown` (not `any`).
- **Validation schemas**: Deduplicate identical schemas (e.g., `corretorSchema = signUpSchema`). Schemas live in `lib/validations.ts`.
- **Modals**: Use `formData` state (not entity props) for display. Update UI instantly without closing modals. See `KNOWLEDGE-BASE/CONTEXT/frontend/02-ERP.md` (Modal Patterns section).
- **Dates**: All date handling uses São Paulo timezone (America/Sao_Paulo). Server calculates dates via Supabase RPC `get_data_sp()`. See `KNOWLEDGE-BASE/CONTEXT/frontend/02-ERP.md` (Date & Timezone Patterns section).

### Token Refresh & 401 Retry (All Products)

Supabase JWTs expire after ~1 hour. Two complementary mechanisms ensure uninterrupted sessions:

**1. Proactive activity-based refresh** (`useActivityRefresh` hook from `@noctusai/shared/design-system`):
- Monitors user activity (mousemove, keydown, scroll, click, touch)
- Every 5 minutes, checks if user was active since last check
- If active: calls `supabase.auth.refreshSession()` (products) or `POST /api/auth/refresh` (Core) — token renewed before it expires
- If inactive: does nothing — token expires naturally for security
- Wired into every product's layout or auth provider
- Core stores both `access_token` and `refresh_token` in localStorage

**2. Reactive 401 retry** at the shared API client level (fallback):

1. **Shared `createApiClient`** (`shared/frontend/src/api.ts`) accepts an `onTokenExpired` callback. When any request returns 401, the client calls `onTokenExpired()` to force a session refresh, then retries the request exactly once with the new token.

2. **Every product api-client** (`lib/api-client.ts`) MUST provide `onTokenExpired`:
   ```ts
   export const api = createApiClient({
     getBaseUrl: () => BACKEND_URL,
     getAuthToken: async () => {
       const { data: { session } } = await supabase.auth.getSession();
       if (!session?.access_token) throw new Error('Nao autenticado');
       return session.access_token;
     },
     onTokenExpired: async () => {
       const { data: { session } } = await supabase.auth.refreshSession();
       return session?.access_token ?? null;
     },
   });
   ```

3. **Raw `fetch` calls** (file uploads via FormData, binary downloads) cannot use the JSON api client. These MUST implement the same 401-retry pattern manually:
   ```ts
   let resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
   if (resp.status === 401) {
     const { data: { session } } = await supabase.auth.refreshSession();
     if (session) {
       resp = await fetch(url, { headers: { Authorization: `Bearer ${session.access_token}` } });
     }
   }
   ```

4. **Never skip this pattern.** Every authenticated HTTP call — whether through the shared api client or raw fetch — must handle token expiry. Failing to do so causes cascading 401 errors on pages with polling (`refetchInterval`), where a single expired token triggers repeated failures every few seconds.

## Notifications (Platform-Level)

Notifications are a **platform concern**, not a product concern. All products share a single `public.notifications` table managed by the core platform.

### Architecture
- **Table**: `public.notifications` — defined in `core/backend/migrations/001_noctusai_core.sql`, has RLS scoped to `user_id = auth.uid()`
- **Core router**: `core/backend/app/routers/notifications.py` — English API (`/api/notifications`) for the core platform frontend
- **Product routers**: Each product has its own `/api/notificacoes` router that proxies to `public.notifications` with Portuguese field mapping

### How to add notifications to a new product

**Backend:**
1. Add `get_core_client()` to the product's `database.py` — creates a Supabase client targeting `schema="public"` (not the product schema)
2. Create `routers/notificacoes.py` — use `get_core_client().table("notifications")` for all CRUD. Map fields: `type→tipo`, `title→titulo`, `message→mensagem`, `read→is_read`
3. Register the router in `main.py`

**Frontend:**
1. Create `hooks/useNotificacoes.ts` — use `createNotificationHooks()` factory from `@noctusai/shared/notifications`
2. Create or copy `components/NotificationBell.tsx`
3. Add `<NotificationBell />` to the layout header

**Shared code:**
- `shared/frontend/src/notifications.ts` — `createNotificationHooks()` factory, `Notificacao` and `ContagemNaoLidas` types
- `shared/backend/` — no shared notification code needed; each product's router is thin enough (~100 lines)

### Field Mapping (core → product API)
| Core (English) | Product API (Portuguese) |
|---|---|
| `type` | `tipo` |
| `title` | `titulo` |
| `message` | `mensagem` |
| `read` | `is_read` |
| `metadata.link` | `link` |

### Migration
Run `core/backend/migrations/004_ensure_notifications.sql` on any database that doesn't have the `notifications` table yet. Safe to run multiple times (uses `IF NOT EXISTS`).

## Subscription & Admin System

The core platform includes a **subscription management system** with admin enforcement:

### Backend (`core/backend/app/`)
- **`dependencies.py`** — `get_current_admin()` dependency verifies `noctus_users.role == "admin"` (403 if not admin)
- **`routers/plans.py`** — Plan tier definitions CRUD (free/pro/enterprise). Public read, admin write.
- **`routers/subscriptions.py`** — Org-to-plan assignments. Admin manages; users can read their own via `/api/subscriptions/me`.
- **`routers/api_keys.py`** — Stripe-like API key management (`noctus_k_...`). Keys are hashed (SHA-256), only prefix stored for display. Full key returned once on creation.

Admin-guarded endpoints: `POST /api/products`, `POST /api/licenses`, `DELETE /api/licenses/{id}`, all plan/subscription write operations, `GET /api/admin/api-keys`, `GET/PATCH/DELETE /api/admin/users`.

### Database tables (Supabase — `public` schema)
- **`plans`** — Plan definitions with pricing, limits, Stripe-ready fields
- **`subscriptions`** — Org subscriptions with status tracking (active/canceled/expired/trial)
- **`api_keys`** — Hashed API keys with scopes and expiry
- **`notifications`** — In-app user notifications (team_invite, subscription_change, usage_alert, system)
- **`audit_logs`** — Action audit trail (user_id, org_id, action, resource_type, resource_id, ip_address)
- **`webhook_endpoints`** — Webhook URL configuration per org (url, secret, events, is_active)
- **`webhook_deliveries`** — Delivery attempt log per endpoint (payload, response_status, attempts, status)
- **`platform_settings`** — Global platform key-value config (service role only)
- **`org_settings`** — Per-org key-value settings with unique `(org_id, key)` constraint
- **`product_usage`** — Per-org, per-product usage metrics (active_users_30d, total_records). Snapshotted daily via pg_cron.

All tables are defined in `core/backend/migrations/001_noctusai_core.sql` (16 tables total for fresh deploys).

### Frontend (`core/frontend/src/`)
- **`lib/auth-context.tsx`** — `AuthProvider` + `useAuth()` hook providing `{ user, organization, isAdmin }` globally
- **`components/AdminLayout.tsx`** — Sidebar layout with navigation for admin pages
- **`pages/admin/`** — Admin pages: Dashboard, Organizations, Subscriptions, API Keys, Plans
- **Admin routes**: `/admin`, `/admin/orgs`, `/admin/subs`, `/admin/api-keys`, `/admin/plans` — all protected by `AdminRoute` (redirects non-admins to `/`)

## Language

The codebase uses **Portuguese (Brazilian)** for business domain terminology (clientes, metas, ativos, funil, etc.) and English for technical/framework concepts. Error messages returned to users are in Portuguese.

## Database Security & RLS Architecture

All 129 tables across all 4 schemas have RLS enabled. Security was comprehensively audited and hardened on 2026-04-09.

### RLS Patterns by Schema

- **`public`** (15 tables) — Org-scoped via `noctus_users.org_id` subquery: `USING (org_id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid())))`. Admin endpoints use `noctus_users.role = 'admin'` check.
- **`erp`** (59 tables) — Two patterns: (1) org-scoped via `org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid` for ~48 tables, (2) role+owner-scoped via `has_role((SELECT auth.uid()), 'admin')` + `(SELECT auth.uid()) = usuario_id` for user-facing tables (clientes, metas, profiles, etc.). Matches scoped via ativos.owner_id FK chain.
- **`personal-finance`** (16 tables) — User-scoped via `user_org_id()` SECURITY DEFINER helper function. Child tables (alocacao_alvo, watchlist_itens, etc.) use parent-table subqueries.
- **`therapy`** (39 tables) — 4-role system (platform_admin, clinic_admin, therapist, patient). Uses `therapy.current_user_role()` and `therapy.current_clinic_id()` SECURITY DEFINER helper functions. Policies are role-aware: platform_admin sees all, clinic_admin sees own clinic, therapist/patient see own data. Clinical session tables chain through appointment joins.

### RLS Rules (Mandatory)

1. **Always use `(SELECT auth.uid())` / `(SELECT auth.jwt())`** — never bare `auth.uid()`. The subselect prevents per-row re-evaluation (InitPlan optimization).
2. **All PostgreSQL functions must include `SET search_path`** — prevents search path injection. Example: `SET search_path = erp, public`.
3. **Therapy uses helper functions** — `therapy.current_user_role()` and `therapy.current_clinic_id()` for efficient role/clinic extraction from JWT.
4. **Leaked password protection is enabled** in Supabase Auth (HaveIBeenPwned check on password changes).
5. **Service role bypasses RLS** — backend operations that need cross-tenant access use `get_admin_client()`.

### Known Gaps (Future Work)

- **ERP `ativos` SELECT policy is `USING(true)`**: All authenticated users can read all ativos (cross-org). This is by current design (org filtering happens at the application layer) but is a candidate for tightening.

## Database Schema Separation

Tables are separated into **product-scoped PostgreSQL schemas**:

- **`public`** — Core platform tables (15 total: `noctus_users`, `organizations`, `products`, `licenses`, `plans`, `subscriptions`, `api_keys`, `roles`, `invitations`, `notifications`, `audit_logs`, `webhook_endpoints`, `webhook_deliveries`, `platform_settings`, `org_settings`) + auth hook functions (`handle_new_user`, `assign_default_corretor_role`, `has_role`)
- **`erp`** — ERP product tables (`metas`, `clientes`, `ativos`, `profiles`, `user_roles`, `condominios`, etc.) + all ERP business logic functions
- **`therapy`** — Therapy platform tables (39 total: `clinics`, `therapist_profiles`, `patient_profiles`, `appointments`, `video_rooms`, `session_records`, `session_summary_versions`, `wallets`, `transactions`, `conversations`, `messages`, `reviews`, `platform_settings`, etc.). Auth is direct Supabase Auth — users reference `auth.users(id)` directly. Multi-tenant via `clinic_id` (not `org_id`). 4-role RLS: platform_admin (full access), clinic_admin (own clinic), therapist (own data + patients), patient (own data). Helper functions `therapy.current_user_role()` and `therapy.current_clinic_id()` extract role/clinic from JWT metadata.

Each product backend's `database.py` uses `ClientOptions(schema="<schema>")` so all `.table()` and `.rpc()` calls target the correct schema automatically. Each product frontend's Supabase client uses `db: { schema: '<schema>' }` for data queries. The Core backend defaults to `public`.

**Supabase Dashboard** must have all product schemas (`erp`, `personal-finance`, `therapy`) in the "Exposed schemas" list (Project Settings → API) for PostgREST to accept the `Accept-Profile` header.

### Core migration files (`core/backend/migrations/`):
- `001_noctusai_core.sql` — Full core schema (16 tables incl. product_usage, RLS policies with InitPlan optimization, FK indexes, helper functions, provisioning trigger, usage snapshot, seed data) for fresh deploys. All RLS policies use `(SELECT auth.uid())` subselect pattern. Includes `roles_read_own_org` SELECT policy, `on_license_change` trigger, `snapshot_product_usage()` function, pg_cron daily job.
- `002_missing_tables.sql` — Adds 6 tables (notifications, audit_logs, webhooks, settings) to existing databases
- `003_license_history.sql` — Modifies licenses table for multiple records per org+product

### ERP migration files (`products/erp-imobiliario/backend/migrations/`):
- `001_erp_imobiliario.sql` — Creates `erp` schema + all ERP objects (fresh deploys). All RLS policies use `(SELECT auth.uid())` / `(SELECT auth.jwt())` subselect pattern. All functions include `SET search_path`. Consolidated admin+user policies (metas, negociacoes, clientes, profiles). Matches scoped via ativos.owner_id FK chain. FK indexes on atividades, ativos, chamados_portal, funil_movimentos, negociacoes, vistorias_rapidas.
- `002_ai_matching.sql` — pgvector embeddings in `erp` schema
- `003_schema_separation.sql` — Moves existing objects from `public` → `erp` (existing databases only)
- `004_mvp_expansion.sql` — 42 new tables for MVP expansion (existing databases)
- `005_fix_sidebar_pages.sql` — Fix `set_timestamps_sp()` trigger, seed all sidebar routes, admin role setup
- `006_lead_scoring.sql` — Adds lead_score columns to erp.clientes
- `007_certidoes_negativas.sql` — Certidões negativas table and indexes
- `007_drop_legacy_tables.sql` — Drops legacy tables no longer in use

### Data migration files (`migratingDB/`):

Migration scripts for importing data from the legacy Django permutas system into `erp.ativos`, `erp.clientes`, and `erp.condominios`. Executed manually in Supabase SQL Editor — not part of the application migration pipeline.

**Phase 1** — Import raw data with placeholder names and inferred mappings:
- `01_setup_staging.sql` — Creates staging tables (`stg_imovel`, `stg_permuta_imovel`, `stg_interesse_*`) and lookup maps (`tipo_imovel_map`, `zona_map`, `imovel_id_map`, etc.)
- `02_load_data.sql` — Loads 264 imóveis, 13 permutas, and interest records into staging tables
- `03_migrate.sql` — Transforms staging → `erp.clientes` (placeholders), `erp.condominios` (placeholders), `erp.ativos` (with JSONB interesses). Generates UUID mappings, builds interesses aggregation
- `04_validate.sql` — Validation queries to verify record counts, orphan checks, interesses population

**Phase 2** — Correct inferred data and enrich placeholders with real values:
- `05_second_migration.sql` — Monolithic corrective migration (10 etapas, single transaction):
  - Etapa 1: Recreates staging tables + loads lookup data (tipo_imovel, zona, corretor, proprietário, condomínio)
  - Etapa 2: Builds correct tipo_imovel and zona mappings (fixes Phase 1 inference errors)
  - Etapa 3: Corrects `tipo_imovel` on ativos via ref-based JOINs to original staging data
  - Etapa 4: Corrects `zona` on ativos via ref-based JOINs
  - Etapa 5: Replaces "Corretor #N" placeholders with real names from lookup
  - Etapa 6: Fixes `tipo_imovel` and `zona` inside JSONB `interesses` (atomic `||` operator, no double-replacement)
  - Etapa 7: Enriches `erp.clientes` — replaces "Proprietário #N" with real nome/telefone/email
  - Etapa 8: Enriches `erp.condominios` — replaces "Condomínio #N" with real nome/cep/cidade/bairro/endereço
  - Etapa 9: Propagates location data from enriched condominios to their linked ativos
  - Etapa 10: Validation queries (distribution checks, remaining placeholders, samples)

**Key conventions**:
- Migrated records identified by: `titulo_anuncio LIKE '[MOCK]%'` (imóveis), `observacoes LIKE '%MIGRADO%'` (clientes/condominios), `natureza = 'permuta_imovel'` (permutas)
- Enriched records marked with `[MIGRADO-ENRIQUECIDO]` in observacoes
- `erp.ativos.tipo_imovel` is TEXT (not the ENUM type), so any value works but enum-compatible values are used for consistency
- Phase 2 uses ref-based JOINs (not UUID) since Phase 1 TEMP tables are gone; placeholder name parsing (`'Proprietário #' || old_id`) for reverse mapping

### Personal Finance migration files (`products/personal-finance/backend/migrations/`):
- `001_personal_finance.sql` — Full PF schema (accounts, transactions, budgets, portfolios, watchlists). All RLS policies use `(SELECT auth.uid())` subselect pattern. `set_updated_at()` function includes `SET search_path`. 24 FK indexes on all foreign key columns.
- `002_seed_product.sql` — Seeds the personal-finance product record in the core products table
- `003_fix_schema_permissions.sql` — Fixes schema permissions for PostgREST access

### Therapy Platform migration files (`products/therapy-platform/backend/migrations/`):
- `001_therapy_platform.sql` — Full therapy schema (39 tables, role-based RLS policies, indexes, seed data, product seed) for fresh deploys. Includes `therapy.current_user_role()` and `therapy.current_clinic_id()` helper functions for RLS. All 39 tables have proper 4-role RLS (platform_admin, clinic_admin, therapist, patient) — no blanket `USING(true)` policies. `therapy.platform_settings` with default AI prompts, commission rates, session timing config. Product-specific env vars use `THERAPY_` prefix.

## External Integrations & Credential Enforcement

Credential resolution chain: `org_settings` table → `platform_settings` table → environment variables. All credentials are managed via the Configurações page (`Configurações > Chaves de API`) and stored in `org_settings` with `is_secret: true`.

### Required vs Optional Credentials

External integrations follow one of two patterns depending on whether a credential is **required** or **optional** for a given feature:

**Required credentials** — Router validates upfront via `check_*_configured()` before any work. Returns HTTP 422 with a clear message pointing to `Configurações > Chaves de API`. No data is created, no background tasks are started.

| Credential | Feature | Router check |
|---|---|---|
| `infosimples_token` | Certidões negativas (all 9 certificate types) | `check_required_credentials()` in `certidoes.py` |
| `openai_api_key` | AI description, lead scoring, price suggestion | `check_openai_configured()` in `ai.py` |
| `openai_api_key` | Embedding generation (embed, embed-batch) | `check_openai_configured()` in `matching.py` |

**Optional credentials** — Feature works without the credential but shows a clear placeholder where results would appear. No fake success status.

| Credential | Feature | Behavior when missing |
|---|---|---|
| `openai_api_key` | Certidões AI analysis (`analise_ia` field) | Placeholder: `"[Análise IA não disponível — OpenAI API Key não configurada...]"` |
| `resend_api_key` | Email delivery | Dry-run: email record created but not dispatched via Resend |
| `clicksign_api_token` / `docusign_*` / `d4sign_*` | Digital signatures | Fallback: internal mock signing with `dry_run: true` |

**Pattern for new integrations**: If a credential is the core requirement for a feature (the feature cannot produce real results without it), validate upfront in the router and block with 422. If a credential enhances results but the feature works without it, return a clear placeholder string in the relevant field so the UI can display it.

Integrations: InfoSimples (certidões), OpenAI (AI features, embeddings, certidão analysis), Resend (email), ClickSign/DocuSign/D4Sign (digital signatures), Meta Graph API (Lead Ads, campaign sync), WAHA/Meta Business API (WhatsApp), Supabase Storage (file uploads), reportlab (PDF generation).

## Creating a New Product

The `templates/product-seed/` directory is the canonical template for all products. **Every product is a copy of this seed, customized with domain-specific data.**

### Seed-Core Sync Rule (Mandatory)

The product seed template MUST stay in sync with the core platform patterns. When any of these change, the seed MUST be updated in the same commit:

- **Shared design system** (tokens.css, tailwind base, AppShell, Sidebar, Header, hooks)
- **Backend bootstrap** (app_factory, config pattern, dependencies pattern, database.py pattern)
- **Test fixtures** (conftest.py MockSupabaseClient, AuthClient pattern)
- **Layout pattern** (single Layout.tsx per product)
- **Auth pattern** (get_current_user, get_org_id, token refresh)
- **Notification pattern** (core proxy via get_core_client)

Every digital environment (core, ERP, PF, therapy, and all future products) is a different digital object inside the ecosystem, but they are all of the same type and must follow the same pattern. The seed is the source of truth for that pattern.

### Step-by-Step: New Product Creation

```bash
# 1. Copy the seed
cp -r templates/product-seed products/<your-product>

# 2. Replace ALL placeholders:
#    {{PRODUCT_NAME}}     → Human-readable name (e.g., "My Product")
#    {{PRODUCT_SLUG}}     → URL-safe slug (e.g., "my-product")
#    {{SCHEMA_NAME}}      → PostgreSQL schema (e.g., "my_product")
#    {{BACKEND_PORT}}     → Unique port (e.g., 8004)
#    {{FRONTEND_PORT}}    → Unique port (e.g., 8100)
#    {{PRODUCT_ICON}}     → Lucide icon component name (e.g., "Briefcase")

# 3. Backend setup
source venv/bin/activate
pip install -r products/<your-product>/backend/requirements.txt

# 4. Frontend setup
cd products/<your-product>/frontend && npm install

# 5. Database: run migrations/001_<schema>.sql in Supabase SQL Editor
#    - Create the schema
#    - Enable RLS on all tables
#    - Use (SELECT auth.uid()) pattern in all policies
#    - Add SET search_path to all functions

# 6. Register product: INSERT into public.products via admin panel

# 7. Add to start.sh, root requirements.txt, and .env (VITE_ vars)
```

### What the Seed Provides (pre-wired)

**Backend**: FastAPI + shared app_factory, Pydantic config with root .env resolution, Supabase client with schema targeting (get_admin_client, get_user_client, get_core_client), auth dependencies, rate limiter, notifications router (proxies to core), health check, test fixtures with auto-patching conftest.

**Frontend**: Vite + React + TypeScript, shared design system (tokens.css import, tailwind base preset), single Layout.tsx with AppShell + Sidebar + Header, SSO callback, auth store, API client with 401 retry, NotificationBell, useTheme, useActivityRefresh.

**The product only needs to add**: domain-specific routers/services/schemas, nav items in Layout.tsx, pages, hooks, and the migration SQL.
