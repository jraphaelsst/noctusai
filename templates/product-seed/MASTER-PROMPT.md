# {{PRODUCT_NAME}} -- Master Prompt

## Purpose

Minimal reference implementation proving the NoctusAI shared stack works end-to-end. Serves as the living source for the product template (`templates/product-seed/`). When creating a new product, the seed is what you copy. Every shared pattern (auth, SSO, roles, invitations, notifications, page status, layout) is demonstrated here in its simplest form.

## Architecture

- Schema: `seed`
- Backend port: {{BACKEND_PORT}} | Frontend port: {{FRONTEND_PORT}}
- Tenant key: `org_id`
- Auth: SSO (from Core) + direct login
- Backend path: `products/seed/backend/app/`
- Frontend path: `products/seed/frontend/src/`

## Key Domains

The seed intentionally has minimal domain logic. It exists to validate infrastructure:

- **health** -- health check endpoint (proves backend is running)
- **notificacoes** -- notification proxy to Core (proves cross-product notification delivery)
- **team** -- team/invitation management (proves shared invitation flow works)

## Backend Structure

```
app/
  main.py          -- FastAPI app via shared app_factory
  database.py      -- Supabase client setup (schema: seed)
  dependencies.py  -- get_current_user (product-local for test mock compatibility)
  routers/
    health.py      -- GET /api/health
    notificacoes.py -- notification CRUD proxying to Core
    team.py        -- invitation + team member management
```

No services directory -- the seed is thin enough that router logic is minimal and delegates to shared library functions directly.

## Frontend Structure

```
src/
  pages/
    Dashboard.tsx     -- main landing page after login
    Equipe.tsx        -- team management page
    Landing.tsx       -- public landing page
    Login.tsx         -- login form
    ForgotPassword.tsx
    AcceptInvite.tsx
    SSOCallback.tsx   -- SSO token exchange handler
    NotFound.tsx
  components/
    Layout.tsx        -- product layout using shared AppShell + Sidebar + Header
```

## Template Auto-Sync

The seed is the source of truth for `templates/product-seed/`. The post-commit git hook runs `scripts/sync-seed-template.sh` automatically, which:

1. Copies seed files to the template directory
2. Replaces product-specific values with template placeholders (`{{PRODUCT_NAME}}`, `{{SCHEMA_NAME}}`, `{{BACKEND_PORT}}`, `{{FRONTEND_PORT}}`, `{{PRODUCT_ICON}}`)
3. Keeps the template always in sync with the latest seed code

Do NOT edit `templates/product-seed/` directly -- edit the seed, and the template updates automatically.

## Development Guidelines

- Follow shared patterns from noctusai_lib (auth, roles, invitations, responses, exceptions)
- Router -> Service -> Schema pattern (though seed is simple enough to skip services)
- RLS policies use `(SELECT auth.uid())` pattern on all tables
- Portuguese for business domain names, English for technical/framework code
- Keep the seed minimal -- it should only demonstrate shared patterns, not add product-specific business logic
- Any new shared feature should be wired into the seed first as proof-of-concept
- Changes to the seed automatically propagate to the template via post-commit hook
- See `TODO-SEED-PRODUCT.md` in the repo root for the seed build checklist

## Testing

```bash
cd products/seed/backend && pytest
```

9 tests (minimal -- validates health, notifications, team endpoints).

## Dependencies

- Shared backend: `noctusai_lib`
- Shared frontend: `@noctusai/lib` + `@noctusai/lib/design-system`
- Supabase: Auth, database, RLS
