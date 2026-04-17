# Seed — MASTER-PROMPT

> Authoritative development guide for the NoctusAI seed framework.
> This is the most critical infrastructure in the platform. Breaking the seed breaks every product.

## Purpose

The seed is the structural foundation of every NoctusAI product. It provides two layers:
- **Library** (`seed/backend/lib/` + `seed/frontend/lib/`) — reusable code (auth, roles, hooks, components)
- **Framework** (`seed/backend/framework/` + `seed/frontend/framework/`) — structural factories that products inherit

Every product imports from the seed. Zero products duplicate it. Change the seed, change all products at once.

## Architecture

```
seed/
  backend/
    lib/          noctusai_lib     pip install -e seed/backend/lib
      noctusai_lib/
        auth.py                    JWT validation, SSO resolution, make_get_current_user
        roles.py                   7-role hierarchy: owner, admin, manager, member, viewer, dev, test
        invitations.py             Invitation lifecycle: create, validate, accept, cancel, list
        email_templates.py         Product-branded emails via Resend
        notifications.py           Portuguese field mapping for core notifications
        app_factory.py             configure_app(): CORS, Sentry, exceptions, middleware, rate limiting
        config.py                  BaseAppSettings (Pydantic)
        database.py                make_supabase_client() with schema targeting
        exceptions.py              AppException hierarchy
        middleware.py              CorrelationIdMiddleware, RequestLoggingMiddleware
        logging_config.py          JSON (prod) / human-readable (dev)
        responses.py               success_response, paginated_response, ok_response
        rate_limit.py              create_limiter() with optional Redis
        page_status.py             Dev-gated page visibility
        action_log.py              Shared action logging (parameterized table/column)
        testing/                   MockSupabaseClient, MockUser, AuthClient
    framework/    noctusai_seed    pip install -e seed/backend/framework
      noctusai_seed/
        app.py                     create_product_app(name, schema, settings, routers, lifespan)
        config.py                  ProductSettings(BaseAppSettings) + JWT production check
        database.py                create_database_module(settings, schema) → DatabaseModule
        dependencies.py            create_dependencies(db) → ProductDependencies
        routers.py                 create_standard_routers() → [health, notificacoes, team]
        rate_limit.py              create_product_limiter(settings)
  frontend/
    lib/          @noctusai/lib    Vite alias → seed/frontend/lib/src
      src/
        api.ts                     createApiClient() with auth token + 401 retry
        auth.ts                    useSupabaseAuthInit()
        roles.ts                   ORG_ROLES, ADMIN_ROLES, helpers
        sso.ts                     resolveSSOContext(), isTrial(), subscriptionDaysRemaining()
        page-status.ts             usePageStatus(), filterNavByPageStatus()
        stores.ts                  createAuthStore(), createFiltrosStore()
        hooks.ts                   createCrudHooks<T>()
        notifications.ts           createNotificationHooks()
        env.ts                     validateEnv(), typed env access
        supabase.ts                createProductSupabase(schema)
        query-client.ts            createQueryClient() with defaults
        utils.ts                   cn(), formatCurrency(), formatDate()
        components/                SSOCallback, ErrorBoundary, createAuthProvider
        design-system/             AppShell, Sidebar, Header, LoginForm, NotificationBell, PageSkeleton, useTheme, tokens.css
    framework/    @noctusai/seed   Vite alias → seed/frontend/framework/src
      src/
        app.tsx                    createProductApp() — flat + role-based routing, providers, auth
        layout.tsx                 createProductLayout() — sidebar, header, page status, useLayoutEnrichment
        infra.tsx                  createProductInfra() — supabase, auth, api, notifications (singleton)
        index.ts                   Public exports
      vite.config.factory.ts       createViteConfig() — aliases, envDir, schema injection

## Key APIs

### Backend: create_product_app()
Creates a fully configured FastAPI app. Products call this with their name, schema, settings, and domain routers. The framework provides: health check, team management, notifications, CORS, Sentry, exception handlers, middleware, rate limiting, logging, JWT validation.

Parameters:
- `name` — human-readable product name
- `schema` — database schema name
- `settings` — ProductSettings instance
- `routers` — list of domain APIRouter instances
- `limiter` — rate limiter (optional)
- `lifespan_startup` / `lifespan_shutdown` — lifecycle hooks (optional, for schedulers)

### Frontend: createProductApp()
Creates a complete React App component. Supports flat routing (single Layout) and role-based routing (multiple Layouts per role).

Key config:
- `routes` / `roleRoutes` — page routes
- `Layout` — from createProductLayout()
- `supabase`, `useAuthStore` — from createProductInfra() via `...infra.appConfig`
- `resolveRole` — for role-based routing (e.g. Therapy)

### Frontend: createProductLayout()
Creates a Layout component with sidebar, header, page status filtering, SSO context, trial/license warnings.

Extension points:
- `useLayoutEnrichment` — inject domain-specific data (DB profiles, roles, conditional nav, theme persistence)
- `standaloneItems` — nav items outside groups
- `roleLabelOverride`, `brandSubtitleOverride` — display overrides
- `roleRoutes` — role-based routing support

### Frontend: createProductInfra()
Creates all boilerplate infrastructure from the schema (auto-detected from VITE_PRODUCT_SCHEMA). Returns singleton exported at `@noctusai/seed/infra`.

Products import directly: `import { supabase, useAuthStore, api } from "@noctusai/seed/infra"`

### Frontend: createViteConfig()
Creates Vite config with all aliases, dependency resolution, and env injection. Products have 3-line vite.config.ts files.

Injects: `VITE_BACKEND_API_URL` (from PRODUCT_MAP), `VITE_PRODUCT_SCHEMA` (from PRODUCT_MAP), `envDir` (repo root for shared VITE_ vars).

## Development Rules

1. **Every change to the seed must be tested against ALL products.** Run: `python mcp/noctusai/cli.py --validate`
2. **All React hooks must be called before any early return.** The `useLayoutEnrichment` pattern has an `isLoading` early return — all hooks must be above it.
3. **Extension points must be optional and backwards-compatible.** Adding a new config field to createProductLayout must not break existing products that don't pass it.
4. **The seed product (`products/seed/`) is the canary.** Test new framework features there first.
5. **Template auto-syncs from the seed product.** The post-commit hook runs `scripts/sync-seed-template.sh` when `products/seed/` changes.

## Testing

```bash
# Backend lib
cd seed/backend/lib && python -m pytest  # if tests exist

# Validate all products use the seed correctly
python mcp/noctusai/cli.py --validate

# Build all frontends (verifies framework compiles)
for p in seed daily-life personal-finance mailing therapy-platform erp-imobiliario; do
  (cd products/$p/frontend && npx vite build)
done
```

## Dependencies

- Backend lib depends on: fastapi, pydantic, supabase-py, PyJWT, slowapi, sentry-sdk
- Backend framework depends on: noctusai_lib + same
- Frontend lib depends on: @supabase/supabase-js, @tanstack/react-query, zustand, sonner, react
- Frontend framework depends on: @noctusai/lib + @radix-ui/react-tooltip + react-router-dom
