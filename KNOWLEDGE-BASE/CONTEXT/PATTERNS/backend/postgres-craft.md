# Postgres craft — modeling, indexing, locking, transactions, zero-downtime migrations

> **What this is.** §5 of the backend craft canon (`KB § PATTERNS/backend/backend-craft-canon.md`),
> split out because the data layer is the deepest single topic. It teaches the general
> Postgres discipline a senior backend engineer is expected to know, and maps every
> principle onto the house mechanism that already implements (or fails to implement) it.
> Owner: `backend-engineer`. Authored 2026-11-05 (agent-refinement W1-S3).
>
> **Why it exists.** The house docs (`database-rls.md`, `migration-chain-replay.md`,
> `migration-sql-security-gates.md`, `postgrest-*.md`) record what bit us. None of them taught
> lock levels, `lock_timeout`, keyset pagination, EXPLAIN, or why a migration must stay
> compatible with the previous image. Prod is first-contact and `deploy_image` auto-rolls back
> (`KB § PATTERNS/devops/dev-fleet-dormant.md`), so these are not optional niceties.
>
> **How to use it.** House mechanism wins. If a seed helper, keeper or toolkit tool covers a
> point, use it; the general canon explains *why* and covers what the house has not yet built.
> Every section ends in a checklist. Sources are in § Sources with access dates.

## 0 · Standard term ↔ house term

| Standard term | House term / mechanism |
|---|---|
| Tenant key | `org_id` on every org-scoped row (therapy's legacy `clinic_id`) — `KB § PATTERNS/backend/database-rls.md` § Multi-tenant isolation |
| Row-level security | Supabase RLS; `(SELECT auth.uid())` form; service role bypasses (`database-rls.md:17-26`) |
| Data-access layer | PostgREST via `supabase-py` builders; bare table names (`KB § PATTERNS/backend/postgrest-schema-targeting.md`) |
| Stored procedure / transaction script | Postgres function called with `.rpc(...)` — one transaction per call |
| Migration tool | `noctus.dev.scaffold_migration` → file → `noctus.dev.migrate_product` (apply) → `migration_replay` (PGlite, pre-commit) |
| Schema drift check | `noctus.dev.schema_drift` (a `predeploy_check` leg, `database-rls.md:182-204`) |
| Work queue | jobs organ `claim_next_job` RPC with `FOR UPDATE SKIP LOCKED` (`seed/lib/backend/noctusai_lib/domain/jobs/migrations/jobs.sql.template:81-111`) |

---

## 1 · Modeling

**Principle.** The schema is the strongest validation layer you have: it holds for every writer
(app, SQL editor, a future product, a migration), forever. Application validation is a UX layer
on top, never the only guard.

**House application.**
- Tenant key on every org-scoped table, RLS on in the same migration that creates the table
  (`database-rls.md:148-152`). Per-user vs org-scoped decision matrix: `database-rls.md` §
  Per-user-scoped vs org-scoped tables.
- Money: the seed's money primitives carry `Decimal` and integer cents
  (`seed/lib/backend/noctusai_lib/primitives/money.py:22-45`); commerce stores `amount_cents`
  (`seed/lib/backend/noctusai_lib/domain/commerce/money_sql.py:242-243`). Use `numeric` or
  integer cents in SQL, never `float`/`real`.
- Phone/CPF-like identifiers are normalized by primitives before they hit a column
  (`primitives/phone.py:91` `normalize_phone`); see `KB § PATTERNS/backend/data-in-the-wrong-field.md`.
- Invariants that must hold across concurrent writers belong in the database: partial unique
  indexes (`products/agents/backend/migrations/035_julia_v2_threads_constraints.sql:53-55`),
  `CHECK` constraints (same file, :61-64), FK with an explicit `ON DELETE` policy.

**Checklist — new table.**
- [ ] `org_id uuid NOT NULL` (or a documented per-user scope) + RLS enabled + policies, same file.
- [ ] Primary key; every FK has an index on the referencing column and an explicit `ON DELETE`.
- [ ] `timestamptz` (never `timestamp`), `created_at DEFAULT now()`.
- [ ] Money = `numeric(…)` or `bigint` cents; enums = `CHECK (col IN (…))` or a lookup table.
- [ ] Uniqueness the business relies on is a (partial) UNIQUE index, not an app-side pre-check.
- [ ] Browser-readable? Default is service-role-only (`database-rls.md` § Service-role-only content tables).

**Anti-patterns.** App-only validation of an invariant ("we check before insert" — races);
`float` money; `text` timestamps; a nullable tenant key "for now".

---

## 2 · Indexing and reading a plan

**Principle.** An index exists to serve a query you can name. B-tree column order matters:
equality columns first, then the range/sort column. A partial index indexes only the rows a
predicate selects — smaller, cheaper to maintain, and usable only when the query's `WHERE`
implies the predicate. A partial UNIQUE index enforces uniqueness over a subset (Postgres docs,
§ Partial Indexes).

**Reading a plan.** `EXPLAIN (ANALYZE, BUFFERS)` runs the statement and reports actual rows,
time and buffer hits/reads per node. Read it bottom-up:
1. **Estimated vs actual rows** off by 10× or more ⇒ stale statistics (`ANALYZE tbl`) or a
   correlated predicate the planner cannot see.
2. **Seq Scan on a large table** under a selective filter ⇒ missing or unusable index.
3. **`Rows Removed by Filter`** large ⇒ the index serves part of the predicate only (column order).
4. **Buffers `read` ≫ `hit`** ⇒ cold data or a working set larger than cache.
5. **Nested Loop with a large outer side** ⇒ check the inner side's index.
`EXPLAIN ANALYZE` executes the statement: wrap a write in `BEGIN; … ROLLBACK;`, and never run it
against prod data you would not want touched. For fleet-level hot spots, `pg_stat_statements`
ranks normalized statements by `total_exec_time` / `mean_exec_time`.

**House application.**
- PostgREST hides the SQL, so get the plan by reproducing the filter in SQL against a Supabase
  branch (never prod; see `seed/lib/backend/noctusai_lib/testing/realdb.py:1-35`).
- `count="exact"` appears 87× across seed + active products (grep, 2026-11-05). Every one is a
  full count of the filtered set on each page request; on a growing table prefer
  `count="planned"`/`"estimated"` or keyset pagination (canon § 4.3).
- RLS policy columns must be indexed (§ 3).

**Checklist — a new query on a table that will grow.**
- [ ] Named the access path: which index serves `WHERE` + `ORDER BY`?
- [ ] Ran `EXPLAIN (ANALYZE, BUFFERS)` on realistic volume (branch DB) and pasted the plan in the PR/commit body.
- [ ] Unbounded result? Paginate (`iter_paged_rows`, `KB § PATTERNS/backend/postgrest-row-cap.md`).
- [ ] `.in_()` over a collection ⇒ batched (row-cap doc § Layer 2).

**Anti-patterns.** Indexing every column "just in case" (write amplification); an index whose
leading column is never filtered on; trusting a plan from an empty dev table.

---

## 3 · RLS performance

**Principle (Supabase guidance).** RLS predicates run for every row the query touches.
1. **Index the policy columns** (e.g. `org_id`, `user_id`) — Supabase reports >100× on large tables.
2. **Wrap functions in a sub-select** — `(SELECT auth.uid())` is evaluated once per statement
   (an initPlan), bare `auth.uid()` per row. Only valid when the result does not depend on the row.
3. **Filter explicitly as well** — "do not rely on RLS for filtering but only for security":
   send `.eq("org_id", …)` so the planner can use the index.
4. **Lookups through `SECURITY DEFINER` functions** so the looked-up table's own RLS is not
   evaluated per row (and lock the function down — `KB § PATTERNS/backend/migration-sql-security-gates.md`).
5. **Name the role with `TO authenticated`** so `anon` short-circuits.

**House application.** Rule 2 is already canonical (`database-rls.md:20-22`). Rules 1 and 3 were
missing from the house doc; they are now part of the new-table and new-query checklists here.
The backend mostly reaches data through the service-role client, which bypasses RLS
(`database-rls.md:25`) — so explicit `.eq("org_id", …)` scoping is the *security* boundary on those
paths, not just a performance hint (`KB § PATTERNS/backend/no-metadata-authz.md`).

**Checklist.** [ ] every column a policy filters on has an index · [ ] functions in policies are
sub-selected · [ ] every service-role query carries its own org filter · [ ] policies name their roles.

---

## 4 · Locks — what each statement blocks

**Principle.** Every DDL statement takes a table lock; the lock mode decides what traffic stalls.
The danger is not only the statement's own duration: a DDL waiting for a lock **queues ahead of
every later query** on that table. A long-running read in front of an `ALTER TABLE` therefore
stalls all traffic until the read finishes. `lock_timeout` bounds that wait.

| Statement | Lock mode | Blocks |
|---|---|---|
| `SELECT` | ACCESS SHARE | only ACCESS EXCLUSIVE |
| `INSERT/UPDATE/DELETE` | ROW EXCLUSIVE | SHARE and stronger |
| `CREATE INDEX` (plain) | SHARE | all writes for the build duration |
| `CREATE INDEX CONCURRENTLY` | SHARE UPDATE EXCLUSIVE | other DDL/VACUUM only; reads + writes continue. Cannot run inside a transaction block. |
| `ALTER TABLE … ADD CONSTRAINT … NOT VALID` | ACCESS EXCLUSIVE, brief (no scan) | everything, for milliseconds |
| `ALTER TABLE … VALIDATE CONSTRAINT` | SHARE UPDATE EXCLUSIVE | other DDL only; reads + writes continue |
| `ALTER TABLE … ADD FOREIGN KEY` | SHARE ROW EXCLUSIVE (both tables) | writes on both tables |
| `ALTER TABLE … ADD COLUMN` non-volatile default | ACCESS EXCLUSIVE, brief, no rewrite | everything, for milliseconds |
| `ALTER TABLE … ADD COLUMN DEFAULT clock_timestamp()` / `ALTER COLUMN TYPE` (most) | ACCESS EXCLUSIVE + table rewrite | everything, for the rewrite |
| Most other `ALTER TABLE` forms, `DROP TABLE`, `TRUNCATE` | ACCESS EXCLUSIVE | everything |

(Postgres docs: Explicit Locking; ALTER TABLE Notes; CREATE INDEX.)

**House application.** `lock_timeout` / `statement_timeout` appear **0 times** in every migration
and in the KB before this doc (grep, 2026-11-05). Active-scope tables are small today, which is
why this has not hurt yet; the agents conversation tables are the first that will grow.

**Checklist.** [ ] the runner applies `lock_timeout` 5s by default (§ 6.3); a file that needs longer says so with `-- noc:lock-timeout <v>`; every migration that alters an existing table may additionally start with `SET lock_timeout = '3s';`
· [ ] no table rewrite on a table with live traffic · [ ] plain `CREATE INDEX` only on a table
you can prove is small (state the row count in the file header, as 035 does at :23-26).

---

## 5 · Transactions, isolation and row locks

**Principle.**
- Postgres defaults to **Read Committed**: each statement sees a fresh snapshot, so two `SELECT`s
  in one transaction can disagree; nonrepeatable and phantom reads are possible. Repeatable Read
  and Serializable give stronger guarantees but **the application must retry on SQLSTATE `40001`**.
- **Check-then-act is a race** under Read Committed. Fix it with a constraint (UNIQUE / CHECK /
  exclusion), an atomic `INSERT … ON CONFLICT`, a conditional `UPDATE … WHERE state = 'x'
  RETURNING`, or `SELECT … FOR UPDATE` inside one transaction.
- `FOR UPDATE SKIP LOCKED` skips rows another transaction holds; the docs call it unsuitable for
  general work (inconsistent view) but right for **queue-like tables with many consumers**.
- PostgREST: **every HTTP request runs inside its own transaction**; a failed constraint or a
  `RAISE` in a function rolls that transaction back. So *one `.table()`/`.rpc()` call = one
  transaction*, and a sequence of calls from Python is N independent transactions with no
  atomicity between them.

**House application.**
- The jobs organ claims work with `FOR UPDATE SKIP LOCKED` inside an RPC
  (`jobs.sql.template:81-111`; Real repo calls it via `.rpc(...)`,
  `seed/lib/backend/noctusai_lib/domain/jobs/repo.py:506-507,655-675`).
- The commerce refund path is an RPC that checks the idempotency key and inserts in one
  transaction (`seed/lib/backend/noctusai_lib/domain/commerce/money_sql.py:193-243`).
- Counter-example: the team-accept flow does membership and invitation writes as separate
  PostgREST calls (`seed/framework/backend/noctusai_seed/routers.py:499-568`) — see canon worked
  example C.

**Decision rule.** Invariant spans >1 row or >1 table ⇒ one plpgsql function (`SECURITY DEFINER`
only when it must cross RLS; then `SET search_path` + `REVOKE EXECUTE … FROM PUBLIC, anon,
authenticated`). Spans Postgres + an external system (GoTrue admin API, Stripe, WAHA) ⇒ a saga
with named compensations (canon § 6.5).

**Checklist.** [ ] named the invariant · [ ] it is enforced by a constraint or lives in one RPC ·
[ ] no Python read-modify-write on a contended row · [ ] Serializable/Repeatable Read callers retry `40001`.

---

## 6 · Zero-downtime migrations

**Why it is mandatory here.** Prod is first-contact for a running image, and `deploy_image`
rolls back automatically to the `:previous` image on a failed health probe
(`mcp/noctusai/tools/noctus/dev/deploy_image.py:1-10`; `KB § PATTERNS/devops/dev-fleet-dormant.md:83`).
Migrations are applied separately and are **not** rolled back. So after any migration, the
**previous image (N-1) must run correctly against the new schema (N)**. A migration that drops,
renames or retypes something N-1 reads turns a routine auto-rollback into an outage.

### 6.1 Expand → migrate → contract (Fowler, "Parallel Change")

| Change | Deploy 1 (expand) | Deploy 2 (migrate) | Deploy 3 (contract) |
|---|---|---|---|
| Rename column `a`→`b` | add `b`; code writes both, reads `a` | backfill `b` in batches; code reads `b` | drop `a` once no image reads it |
| Change type | add new column of new type | dual-write + backfill | swap reads, then drop old |
| Add NOT NULL | add nullable + app always writes it | backfill; `ADD CONSTRAINT … CHECK (col IS NOT NULL) NOT VALID` → `VALIDATE` | `SET NOT NULL` (a valid CHECK proving no NULLs lets it skip the scan) |
| Drop column/table | stop reading/writing in code | (wait one release) | drop |
| New unique rule | build index `CONCURRENTLY` | attach `USING INDEX` | — |

Each deploy is individually safe to roll back. "Wait one release" is literal: the N-1 image must
no longer reference the thing you drop.

### 6.2 Statement-level rules

- **`lock_timeout`** — the runner sets 5s by default (§ 6.3); a stricter `SET lock_timeout = '3s';` at
  the top of a migration that touches an existing table is still fine (fail fast and retry instead of queueing in front of all traffic; § 4). Optionally
  `SET statement_timeout` for backfills.
- **Constraints:** `ADD CONSTRAINT … NOT VALID` (no scan, brief lock) then
  `VALIDATE CONSTRAINT` (SHARE UPDATE EXCLUSIVE, traffic continues).
- **Indexes on a live table:** `CREATE INDEX CONCURRENTLY`. It cannot run in a transaction block,
  and a failed concurrent build leaves an `INVALID` index behind to drop and retry (CREATE INDEX docs).
- **Backfills:** batches by primary-key range, each its own transaction, never one giant `UPDATE`.
- **Defaults:** non-volatile default on `ADD COLUMN` is metadata-only; a volatile default rewrites.

### 6.3 The house runner, its default lock_timeout, and the directives

`migrate_product` sends each pending file as **one** Management-API query
(`mcp/noctusai/tools/noctus/dev/migrate_product.py:1111-1146` `_apply_migration_sql`, executor
`SupabaseMgmtExecutor`). Postgres runs a multi-statement simple-query message as **one implicit
transaction** (protocol docs § Multiple Statements in a Simple Query). Consequences:
- A file is atomic — any error rolls back the whole file (pairs with `migration-chain-replay.md`'s
  run-twice rule).
- **Default `lock_timeout` = 5s** (`migration_directives.py:25`). The runner prepends
  `SET LOCAL lock_timeout = '5s';` to the SAME request, so it dies with the file's transaction and
  never leaks onto the session or the separate ledger INSERT. Because of the prefix a transactional file is always a multi-statement request, so
  `CONCURRENTLY` in it always fails — it needs the directive below. Blocked DDL fails fast instead of
  queueing in front of live traffic. A file's own `SET lock_timeout` still wins (it runs later).
- Ledger write (`INSERT INTO <schema>.schema_migrations`) is a separate request after success and
  stays non-fatal (a WARNING) — a migration that renames its own schema depends on that.

**Directives** — `-- noc:<name> [value]` comment lines in the file's LEADING comment block (before
the first statement), parsed by `migration_directives.py:52` `parse_directives`. Strict: unknown
name, bad/missing value, duplicate, or placement after the first statement refuses the whole batch
BEFORE any DDL (`migrate_product.py:1597-1613`).
- `-- noc:lock-timeout <v>` — override the default. `0` = off; else `<int>` + `ms|s|min|h|d`
  (`30s`, `2min`). A bare number without unit is rejected (ambiguous).
- `-- noc:no-transaction` — run outside the implicit transaction: the file is split on top-level
  `;` (`migration_directives.py:94` `split_statements`, quote/`$tag$`/comment aware) and each
  statement is its own request, so `CREATE INDEX CONCURRENTLY` / `DROP INDEX CONCURRENTLY` work.
  `lock_timeout` is scoped PER STATEMENT (`migrate_product.py:1112` `_apply_migration_sql`): a
  statement that cannot run in a transaction block goes BARE, with no guard
  (`migration_directives.py:188` `needs_bare_request`: any `CONCURRENTLY` — CREATE/DROP INDEX,
  REINDEX, REFRESH MATERIALIZED VIEW — plus `VACUUM`, `CLUSTER`, `DISCARD`, `ALTER SYSTEM`,
  `CREATE/DROP DATABASE|TABLESPACE|SUBSCRIPTION`, `REINDEX DATABASE|SCHEMA|SYSTEM`); every other
  statement is sent as `SET LOCAL lock_timeout = <lit>;\n<stmt>` in its own implicit
  transaction, and `noc:lock-timeout` applies to those. The result's `unguarded_statements`
  (`{file: [statement numbers]}`) names what ran without a guard. There is no session SET/RESET.
  `BEGIN/COMMIT/SAVEPOINT…` inside such a file is refused. The ledger INSERT still runs only after
  every statement succeeded.

**Half-failed no-transaction file.** It is NOT atomic. Statements before the failing one stay
applied, the ledger row is not written, the error says `statement i/n failed`. A failed
`CONCURRENTLY` build leaves an `INVALID` index (CREATE INDEX docs): `DROP INDEX CONCURRENTLY IF
EXISTS <name>` it or let the re-run do so. Therefore every statement of such a file must be
idempotent (`IF NOT EXISTS` / `IF EXISTS`); the re-run replays from statement 1. Keep the file to
the non-transactional statements and put `NOT VALID`/`VALIDATE` pairs in the same idempotent shape.

PGlite replay (`mcp/noctusai/node/migration_replay/replay.mjs`) honours `noc:no-transaction`
(statement-by-statement, twice) so `CONCURRENTLY` files replay green. `scaffold_migration`'s
generated body carries a hint comment about both directives.

**Live evidence (2026-11-05, Supabase project `nyplttplcoyiiqjrvtiw`, data-free probes).**
- No connection reuse: 5 Management-API requests returned 5 different `pg_backend_pid()`; after
  `SET lock_timeout='7s'` the next requests read `0`. A session `SET` can never guard a later
  request, so the first design (session SET + RESET) was a no-op and was removed.
- A multi-statement request is a transaction block: `SET lock_timeout='5s'; DISCARD ALL;` failed
  `25001 … cannot run inside a transaction block`; `DISCARD ALL;` alone succeeded. Hence a
  CONCURRENTLY-class statement can never share a request with a SET — it runs bare.
- Transactional path: `SET LOCAL` read `5s` inside the request and `0` after (no leak), also for a
  file with its own `BEGIN;…COMMIT;`. It fires: a waiter on a `pg_advisory_xact_lock` held 8s by
  another request, under `noc:lock-timeout 2s`, was cancelled with `55P03 canceling statement due
  to lock timeout`.
