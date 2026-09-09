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
) → dict
```

Return shape:
```json
{
    "status": "dry_run | applied | up_to_date | not_configured | error",
    "product": "...",
    "schema": "...",
    "schema_source": "explicit_override | main_py_declaration | slug_fallback",
    "project_ref": "...",
    "applied": ["001_seed.sql", "..."],
    "skipped_already_applied": ["002_crm.sql"],
    "pending": ["003_rls.sql"],
    "error": null
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
- `KB § PATTERNS/architect/mcp-first-scripts.md` — MCP-first principle
- `noctus.dev.scaffold_migration` — creates the next numbered migration file
