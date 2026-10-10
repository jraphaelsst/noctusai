# Migration chain replay — execute every chain on a real Postgres before prod does

`noctus.dev.migration_replay` (CLI `--migration-replay`) replays product migration
chains on a fresh **PGlite** (PG16 compiled to WASM, in-process — no server, no
Docker) and judges them. It is the first gate that EXECUTES a migration before
production does; every other migration gate is static (keepers parse the SQL) or
runs against prod (`migrate_product`, `verify_db_guards`).

## Why it exists

SW migration 231 v1 (2026-10-10) backfilled `atendimento_intermediarios` rows to the
punctuated form while the old bare-digit CHECK was still in force, so prod refused
the migration with `23514`. Every static gate was green. Any real Postgres holding
the same rows would have refused it at commit time. The replay now reproduces it:
`tests/test_migration_replay.py::test_sw_231_v1_goes_red_with_23514_and_the_fix_goes_green`.

## The contract

| Piece | Rule |
|---|---|
| **Order** | core FIRST, then the product. Every product's 001 references core's `public` tables; without the prefix, every non-core chain dies on `public.noctus_users`. File order = `migrate_product`'s (numbered direct children, by number then name). |
| **Stubs** | `mcp/noctusai/node/migration_replay/stubs.sql`, versioned (`STUBS_VERSION`). One commented block per Supabase surface: roles, `auth`, `storage`, realtime publication, `cron`, `net`, `vault`, the `extensions` schema (real pgvector; `gen_random_bytes` shape stub because PGlite 0.2.17 has no pgcrypto). Shapes only, never behaviour. `CREATE EXTENSION pg_net/pg_cron` is stripped. Each file starts a fresh session with Supabase's default `search_path` (`"$user", public, extensions`). |
| **History** | Files the change does not touch replay **statement by statement**, in order, autocommit. A failure never hides its neighbours. |
| **Targets** | New/changed files apply as a **whole file in one simple-query call** (how `migrate_product` sends them: implicit transaction, atomic), then **a second time**. A re-apply failure is red (idempotency). |
| **Residue** | `products/<slug>/backend/migration-replay.json` → `residue[]`: the known history failures as `{file, error, count, remediate}`. Red = a failure not covered there. Every `remediate` class must be declared (with its `NOC-REMEDIATE[...]` marker) in `migration_replay.REMEDIATE_CLASSES`, or the config is refused. When a failure stops happening, the tool reports it under `resolved_residue`: prune that entry. |
| **Fixtures** | Same JSON → `fixtures[]`: `{before, why, sql}` inserted just before the named file. A fresh DB is empty, and an empty table never trips a CHECK, so the rows a migration will meet in prod must be in the replay. `session_replication_role = replica` may leave a fixture's *own* references dangling. It never disables a CHECK. Rows a migration updates twice in one transaction need real FK parents, because Postgres re-checks the FK on such a row. |
| **Verdict** | `green` · `red` · `inconclusive`. Not being able to MEASURE (no `node`, PGlite not installed, stubs failing, crash, timeout, a bad config) is `inconclusive`: never green, never a verdict on the migration. CLI exit 0 / 1 / 2. |

## Statement-level replay: the transaction-control trap

Statement replay must skip `BEGIN`/`COMMIT`, and detection must ignore leading
comments. A file reading `-- note\nBEGIN` slips past a naive `^BEGIN` test and opens
a transaction. The next statement error's `ROLLBACK` then silently wipes every object
created since. The first measurement read **2749 false failures** in social-wiring
that way. `split_sql.mjs` `isTransactionControl` tests the comment-stripped text;
regression `test_comment_before_begin_is_still_transaction_control` +
`test_comment_begin_in_history_does_not_wipe_earlier_objects`.

## Gates

- **pre-commit 6i**: fires when `products/*/backend/migrations/*.sql` or a
  `migration-replay.json` is staged. It replays the touched products from the
  **staged blobs** (`--migration-replay-source index`). Red blocks. Inconclusive
  warns, and CI judges.
- **CI** (`commit-range-keepers` job): the same check over the push/PR range
  (`--migration-replay-base`), after `npm ci` of the pinned PGlite. Here
  inconclusive FAILS: CI is where the measurement is guaranteed.
- **`gate_sweep`** maps every migration/config path to a `migration_replay` gate.
  `migration_replay: INCONCLUSIVE` is a registered harness signature.

Asleep products are skipped (the product catalog's active scope). Replaying their
chain is waking them.

## Cost (measured 2026-10-10, M-series laptop)

core 683 stmts 1.2s · academia 903 1.1s · agents 1164 1.2s · igig 1236 1.2s ·
seed 734 1.1s · **social-wiring 4447 stmts 2.5s** (incl. the core prefix). All six
active chains: ~9s wall. That fits the 90s integrate box with a wide margin.

## Measurement that shaped it (2026-10-10)

- Bare PGlite: 6/6 chains fail on 001 (`auth` schema / `anon` role).
- With stubs + core prefix: academia / agents / igig / seed replay with **zero**
  failures.
- core keeps 14 known failures: 002 re-creates 001's policies, and 027 renames
  columns 001 already renamed.
- social-wiring keeps 54:
  - 001 forward-references 005+ tables;
  - 011 alters `erp` (owner erp-imobiliario is asleep);
  - 012/212/214 alter `mailing`, which no migration creates.
- Idempotency of the existing chains: 35 of 374 files fail a second apply (the newest
  SW one is 166). The gate only applies files twice when they are new or changed.
- `products/seed`'s `001_seed.sql` / `003_examples.sql` (the scaffold source) fail
  a re-apply (`status_pagina` / `examples` already exist). A product scaffolded from
  them goes red on its first commit until the template is idempotent.

Applied migrations are **immutable**: `schema_migrations` stores each file's sha256.
So the residue is baselined with a destination instead of being fixed by editing
history:

- `migration-chain-rebaseline`: core 002/027, SW 001;
- `mailing-schema-migration`: a migration that creates the schema;
- `erp-asleep-owner`.

## Composed with

`KB § PATTERNS/backend/migrate-product-mcp-tool.md` (the prod apply this mirrors) ·
`KB § PATTERNS/compliance/testing.md § CHECK constraints` (the mock layer's CHECK
enforcement: unit speed, no DDL) · `KB § PATTERNS/common/remediation-markers.md` ·
`KB § PATTERNS/common/methodology-execution-discipline.md` (inconclusive ≠ red ≠ green).
