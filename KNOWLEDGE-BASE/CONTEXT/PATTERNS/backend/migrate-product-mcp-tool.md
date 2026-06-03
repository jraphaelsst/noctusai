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
- Schema derived from product slug: `slug.replace("-", "_")` — override via
  `schema=` arg.
- Each applied file is recorded with a SHA-256 checksum of its content.
- `ON CONFLICT (filename) DO NOTHING` makes recording idempotent.

## Signature

```python
migrate_product(
    product: str,           # slug — e.g. "orbity", "erp-imobiliario"
    confirm: bool = False,  # dry-run default; True = apply
    target: str | None = None,   # optional single-file filter
    project_ref: str = "nyplttplcoyiiqjrvtiw",  # noctusai production
    schema: str | None = None,   # override derived schema
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
    "project_ref": "...",
    "applied": ["001_seed.sql", "..."],
    "skipped_already_applied": ["002_crm.sql"],
    "pending": ["003_rls.sql"],
    "error": null
}
```

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
