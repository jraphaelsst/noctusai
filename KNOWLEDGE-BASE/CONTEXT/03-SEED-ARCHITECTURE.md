# 10 — Seed Architecture (The Skeleton)

> The seed is the structural skeleton of every NoctusAI product. All products inherit their structural infrastructure from `seed/` through live imports. Change the skeleton, change every attached product at once.

## Seed as Skeleton

This is the platform's first-rule analogy:

- `seed/` = skeleton
- products = organs
- shared libraries = connective tissue / nervous system
- templates = scaffolding for future organisms, not the living anatomy of existing ones

The analogy is not decorative. It is an architectural decision rule.

### What the analogy means operationally

The skeleton owns structure:

- app assembly
- dependency wiring
- routing infrastructure
- auth/session plumbing
- layout primitives
- shared build wiring
- shared platform capabilities that multiple products should inherit automatically

The organs own domain behavior:

- product-specific routers
- product-specific services
- product-specific pages
- product-specific schemas
- product-specific workflows and UX

An organ can be different from another organ without growing its own skeleton.
That is the key distinction.

Products are allowed to specialize. They are not allowed to fork structural bones casually.

### The practical test

If a structural change requires manually editing multiple products, the skeleton model is drifting.

The desired state is:

- edit structure once in `seed`
- products inherit it automatically through imports
- products only adapt through named extension seams

### Practical decision test — 4 questions before any structural change

Any agent proposing or implementing a structural change MUST answer these four questions before writing code. A "no" on #4 is the alarm.

1. **Is this a bone or an organ?** — bones are structural infrastructure (app assembly, auth, layout, DB clients, routing). Organs are domain behavior (product-specific routers, pages, services).
2. **If it is a bone, why is it not in `seed/` yet?** — if the answer is "because the seed doesn't have a seam for this yet," the seed needs a new named seam (triage → formalize per `01-PHILOSOPHY.md § Triage at decision time`).
3. **If it is an organ, is it truly domain-specific or just duplicated structure wearing domain clothes?** — if the "domain" version looks like a generic pattern dressed in one product's vocabulary, extract it to shared lib (`noctusai_lib` / `@noctusai/lib`). Recurrence in ≥2 products is the signal.
4. **Will changing `seed` propagate this to every wired product automatically?** — if "no," the runtime-inheritance chain is broken. Investigate BEFORE shipping — products may be on stale installs, stale aliases, or have silently forked. Fix the inheritance first; ship the behavior change second.

This test is the operational form of the seed-first rule. Every triage outcome (formalize / refactor / accept-with-rationale per `01-PHILOSOPHY.md`) flows through this test.

### Runtime inheritance vs scaffold inheritance

These are different mechanisms and should never be conflated.

#### Runtime inheritance

This is the real skeleton model for existing products.

Examples:

- backend imports from `noctusai_seed`
- backend depends on `seed/framework/backend` and `seed/lib/backend`
- frontend imports from `@noctusai/seed` and `@noctusai/lib`
- frontend TS/Vite path aliases point directly to `seed/{lib,framework}/frontend/...`
- products assemble themselves through seed-owned factories

This is what should make existing products change automatically when `seed` changes.

#### Scaffold inheritance

This is only for creating future products.

Examples:

- `products/seed/`
- `templates/product-seed/`
- `scripts/sync-seed-template.sh`

This path is valid, but it is not the mechanism that keeps existing products aligned.

### Named seams vs structural forks

The skeleton model does not require all products to look identical.

Variation is allowed, but it must flow through named seams that the skeleton owns.

Examples of named seams:

- `standard_routers=[...]`
- `routers=[...]`
- `authProvider`
- `Layout`
- role routing configuration
- `lifespan_*` hooks

If a product needs a real structural variation and there is no seam for it yet, the default question is not:

- "should this product fork locally?"

The default question is:

- "should seed formalize a seam for this?"

Only after evaluating recurrence, scope, and complexity should the platform choose between:

- formalize a new seam
- refactor the product into an existing seam
- accept-with-rationale as a legitimate exception

### Documentation rule

The skeleton methodology has one deep authoritative home:

- this file

Thin model-specific root files such as `CLAUDE.md` and `OPENAI.md` should point here rather than duplicate the methodology in full.

When the skeleton rule evolves:

1. update this file first
2. update any other KB file that depends on the methodology
3. then sync the short pointer text in the model-specific outer maps

This preserves DRY across model families and across future agents.

## Two Layers

| Layer | Backend Package | Frontend Package | Location | Purpose |
|-------|----------------|-----------------|----------|---------|
| Shared Library | `noctusai_lib` | `@noctusai/lib` | `seed/lib/` | Reusable code: auth, roles, hooks, components, utils |
| Framework | `noctusai_seed` | `@noctusai/seed` | `seed/framework/` | Structural bones: app factory, database, deps, routing |

## Backend Framework API (`noctusai_seed`)

### `create_product_app(name, schema, settings, routers, *, standard_routers=(...), ...)`
Creates a fully configured FastAPI app. Includes: logging, database clients, auth dependencies, CORS, Sentry, exception handlers, middleware, rate limiting. Products opt into the bundled standard routers via `standard_routers=[...]` — valid names are the keys of `noctusai_seed.routers._STANDARD_ROUTERS`: `"health"`, `"notificacoes"`, `"team"`, `"llm"`, `"ai_outputs"`, `"ai_feedback"`. Pass `[]` to opt out entirely.

### `ProductSettings`
Base Pydantic settings class. Provides: jwt_secret (with production safety check), core_api_url, cors_origins. Products extend with domain fields.

### `create_database_module(settings, schema)`
Returns a DatabaseModule with: `get_client(token)` (user-authenticated), `get_admin_client()` (service role), `get_core_client()` (public schema).

### `create_dependencies(db)`
Returns ProductDependencies with: `get_current_user()`, `get_user_role()`, `get_org_id()`, `get_user_client()`, `get_admin_client()`, `get_core_client()`.

### `build_standard_routers(deps, settings, product_name, version, names)`
Returns only the named subset of standard routers. `names` is a sequence of strings drawn from the `_STANDARD_ROUTERS` registry keys (`"health"`, `"notificacoes"`, `"team"`, `"llm"`, `"ai_outputs"`, `"ai_feedback"`). Unknown names raise `ValueError` naming every invalid key and listing the valid set. Order is preserved. `create_product_app()` calls this internally based on the `standard_routers=[...]` kwarg — products don't invoke it directly.

## Frontend Framework API (`@noctusai/seed`)

### `createProductApp(config)`
Creates a complete App component with: QueryClientProvider, TooltipProvider, BrowserRouter, AuthProvider, ErrorBoundary, Suspense, standard public routes (landing, login, SSO, accept-invite, forgot-password), auth-gated routing.

### `createProductLayout(config)`
Creates a Layout component with: AppShell, Sidebar, Header, page status filtering, SSO context, trial/license warnings, activity refresh, inactivity warning, profile update handlers.

#### `LayoutEnrichment` — extension shape returned by the optional `useLayoutEnrichment` hook
Products inject domain-specific data (DB profile, conditional nav, theme persistence, etc.) without forking the layout. Fields are all optional. Notable extension points:

| Field | Use case |
|---|---|
| `userName` / `userEmail` / `userPhone` / `userAvatar` / `roleLabel` | Override Header user-display fields with product-DB-derived values. |
| `extraNavGroups` | Append conditional nav (e.g. admin panel only when role permits). |
| `effectiveDevRole` | Override page-status filter for dev-gated pages. |
| `onUpdateProfile` / `onThemePersist` / `initialTheme` | Custom profile/theme persistence callbacks. |
| `aiBadge` | **P4 pattern** (Tier 2 Phase 5, 2026-04-25). Optional `string \| ReactNode \| null` rendered next to the notification bell in the Header. Use for ambient AI signals: today's brief indicator, pending-consent count, monthly-spend watermark, "homework due" badge. Empty values auto-hide. |

## How Products Consume the Seed

### Backend (minimal main.py)
```python
from noctusai_seed import create_product_app, ProductSettings
from app.routers import domain_router_1, domain_router_2

class MySettings(ProductSettings):
    custom_field: str = ""

settings = MySettings()
app = create_product_app(
    name="My Product",
    schema="my_schema",
    settings=settings,
    routers=[domain_router_1.router, domain_router_2.router],
    standard_routers=["health", "notificacoes", "team"],  # opt into the bundled routers you actually consume
)
```

### Frontend (minimal App.tsx — ~80 lines with nav config)
```tsx
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import { NotificationBell } from "@/components/NotificationBell";
import type { NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";
import { LayoutDashboard, Users, Home, Mail } from "lucide-react";

const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Equipe = lazy(() => import("@/pages/Equipe"));
// ... more pages

const NAV_GROUPS: NavGroupWithRoute[] = [
  { key: "principal", label: "Principal", icon: Home, defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
    ],
  },
];

const NAV_FALLBACK: NavGroup[] = NAV_GROUPS.map(g => ({
  ...g, items: g.items.map(({ route, ...item }) => item),
})) as NavGroup[];

const Layout = createProductLayout({
  brandIcon: Mail,
  brandTitle: "Product Name",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  supabase,
  useAuthStore,
  NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/equipe", component: Equipe },
  ],
  Layout,
  supabase,
  useAuthStore,
  Landing: lazy(() => import("@/pages/Landing")),
  Login: lazy(() => import("@/pages/Login")),
  AcceptInvite: lazy(() => import("@/pages/AcceptInvite")),
  ForgotPassword: lazy(() => import("@/pages/ForgotPassword")),
  NotFound: lazy(() => import("@/pages/NotFound")),
});
```

### Frontend (`vite.config.ts` — 3 lines)
```ts
import { createViteConfig } from "../../../seed/framework/frontend/vite.config.factory";
export default createViteConfig({ port: 8120 });
```

### Frontend (`vitest.config.ts` — 3 lines)
```ts
import { createProductVitestConfig } from "../../../seed/framework/frontend/vitest.config.factory";
export default createProductVitestConfig();
```

### Frontend files you do NOT create (framework provides):
- No manual QueryClientProvider, BrowserRouter, AuthProvider, TooltipProvider wiring
- No Layout.tsx with AppShell/Sidebar/Header (createProductLayout handles it)
- No manual Vite alias/dedupe configuration
- No ErrorBoundary/Suspense/PageSkeleton wiring

### Frontend files you DO create (domain-specific only):
- `src/pages/*.tsx` — product pages (import `{ supabase, useAuthStore, api }` from `@noctusai/seed/infra`)
- `src/components/*.tsx` — product components
- `src/hooks/*.ts` — TanStack Query hooks (one per domain entity)

### Frontend files you do NOT create (framework provides via `@noctusai/seed/infra`):
- No authStore.ts, AuthProvider.tsx, ErrorBoundary.tsx
- No NotificationBell.tsx, useNotificacoes.ts
- No supabase/client.ts, api-client.ts
- No infra.ts — import directly from `@noctusai/seed/infra`

### Role-based routing (complex products like Therapy)
For products with multiple user roles that need different nav structures:
```tsx
// Create one layout per role using the framework
const AdminLayout = createProductLayout({ brandTitle: "Admin", navGroups: ADMIN_NAV, ... });
const UserLayout = createProductLayout({ brandTitle: "User", navGroups: USER_NAV, ... });

// Custom App.tsx with role-based routing (framework provides layouts, product provides routing)
```

## Migration Results (2026-04-15)

All 6 products migrated. Boilerplate reduced by 85% (3,188 → 483 lines). Framework code: 450 lines written once, inherited by all.

| Product | Before (lines) | After (lines) | Reduction |
|---------|----------------|---------------|-----------|
| Seed | 673 | 64 | -90% |
| Daily Life | 664 | 63 | -91% |
| PF | 603 | 91 | -85% |
| Therapy | 445 | 143 | -68% |
| ERP | 803 | 122 | -85% |
| Mailing | 0 (new) | 30 | Born from framework |

## Building New Products (for future agents)

When asked to create a new product, follow this pattern exactly:

### Backend (`main.py` — ~15 lines)
```python
from noctusai_seed import create_product_app, ProductSettings
from app.config import settings
from app.rate_limit import limiter
from app.routers import domain_router_1, domain_router_2

app = create_product_app(
    name="Product Name",
    schema="schema_name",
    settings=settings,
    routers=[domain_router_1.router, domain_router_2.router],
    limiter=limiter,
)
```

### Backend (`config.py` — ~10 lines)
```python
from noctusai_seed import ProductSettings

class MySettings(ProductSettings):
    cors_origins: str = "http://localhost:PORT,http://localhost:5173"
    # domain-specific fields here

settings = MySettings()
```

### Backend (`database.py` — ~6 lines)
```python
from noctusai_seed import create_database_module
from app.config import settings
db = create_database_module(settings, schema="schema_name")
get_supabase_client = db.get_client
get_core_client = db.get_core_client
get_admin_client = db.get_admin_client
```

### Backend (`dependencies.py` — ~8 lines + domain extensions)
```python
from noctusai_seed import create_dependencies, create_database_module
from app.config import settings
_db = create_database_module(settings, schema="schema_name")
deps = create_dependencies(_db)
get_current_user = deps.get_current_user
get_user_role = deps.get_user_role
get_org_id = deps.get_org_id
get_admin_client = deps.get_admin_client
```

### Backend (`requirements.txt`)
```
-e seed/lib/backend
-e seed/framework/backend
fastapi==0.115.0
# ... domain deps
```

You do NOT create: health.py, notificacoes.py, team.py — the framework provides them automatically.

## Product Registration

Products are registered in `public.products` table (Supabase). The Core dashboard reads from this table dynamically — no hardcoding. When creating a new product, insert a row:

```sql
INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES ('Product Name', 'slug', 'Description', 'LucideIcon', 'http://localhost:PORT', '#hex', true);
```

Fields: `nome` (display name), `slug` (unique identifier), `icone` (Lucide icon name), `url_base` (frontend URL), `cor` (hex color for cards), `ativo` (visible on dashboard).

The dashboard shows `has_access: true/false` per product based on the org's licenses (`public.licenses` table). Unlicensed products appear grayed out.

## New Product Checklist (complete before committing)

When creating a new product, ALL of these must be done before the first commit:

1. **Backend**: `main.py` uses `create_product_app()`, domain routers + services + schemas, tests passing
2. **Frontend**: `App.tsx` uses `createProductApp()` + `createProductLayout()`, `vite.config.ts` uses `createViteConfig()`
3. **Frontend hooks**: TanStack Query hooks wired to backend API (`useContacts`, `useCampaigns`, etc.)
4. **Frontend pages**: Real pages with API integration — NOT placeholders. Pages must fetch, submit, show loading.
5. **Database**: Migration applied via Supabase MCP
6. **Tests**: Backend tests passing, frontend builds
7. **Docs**: README.md + MASTER-PROMPT.md

"Scaffolded" is NOT "complete." Both backend and frontend must be at the same maturity level.

## Rules

1. **Never duplicate seed code in a product.** If it's structural, it belongs in the seed.
2. **Products only contain domain code.** Routers, services, schemas, pages, components specific to that product.
3. **Test the seed before testing products.** If the seed breaks, everything breaks.
4. **The seed product (`products/seed/`) is the reference implementation.** Simplest product — just the spine.

## Seed Contract

> **Authoritative source** for "seed-compliant." All downstream sections (Compliance check, Audit, Known violations) reference this. Extended 2026-04-22 (originating project archived after close).

The contract has four parts: what lives in seed, what products own, named extension seams, and out-of-contract patterns.

### 1. What MUST live in seed

The seed is the structural skeleton. Every item below is authored once in `seed/` and imported by products — never copy-pasted.

**Structural factories** (`seed/framework/backend/noctusai_seed/` + `seed/framework/frontend/@noctusai/seed/`):
- `create_product_app()` — FastAPI app assembly (logging, credentials, LLM, database, deps, middleware, CORS, Sentry, rate limiting, standard routers, product routers, lifespan).
- `create_database_module(settings, schema)` — Supabase client factories (user / admin / core-schema).
- `create_dependencies(db)` — `ProductDependencies` (auth, role resolution, org resolution, user/admin clients).
- `build_standard_routers(...)` — opt-in bundled routers dispatcher.
- `createProductApp(config)` — React app assembly (providers, routing, auth, error boundaries, suspense).
- `createProductLayout(config)` — standard Layout component.
- `createProductInfra(...)` — singleton exports of supabase / auth / api / notifications.

**Shared primitives** (`noctusai_lib` + `@noctusai/lib`):
- Auth helpers (`resolve_sso_role`, `first_or_none`, `make_get_current_user`).
- Role constants + label maps (`ORG_ROLES`, `ADMIN_ROLES`, `ORG_ROLE_LABELS`).
- Invitation lifecycle (`create_invitation`, `validate_invitation`, `accept_invitation`, `cancel_invitation`, `list_pending_invitations`, `send_product_invitation_email`).
- Notification mappers (`map_notification_to_pt`).
- Design-system components (`AppShell`, `Sidebar`, `Header`, `NotificationBell`, `LoginForm`, `PageSkeleton`, `InactivityWarning`).
- LLM access surface (`noctusai_lib.llm`: catalog, client, cache, usage).
- Testing helpers (`MockSupabaseClient`, `MockUser`, `AuthClient`, `MockSupabaseResponse`).

**Configuration factories:**
- `ProductSettings` / `BaseAppSettings` — base Pydantic settings with JWT production safety check.
- `createViteConfig({ port })` — shared Vite config + aliases.
- `createProductVitestConfig({ ... })` — shared Vitest config + aliases (jsdom + globals + e2e exclude + four seed-scope aliases). Mirrors `createViteConfig`'s skeleton/organ split.
- `tailwind.config.base` — shared Tailwind preset.
- Migration conventions (`products/<product>/backend/migrations/NNN_<name>.sql`, mirror-the-file rule).

**Test harnesses** (`seed/framework/backend/tests/`, `seed/lib/backend/tests/`, `seed/framework/frontend/tests/`).

### 2. What products are ALLOWED to own

**Domain code**: routers, services, schemas, pages, hooks — product-specific business logic.

**Product-specific configuration**:
- Extended `ProductSettings` subclass with domain fields.
- Product-specific `.env` overrides (per root `.env` rule).
- Product-scoped migrations in `products/<product>/backend/migrations/`.

**Product-specific UI chrome** *IF NOT* conflicting with seed's layout (e.g., brand-specific landing page content, domain navigation items via `navGroups` config, sidebar customization via `createProductLayout`'s `standaloneItems` / `brandSubtitleOverride` / `roleRoutes`).

**Product-specific rate limiter / lifespan hooks** — passed to `create_product_app()` as kwargs (`limiter`, `lifespan_startup`, `lifespan_shutdown`).

**Product-local test fixtures** (in `tests/conftest.py`) that compose the shared `MockSupabaseClient` etc.

### 3. Named approved extension seams

Any product customization MUST flow through one of these seams. Any customization NOT flowing through a named seam is a **structural fork** (contract violation) and must be either (a) refactored to use a seam, or (b) an existing seam extended to cover it, or (c) a new seam formalized in seed (Phase 4 of `seed-inheritance-hardening`).

**Backend seams** (kwargs / parameters on `create_product_app`):
| Seam | Purpose | Used by |
|---|---|---|
| `routers=[...]` | Product-specific domain routers. Always used. | Every product. |
| `standard_routers=[...]` | Opt into bundled seed routers (`health`, `notificacoes`, `team`, `llm`). | Every product (core: `["health"]`; therapy: `["health","notificacoes","llm"]`; etc.). |
| `limiter=` | Custom rate-limiter instance from `create_limiter(redis_url=...)`. | Every product. |
| `lifespan_startup=` / `lifespan_shutdown=` | Async callables for scheduler start/stop, recovery tasks. | mailing, personal-finance, erp (schedulers). |
| `llm_config=` | Override the default `LLMConfig` via `default_llm_config(**overrides)`. | Any product needing a non-default chat model, cache-off for sensitive content, etc. |
| `consent_features=` | Dotted module path whose import-time side effect populates the LGPD consent catalog (each product calls `register_feature(...)` from this module). The framework imports it once via `importlib.import_module(...)` after `configure_consent_module(...)`. Default `None` — products with no consent-gated AI features omit the kwarg. **Replaces** the old per-product `from app.services import ai_consent_features  # noqa: F401` line in `app/main.py` (formalized 2026-04-28). | mailing, ERP, daily-life, personal-finance, core, therapy-platform. |

**Frontend seams** (fields on `ProductAppConfig` / `ProductLayoutConfig`):
| Seam | Purpose | Used by |
|---|---|---|
| `routes` / `roleRoutes` | Product-specific pages + role-based routing. | Every product. |
| `Layout` | Custom Layout component. Accepts `{children}`. **Named extension seam** for products that can't or shouldn't use `createProductLayout()` (e.g., core's `CoreLayout` — admin branch + passthrough). | core. |
| `authProvider` | Custom auth provider — identity-source products that auth directly against their own backend (not Supabase). Shape: `{ AuthProvider, useAuth }`. | core. |
| `supabase` / `useAuthStore` | Default Supabase-based auth path. **Mutually exclusive with `authProvider`.** | Every consumer product. |
| `unauthRedirect` | Path to redirect unauth'd users. Defaults to `/landing`; core overrides to `/login`. | core. |
| `Landing` / `Login` / `AcceptInvite` / `ForgotPassword` / `NotFound` | Public-route components — optional. | Most products. |
| `publicRoutes` | Additional no-auth routes. | core (`/invite/:token`). |
| `unwrappedRoutes` | Routes rendered without `Layout` wrapper — for full-screen UIs (video sessions, etc.). | therapy. |
| `useLayoutEnrichment` (layout config) | Inject domain data (DB profiles, theme persistence, custom nav). | erp, therapy. |

**Cross-cutting seams:**
- `createProductSupabase(schema)` — product-specific Supabase client.
- `createAuthStore()` / `createFiltrosStore()` — Zustand store factories.
- `createCrudHooks<T>()` / `createNotificationHooks()` — TanStack Query hook factories.

**Dependencies extension pattern** (composition, not a kwarg). Formalized 2026-04-24 (originating projects archived). The canonical shape for adding product-specific auth / domain helpers on top of framework primitives without forking `app/dependencies.py`.

The principle: the framework exposes a small, generic surface (`get_current_user`, `get_user_client`, `get_admin_client`) via `create_dependencies(_db)`; products **import** that surface, **re-expose** it, and **add** their own helpers in the same module. No new kwarg on `create_product_app` is needed — composition handles it. Changing the framework primitive propagates to every product that re-exposes it.

Canonical shape (excerpt from `products/core/backend/app/dependencies.py`, post-v2):

```python
from noctusai_seed import create_database_module, create_dependencies

from app.config import settings

# ── Framework inheritance ──
_db  = create_database_module(settings, schema="public")
deps = create_dependencies(_db)

# Re-expose framework primitives unchanged.
get_current_user  = deps.get_current_user
get_user_client   = deps.get_user_client

# ── Product-specific extensions (compose, don't replace) ──
async def get_current_admin(authorization = Header(None)):
    user, token = await get_current_user(authorization)   # ← re-uses framework
    # …product-specific role check on `noctus_users.role == 'admin'`…
    return user, token

async def get_org_id(user) -> str:
    # Core's source-of-truth is the `noctus_users` table, not user_metadata.
    # This HELPER overrides framework's default `deps.get_org_id` by name-collision
    # on import — explicit, local-to-core behavior.
    ...
```

Rules for the pattern:
- **Re-expose, don't wrap.** `get_current_user = deps.get_current_user` is a reference, not a new function. If a product needs to *modify* the behavior (e.g., add logging around auth), wrap it — but only for that specific helper.
- **Override by name-collision when justified.** If a product's domain truly needs a different shape than the framework default (e.g., core's `async get_org_id(user)` reads from DB; framework's sync `get_org_id(user)` reads `user_metadata`), redefine the name in the product's module. The override is local; other products keep the framework behavior. Document the reason in a docstring (§11 of the PROJECT.md that introduced the override is the canonical reference).
- **Extensions compose on top, never inside.** `get_current_admin` calls `await get_current_user(...)` — it reuses the framework primitive. It does NOT redefine `get_current_user` with admin logic baked in.
- **No new kwarg, ever.** If you find yourself proposing `create_product_app(..., customDependencies=...)`, you're solving the wrong problem. Composition at the module level IS the seam.

Which products use this pattern (as of 2026-04-24):
- **core** — `get_current_admin`, `get_current_user_with_permissions`, `get_org_id` (DB-backed override), `check_org_license`, `get_licensed_product_ids`.
- **therapy-platform** — therapist/patient role resolvers, session-scope helpers.
- **erp-imobiliario** — team-based permission helpers on top of `resolve_sso_role`.
- **personal-finance** — minimal (framework primitives suffice for most endpoints).

Recurrence signal: if 3+ products end up with near-identical helpers (e.g., `get_current_admin` appears in core + a hypothetical 2nd identity-source product with the same shape), promote the shared helper to `noctusai_seed.dependencies` or `noctusai_lib.auth` per the *promote-on-second-occurrence* rule.

**Control-plane product seam** (role-level, not a single kwarg). Added by `core-seed-wiring-v2` Phase 4 (2026-04-23).

A **control-plane product** is a product that OWNS identity endpoints (`/api/auth/*`, `/api/sso/*`, `/api/oauth/*`) and `public` schema identity tables (`organizations`, `noctus_users`, `roles`, `licenses`, `subscriptions`, `api_keys`). It uses the standard framework factories like any consumer product — `create_product_app(name=..., schema="public", routers=[...])`, `create_database_module(settings, schema="public")`, `create_dependencies(_db)`. The DIFFERENCE is the set of primitives it composes:

| Primitive | Where it lives | Purpose for control-plane |
|---|---|---|
| `create_sso_token_factory(settings)` | `noctusai_lib.auth` | Returns a callable that mints short-lived SSO JWTs for cross-product launch. Parameterized by `settings.jwt_secret` + `settings.jwt_algorithm` + `settings.sso_token_expiration_minutes`. |
| `verify_sso_token_factory(settings)` | `noctusai_lib.auth` | Returns a callable that validates SSO JWTs. Raises `HTTPException(401)` on expired / invalid / non-SSO. |
| `SSOSessionCache(ttl_seconds=300)` | `noctusai_lib.auth` | Thread-safe in-memory cache of Supabase sessions per email with TTL + per-key locks + explicit invalidation API. Flush on role-change / license-revoke / org-reassign via `cache.invalidate(email)`. |

The endpoint routers themselves (`auth.py`, `sso.py`, `oauth.py`) remain **organ routers** in the product — they're not bundled in framework's `standard_routers`. **Recurrence rule**: promote endpoint routers to framework's bundle if and only if a **second** control-plane product surfaces. Today's sole consumer is `core`; the lib primitives exist to make a 2nd identity-source product trivial to wire.

Frontend-side control-plane shape: `createProductApp({ authProvider, Layout, unauthRedirect: '/login', Login, publicRoutes })` — uses the `authProvider` seam instead of the default Supabase path (see row in frontend seams table above).

### 4. Divergences worth surfacing (triage at decision time)

The contract describes the **ideal shape**. Each pattern below is a *divergence worth surfacing* — not an automatic failure. Finding one in a product triggers triage per `KB § 01-PHILOSOPHY.md § Triage at decision time`: each divergence lands on **formalize** (extend the seam), **refactor** (align with the contract), or **accept-with-rationale** (document why the divergence is legitimate in PROJECT.md §11 / MASTER-PROMPT.md).

Rows marked 🔧 are **mechanical-inheritance** items — the physics that makes propagation work. A product without editable installs cannot receive seed updates; a product without `createProductApp` cannot assemble providers in the shared shape. These are refactor-or-it-doesn't-work items, not triageable. Rows without 🔧 are policy-level and fully triageable.

| Pattern | Why it's worth surfacing | Typical triage |
|---|---|---|
| 🔧 Direct `FastAPI()` instantiation in `products/<product>/backend/app/main.py` | Bypasses `create_product_app()` behavior (logging, creds, LLM config, middleware, standard routers) — mechanical inheritance broken. | **Refactor.** Migrate to `create_product_app()`. |
| 🔧 `from @noctusai/seed` missing from `main.tsx` / `App.tsx` | Frontend bypasses `createProductApp` — mechanical inheritance broken. | **Refactor.** |
| 🔧 `vite.config.ts` not using `createViteConfig()` | Vite alias + envDir + PRODUCT_MAP bindings bypass — mechanical inheritance broken. | **Refactor.** |
| 🔧 `vitest.config.ts` not using `createProductVitestConfig()` | jsdom + globals + e2e exclude + seed alias resolution bypass — every product would re-derive the same shape and drift on canonical changes. Mechanical inheritance broken. | **Refactor.** |
| 🔧 `tailwind.config.ts` not importing the shared `tailwind.config.base` preset | Design-system drift at build time. | **Refactor.** |
| 🔧 `requirements.txt` missing `-e seed/{lib,framework}/backend` | No editable install → no live seed propagation. | **Refactor.** |
| Product-level `AuthProvider` / `BrowserRouter` / `QueryClientProvider` wiring | Should flow through `createProductApp`; if custom auth is legitimately needed → use `authProvider` seam. | **Formalize** (new seam) or **refactor** (use existing seam) or **accept** if genuinely unique. Core's `authProvider` case was formalized 2026-04-22. |
| Reimplementing `create_database_module` (custom `make_supabase_client` factory in product code) | Framework DB factory changes don't propagate; stale when seed evolves. | **Refactor.** Core was the last standing case; resolved 2026-04-23 by `core-seed-wiring-v2` Phase 1 (`app/database.py` 35→14 LOC, delegates to `create_database_module(settings, schema="public")`). Zero products today reimplement the factory. |
| Custom `get_current_user` / `get_user_role` / `get_org_id` in `app/dependencies.py` instead of consuming `create_dependencies()` | Shallow inheritance — framework deps can't evolve into products. | **Refactor via composition.** Core's case resolved 2026-04-23 by `core-seed-wiring-v2` Phase 2 (re-exposes `deps.get_current_user`/`get_user_client`; adds product-specific helpers on top). Pattern formalized as **§ 3 Dependencies extension pattern** above on 2026-04-24. Future products with the same need: follow the canonical shape there; do NOT fork `dependencies.py`. |
| Own `<product>/backend/app/routers/{team,notificacoes,health}.py` when opting into those standard routers | Collision with seed's bundled routers. | **Refactor** (drop local, opt in) OR **accept** (self-provide, opt out — core's pattern; `check_standard_routers_audit` respects self-provision). |
| Product-like tree living OUTSIDE `products/*/` | Bypasses every platform convention, compliance check, and audit surface. | **Refactor** (migrate into `products/<name>/`) OR **accept** with formal classification + migration plan (e.g., `/adconnect/` was tracked by `projects/adconnect-migration/` and reconciled 2026-04-22). |
| Stray `.md` docs at repo root (audit handoffs, session recaps) | Violates `KB § PATTERNS/project-execution.md § 11 Clean-folder principle`. | **Refactor** (absorb into appropriate project folder) OR **accept** (platform-wide file like `CLAUDE.md`). |
| Reimplementing notification-field mapping (English ↔ Portuguese) per product | Duplicated logic; stale when seed's mapper evolves. | **Refactor.** Use `noctusai_lib.notifications.map_notification_to_pt`. |

**Recurrence signal**: if the same policy-level divergence triages to `accept` in 2+ products, re-evaluate toward `formalize` — strong evidence the framework is under-serving a real need.

### 5. Contract enforcement

The contract is validated at three layers:

1. **Compliance check** (`python mcp/noctusai/cli.py --review`) — deterministic detectors in `mcp/noctusai/tools/compliance.py`:
   - `check_seed_compliance` — `create_product_app` presence, editable installs, no boilerplate routers on products that opt in, frontend wiring. Control-plane-aware via `CONTROL_PLANE_PRODUCTS = {"core"}` — core legitimately owns `team.py` / `notifications.py` / custom `Layout.tsx` (identity source), so those warnings are suppressed for it.
   - `check_path_references` — catches stale `shared/*` paths that should be `seed/*`.
   - `check_standard_routers_audit` — cross-audits `standard_routers=[...]` opt-in vs real frontend usage via signal map. **Self-provision v2** (AST): parses `routers=[<mod>.router, ...]` in `main.py` to detect actually-wired routers; a file-on-disk that isn't wired no longer counts (would 404). Falls back to filename-based when AST is unparseable.
   - `check_frontend_entrypoint` — verifies `main.tsx` (or its delegated `App.tsx`) actually CALLS `createProductApp(...)`. Rendering a raw `<BrowserRouter>` / `<QueryClientProvider>` tree without the factory is flagged `critical`.
   - `check_config_extends_product_settings` — AST-walks `backend/app/config.py` and asserts every class extending `BaseAppSettings` also extends `ProductSettings`. Direct `BaseAppSettings` extension is a structural fork: the product duplicates env_file resolution and loses the seed's `parents[4] / .env` math. Added 2026-04-25 by the `keeper-config-inheritance-audit` project (shipped + folder deleted per clean-folder rule; detector code lives at `mcp/noctusai/tools/compliance.py`). Origin: same-day `core-seed-wiring` Phase 6 regression (`parents[3]`-vs-`parents[4]` bug → silent `supabase_url=""` → 500 on login). Severity `critical`.
   - `check_frontend_config_paths` — regex-extracts every quoted relative path containing `seed/` from `frontend/vite.config.ts`, `frontend/tailwind.config.ts`, and `frontend/postcss.config.js`; resolves each against the config file's location (with TS module-resolution fallback for extensionless imports + glob-prefix resolution for tailwind content arrays); flags any path that doesn't resolve to an existing target. Added 2026-04-25 by the `keeper-frontend-config-paths-audit` project (shipped + folder deleted per clean-folder rule; detector code lives at `mcp/noctusai/tools/compliance.py`). Origin: 2026-04-20 seed-relocation broke core's frontend (`../../seed/` → `../../../seed/`). Severity `critical`.
   - `check_out_of_contract_trees` — global repo-root sweep; flags any product-shaped directory (has `backend/app/main.py` or `frontend/src/main.tsx`) that lives outside `products/*/`. Remediation pointer: migrate via `<name>-seed-wiring` project OR delete if legacy.
2. **Runtime propagation check** (planned, `seed-inheritance-hardening` Phase 3) — `__seed_version__` instrumentation; each product's boot path reports the version; keeper detects drift.
3. **Audit command** (see § Compliance check below) — bash grep for missing wiring across all products.

Failing any layer → contract violation → either remediate via a `<product>-seed-wiring` project OR formalize the divergence via Phase 4 of `seed-inheritance-hardening`.

## Compliance check

Every product under `products/` **must** inherit from the seed framework, not just the library. A product that uses only `noctusai_lib` / `@noctusai/lib` but instantiates `FastAPI()` / `createRoot()` directly is **not compliant** — it's using the reusable code but bypassing the shared structure that makes the "change the seed, change everything" guarantee work.

### What "compliant" looks like

**Backend** (`products/<product>/backend/app/main.py`):

```python
from noctusai_seed import create_product_app, ProductSettings

app = create_product_app(
    name="<Product Name>",
    schema="<product-schema>",
    settings=settings,
    routers=[...],  # product-specific domain routers only
)
```

**Frontend** (`products/<product>/frontend/src/main.tsx`):

Consumer products (Supabase auth):

```tsx
import { createProductApp } from "@noctusai/seed";
import { supabase, useAuthStore } from "@noctusai/seed/infra";

const App = createProductApp({
  supabase,
  useAuthStore,
  routes,
  Layout,
  Login,
  // ...
});
```

Control-plane products — core only today (identity-source auth, see § Control-plane vs. consumer products):

```tsx
import { createProductApp } from "@noctusai/seed";
import { coreAuthProvider } from "./lib/seed-auth-adapter";

const App = createProductApp({
  authProvider: coreAuthProvider,
  routes,
  Layout,
  Login,
  unauthRedirect: "/login",
  // ...
});
```

### Audit — "who is NOT wired?"

The right question is always **who is *not* wired**, not who uses the framework. All products should; the audit looks for violators:

```bash
# Backend violators
for p in products/*/; do
  name=$(basename "$p")
  grep -q "create_product_app" "$p/backend/app/main.py" 2>/dev/null || echo "  ✗ $name (backend not wired)"
done

# Frontend violators
for p in products/*/; do
  name=$(basename "$p")
  if [ -f "$p/frontend/src/main.tsx" ]; then
    grep -qE "@noctusai/seed|createProductApp" "$p/frontend/src/main.tsx" "$p/frontend/src/App.tsx" 2>/dev/null || echo "  ✗ $name (frontend not wired)"
  fi
done
```

### Known violations

None. Every product under `products/` is seed-compliant on both backend and frontend as of 2026-04-22 (closure of the `core-seed-wiring` project). `products/core` — the last open case — inherited from the framework on its backend via `create_product_app(standard_routers=["health"])` and on its frontend via `createProductApp({ authProvider: coreAuthProvider })` (see § Control-plane vs. consumer products below for the two auth paths).

### Control-plane vs. consumer products

Two shapes of product inherit from the seed, distinguished by their auth model:

**Consumer products** (`personal-finance`, `erp-imobiliario`, `therapy-platform`, `mailing`, `daily-life`, `adconnect`, `seed`) — auth flows through **Supabase** on the frontend. Users log in, Supabase creates a session (delegating to core's backend for credential verification), and the product's frontend uses Supabase's client SDK (`supabase.auth.getSession()`, `.onAuthStateChange()`, RLS-scoped queries with auto-set JWT headers). These products call:

```ts
createProductApp({ supabase, useAuthStore, routes, Layout, ... })
```

**Control-plane products** (`core` today; potentially future dedicated admin UIs) — IS the identity provider Supabase delegates to. A Supabase-client-auth path would be circular. Instead these products auth directly against their own backend (custom JWT + refresh-token, OAuth hash-callback, etc.) and supply a `CustomAuthProvider` to the framework:

```ts
createProductApp({ authProvider: customAuthProvider, routes, Layout, unauthRedirect: "/login", ... })
```

`CustomAuthProvider` is a pair of `{ AuthProvider: React.ComponentType, useAuth: () => { user, isInitialized } }` — the framework uses these for route guards and role resolution. `supabase` and `useAuthStore` are not read when `authProvider` is present.

**When a new product needs `authProvider`:** only if it is the identity source itself. If it consumes identity (auths users, reads RLS-scoped data), it is a consumer product and uses the Supabase path. Every consumer product should continue to use the default; adding `authProvider` to a consumer product would throw away Supabase's real-time subscriptions, RLS-header enforcement, and built-in OAuth/SSO flows with no architectural benefit.

### If you find a new non-compliant product

### If you find a new non-compliant product

Do **not** paper over the gap by duplicating what the seed provides. Do **not** defer indefinitely. File a project:

- Slug: `<product>-seed-wiring` (intent=`wiring` per `PATTERNS/project-execution.md §8`).
- Location: `products/<product>/projects/<product>-seed-wiring/PROJECT.md` from `templates/PROJECT-TEMPLATE.md`.
- Scope: move the product onto the framework factories; keep the test baseline green; ship behind the product's existing deploy.

The directory tree under `products/` already implies "all of these are seed-inheriting products" — a silent non-compliant entry lies to every agent who reads it.
