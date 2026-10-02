# Store

Minimal reference implementation — the spine with no organs. Proves that both seed packages (`noctusai_lib` + `noctusai_seed` backend, `@noctusai/lib` + `@noctusai/seed` frontend) work end-to-end. Source of truth for the product template (`templates/product-seed/`).

## Stack

- **Backend**: FastAPI via `create_product_app()` from `noctusai_seed` (port 8018)
- **Frontend**: React via `createProductApp()` + `createProductLayout()` from `@noctusai/seed` (port 8220)
- **Build**: `createViteConfig()` from seed framework (3-line vite.config.ts)
- **Database**: Supabase (schema: `store`)
- **Auth**: SSO + direct login

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8018 --app-dir products/store/backend

# Frontend
cd products/store/frontend && npm run dev
```

## What it proves

- `create_product_app()` works (health, team, notifications — all from framework)
- `createProductApp()` + `createProductLayout()` works (routing, auth, sidebar, header)
- `createViteConfig()` works (alias resolution, dependency deduplication)
- SSO authentication flow
- Page status filtering
- Notification proxying
- Team/invitation management
- Template auto-sync (post-commit hook → `templates/product-seed/`)

## Tests

```bash
cd products/store/backend && pytest  # 6 tests
```
