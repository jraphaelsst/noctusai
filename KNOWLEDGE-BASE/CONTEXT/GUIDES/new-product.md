# Creating a New Product

Products are born from the seed. The backend `main.py` imports `create_product_app()` from `noctusai_seed`. The frontend `App.tsx` imports `createProductApp()` from `@noctusai/seed`. Products only add domain-specific routers, services, pages, and components.

## Reference implementation

`products/seed/` is the simplest possible product — just the spine with no domain code. The template at `templates/product-seed/` is auto-generated from it via `scripts/sync-seed-template.sh`, invoked by the pre-commit hook whenever a `products/seed/` file is staged.

## Mandatory files from day one

1. `README.md` — what the product does, stack, ports, features.
2. `MASTER-PROMPT.md` — authoritative development guide (purpose, architecture, domains, testing, dependencies).
3. `frontend/.env.example` — all required `VITE_` vars with placeholders.
4. `backend/migrations/001_<schema>.sql` — full schema with RLS enabled.
5. Registration in `start.sh` with backend + frontend blocks.
6. `backend/app/main.py` — uses `create_product_app()` from seed framework.
7. `frontend/src/App.tsx` — uses `createProductApp()` from seed framework.

## Checklist for launch

- [ ] Schema migration runs clean on a fresh Supabase.
- [ ] RLS policies on every table (see `../PATTERNS/database-rls.md`).
- [ ] Backend starts on its port, hits `/api/health` green.
- [ ] Frontend starts on its port, loads the login page.
- [ ] SSO works from Core.
- [ ] Notifications proxy works (`/api/notificacoes/contagem`).
- [ ] Port added to root `.env CORS_ORIGINS`.
- [ ] All three test layers pass (routers, services, integration).
- [ ] E2E golden-path test passes.
- [ ] `tests/conftest.py` calls `bind_consent_module_to_mock(mock_sb)` inside the `client` fixture (default in `templates/product-seed/` since 2026-04-27 — verify it survived your scaffold). Required even if your product doesn't register consent features today; idempotent if catalog is empty. See `../PATTERNS/testing.md § Consent-guard product conftest pattern` for the full rationale.
- [ ] Added to `CLAUDE.md` product table AND `02-LANDSCAPE.md`.
- [ ] Per-product KB doc created (`CONTEXT/backend/0X-<NAME>.md`, `CONTEXT/frontend/0X-<NAME>.md`).

## Don't do

- ❌ Don't copy `app.main` from another product. Use the factory.
- ❌ Don't add a per-product `.env`. Use root `.env`.
- ❌ Don't re-implement auth, notifications, team routes, or layout. The seed provides them.
- ❌ Don't commit until backend AND frontend have real working pages wired to the backend.

---

See also:
- `../03-SEED-ARCHITECTURE.md` — the factory functions
- `../04-SHARED-LIBRARY.md` — reusable components (don't rebuild these)
- `../PATTERNS/` — all the patterns your new product must follow
- For **plans** (not products): start from `templates/PLAN-TEMPLATE.md` — never re-invent the plan structure.
