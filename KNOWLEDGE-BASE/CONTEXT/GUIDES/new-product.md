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
8. `products/core/backend/migrations/NNN_seed_<slug>_product.sql` — seed-row migration that inserts the new product into `public.products`. **Auto-emitted by `scaffold_product`** (since 2026-05-05); apply via Supabase MCP `apply_migration` so the row lands on the live DB and the noc dashboard surfaces the product.
9. **Docker artifacts at the workspace root** — `Dockerfile`, `Dockerfile.frontend`, `docker-compose.yml`, `.dockerignore`, `.env.example`. **Auto-emitted at workspace bootstrap** (`scripts/bootstrap-seed-workspace.sh` since 2026-05-06) with placeholder values; **substituted in place** by `scaffold_product`'s `_patch_workspace_docker_files` step. The user can `docker compose up` immediately after the first product scaffolds — no hand-authored compose required. Source templates live at `templates/seed-workspace-docker/`. Convention exists so the user can put a freshly scaffolded product **online to test it before absorbing functionality**. See `../PATTERNS/seed-workspace.md § Docker scaffolding`.

10. **Workspace ops scripts** — `start.sh` + `stop.sh` at the workspace root, alongside the docker artifacts. **Auto-emitted at bootstrap** (since 2026-05-07), placeholders patched + executable bit re-stamped by `scaffold_product`. The user runs `./start.sh` to bring the stack online (full|minimal|tunnel profiles, polls `/api/health`, prints URLs + WAHA dashboard credentials) and `./stop.sh` to tear it down (graceful|--volumes|--prune). Source templates live at `templates/seed-workspace-docker/`. **Inherited surface — never hand-authored per workspace.** See `../GUIDES/deploy-workspace-online.md` for trigger phrases and the full recipe.

11. **Day-one route skeleton** — `app/routers/example_router.py` + `app/schemas/example.py` + `app/services/example_service.py` + `frontend/src/pages/Example.tsx` (route `/example`, nav entry, lazy-loaded). Inherited from `products/seed/` via `scaffold_product`. The router demonstrates the **canonical patterns** every new product must follow: `Depends(get_current_user_org)` factory dep, `coerce_org_uuid(raw_org)` helper, user-scoped Supabase client per request, Pydantic request/response models in `schemas/`, business logic in `services/`, explicit `status_code=` on POST, status-code-pinned tests in `tests/routers/test_example_router.py`. Look for `TODO(new-product):` markers — those are exactly the lines you rename and fill in. Day-one tests are 5 (auth + validation) — they pass green from scaffold; placeholder service methods raise `NotImplementedError` so list/create body tests are deferred until the new product fills in the service. **Don't delete the example skeleton before you have a real router** — losing it leaves no day-one example to reference.

12. **Day-one webhook receiver skeleton** — `app/routers/webhook_router.py` + `tests/routers/test_webhook_router.py` (5 status-pinned tests) + `example_webhook_secret` + `webhook_rate_limit` config fields. Inherited from `products/seed/` via `scaffold_product`. Demonstrates the **5-pin compliance contract** every webhook receiver must satisfy: (1) `webhook_endpoint(...)` from `noctusai_lib.security.webhook_signatures`, (2) per-request `ResolvedSecret` resolver, (3) explicit `bypass_when_unset=`, (4) `@limiter.limit(settings.webhook_rate_limit)`, (5) status-code-pinned tests. The skeleton ships with `scheme="svix"` (most common modern shape — Resend, Clerk); rename + switch scheme via the `TODO(new-product):` markers. Stripe SDK is the carve-out from pins 1+2+3; pins 4+5 still apply. See `../PATTERNS/webhook-signatures.md § The 5-pin compliance contract`.

13. **Day-one frontend skeleton** — `frontend/vitest.config.ts` (1-line factory call), `frontend/src/lib/{api,utils}.ts` (re-exports from `@noctusai/seed/infra` + `@noctusai/lib/utils`), `frontend/src/hooks/useExample.ts` (canonical `{data, loading, error, reload}` shape with `AbortController` cancellation), `frontend/src/components/ExampleCard.tsx` (design-token reference: `bg-card`, `border-border`, `text-foreground`, `cn()` from utils). Inherited from `products/seed/` via `scaffold_product`. Closes the 4-product gap where every new product invented its own hook + lib + component conventions. **Don't redefine helpers that already live in `@noctusai/lib/utils`** — if you copy one, lift it into the lib (recurrence rule).

14. **Backend namespace shortcuts** — `app/middleware.py` + `app/logging_config.py` re-export from `noctusai_lib.api.middleware` + `noctusai_lib.logging_config`. Inherited from `products/seed/` via `scaffold_product`. Mirrors the 4-product convention (core, ERP, PF, therapy). Lets product code `from app.middleware import CorrelationIdMiddleware` without crossing the seed boundary, and gives a canonical place to layer product-specific middleware or suppress a noisy third-party logger.

## Auto-registration to the noc dashboard

The noc dashboard (`products/core/frontend/src/pages/Dashboard.tsx`) reads products dynamically from `/api/auth/me`, which joins `public.products`. A scaffolded product that's not in that table is invisible.

**Rule.** Scaffolding a product MUST also register it in `public.products`. `noctus.dev.scaffold_product` enforces this by emitting `products/core/backend/migrations/NNN_seed_<slug>_product.sql` (idempotent `INSERT … ON CONFLICT (slug) DO NOTHING`). The scaffold response surfaces the file path in `next_steps` — apply it via Supabase MCP `apply_migration` to land the row on the live DB ("MCP migrations mirror the file" rule). Skipping this step = a product that exists on disk but not on the dashboard, which is the exact slip `media-scheduling` revealed on 2026-05-05.

**Inputs the scaffold tool accepts** for the seed-row migration: `name`, `slug`, `icon` (Lucide name or emoji), `color` (hex, defaults `#6366f1`), `description` (Portuguese 1-line, optional), `frontend_port` (becomes `url_base = http://localhost:<port>`).

**When the auto-emit is skipped** (e.g., a template workspace where `products/core/backend/migrations/` doesn't exist — "templates can't modify noc" rule), the scaffold response surfaces the gap in `next_steps` and the operator emits the migration manually in noc.

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
- [ ] Seed-row migration emitted by scaffold + applied to live DB via Supabase MCP — verify with `SELECT slug FROM public.products WHERE slug = '<slug>'`.

## Don't do

- ❌ Don't copy `app.main` from another product. Use the factory.
- ❌ Don't add a per-product `.env`. Use root `.env`.
- ❌ Don't re-implement auth, notifications, team routes, or layout. The seed provides them.
- ❌ Don't commit until backend AND frontend have real working pages wired to the backend.
- ❌ Don't hand-write a `docker-compose.yml`, `start.sh`, `stop.sh`, or any docker artifact for a workspace product. Source of truth is `templates/seed-workspace-docker/`. Re-run `bash scripts/bootstrap-seed-workspace.sh --target <workspace>` if any are missing.
- ❌ Don't delete the inherited `example_router.py` + `Example.tsx` skeleton until you have a real router/page to replace it with — those are the canonical reference for the auth pattern, the schema/service split, and the design tokens.
- ❌ Don't wire `Depends(get_org_id)` / `Depends(get_user_role)` directly. Always use `Depends(get_current_user_org)` from the product's `dependencies.py` (the factory-bound shape inherited from the seed). The deprecated shape emits a frame-aware DeprecationWarning at request time — see `../PATTERNS/backend.md § Auth — canonical pattern`.

---

See also:
- `../03-SEED-ARCHITECTURE.md` — the factory functions
- `../04-SHARED-LIBRARY.md` — reusable components (don't rebuild these)
- `../PATTERNS/` — all the patterns your new product must follow
- For **plans** (not products): start from `templates/PLAN-TEMPLATE.md` — never re-invent the plan structure.
