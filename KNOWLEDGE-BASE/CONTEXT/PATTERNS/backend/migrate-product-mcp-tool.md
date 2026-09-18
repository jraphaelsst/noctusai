# migrate-product-mcp-tool — `noctus.dev.migrate_product`

## Why it exists

Applying `products/<slug>/backend/migrations/NNN_*.sql` to the shared Supabase
project used to be a hand-piped procedure: copy each file's SQL, paste into the
Supabase MCP `apply_migration` or `db.query`, confirm, repeat — done ~8× per
session during product launches. The `noctus.dev.migrate_product` tool automates
the whole cycle (MCP-first-scripts rule applied to a recurring hand-operation).

## Exec mechanism: Supabase Management API

The tool calls `POST /v1/projects/{ref}/database/query` on the Supabase
Management API — the same endpoint used by `mcp/supabase/tools/db.py`. This
endpoint can run raw DDL (`CREATE TABLE`, `CREATE SCHEMA`, etc.) unlike the
supabase-py / PostgREST client, which operates over HTTP and cannot issue DDL.

**Required credential:** `SUPABASE_ACCESS_TOKEN` — a Supabase Personal Access
Token (PAT). Add it to the noctusai MCP server environment (`.env` or Claude
Desktop `config.json` env block). Create at:
<https://supabase.com/dashboard/account/tokens>

When the token is absent the tool returns `status='not_configured'` with a
`NOC-REMEDIATE[credentials]` block — the tech-lead wires the credential; the
tool is fully testable via the `FakeSqlExecutor` seam without a real token.

## IO seam (Protocol + Fake + Real)

Follows `KB § PATTERNS/backend/seed-fake-real-adapter.md`:

| Layer | Class | Used by |
|---|---|---|
| Protocol | `SqlExecutor` (`.execute(sql) → dict`) | type annotations |
| Fake | `FakeSqlExecutor` | unit tests |
| Real | `SupabaseMgmtExecutor` | live tool |
| Factory | `make_sql_executor(access_token, project_ref)` | `migrate_product()` |

`FakeSqlExecutor` accepts `preset_rows` (keyed by SQL-fragment substring) and
`fail_on` (fragments that trigger a synthetic failure), and accumulates all
executed SQL strings in `.executed` for test assertions.

## Tracking table

```sql
CREATE TABLE IF NOT EXISTS <schema>.schema_migrations (
    filename   TEXT        PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    checksum   TEXT        NOT NULL
);
```

- Created automatically on first run (`CREATE TABLE IF NOT EXISTS`).
- Schema is **derived**, not hand-transformed — see "Schema derivation" below.
- Schema identifiers are always double-quoted in generated SQL (`_quote_ident`)
  — required for a hyphenated schema (`personal-finance`); harmless no-op for
  every other schema.
- Each applied file is recorded with a SHA-256 checksum of its content.
- `ON CONFLICT (filename) DO NOTHING` makes recording idempotent.
- **RLS-locked against PostgREST (2026-09-16)** — see § Ledger RLS hardening
  below; every product schema is PostgREST-exposed with default grants to
  `anon`/`authenticated`, so a bare tracking table is readable AND writable
  over REST by anyone unless explicitly locked down.

## Ledger RLS hardening (2026-09-16)

**The bug.** `_ensure_tracking_table_sql` created `<schema>.schema_migrations`
with no RLS and Postgres' default grants intact. Every product schema is
exposed via PostgREST (`authenticator`'s `pgrst.db_schemas`, see
`KB § GUIDES/new-product.md` § PostgREST schema exposure), so the bare
table was readable AND writable over the REST API by `anon` /
`authenticated` — including inserting a fake filename to make a future
`migrate_product` run silently skip a real migration (the ledger is
trusted as "already applied").

**The fix.** `_ensure_tracking_table_sql` now emits two extra statements
after the `CREATE TABLE IF NOT EXISTS`:

```sql
ALTER TABLE <schema>.schema_migrations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON <schema>.schema_migrations FROM anon, authenticated;
```

Both are idempotent — re-enabling RLS on an already-RLS'd table is a
no-op, and revoking a privilege a role doesn't hold is also a no-op — so
re-running this on an already-hardened schema is safe.

**Verified live** on Supabase project `nyplttplcoyiiqjrvtiw`, 2026-09-16:
an anon REST call against `<schema>.schema_migrations` now returns `42501`;
the Management-API executor (the table owner — RLS never restricts the
owner) still reads/writes it fine, so `migrate_product` itself is
unaffected.

**Codified fleet-wide** by
`products/core/backend/migrations/048_lock_schema_migrations_ledgers.sql`
— an idempotent DO-loop over every `schema_migrations` table outside the
Supabase-internal schemas (`auth`, `realtime`, `supabase_migrations`),
skipping the `ENABLE` leg for a table whose `pg_class.relrowsecurity` is
already `true` and always running the (idempotent) `REVOKE`.

## Schema derivation (fixed 2026-09)

The tool used to derive its target schema unconditionally as
`slug.replace("-", "_")`. That's wrong for any product whose declared schema
differs from its slug transform — `erp-imobiliario` declares `schema="erp"`,
`therapy-platform` declares `schema="therapy"`, and `personal-finance`
declares the **hyphenated** `schema="personal-finance"`. For those three
products the tool's own tracking rows landed in an empty phantom schema
(`erp_imobiliario` / `therapy_platform` / `personal_finance`) for months —
the migration DDL itself always landed correctly (each file's own
`SET search_path = <real-schema>` routes it); only the bookkeeping was
stranded. Proof: `erp_imobiliario.schema_migrations` claimed
`043_api_tokens.sql` applied while `to_regclass('erp_imobiliario.api_tokens')`
was NULL — the table was at `erp.api_tokens` the whole time.

`_resolve_schema()` precedence, in order:

1. **explicit `schema=` arg** — unchanged escape hatch.
2. **derived from the product's own `app/main.py`** — every product declares
   its schema exactly once, as the `schema="..."` keyword literal on its
   `create_product_app(...)` call (the same declaration
   `create_database_module` reads and every migration's `SET search_path`
   targets). AST-parsed (`_schema_from_main_py`, `KB § PATTERNS/common/ast.md`)
   — not regexed, not a hand-maintained slug→schema map.
3. **fallback**: the historical `slug.replace("-", "_")` transform — used
   only when no product declares a schema (main.py missing / unparseable /
   `schema=` not a literal string).

The result payload's `schema_source` field says which path fired
(`explicit_override` / `main_py_declaration` / `slug_fallback`) — a fallback
is never silently indistinguishable from a verified derivation.

## Stale-tree refusal (2026-09-17 incident)

`migrate_product` reads migration files from a filesystem tree
(`products/<slug>/backend/migrations/`), never from git history — so a tree
that is **behind its upstream** silently omits any migration added upstream,
with no signal that anything is missing. On 2026-09-17, during a real prod
deploy, the primary checkout was 26 commits behind `origin/dev` and did not
contain `134_contrato_assinatura.sql` at all. The dry-run confidently printed
a pending set that OMITTED the migration actually being deployed — a
reassuring, green-looking output computed against the wrong tree. That is a
silent error in the CLAUDE.md §1 sense: the dangerous behaviour (trust
whatever tree happens to be checked out) was the *default*.

**The fix — refuse-not-null.** Before reading a single migration file,
`migrate_product` now inspects the tree it is about to read from and
REFUSES — `status='refused_stale_tree'`, `exit_code=1`, never a warning the
caller can miss — whenever ANY of these is true:

1. **Behind its upstream** — `HEAD..<upstream>` is non-empty
   (`git rev-list --count`).
2. **Uncommitted changes under `products/*/backend/migrations/`** anywhere
   in the tree — staged, unstaged, OR untracked (`git status --porcelain`,
   filtered to that path prefix). An added-but-uncommitted migration is the
   same unreviewed-state problem as an edited one.
3. **Any git query the check depends on fails**, or the tree isn't a git
   work tree at all — fail-closed by construction (`GitQueryError`): an
   unanswerable question is treated as untrustworthy, never silently as
   clean. This is deliberately the same posture as the third leg of
   `predeploy_check`'s `schema_exposure` check ("FAILS, never skips, when
   it can't verify").

The refusal's `error` message names the inspected tree (absolute path), its
branch, `commits_behind`, and the exact remedy
(`` `git merge --ff-only <upstream>` ``, or pass `worktree_path=` /
`repo_root=` to pin a different tree). The full verdict also always rides
along as the `stale_tree` key on **every** returned status — dry_run /
applied / up_to_date / error / refused_stale_tree alike — never only on the
refusal path.

**`worktree_path=`** pins BOTH which tree the staleness check inspects AND
where migrations are read from — same parameter name and semantics as
`predeploy_check`'s (the MCP server is one long-running stdio process fixed
at whatever directory it booted in; there is no way to auto-detect a
caller's cwd). Omit it to target the primary checkout.

**`allow_stale_tree: bool = False`** is the documented escape hatch — same
shape as `deploy_image`'s `skip_ancestry_check` — for the rare deliberate
case (e.g. a human has already manually diffed the pending set against what
is actually merged upstream). Setting it True is almost always wrong; the
staleness check still runs and its verdict still rides on `stale_tree` even
when bypassed, so the override is visible in the result, never silent.

**GitRunner Protocol + Fake + Real** (mirrors `SqlExecutor`'s shape exactly,
`KB § PATTERNS/backend/seed-fake-real-adapter.md`): `GitRunner` Protocol
(`.run(root, args) → str`, raises `GitQueryError` on any failure) →
`FakeGitRunner` (unit tests — zero real git processes) →
`SubprocessGitRunner` (the live tool, 15s-bounded). Tests inject
`git_runner=FakeGitRunner(responses={...}, fail_on={...})` — never shell out
to a real repo.

Verdict-channel integrity note: this gate is the same discipline as
`KB § PATTERNS/common/methodology-execution-discipline.md`'s "verdict-channel
integrity" rule (the exit code you read must belong to what you are
judging) — a dry-run's `pending` list is a verdict about a specific tree,
and reading it without first verifying that tree is exactly the silent
mismatch the rule warns about.

## Signature

```python
migrate_product(
    product: str,           # slug — e.g. "orbity", "erp-imobiliario"
    confirm: bool = False,  # dry-run default; True = apply
    target: str | None = None,   # optional single-file filter
    project_ref: str = "nyplttplcoyiiqjrvtiw",  # noctusai production
    schema: str | None = None,   # override the DERIVED schema
    executor: SqlExecutor | None = None,  # injection seam for tests
    products_dir: Path | None = None,     # injection seam for tests
    worktree_path: str | None = None,     # pins the inspected + read tree
    allow_stale_tree: bool = False,       # escape hatch — almost always wrong
    repo_root: str | Path | None = None,  # test seam — wins over worktree_path
    git_runner: GitRunner | None = None,  # injection seam for tests
) → dict
```

Return shape:
```json
{
    "status": "dry_run | applied | up_to_date | not_configured | error | refused_stale_tree",
    "exit_code": 0,
    "product": "...",
    "schema": "...",
    "schema_source": "explicit_override | main_py_declaration | slug_fallback",
    "project_ref": "...",
    "applied": ["001_seed.sql", "..."],
    "skipped_already_applied": ["002_crm.sql"],
    "pending": ["003_rls.sql"],
    "error": null,
    "stale_tree": {
        "stale": false,
        "check": null,
        "branch": "dev",
        "upstream": "origin/dev",
        "commits_behind": 0,
        "dirty_migration_files": [],
        "detail": "clean"
    },
    "allow_stale_tree": false
}
```

## Ledger repair — `noctus.dev.repair_migration_ledger`

Moves `schema_migrations` rows stranded in a phantom schema (written back
when this tool used the naive slug transform unconditionally) to the real
schema. DRY-RUN by default; `confirm=True` required to write. Idempotent —
copies via `ON CONFLICT (filename) DO NOTHING` (never overwrites a real row),
then clears only the copied rows from the phantom table (never a bare
`TRUNCATE`). Never drops the phantom schema itself — repair only.

```python
repair_schema_migrations_ledger(
    product: str,
    confirm: bool = False,
    from_schema: str | None = None,  # override the phantom schema (default: naive slug transform)
    to_schema: str | None = None,    # override the target schema (default: _resolve_schema)
    project_ref: str = "nyplttplcoyiiqjrvtiw",
    executor: SqlExecutor | None = None,
    products_dir: Path | None = None,
) → dict
```

Return shape:
```json
{
    "status": "dry_run | no_op | up_to_date | repaired | not_configured | error",
    "product": "...",
    "phantom_schema": "...",
    "target_schema": "...",
    "target_schema_source": "...",
    "rows_to_move": ["043_api_tokens.sql"],
    "already_in_target": [],
    "moved": [],
    "error": null
}
```

`status='no_op'` covers: phantom schema equals target schema (nothing
phantom to repair), or the phantom `schema_migrations` table doesn't exist at
all, or it exists but is empty — all three are the healthy case for a product
that never hit the bug (e.g. `orbity`).

## Backstop keeper — `check_migration_applied_ledger_drift`

Repairing the three known products doesn't prevent a FUTURE gap of the same
shape (applied ≠ recorded) under a different cause — e.g. a migration run via
the Supabase Management API's own `apply_migration` path, which records into
the Supabase-managed `supabase_migrations.schema_migrations` catalog, not a
product's own tracking table. This detector is mechanism-agnostic: per
product, migration files on disk MINUS rows in `<real schema>.schema_migrations`,
intersected with names present in `supabase_migrations.schema_migrations` —
that intersection is the "applied through the non-recording path" set.

- First DB-touching detector in `compliance.py` — requires a resolvable
  `SqlExecutor` (via `make_sql_executor`, or an injected Fake in tests). When
  no executor resolves, returns a single `severity='skipped'` finding rather
  than `[]` — an empty list reads as "checked, clean" everywhere else in this
  file, and a DB check that silently no-ops on missing credentials must never
  look like a pass.
- Severity `warning` (observe-first — new detector, large pre-existing
  backlog; not a hard-block).
- Wired into `scripts/hooks/pre-push` (needs a DB round-trip → pre-push,
  never pre-commit), following the `_ld_py` primary-fallback idiom the
  ledger-drain keeper block establishes (a worktree has no
  `mcp/noctusai/.venv`). NOT wired into `check_all_products()` /
  `review.py::_detect()` — same posture as its closest sibling,
  `check_migration_number_collision` (a repo-level git/DB keeper, not a
  per-product static seed-compliance check).
- CLI: `python cli.py --check-migration-applied-ledger-drift`.

**🔴 The server and the CLI must resolve the SAME `supabase_access_token` —
they didn't, once (2026-09-14).** `_resolve_access_token` (above) is DB-first
via the seed `resolve_credential` seam, which needs `SUPABASE_URL` +
`SUPABASE_SERVICE_ROLE_KEY` in `os.environ` before it can even attempt the
DB tier, falling back to plain env `SUPABASE_ACCESS_TOKEN` (Tier 3) either
way. The MCP server (`server.py`) has loaded the repo-root `.env` into its
own process at import time since 2026-08-31 — but `scripts/hooks/pre-push`
invokes `cli.py` directly, and `cli.py` never loaded `.env` at all, so this
keeper SKIPped from the hook path ("no supabase_access_token resolved") even
though the identical MCP-server-backed tool call resolved the same
credential fine. Both entry points now call the SAME loader —
`mcp/noctusai/env_bootstrap.load_repo_env(REPO_ROOT)` — so there is exactly
one dotenv-loading code path for this platform, not two independently
maintained copies. The loader also handles the worktree wrinkle: a worktree
never carries its own `.env` (gitignored), but `cli.py` legitimately runs
with `settings.REPO_ROOT` pointed at a worktree when invoked from
`scripts/hooks/pre-push` there — `load_repo_env` falls back to the PRIMARY
checkout's `.env` via `git rev-parse --git-common-dir` in that case. The
keeper's own `severity='skipped'` message now names which sources were
tried (`_describe_credential_sources_tried` in `compliance.py`) instead of a
generic "not resolved", so a genuine no-credentials-anywhere state (fresh
clone, CI without secrets) is still honestly distinguishable from this class
of bootstrap gap.

## Usage flow

```
# Dry-run: see what would be applied (no DDL executed)
noctus.dev.migrate_product product="orbity"

# Apply all pending migrations
noctus.dev.migrate_product product="orbity" confirm=true

# Apply a single file
noctus.dev.migrate_product product="orbity" confirm=true target="005_crm_core.sql"

# Re-run is safe — already-applied files are skipped
noctus.dev.migrate_product product="orbity" confirm=true
# → status: up_to_date, applied: [], skipped_already_applied: [...]
```

## Migration file convention

Files must follow `NNN_<description>.sql` (same as `noctus.dev.scaffold_migration`
produces). Files without a leading numeric prefix are silently skipped (logged at
`DEBUG`). Files are applied in ascending numeric order.

## Composed-with

- `KB § PATTERNS/backend/database-rls.md` — migration conventions + RLS
- `KB § PATTERNS/backend/seed-fake-real-adapter.md` — IO seam shape
  (`SqlExecutor` AND `GitRunner` both follow it)
- `KB § PATTERNS/architect/mcp-first-scripts.md` — MCP-first principle
- `KB § PATTERNS/common/methodology-execution-discipline.md` —
  verdict-channel integrity (the stale-tree refusal is this rule made
  concrete for a dry-run's pending-migrations list)
- `KB § GUIDES/new-product.md` — PostgREST schema-exposure onboarding leg
  (the sibling gap: a new product's DATA schema must ALSO be exposed, or
  every REST call 404s with `PGRST106`)
- `noctus.dev.predeploy_check` — shares the `worktree_path=` parameter name
  and semantics, and the same "FAILS, never skips, when it can't verify"
  fail-closed posture (its `schema_exposure` leg)
- `noctus.dev.deploy_image` — `allow_stale_tree`'s escape-hatch shape
  mirrors `skip_ancestry_check`
- `noctus.dev.scaffold_migration` — creates the next numbered migration file
