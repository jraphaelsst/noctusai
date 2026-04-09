# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Engineering Philosophy

**No workarounds. Ever.** Always implement the correct solution using the real API, SDK, or framework behavior — even when it adds complexity. Monkeypatches, shims, hacks, and "temporary" fixes are not acceptable. If the proper solution requires touching more files, adding abstractions, or refactoring existing code, that is the right path. Complexity in service of correctness and solidity is a worthwhile trade-off; fragile shortcuts are not.

**DRY — Don't Repeat Yourself.** Every piece of knowledge, logic, or configuration must have a single authoritative source. Never duplicate code, constants, utilities, validation rules, or business logic across files. Extract shared helpers, reuse existing services, import from centralized modules. If two files need the same function, it belongs in a shared module. If three routers do the same org_id lookup, it belongs in `dependencies.py`. Three similar lines are acceptable; three similar blocks are not — extract and reuse. This applies to backend (services, helpers, schemas) and frontend (hooks, utils, constants, shared components) equally.

**Docs stay in sync with code.** Every commit must include documentation updates. When committing changes, update `CLAUDE.md` to reflect what changed: router/service/page/hook counts, new modules, deleted modules, new patterns, test counts, migration files, infrastructure changes. Documentation is part of the changeset, not a separate task. The user should never have to ask "are the docs up to date?" — they always are.

## Architecture

This is a **multi-tenant, multi-product SaaS monorepo**. Each organization (tenant) signs up once on the core platform and gets access to licensed products. Tenant isolation is enforced at the database level via Supabase RLS policies scoped to `org_id`, so data from one organization is never visible to another. Products are independently deployable but share authentication and tenant context through SSO.

- **`core/`** — NoctusAI Platform foundation (20 routers, 8 services): authentication, organizations, products, licenses, SSO, notifications, webhooks, audit logs, settings. Manages tenants, user-to-org mapping, and cross-product access. Every user belongs to an organization; every product access requires an active license for that org.
- **`products/erp-imobiliario/`** — Real estate CRM product with 48 routers and 40 services: client management, property listings (ativos), sales funnel, AI matching, financial operations, WhatsApp messaging, digital signatures, PDF generation, notifications, Meta Ads integration, and compliance reporting. All data is scoped to the user's organization.
- **`products/personal-finance/`** — Personal finance tracker product: multi-account transaction management, budgets (orcamentos), recurring transactions, investment portfolio tracking (carteiras), stock watchlists with real-time quotes (yfinance), reports, and dashboard analytics. Uses the same FastAPI + Supabase backend / React + TypeScript frontend stack.
- **`products/therapy-platform/`** — Online therapy platform with 7 routers and 6 services: therapist/patient/clinic profiles, directory discovery, reviews, admin approval, and notifications. 4 user roles (platform_admin, clinic_admin, therapist, patient) with role-based layouts. Auth is direct Supabase Auth (NOT NoctusAI SSO). Multi-tenant via `clinic_id` (not `org_id`). Schema: `therapy`. Backend port 8003, frontend port 8095. 39 database tables covering identity, scheduling, video sessions, clinical AI, financials, messaging, and reviews.

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

All shared backend modules use `from __future__ import annotations` for Python 3.9 compatibility.

## Python Virtual Environment

A **single root-level venv** (`venv/`) is shared by all backends. The root `requirements.txt` is the merged superset of both per-backend files. Per-backend `requirements.txt` files are kept for independent Docker deploys.

```bash
# First-time setup (or after pulling new deps)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

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

Tests use **pytest** with a fully mocked Supabase layer (299 core tests, 1549 ERP tests, 465 PF tests). Key fixtures are in `tests/conftest.py`:

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
- **RLS InitPlan optimization**: All RLS policies wrap `auth.uid()`, `auth.jwt()`, and `current_setting()` calls in subselects — `(SELECT auth.uid())` instead of `auth.uid()` — to prevent per-row re-evaluation. The therapy schema uses helper functions `therapy.current_user_role()` and `therapy.current_clinic_id()` for the same purpose. Never write a new RLS policy with a bare `auth.uid()` or `auth.jwt()` call.
- **Function search_path**: All PostgreSQL functions must include `SET search_path = <schema>, public` to prevent search path injection. This applies to both `erp` and `personal-finance` schema functions.

### Frontend Patterns

- **Toasts**: Use `import { toast } from 'sonner'`. Pattern: `toast.success("Msg")`, `toast.error("Msg", { description: "Details" })`. Never use the old `useToast` hook (deleted).
- **Centralized constants**: Status/type label maps live in `lib/constants.ts` (e.g., `PROPOSTA_STATUS_CONFIG`, `CONTRATO_STATUS_CONFIG`). All labels use proper Portuguese accents ("Concluído", "Locação", "Reunião"). Import from `@/lib/constants` — never define local copies.
- **Centralized utilities**: `formatCurrency()`, `formatDate()`, `getTodayAtMidnight()` live in `lib/utils.ts`. Never define local `formatCurrency` or inline `Intl.NumberFormat`.
- **Shared components**: Reusable cross-entity components live in `components/shared/` (e.g., `DocumentosTab` accepting `{ entityType, entityId }`). Prefer thin wrappers over copy-pasting.
- **TanStack Query hooks**: Every query hook must have: (1) `enabled: !!user` guard to prevent unauthenticated requests, (2) appropriate `staleTime` (reference data: 10min, active data: 2-3min, real-time: 30s), (3) correct `invalidateQueries` in related mutations (e.g., creating a locação must invalidate `['imoveis']`).
- **Zustand stores**: Date fields use `string | undefined` (ISO strings), not `Date`. Convert at component boundaries: `selected={dataInicio ? new Date(dataInicio) : undefined}`, `onSelect={(date) => setDataInicio(date?.toISOString())}`.
- **Auth initialization**: `authStore` has `isInitialized` flag. `AuthProvider` calls `setInitialized()` after `getSession()`. `AppContent` shows `<PageSkeleton />` while `!isInitialized` to prevent login form flash.
- **API client** (`lib/api-client.ts`): Handles 204 No Content, uses `safeFetch()` for all methods (not raw `fetch`). Body params typed as `unknown` (not `any`).
- **Validation schemas**: Deduplicate identical schemas (e.g., `corretorSchema = signUpSchema`). Schemas live in `lib/validations.ts`.
- **Modals**: Use `formData` state (not entity props) for display. Update UI instantly without closing modals.
- **Dates**: All date handling uses São Paulo timezone (America/Sao_Paulo). Server calculates dates via Supabase RPC `get_data_sp()`.

### Token Refresh & 401 Retry (All Products)

Supabase JWTs expire after ~1 hour. `supabase.auth.getSession()` returns a **cached** token that may already be expired — it does NOT auto-refresh. The auto-refresh (`onAuthStateChange`) happens asynchronously and there is a gap between expiry and refresh. During this gap, API calls fail with 401.

**Solution — automatic retry on 401 at the shared API client level:**

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

Admin-guarded endpoints: `POST /api/products`, `POST /api/licenses`, `DELETE /api/licenses/{id}`, all plan/subscription write operations, `GET /api/admin/api-keys`.

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

All tables are defined in `core/backend/migrations/001_noctusai_core.sql` (15 tables total for fresh deploys).

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

- **Provisioning lifecycle**: When a license is created in `public.licenses`, no mechanism bootstraps per-org data in the target product schema. The `license.granted` webhook fires to external URLs only, not to product backends.
- **Usage reporting**: Products don't report metrics back to core for billing/admin dashboards.
- **ERP `ativos` SELECT policy is `USING(true)`**: All authenticated users can read all ativos (cross-org). This is by current design (org filtering happens at the application layer) but is a candidate for tightening.

## Database Schema Separation

Tables are separated into **product-scoped PostgreSQL schemas**:

- **`public`** — Core platform tables (15 total: `noctus_users`, `organizations`, `products`, `licenses`, `plans`, `subscriptions`, `api_keys`, `roles`, `invitations`, `notifications`, `audit_logs`, `webhook_endpoints`, `webhook_deliveries`, `platform_settings`, `org_settings`) + auth hook functions (`handle_new_user`, `assign_default_corretor_role`, `has_role`)
- **`erp`** — ERP product tables (`metas`, `clientes`, `ativos`, `profiles`, `user_roles`, `condominios`, etc.) + all ERP business logic functions
- **`therapy`** — Therapy platform tables (39 total: `clinics`, `therapist_profiles`, `patient_profiles`, `appointments`, `video_rooms`, `session_records`, `session_summary_versions`, `wallets`, `transactions`, `conversations`, `messages`, `reviews`, `platform_settings`, etc.). Auth is direct Supabase Auth — users reference `auth.users(id)` directly. Multi-tenant via `clinic_id` (not `org_id`). 4-role RLS: platform_admin (full access), clinic_admin (own clinic), therapist (own data + patients), patient (own data). Helper functions `therapy.current_user_role()` and `therapy.current_clinic_id()` extract role/clinic from JWT metadata.

Each product backend's `database.py` uses `ClientOptions(schema="<schema>")` so all `.table()` and `.rpc()` calls target the correct schema automatically. Each product frontend's Supabase client uses `db: { schema: '<schema>' }` for data queries. The Core backend defaults to `public`.

**Supabase Dashboard** must have all product schemas (`erp`, `personal-finance`, `therapy`) in the "Exposed schemas" list (Project Settings → API) for PostgREST to accept the `Accept-Profile` header.

### Core migration files (`core/backend/migrations/`):
- `001_noctusai_core.sql` — Full core schema (15 tables, RLS policies with InitPlan optimization, FK indexes, seed data) for fresh deploys. All RLS policies use `(SELECT auth.uid())` subselect pattern. Includes `roles_read_own_org` SELECT policy.
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
