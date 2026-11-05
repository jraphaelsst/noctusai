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

**Checklist.** [ ] every migration that alters an existing table starts with `SET lock_timeout = '3s';`
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

- **`SET lock_timeout = '3s';`** at the top of every migration that touches an existing table
  (fail fast and retry instead of queueing in front of all traffic; § 4). Optionally
  `SET statement_timeout` for backfills.
- **Constraints:** `ADD CONSTRAINT … NOT VALID` (no scan, brief lock) then
  `VALIDATE CONSTRAINT` (SHARE UPDATE EXCLUSIVE, traffic continues).
- **Indexes on a live table:** `CREATE INDEX CONCURRENTLY`. It cannot run in a transaction block,
  and a failed concurrent build leaves an `INVALID` index behind to drop and retry (CREATE INDEX docs).
- **Backfills:** batches by primary-key range, each its own transaction, never one giant `UPDATE`.
- **Defaults:** non-volatile default on `ADD COLUMN` is metadata-only; a volatile default rewrites.

### 6.3 The house runner and the transaction-block problem

`migrate_product` sends each pending file as **one** Management-API query
(`mcp/noctusai/tools/noctus/dev/migrate_product.py:1542-1544`, executor at :595-625). Postgres
runs a multi-statement simple-query message as **one implicit transaction** (protocol docs §
Multiple Statements in a Simple Query). Consequences:
- Good: a file is atomic — any error rolls back the whole file (pairs with
  `migration-chain-replay.md`'s run-twice rule).
- Bad: `CREATE INDEX CONCURRENTLY` is impossible inside a normal migration file; 035 reasoned this
  out by hand (`035_julia_v2_threads_constraints.sql:23-26`).
- A `SET lock_timeout` at the top of the file applies to that implicit transaction — exactly the
  scope wanted.

**Gap (named destination).** A runner directive (e.g. a first-line `-- noc:no-transaction`
marker that makes `migrate_product` send each statement separately) is the root fix for
`CONCURRENTLY`. It is a toolkit change touching the applied-record path, which sits in the
git/merge redesign zone (`KB § PATTERNS/backend/migrate-product-mcp-tool.md:421`) — tracked in
`project-history/roadmaps/agent-refinement-followups-2026-11.md` §2 (`feat/df-migration-runner`). Until it lands: plain index build
only with a stated small row count, otherwise surface to the tech-lead.

### 6.4 Migration checklist (one page)

- [ ] Authored via `noctus.dev.scaffold_migration`; idempotent (`IF NOT EXISTS`); runs twice on PGlite.
- [ ] N-1 image works against this schema (no drop/rename/retype of anything N-1 reads).
- [ ] `SET lock_timeout` when altering an existing table.
- [ ] New constraint on existing data ⇒ `NOT VALID` + `VALIDATE`; precondition guard that `RAISE`s
      when data is not clean (035 :33-51 is the reference shape).
- [ ] Index on a non-trivial live table ⇒ `CONCURRENTLY` (needs the runner directive) or surface.
- [ ] RLS + policies + grants in the same file; `SECURITY DEFINER` ⇒ `search_path` + `REVOKE`.
- [ ] Data backfill batched; never mixed with a long DDL lock.
- [ ] `schema_drift` / `predeploy_check` green after apply.

**Anti-patterns.** Rename-in-place; drop-in-the-same-deploy; "it's a small table" without a count;
a backfill `UPDATE` over the whole table in the same file as the DDL; no `lock_timeout`.

---

## 7 · Escalation

Per `KB § PATTERNS/architect/dispatch-engineer-tuning.md` § 4·1: a migration on a large or hot
table, a constraint/index/type change on existing data, or a new multi-table invariant is
judgment-heavy work — the dispatcher should run it on Opus, and a Sonnet executor that meets one
unannounced should surface rather than improvise.

## Sources

- PostgreSQL — Explicit Locking — https://www.postgresql.org/docs/current/explicit-locking.html — lock modes and conflicts (§ 4). Accessed 2026-11-05 (audit-verified).
- PostgreSQL — ALTER TABLE — https://www.postgresql.org/docs/current/sql-altertable.html — `NOT VALID` / `VALIDATE` (SHARE UPDATE EXCLUSIVE), FK lock, `USING INDEX`, non-volatile default without rewrite (§ 4, § 6). Accessed 2026-11-05.
- PostgreSQL — CREATE INDEX — https://www.postgresql.org/docs/current/sql-createindex.html — `CONCURRENTLY` cannot run in a transaction block (§ 6). Accessed 2026-11-05 (audit-verified).
- PostgreSQL — Message Flow, Multiple Statements in a Simple Query — https://www.postgresql.org/docs/current/protocol-flow.html — implicit transaction block (§ 6.3). Accessed 2026-11-05.
- PostgreSQL — Client Connection Defaults — https://www.postgresql.org/docs/current/runtime-config-client.html — `lock_timeout`, `statement_timeout` (§ 4, § 6). Accessed 2026-11-05 (audit-verified).
- PostgreSQL — Transaction Isolation — https://www.postgresql.org/docs/current/transaction-iso.html — Read Committed default; retry on `40001` (§ 5). Accessed 2026-11-05.
- PostgreSQL — SELECT, The Locking Clause — https://www.postgresql.org/docs/current/sql-select.html — `SKIP LOCKED` for queue-like tables (§ 5). Accessed 2026-11-05.
- PostgreSQL — Using EXPLAIN — https://www.postgresql.org/docs/current/using-explain.html — plan reading (§ 2). Accessed 2026-11-05 (audit-verified).
- PostgreSQL — Partial Indexes — https://www.postgresql.org/docs/current/indexes-partial.html — partial and partial-unique indexes (§ 1, § 2). Accessed 2026-11-05.
- PostgreSQL — pg_stat_statements — https://www.postgresql.org/docs/current/pgstatstatements.html — ranking statements by execution time (§ 2). Accessed 2026-11-05.
- Supabase — Row Level Security — https://supabase.com/docs/guides/database/postgres/row-level-security — `(select auth.uid())`, index policy columns (§ 3). Accessed 2026-11-05 (audit-verified).
- Supabase — RLS Performance and Best Practices — https://supabase.com/docs/guides/troubleshooting/rls-performance-and-best-practices-Z5Jjwv — the six recommendations (§ 3). Accessed 2026-11-05.
- PostgREST — Transactions — https://github.com/PostgREST/postgrest-docs/blob/main/docs/references/transactions.rst — every request runs inside a transaction; RAISE rolls back (§ 5). Accessed 2026-11-05 (docs.postgrest.org returned HTTP 429; content read from the docs source repo).
- Martin Fowler — Parallel Change — https://martinfowler.com/bliki/ParallelChange.html — expand/migrate/contract (§ 6.1). Accessed 2026-11-05 (audit-verified).
