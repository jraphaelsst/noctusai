# containerization-backlog-closure — Orchestration Findings

> Per `KB § 01-PHILOSOPHY.md § Knowledge tracking` + `KB § PATTERNS/branching-and-merging.md §17`. Append-as-you-go during dispatch; synthesized at project close.

---

## Errors encountered

- **(T4, 2026-05-10) `psql -v ON_ERROR_STOP=1` aborts the whole init file on first failure.** The default postgres docker entrypoint runs every `.sql` in `/docker-entrypoint-initdb.d/` with `ON_ERROR_STOP=1`. When one product's migration referenced `cron.schedule()` (Supabase-only), psql aborted, the entrypoint exited non-zero, and the entire database was effectively discarded — all 17 CREATE TABLEs that ran successfully before the cron line were rolled back when postgres restarted and found the data dir in an inconsistent state. **Fix:** explicit `\set ON_ERROR_STOP off` at the top of the generated `02-migrations.sql` so a per-product `BEGIN;...COMMIT;` failure only rolls back that product's block; subsequent products still apply.
- **(T4, 2026-05-10) `cron.schedule()` shim's `jobname` parameter shadowed the table column.** Initial cron stub used `jobname TEXT` as both the parameter name and an `ON CONFLICT (jobname)` reference, triggering `ERROR: column reference "jobname" is ambiguous`. Renamed to `p_jobname` prefix. Lesson: name function params with a prefix when they could collide with column names of tables the function writes to.

---

## Mistakes / slips

- **(T4, 2026-05-10) Initial slip: built only the cross-product schemas, missed the role/shim layer.** First pass installed extensions + schemas + migrations and called it done — verification showed 0 tables in any schema because every product migration GRANTed to `anon`/`authenticated`/`service_role` (Supabase roles, not installed in plain postgres). Added `00a-supabase-shims.sql` shipping the roles + `auth.{jwt,uid,role,email}()` no-op functions + `extensions`/`storage`/`cron` schemas + minimal `auth.users` table. Lesson: a Supabase migration is NOT pure SQL — it's SQL + a thick Supabase runtime contract. Offline-dev profiles need to shim the contract.
- **(T4, 2026-05-10) Slip: forgot `core` must run before products that FK to `public.organizations`.** Default alphabetical sort put `adconnect` (FK target: `public.organizations`) BEFORE `core` (creator of that table). Generator reordered to put `core` first; rest stay alphabetical. Lesson: cross-product schema dependencies in migrations have a topological order that's often distinct from product slug order.

---

## Lessons learned (durable rules)

- **(2026-05-10, orchestrator at scaffold time)** Three-way-syncing the methodology BEFORE dispatching teams under it is the right ordering. The teams operate under the rule that they're supposed to be exemplifying; if the rule isn't documented when they execute, the methodology amendment is post-hoc and weaker. Capture-first-execute-second.
- **(T4, 2026-05-10) Docker volume init runs ONCE — verification must include the teardown-and-reup cycle.** The postgres-official-image init scripts only fire when the data directory is empty. A "looks green" first run can mask a slip that only surfaces on a fresh volume. Every postgres-init verification should explicitly `down -v` + `up` again to exercise the cold path. Captured as a §11b caveat.
- **(T4, 2026-05-10) Shim layer > skip-broken-statements in generated SQL.** When the first attempt hit `cron.schedule does not exist`, the easy fix was to grep-strip cron lines from the generated migrations. The better fix was to expose `cron` as a stub schema/function in `00a-supabase-shims.sql` — the migrations stay byte-identical to production, the local image carries the compatibility surface. Generated artifacts should never silently diverge from their source.

---

## Interesting findings (surprises, discoveries)

- **(T4, 2026-05-10) dev-team uses 4-digit `0001_` prefix while every other product uses 3-digit `001_`.** The generator's initial glob (`001_*.sql`) silently missed dev-team. Switched to per-product "lexically-first numeric-prefixed `.sql`" discovery. Lesson: migration naming conventions across products are not yet standardized; the seed-first scaffolder writes 3-digit but dev-team predates that. Candidate for a separate normalization project.
- **(T4, 2026-05-10) `core` doesn't declare its own schema — it lives in `public`.** Of all 10 products, only core's migration omits `CREATE SCHEMA IF NOT EXISTS <slug>`. Its tables live in `public` directly. The `\dn` output thus shows 9 product schemas + `public` (with core's tables) — not 10 product schemas as the brief expected. Documented in §11b.
- **(T4, 2026-05-10) ERP's migration is the only one that uses Supabase extensions that alpine doesn't bundle.** `pg_cron`, `pg_net`, `vector` are all in ERP's `001_erp_imobiliario.sql` `CREATE EXTENSION ... WITH SCHEMA extensions` block. Offline-dev posture: accept ERP empty in local-db mode (cataloged in §11b caveat); production still uses Supabase.

---

## Knowledge pieces (durable patterns)

- **The Supabase compatibility shim layer.** For offline-dev with plain Postgres, you need MORE than just extensions — Supabase migrations bake in: 3 roles (`anon`/`authenticated`/`service_role`), the `auth` schema with `auth.jwt()`/`auth.uid()`/`auth.role()`/`auth.email()` STABLE functions, an `extensions` schema, a `storage` schema (sometimes referenced by RLS), an `auth.users` table (FK target), and on some products a `cron.schedule()` stub. The full shim is at `scripts/init-local-db/00a-supabase-shims.sql` and serves as the canonical "Supabase compatibility surface" reference for any future tool that needs to apply real migrations against plain Postgres (CI integration tests, schema-diff tooling, etc.).
- **`BEGIN; product-migration; COMMIT;` blocks + `\set ON_ERROR_STOP off` is the right shape for concatenating per-product migrations.** Each block atomically applies-or-rolls-back; psql continues to the next block on failure; cascade errors ("current transaction is aborted") in failed blocks fill the logs but don't poison neighbors. Generated by `scripts/build-init-local-db.sh`.



- **Pause-on-dependency event log shape.** Each pause-and-resume gets a row here:
  - **Event:** _(none yet)_
  - **Surfaced by:** engineer-name
  - **Gap:** what was missing
  - **Dependency team dispatched:** team-name + brief slug
  - **Resume signal:** when the original chunk re-dispatched
  - **Resumed brief delta:** what changed in the re-dispatch vs. the original

---

## Wave-by-wave speed-gain log (per `feedback_TEMP_methodology_validation_in_progress.md`)

| Wave | Engineers | Wall-clock parallel | Estimated serial | Speed gain | Tokens | Notes |
|---|---|---|---|---|---|---|
| 1 | 6 | _pending_ | _pending_ | _pending_ | _pending_ | T1-T6: backend Dockerfile / frontend / VITE args / postgres / registry / healthcheck |
| 2 | 2 | _pending_ | _pending_ | _pending_ | _pending_ | T7-T8: dev override / prod overlay |
| 3 | 1 | _pending_ | _pending_ | _pending_ | _pending_ | T9: CI workflow (matrix + registry push + scan) |
| **Cumulative** | **9** | **pending** | **pending** | **pending** | **pending** | First orchestration under §18 wave-dispatch methodology |

This is the first orchestration under the new §18 methodology. Track diligently for the validation log.
