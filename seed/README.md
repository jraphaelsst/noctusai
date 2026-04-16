# The Seed — Spine of Every NoctusAI Product

The `seed/` directory is the structural foundation of the entire NoctusAI platform. Every product — existing and future — inherits its infrastructure from here. **Change the seed, change all products at once.**

## Architecture: Two Layers

```
seed/
  lib/          noctusai_shared    Code library (auth, roles, hooks, components, utils)
  framework/    noctusai_seed      Structural framework (app factory, database, deps, routing)
```

### Layer 1: Shared Library (`seed/lib/`)

Reusable, atomic code that products import as functions and components.

- **Backend** (`noctusai_shared`): auth, roles, invitations, email_templates, notifications, config, database, app_factory, exceptions, middleware, logging, testing
- **Frontend** (`@noctusai/shared`): api, sso, roles, page-status, auth, stores, hooks, notifications, supabase, components, design-system

**How products consume it:** `from noctusai_shared.auth import ...` / `import { ... } from '@noctusai/shared'`

### Layer 2: Framework (`seed/framework/`)

Structural bones that define HOW a product is assembled. Products don't copy this code — they import and extend it.

- **Backend** (`noctusai_seed`): `create_product_app()`, `ProductSettings`, `create_database_module()`, `create_dependencies()`, `create_standard_routers()`
- **Frontend** (`@noctusai/seed`): `createProductApp()`, `createProductLayout()`

**How products consume it:** A product's `main.py` becomes ~10 lines. Its `App.tsx` becomes ~30 lines. All the structural wiring is inherited.

## The Spine Metaphor

Think of it like a human body:

- **Seed = spine + skeleton.** The structural bones that hold everything together.
- **Products = organs + muscles.** Domain-specific functionality that serves a purpose.
- **Shared library = blood + nervous system.** Reusable utilities that flow through everything.

You don't build a new spine for every organ. You attach the organ to the existing spine. If the spine gets stronger, every organ benefits.

## How Changes Propagate

| What changed | What happens |
|-------------|-------------|
| Fix in `seed/lib/` | All products get the fix (it's an imported dependency) |
| Fix in `seed/framework/` | All products get the fix (it's an imported dependency) |
| New shared component | Available to all products immediately via import |
| New framework feature | Available to all products immediately via import |

**This is NOT a copy-paste model.** Products don't snapshot the seed — they reference it live. One source of truth, many consumers.

## Product Architecture After Seed

A product using the seed framework looks like this:

### Backend (`products/<name>/backend/app/main.py`)
```python
from noctusai_seed import create_product_app, ProductSettings

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

That's it. Health check, team management, notifications, CORS, Sentry, logging, JWT validation, database clients — all inherited from the seed.

### Frontend (`products/<name>/frontend/src/App.tsx`)
```tsx
import { createProductApp, createProductLayout } from '@noctusai/seed';

const Layout = createProductLayout({ brandIcon: Mail, brandTitle: "My Product", ... });
const App = createProductApp({ routes, Layout, supabase, useAuthStore, ... });
export default App;
```

TooltipProvider, QueryClient, AuthProvider, ErrorBoundary, Suspense, routing, page status filtering — all inherited from the seed.

## Rules (Non-Negotiable)

1. **Every product MUST inherit from the seed.** Use `create_product_app()` and `createProductApp()`. No exceptions, no alternatives, no "I'll do it manually this time." This is the #1 engineering rule of the platform.
2. **Never duplicate seed code in a product.** If you need structural code, it belongs in the seed. If you find yourself writing auth logic, database client setup, health checks, team management, notification proxies, or layout/routing boilerplate — stop. It already exists in the seed.
3. **Products only contain domain code.** Routers, services, schemas, pages, components specific to that product's purpose. Everything else comes from the seed.
4. **The seed is the most important piece of infrastructure.** It is the skeleton of every product. Breaking the seed breaks everything. Improving the seed improves everything.
5. **The seed product (`products/seed/`) is the reference implementation.** It's the simplest possible product — just the spine, no organs. Use it to verify the framework works.
6. **Test the seed before testing products.** If the seed breaks, everything breaks.
7. **Document changes to the seed in CLAUDE.md.** The seed is critical infrastructure.
8. **AI agents must use the seed without asking.** When instructed to create a new product, agents should immediately scaffold using the seed framework. No questions, no doubts, no alternative approaches.

## Directory Map

```
seed/
  lib/
    backend/
      noctusai_shared/        Python package (pip install -e seed/lib/backend)
        auth.py               JWT validation, SSO resolution
        roles.py              7-role hierarchy constants
        invitations.py        Invitation lifecycle
        email_templates.py    Product-branded email sending
        notifications.py      Notification field mapping
        app_factory.py        CORS, Sentry, exception handlers
        config.py             BaseAppSettings
        database.py           make_supabase_client()
        exceptions.py         AppException hierarchy
        middleware.py          Correlation ID, request logging
        logging_config.py     JSON/human-readable logging
        responses.py          success_response, paginated_response
        testing/              MockSupabaseClient, AuthClient
    frontend/
      src/
        api.ts                HTTP client factory
        auth.ts               useSupabaseAuthInit
        roles.ts              Role constants + helpers
        sso.ts                SSO context resolution
        page-status.ts        Dev-gated page visibility
        stores.ts             createAuthStore, createFiltrosStore
        hooks.ts              createCrudHooks
        notifications.ts      createNotificationHooks
        env.ts                Typed env access
        supabase.ts           createProductSupabase
        design-system/        AppShell, Sidebar, Header, LoginForm, etc.
  framework/
    backend/
      noctusai_seed/          Python package (pip install -e seed/framework/backend)
        app.py                create_product_app()
        config.py             ProductSettings (extends BaseAppSettings)
        database.py           create_database_module() → DatabaseModule
        dependencies.py       create_dependencies() → ProductDependencies
        routers.py            create_standard_routers() → [health, notificacoes, team]
    frontend/
      src/
        app.tsx               createProductApp()
        layout.tsx            createProductLayout()
```
