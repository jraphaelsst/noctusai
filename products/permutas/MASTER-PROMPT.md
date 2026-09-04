# Permutas -- Master Prompt

## Purpose

Property-barter (permuta) matching platform for ONE Consultoria Imobiliaria. Brokers property-for-property and property-for-vehicle exchanges: every listed imovel carries declared *interesses* (what its owner would accept in trade), and a Celery job scores bilateral matches between what each side has and what each side wants. Absorbed 2026-09-04 from the standalone legacy Django app at `github.com/jraphaelsst/one-permutas`.

## Architecture

- Schema: `permutas`
- Backend port: 8015 | Frontend port: 8190
- Auth: app-local JWT (`authsys_user` + simplejwt), NOT Core SSO
- Backend path: `products/permutas/backend/`
- Frontend path: `products/permutas/frontend/src/`
- Stack: Django 4.2 + DRF + Celery + React CRA -- a DELIBERATE divergence from the seed FastAPI/Vite stack

## Divergence contract

This product honours the house CONTAINER shape, not the house STACK. One container, one port (Django + WhiteNoise serve API and SPA together -- the Django-native `serve_spa` equivalent), `FROM noctus-seed-*-base`, non-root, healthcheck. See `KB § PATTERNS/devops/containerization.md §12a`.

Do NOT "fix" this by scaffolding seed FastAPI routers alongside it. Either it stays Django, or it is ported wholesale -- a half-port is the fork this contract exists to prevent.

## Key Domains

### Inventory
- **imovel_imovel** -- listed properties (ref, valor_venda, tipo, zona, condominio, proprietario, corretor)
- **permuta_permutaimovel** / **permuta_permutaautomovel** -- assets offered INTO a barter

### Declared interest (the thing that makes a match possible)
- **imovel_interesseimovel** / **imovel_interesseautomovel** -- what an imovel's owner accepts in trade
- **permuta_interessepermutaimovel** / **permuta_interessepermutaautomovel** -- the mirror side

### Matching
- **permuta_match** -- scored pairings, funnel stage (`etapa_do_funil`), `is_bilateral`. A CHECK constraint (`match_exactly_one_source`) enforces exactly one of imovel_match / permuta_automovel / permuta_imovel as the source.

### Cadastros
- **proprietario_proprietario**, **corretor_corretor**, **condominio_condominio**, **zona_zona**, **tipo_imovel_tipoimovel**, **tipo_automovel_tipoautomovel**

## Gotchas

- **Celery is mandatory for matching.** Without a worker, match processing fails SILENTLY -- no error surfaces to the UI.
- **Type vocabulary is dirty.** `Casa em condominio` exists twice (ids 7 and 9, differing only by accent), `Casa`/`casa`, and three spellings of `Sitio`. Filter by type ID set, never by name.
- **The SPA loads without the database.** Static assets are served by WhiteNoise, so the site returns HTTP 200 and looks healthy while every DB operation fails. A green homepage is NOT a health signal here -- probe `/api/`.
- **LGPD.** `proprietario_proprietario` holds 256 rows of real names, phones and emails. The upstream public repo committed a `db.sqlite3` with this data; it is excluded from the vendored copy and must stay excluded.
