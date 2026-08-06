# PostgREST schema targeting — the table name is BARE, never qualified

> Formalized 2026-08-06 from a live fleet-wide 500: every social-wiring team
> invite failed with `Could not find the table
> 'social_wiring.social_wiring.invitations' in the schema cache`. Nine products
> mount the same seed router, so all nine were broken. Self-contained.

## The rule

**A Supabase/PostgREST client already carries its schema. The table name you
hand it must be BARE.**

```python
db = deps.get_admin_client()      # bound to schema="social_wiring"

db.table("invitations")           # ✅  → social_wiring.invitations
db.table(f"{schema}.invitations") # ❌  → social_wiring."social_wiring.invitations"
```

PostgREST resolves `.table(name)` **relative to** the schema on the request
(`Accept-Profile` / `Content-Profile`, set by `make_supabase_client(schema=…)`).
It never parses a dot as a schema separator — it looks for a table whose *name
literally contains a dot*. So a qualified name doesn't select the wrong table;
it selects a table that cannot exist.

## Why it reads as a missing migration

The error message doubles the schema:

```
Could not find the table 'social_wiring.social_wiring.invitations' in the schema cache
```

Nobody wrote that table, so the first read is "the migration never ran" — and
the investigation goes to `migrations/`, `schema_migrations`, and PostgREST's
schema-cache reload, all of which are fine. **The doubled prefix in the message
is the tell**: `<schema>.<schema>.<table>` means the caller qualified a name
that was already scoped. Read the message before reading the migrations.

## Why unit tests do not catch it

`MockSupabaseClient` keys its tables by whatever string `.table()` is handed
(`self._tables[name]`). A fixture that seeds `"test.invitations"` agrees with a
caller that asks for `"test.invitations"` — green, forever, against code that
500s on first contact with real PostgREST. This is a textbook
**fixture-vs-real** false-green (`§ CONTEXT/PATTERNS/compliance/testing.md`):
the mock has no opinion on the one thing under test.

The general lesson: **when the mock's key is derived from the same expression
as the code under test, the test asserts nothing.** Assert on the key the code
*chose* — `set(mock_db._tables) == {"invitations"}` — not on data you seeded
under that key.

## The three-layer fix (all three ship together)

| Layer | Mechanism | Where |
|---|---|---|
| Compliance-by-construction | Module constant `_INVITATIONS_TABLE = "invitations"` + comment naming the failure | `seed/framework/backend/noctusai_seed/routers.py` |
| Loud boundary refusal | `_require_bare_table()` raises `ValueError` on any dotted name, called by every public helper | `seed/lib/backend/noctusai_lib/domain/invitations.py` |
| Static backstop | Keeper `check_postgrest_schema_qualified_table` | `mcp/noctusai/tools/noctus/dev/compliance.py` |

The guard is the load-bearing one: it turns a confusing runtime 500 into a
named programming error on the *first* call, including under a mock — which is
exactly where the original slip hid. The keeper is the backstop, per
`§ CONTEXT/PATTERNS/common/gate-methodology-sync.md` (never gate-only).

## The keeper

`check_postgrest_schema_qualified_table` scans `seed/**` + `products/*/backend/**`
`*.py` for two shapes on `.table(...)` / `.from_(...)`:

1. **Interpolated** — `.table(f"{…schema…}.invitations")`: an f-string whose
   first segment interpolates something named `schema` and is followed by a dot.
   This is the exact live shape.
2. **Literal** — `.table("social_wiring.invitations")`: a hardcoded dotted name.

Severity `high` (this is a guaranteed runtime 500, not a style preference).
Escape hatch: `postgrest-qualified-ok` in a same-line or up-to-3-preceding-line
comment — for the vanishingly rare table whose name genuinely contains a dot.
CLI: `python mcp/noctusai/cli.py --check-postgrest-schema-qualified-table`.
Regression tests: `TestCheckPostgrestSchemaQualifiedTable` in
`mcp/noctusai/tests/test_compliance.py`.

## Where the schema actually gets bound

`DatabaseModule` (`seed/framework/backend/noctusai_seed/database.py`) is the
single place a product's schema enters the client:

- `get_client(token)` → product schema, user-authenticated (respects RLS)
- `get_admin_client()` → product schema, service role (cached, bypasses RLS)
- `get_core_client()` → `public` (platform tables: `noctus_users`, `notifications`)

`deps._db.schema` exists to *report* that binding, not to re-apply it. If you
find yourself string-formatting it into a table name, the binding is already
done — that is the signal to stop.

## Live incident

- **2026-08-06** — `POST /api/team/invite` → 500 on the social-wiring Equipe
  page. Root cause introduced in `06b5eeb6` ("fix(seed): team router /accept
  TypeError"), which converted the domain calls from `create_invitation(db=…,
  schema=…)` kwargs to positional `(db, table)` — and built `table` as
  `f"{deps._db.schema}.invitations"`. Correct arity, wrong value; the
  accompanying test file seeded `"test.invitations"` to match, so the suite
  went green on broken code and stayed green for ~3 months.
- Same commit's handler also dropped `org_id` from `cancel_invitation(db, table,
  invitation_id, org_id)` → `TypeError` → 500 on every `DELETE
  /api/team/invitations/{id}`, **and** silently removed the org scoping that
  stops an admin of org A cancelling org B's invite. Arity bugs in a
  positional-args refactor are not only crashes — check what the dropped
  argument was *for*.

## See also

`§ CONTEXT/PATTERNS/backend/database-rls.md` (schema + RLS wiring) ·
`§ CONTEXT/PATTERNS/compliance/testing.md` (fixture-vs-real, no-monkey-patching) ·
`§ CONTEXT/PATTERNS/backend/boundary-contract-tests.md` (the class: each side
tested, the contract crossing them untested) ·
`§ CONTEXT/PATTERNS/common/gate-methodology-sync.md`.
