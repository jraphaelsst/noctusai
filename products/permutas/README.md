# Permutas — property-barter matching platform

Absorbed **2026-09-04** from the standalone legacy app *"Sistema de Permutas
Imobiliárias"* (ONE Consultoria Imobiliária), previously living outside noc at
`github.com/jraphaelsst/one-permutas` and deployed to `legacy.noctusai.com`.

## What it does

Brokers **permutas** — property-for-property (or property-for-vehicle) barter
deals. An `imovel` is listed for sale AND carries declared *interesses*: what
its owner would accept in exchange. A Celery job scores bilateral matches
between what each side has and what each side wants.

Domain tables (schema `permutas`, table names unchanged from upstream):

| Área | Tables |
|---|---|
| Inventory | `imovel_imovel`, `permuta_permutaimovel`, `permuta_permutaautomovel` |
| Declared interest | `imovel_interesseimovel`, `imovel_interesseautomovel`, `permuta_interessepermuta*` |
| Matching | `permuta_match` |
| Cadastros | `proprietario_proprietario`, `corretor_corretor`, `condominio_condominio`, `zona_zona`, `tipo_imovel_tipoimovel`, `tipo_automovel_tipoautomovel` |
| Auth | `authsys_user`, `authsys_profile`, `auth_permission`, `token_blacklist_*` |

## Stack — a deliberate divergence

This is **not** a seed FastAPI product. It is Django 4.2 + DRF + Celery with a
React CRA frontend, absorbed as-is. It honours the house *container* contract
(`KB § PATTERNS/devops/containerization.md §12a`) rather than the house *stack*:

- **One container, one port.** Django serves `/api/` and the SPA together via
  WhiteNoise — the Django-native equivalent of the seed factory's `serve_spa`.
- **`FROM noctus-seed-*-base`** — inherit-and-extend, never fork.
- Non-root, healthcheck, `GIT_SHA` label, same as every other product.

Porting the domain to the seed stack (and lifting its matching engine into a
seed organ) is a **later** phase — see *Open work* below. The absorption did not
attempt it, because a rewrite and a data migration in the same step would have
made a data-loss bug indistinguishable from a port bug.

## Database

Schema **`permutas`** in the shared `noctusai` Supabase project.

The data was migrated out of the standalone `One Permutas` project
(`eourhjahxxkhozxmpyno`), which had been **paused** — the direct cause of the
"can't register, data doesn't appear" outage, since the SPA still returned
HTTP 200 while every DB operation failed.

Migration fidelity was verified two ways, not one:

- **Row parity** — all 27 tables, source vs target.
- **Content checksum** — `md5(string_agg(row::text))` per business table,
  matching byte-for-byte on both sides.
- Identity sequences re-synced to `max(id)`, so the next insert cannot collide.

`backend/migrations/001_permutas_schema.sql` is the reproducible DDL (schema +
27 tables + 56 FKs + 16 uniques + 13 checks + 118 indexes). The one-time data
backfill is deliberately **not** replayed there.

## Open work

1. **Deploy to the VPS.** Blocked on the `noctusai` Postgres connection string —
   Django needs a direct psycopg connection, and unlike the rest of the fleet
   (which talks PostgREST with a service key) that password exists nowhere in
   the repo or on the VPS.
2. **Tunnel ingress.** `deploy/tunnel/config.yml` still routes
   `legacy.noctusai.com → http://legacy:5000`, a container that does not exist.
   Live traffic is served from another origin (almost certainly the never-retired
   Replit deployment). Reconcile at cutover.
3. **Celery.** Bilateral matching is async and fails silently without a worker.
   The house shape forbids a second container, so this resolves as in-process
   (`CELERY_ALWAYS_EAGER`) or as a declared seed seam.
4. **Seed uplift.** The matching engine is the capability worth promoting to a
   seed organ; `erp-imobiliario`'s `erp.ativos` already models the same domain
   and is empty. Consolidation is a real question, not a foregone one.

## Data-quality debt (found during the absorption)

- `tipo_imovel_tipoimovel` has near-duplicate rows: `Casa em condomínio` (id 7,
  210 imóveis) vs `Casa em condominio` (id 9, 3), `Casa` (2) vs `casa` (12),
  and three spellings of `Sítio`. Any filter by type name silently under-reports.
- `imovel_imovel` ref `ONE9445` is duplicated (ids 79 and 81, identical).
- `valor_minimo` is 0 on virtually every interest row — only the ceiling carries
  signal.
