# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Engineering Philosophy

**No workarounds. Ever.** Always implement the correct solution using the real API, SDK, or framework behavior — even when it adds complexity. Monkeypatches, shims, hacks, and "temporary" fixes are not acceptable. If the proper solution requires touching more files, adding abstractions, or refactoring existing code, that is the right path. Complexity in service of correctness and solidity is a worthwhile trade-off; fragile shortcuts are not.

## Architecture

This is a **multi-tenant, multi-product SaaS monorepo**. Each organization (tenant) signs up once on the core platform and gets access to licensed products. Tenant isolation is enforced at the database level via Supabase RLS policies scoped to `org_id`, so data from one organization is never visible to another. Products are independently deployable but share authentication and tenant context through SSO.

- **`core/`** — NoctusAI Platform foundation (20 routers, 8 services): authentication, organizations, products, licenses, SSO, notifications, webhooks, audit logs, settings. Manages tenants, user-to-org mapping, and cross-product access. Every user belongs to an organization; every product access requires an active license for that org.
- **`products/erp-imobiliario/`** — Real estate CRM product with 46 routers and 37 services: client management, property listings (ativos), sales funnel, AI matching, financial operations, WhatsApp messaging, digital signatures, PDF generation, notifications, Meta Ads integration, and compliance reporting. All data is scoped to the user's organization.

Both layers follow the same stack: **FastAPI + Supabase** backend, **React + TypeScript + Vite** frontend. Each has independent backend and frontend directories.

### Backend Layers (FastAPI)

```
routers/     → HTTP handlers (thin: auth + validation + delegation)
services/    → Business logic (matching algorithm, CRUD orchestration)
schemas/     → Pydantic models for request/response
dependencies.py → Auth helpers (get_current_user, get_user_client, get_admin_client)
database.py  → Supabase client singleton
exceptions.py → Centralized error handling (AppException hierarchy)
middleware.py → Correlation IDs, request logging
```

**Supabase client pattern**: `get_user_client(token)` respects RLS; `get_admin_client()` uses service role (admin-only operations).

### Frontend Layers (React)

```
pages/       → Route-level components
components/  → UI components (shadcn/ui base + domain-specific)
hooks/       → TanStack Query hooks per domain (useMetas, useClientes, etc.)
store/       → Zustand stores (authStore, filtrosStore)
lib/         → API client, validation schemas, utilities
types/       → TypeScript definitions
```

State management: **Zustand** for global UI state, **TanStack Query** for server state.

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
pytest tests/routers/test_matching_service.py::TestCompatibilidadeRegiao::test_exact_city_state_bairro_match -v
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

### Full Stack (Replit)

```bash
bash start.sh    # Creates root venv, installs deps, starts all backends + frontends
```

## Testing

Tests use **pytest** with a fully mocked Supabase layer (294 core tests, 986 ERP tests). Key fixtures are in `tests/conftest.py`:

- `MockSupabaseClient` / `MockQueryBuilder` — Chainable query builder that simulates Supabase PostgREST
- `AuthClient` — Wraps FastAPI `TestClient` with automatic `Authorization: Bearer` headers
- `client` fixture — Fully wired test client with mocked auth and logging
- Core also has `admin_client` (admin role) and `unauth_client` (no auth) fixtures

Integration tests in `tests/integration/` use `StatefulMockClient` that persists data across operations for CRUD cycle testing.

Test naming convention: `test_{router_name}_router.py` for router tests, `test_{service_name}_service.py` for service tests.

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
OPENAI_API_KEY=      # Optional (ERP product)
RESEND_API_KEY=      # Optional (email delivery)
CLICKSIGN_API_TOKEN= # Optional (digital signatures)
```

Frontend uses `VITE_`-prefixed vars in their own `.env` files (security boundary — frontend vars end up in browser bundles).

## Key Patterns

- **Auth in routers**: Every protected endpoint takes `authorization: Optional[str] = Header(None)` and calls `await get_current_user(authorization)` which returns `(user, token)`. Admin-only endpoints use `await get_current_admin(authorization)` which additionally verifies `noctus_users.role == "admin"`.
- **Responses**: List endpoints return `paginated_response(data, total, page, page_size)`. Single items return `success_response(data)`. Deletes return `ok_response(message)`.
- **Pagination**: All list endpoints accept `page` and `page_size` query params. Pagination is implemented via Supabase `.range()`.
- **Validation**: Pydantic models use `Field()` constraints (ge, le, max_length). Use `Literal` types for enum-like fields.
- **Error handling**: Raise `HTTPException` for simple cases. Use custom `AppException` subclasses for structured errors. All exceptions are caught by centralized handlers in `main.py`. Both backends register a `postgrest_exception_handler` that catches Supabase PostgREST `APIError` with code `PGRST116` (`.single()` returning 0 rows) and converts it to a 404 response.
- **Logging**: Structured JSON in production, human-readable in dev. Every request gets a correlation ID via middleware.
- **Frontend modals**: Use `formData` state (not entity props) for display. Update UI instantly without closing modals. See `AGENTIC-WORKFLOW/CONTEXT/03-ERP-FRONTEND.md` (Modal Patterns section).
- **Dates**: All date handling uses São Paulo timezone (America/Sao_Paulo). Server calculates dates via Supabase RPC `get_data_sp()`. See `AGENTIC-WORKFLOW/CONTEXT/03-ERP-FRONTEND.md` (Date & Timezone Patterns section).

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

## Database Schema Separation

Tables are separated into **product-scoped PostgreSQL schemas**:

- **`public`** — Core platform tables (15 total: `noctus_users`, `organizations`, `products`, `licenses`, `plans`, `subscriptions`, `api_keys`, `roles`, `invitations`, `notifications`, `audit_logs`, `webhook_endpoints`, `webhook_deliveries`, `platform_settings`, `org_settings`) + auth hook functions (`handle_new_user`, `assign_default_corretor_role`, `has_role`)
- **`erp`** — ERP product tables (`metas`, `clientes`, `ativos`, `profiles`, `user_roles`, `condominios`, etc.) + all ERP business logic functions

The ERP backend's `database.py` uses `ClientOptions(schema="erp")` so all `.table()` and `.rpc()` calls target the `erp` schema automatically. The ERP frontend's Supabase client uses `db: { schema: 'erp' }` so all direct `.from()` calls also target the `erp` schema. The Core backend defaults to `public`.

**Supabase Dashboard** must have `erp` in the "Exposed schemas" list (Project Settings → API) for PostgREST to accept the `Accept-Profile: erp` header.

### Core migration files (`core/backend/migrations/`):
- `001_noctusai_core.sql` — Full core schema (15 tables, RLS policies, seed data) for fresh deploys
- `002_missing_tables.sql` — Adds 6 tables (notifications, audit_logs, webhooks, settings) to existing databases

### ERP migration files (`products/erp-imobiliario/backend/migrations/`):
- `001_erp_imobiliario.sql` — Creates `erp` schema + all ERP objects (fresh deploys)
- `002_ai_matching.sql` — pgvector embeddings in `erp` schema
- `003_schema_separation.sql` — Moves existing objects from `public` → `erp` (existing databases only)
- `004_mvp_expansion.sql` — 42 new tables for MVP expansion (existing databases)
- `005_fix_sidebar_pages.sql` — Fix `set_timestamps_sp()` trigger, seed all sidebar routes, admin role setup

## External Integrations (Dry-Run Pattern)

All external integrations follow a **dry-run pattern**: when API keys/credentials are not configured, services log actions and return mock responses. This allows development and testing without real API keys. Credential resolution chain: `org_settings` table → `platform_settings` table → environment variables.

Integrations: Resend (email), ClickSign/DocuSign/D4Sign (digital signatures), Meta Graph API (Lead Ads, campaign sync), WAHA/Meta Business API (WhatsApp), Supabase Storage (file uploads), reportlab (PDF generation).
