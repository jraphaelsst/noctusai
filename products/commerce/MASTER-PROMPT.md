# Commerce — MASTER-PROMPT

> Authoritative development guide for the Commerce host product.

## Purpose

Generic e-commerce + ERP reference store for the NoctusAI commerce vertical seed. It consumes `noctusai_lib.domain.commerce` (backend organ) and the `@noctusai/lib` commerce components (frontend organ); it adds no commerce logic of its own. Client-specific differences are org settings, then client extension packs inside this product, never `if org == …` in shared code (`KB § PATTERNS/architect/vertical-seed.md`). Contract: `projects/commerce-seed-p3/CONTRACT.md` §6.

## Architecture

### Backend

```
products/commerce/backend/app/
  main.py              → create_product_app("Commerce", "commerce", settings, routers=[...])
  config.py            → ProductSettings subclass
  database.py          → create_database_module(settings, "commerce")
  dependencies.py      → create_dependencies(db)
  rate_limit.py        → create_product_limiter(settings)
  routers/             → example + webhook skeletons (day-one); organ staff/storefront/webhook routers are mounted in Part 2
```

`app/commerce.py` (`CommerceConfig`), `migrations/0NN_commerce.sql` rendered verbatim from `commerce_migration(cfg, "commerce")` plus a parity test (precedent: `products/igig/backend/migrations/019_card_hub.sql`), the Asaas api-key spec with readiness tester, and fake-or-refuse dependencies (precedent: `products/store/backend/app/store_deps.py`).

### Frontend

`createProductApp()` + `createProductLayout()`; back-office pages under `/admin/*` use the staff organ components; `/` is the host-resolved storefront. Store settings are ONE page on the seed `SectionTabsPage` organ: `/admin/configuracoes/{loja,enderecos,integracoes}` (`pages/admin/Configuracoes.tsx`; nav row `configuracoes` from migration `030_status_pagina_configuracoes.sql`); the old `/admin/loja`, `/admin/enderecos`, `/admin/integracoes` paths redirect there.

### Database

Schema `commerce`, exposed to PostgREST by core migration 080 (append-only `pgrst.db_schemas`). Catalog row: `ativo=true`, `deploy_scope='dev'`, `aceita_clientes=false`.

## Rules

- Seed first: factories only, no custom app/auth.
- Auth tests assert strict `== 401`.
- Migrations mirror the live DB; generated commerce DDL is never hand-edited (the parity test pins it).
- Going live (`deploy_scope='live'`, tunnel ingress, build scope) needs the owner's consent file `deploy/consent/commerce.prod.yml`.

## Testing

```bash
cd products/commerce/backend && pytest
cd products/commerce/frontend && npx vite build
```

## Dependencies

- Backend: `noctusai_lib` + `noctusai_seed`
- Frontend: `@noctusai/lib` + `@noctusai/seed`
