# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

This is a **multi-tenant, multi-product SaaS monorepo**. Each organization (tenant) signs up once on the core platform and gets access to licensed products. Tenant isolation is enforced at the database level via Supabase RLS policies scoped to `org_id`, so data from one organization is never visible to another. Products are independently deployable but share authentication and tenant context through SSO.

- **`core/`** — NoctusAI Platform foundation: authentication, organizations, products, licenses, SSO. Manages tenants, user-to-org mapping, and cross-product access. Every user belongs to an organization; every product access requires an active license for that org.
- **`products/erp-imobiliario/`** — Real estate CRM product: client management, property listings (ativos), sales funnel, matching algorithm, goal tracking. All data is scoped to the user's organization.

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

Tests use **pytest** with a fully mocked Supabase layer. Key fixtures are in `tests/conftest.py`:

- `MockSupabaseClient` / `MockQueryBuilder` — Chainable query builder that simulates Supabase PostgREST
- `AuthClient` — Wraps FastAPI `TestClient` with automatic `Authorization: Bearer` headers
- `client` fixture — Fully wired test client with mocked auth and logging

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
CORE_API_URL=http://localhost:8001
SENTRY_DSN=          # Optional
REDIS_URL=           # Optional
OPENAI_API_KEY=      # Optional (ERP product)
```

Frontend uses `VITE_`-prefixed vars in their own `.env` files (security boundary — frontend vars end up in browser bundles).

## Key Patterns

- **Auth in routers**: Every protected endpoint takes `authorization: Optional[str] = Header(None)` and calls `await get_current_user(authorization)` which returns `(user, token)`. Admin-only endpoints use `await get_current_admin(authorization)` which additionally verifies `noctus_users.role == "admin"`.
- **Responses**: List endpoints return `paginated_response(data, total, page, page_size)`. Single items return `success_response(data)`. Deletes return `ok_response(message)`.
- **Pagination**: All list endpoints accept `page` and `page_size` query params. Pagination is implemented via Supabase `.range()`.
- **Validation**: Pydantic models use `Field()` constraints (ge, le, max_length). Use `Literal` types for enum-like fields.
- **Error handling**: Raise `HTTPException` for simple cases. Use custom `AppException` subclasses for structured errors. All exceptions are caught by centralized handlers in `main.py`.
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

### Database tables (Supabase)
- **`plans`** — Plan definitions with pricing, limits, Stripe-ready fields
- **`subscriptions`** — Org subscriptions with status tracking (active/canceled/expired/trial)
- **`api_keys`** — Hashed API keys with scopes and expiry

SQL for creating these tables is documented as comments in each router file.

### Frontend (`core/frontend/src/`)
- **`lib/auth-context.tsx`** — `AuthProvider` + `useAuth()` hook providing `{ user, organization, isAdmin }` globally
- **`components/AdminLayout.tsx`** — Sidebar layout with navigation for admin pages
- **`pages/admin/`** — Admin pages: Dashboard, Organizations, Subscriptions, API Keys, Plans
- **Admin routes**: `/admin`, `/admin/orgs`, `/admin/subs`, `/admin/api-keys`, `/admin/plans` — all protected by `AdminRoute` (redirects non-admins to `/`)

## Language

The codebase uses **Portuguese (Brazilian)** for business domain terminology (clientes, metas, ativos, funil, etc.) and English for technical/framework concepts. Error messages returned to users are in Portuguese.
