# {{PRODUCT_NAME}} — MASTER-PROMPT

> Authoritative development guide for the seed reference product.

## Purpose

Minimal reference implementation proving the NoctusAI seed framework works end-to-end. The simplest possible product — just the spine, no domain logic. When the seed breaks, the framework broke. When creating a new product, the seed is the pattern to follow.

## Architecture

**Born from the seed framework.** This product has ZERO domain code. Everything comes from the framework.

### Backend (19 lines in main.py)

```
products/seed/backend/app/
  main.py              → create_product_app("{{PRODUCT_NAME}}", "{{SCHEMA_NAME}}", settings)
  config.py            → SeedSettings(ProductSettings) — no extra fields
  database.py          → create_database_module(settings, "{{SCHEMA_NAME}}")
  dependencies.py      → create_dependencies(db)
  rate_limit.py        → create_product_limiter(settings)
  routers/             → EMPTY — framework provides health, team, notifications
```

### Frontend (App.tsx uses framework factories)

```
products/seed/frontend/src/
  App.tsx              → createProductApp() + createProductLayout()
  vite.config.ts       → createViteConfig({ port: {{FRONTEND_PORT}} }) — 3 lines
  pages/               → Dashboard (stack status), Equipe (team), Landing, Login, etc.
  hooks/               → useNotificacoes (from seed lib)
  components/          → NotificationBell, ErrorBoundary, AuthProvider (from seed lib)
  NO Layout.tsx        → framework provides it via createProductLayout()
```

### Database

Schema: `seed` — only `status_pagina` (feature flags) and `invitations` (team invites). Zero domain tables.

## What the framework provides automatically

- `/api/health` — health check
- `/api/team` — team management (invite, accept, list, cancel, remove)
- `/api/notificacoes` — notification proxy to core
- `/api/llm/providers`, `/api/llm/models`, `/api/llm/preferences` — shared LLM router from `noctusai_seed.llm_router`
- Multi-provider LLM access: `create_product_app()` auto-wires `configure_credentials()` + `configure_llm(default_llm_config())` + `shutdown_llm()` in lifespan. Products inherit `noctusai_lib.llm.chat_completion` / `generate_embedding` / `transcribe_audio` / `analyze_image` with zero plumbing. Override only when the product needs different defaults: `create_product_app(..., llm_config=default_llm_config(default_chat_model="gpt-4o"))`.
- CORS, Sentry, exception handlers, middleware, rate limiting, logging
- Sidebar, Header, AppShell, page status filtering, SSO context, trial/license warnings
- TooltipProvider, QueryClientProvider, AuthProvider, ErrorBoundary, Suspense

## Template Auto-Sync

The seed is the source for `templates/product-seed/`. Post-commit hook runs `scripts/sync-seed-template.sh`:
1. Copies seed → template
2. Replaces values with `{{PLACEHOLDERS}}`
3. Template always in sync

Do NOT edit `templates/product-seed/` directly.

## Rules

- Keep the seed minimal — zero domain logic
- Any new framework feature must work in the seed first
- Changes to the seed propagate to the template automatically
- 6 tests must always pass

## Testing

```bash
cd products/seed/backend && pytest  # 6 tests
cd products/seed/frontend && npx vite build  # must build clean
```

## Dependencies

- Backend: `noctusai_lib` (code library) + `noctusai_seed` (framework)
- Frontend: `@noctusai/lib` (code library) + `@noctusai/seed` (framework)
