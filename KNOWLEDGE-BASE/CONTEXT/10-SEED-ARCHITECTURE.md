# 10 — Seed Architecture (The Spine)

> The seed is the spine of every NoctusAI product. All products inherit their structural infrastructure from `seed/`. Change the seed, change all products at once.

## Two Layers

| Layer | Backend Package | Frontend Package | Location | Purpose |
|-------|----------------|-----------------|----------|---------|
| Shared Library | `noctusai_shared` | `@noctusai/shared` | `seed/lib/` | Reusable code: auth, roles, hooks, components, utils |
| Framework | `noctusai_seed` | `@noctusai/seed` | `seed/framework/` | Structural bones: app factory, database, deps, routing |

## Backend Framework API (`noctusai_seed`)

### `create_product_app(name, schema, settings, routers, ...)`
Creates a fully configured FastAPI app. Includes: logging, database clients, auth dependencies, standard routers (health, notifications, team), CORS, Sentry, exception handlers, middleware, rate limiting.

### `ProductSettings`
Base Pydantic settings class. Provides: jwt_secret (with production safety check), core_api_url, cors_origins. Products extend with domain fields.

### `create_database_module(settings, schema)`
Returns a DatabaseModule with: `get_client(token)` (user-authenticated), `get_admin_client()` (service role), `get_core_client()` (public schema).

### `create_dependencies(db)`
Returns ProductDependencies with: `get_current_user()`, `get_user_role()`, `get_org_id()`, `get_user_client()`, `get_admin_client()`, `get_core_client()`.

### `create_standard_routers(deps, settings, product_name)`
Returns [health, notificacoes, team] routers. Every product gets these automatically.

## Frontend Framework API (`@noctusai/seed`)

### `createProductApp(config)`
Creates a complete App component with: QueryClientProvider, TooltipProvider, BrowserRouter, AuthProvider, ErrorBoundary, Suspense, standard public routes (landing, login, SSO, accept-invite, forgot-password), auth-gated routing.

### `createProductLayout(config)`
Creates a Layout component with: AppShell, Sidebar, Header, page status filtering, SSO context, trial/license warnings, activity refresh, inactivity warning, profile update handlers.

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
)
```

### Frontend (minimal App.tsx — ~80 lines with nav config)
```tsx
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import { NotificationBell } from "@/components/NotificationBell";
import type { NavGroupWithRoute } from "@noctusai/shared";
import type { NavGroup } from "@noctusai/shared/design-system";
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

### Frontend files you do NOT create (framework provides):
- No manual QueryClientProvider, BrowserRouter, AuthProvider, TooltipProvider wiring
- No Layout.tsx with AppShell/Sidebar/Header (createProductLayout handles it)
- No manual Vite alias/dedupe configuration
- No ErrorBoundary/Suspense/PageSkeleton wiring

### Frontend files you DO create (domain-specific):
- `src/pages/*.tsx` — product pages
- `src/components/*.tsx` — product components
- `src/hooks/*.ts` — TanStack Query hooks
- `src/store/authStore.ts` — createAuthStore() from shared
- `src/integrations/supabase/client.ts` — createProductSupabase() from shared
- `src/components/NotificationBell.tsx` — wraps shared NotificationBell with hooks
- `src/hooks/useNotificacoes.ts` — createNotificationHooks() from shared

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

## Rules

1. **Never duplicate seed code in a product.** If it's structural, it belongs in the seed.
2. **Products only contain domain code.** Routers, services, schemas, pages, components specific to that product.
3. **Test the seed before testing products.** If the seed breaks, everything breaks.
4. **The seed product (`products/seed/`) is the reference implementation.** Simplest product — just the spine.
