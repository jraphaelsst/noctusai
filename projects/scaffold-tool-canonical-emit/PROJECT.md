# scaffold-tool-canonical-emit — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** ✅ **CLOSED.** Engineer dispatched Phases 0-2; scaffold tool now emits `001_<slug>.sql` with `prelude(schema)` header. 5 SQL templates integration tests green; smoke test verified canonical filename + prelude content under `worktree_path` resolution. 2 pre-existing TestSlugPlaceholder failures unrelated to this scope.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `scaffold-tool-canonical-emit`
- **Related docs:**
  - `mcp/noctusai/tools/noctus/dev/scaffold.py` — the tool to amend
  - `seed/lib/backend/noctusai_lib/sql.py` — the `prelude()` helper to consume
  - `feedback_migration_prelude_helpers.md` — memory rule

---

## 1. Context & Purpose

Engineer U's imobi P2 close surfaced two N≥3 recurrences in scaffold output:

1. **Migration filename**: `noctus.dev.scaffold_product` emits `001_seed.sql` regardless of product slug. **N=3 in tree** (`media-scheduling/backend/migrations/001_seed.sql`, `youtube-crawler/backend/migrations/001_seed.sql`, `imobi-scheduling` before Engineer U's rename). Every product engineer has to `git mv` it to `001_<slug>.sql` by hand.

2. **Migration header**: Scaffold emits a hand-rolled prelude block; `noctusai_lib.sql.prelude(schema)` helper exists but scaffold never consumes it. **N=10 in tree** — every product has a hand-rolled prelude. Way past N=3 formalize.

Both are MCP-toolkit gaps: the tool's emission doesn't match what we want every product to use.

## 2. Confirmed constraints

- Helper `noctusai_lib.sql.prelude(schema: str)` ships and is used by `scaffold_migration` for follow-up migrations — just not by `scaffold_product` for the initial `001`.
- **Existing migrations stay as-is** (per `feedback_migration_prelude_helpers.md`). Backfilling all 10 products to consume `prelude()` is OUT OF SCOPE; this project amends the SCAFFOLD-TIME emission only.
- Filename rule: `001_<slug>.sql` per single-001-migration-per-product convention (`feedback_single_001_migration.md`).

## 3. Design principles

1. **Substitute slug into filename at scaffold time.** `001_seed.sql` → `001_{slug}.sql`.
2. **Emit `prelude({slug})` output verbatim** at scaffold time — call the helper, write its output.
3. **Single source of truth**: scaffold tool consumes the same `prelude()` helper that consumer migrations use; no copy-paste of the prelude block.

## 3a. Seed-first analysis

- **Cross-product?** YES — every future scaffold benefits. Per-product code count after change: 0 (everyone gets canonical from day 1).
- **Seed home?** `mcp/noctusai/tools/noctus/dev/scaffold.py` + `noctusai_lib.sql.prelude()`.

## 4. Scope

- **In scope:**
  - Scaffold tool emits `001_<slug>.sql` (filename substitution).
  - Scaffold tool calls `prelude(schema_name)` and writes the output verbatim into the initial migration.
  - Update existing scaffold tests.
  - Regression test asserting new product scaffolded with slug X gets `001_X.sql` containing `prelude(X)` output.

- **Out of scope:**
  - Backfilling existing 10 products' migrations (already shipped; leaving as-is per memory rule).
  - Adding `whatsapp_webhook` to `_STANDARD_ROUTERS` registry (Engineer U flagged — separate Phase 5 scope for imobi).

## 5. Architecture / Data Model

In `mcp/noctusai/tools/noctus/dev/scaffold.py`, the `_render_seed_migration(...)` (or equivalent) helper currently emits a static `001_seed.sql` body. Change:

```python
# OLD
output_path = product_root / "backend" / "migrations" / "001_seed.sql"
output_path.write_text(SEED_MIGRATION_TEMPLATE.replace("{schema}", schema_name))

# NEW
from noctusai_lib.sql import prelude
output_path = product_root / "backend" / "migrations" / f"001_{slug}.sql"
output_path.write_text(prelude(schema_name) + "\n\n" + DOMAIN_TEMPLATE_BODY)
```

## 6. Implementation phases

### Phase 0 — Audit current scaffold output

- [x] Re-grep `mcp/noctusai/tools/noctus/dev/scaffold.py` for the migration-emission site. Catalog the current template + filename construction.
- [x] Confirm `noctusai_lib.sql.prelude(schema)` shape — read source + tests; verify it's safe to call from scaffold's context.

**Findings:** Scaffold copies `templates/product-seed/` via `shutil.copytree(...)` at scaffold.py:597; then runs mechanical `{{...}}` substitution on file *contents* only — **filename is never rewritten**, so every scaffolded product inherits `001_seed.sql` literal. Migration header lives in template body (lines 1-11 of `001_seed.sql`) as a hand-rolled comment block + `SET search_path = {{SCHEMA_NAME}}, public;` — duplicate of what `noctusai_lib.sql.prelude(schema)` emits. `prelude(schema)` is pure string emission (no IO, no DB) — safe to call at scaffold time.

### Phase 1 — Refactor scaffold emission

- [x] Substitute slug into filename: `001_{slug}.sql`.
- [x] Replace hardcoded prelude block with `prelude(schema)` call at write time.
- [x] AST-first (libcst). NEVER sed/regex.
- [x] Update scaffold tests at `mcp/noctusai/tests/test_scaffold.py` — assert filename + prelude content.

**Implementation:** Added `_canonicalize_seed_migration(target, slug, schema)` helper module-level in `scaffold.py` via libcst codemod. Helper is called inside `scaffold_product` immediately after `shutil.copytree(...)` (step 1.b) and before `_write_scaffold_brief(...)` so subsequent mechanical-substitution + LLM-rewrite passes see the canonicalized body. New import `from noctusai_lib.sql import prelude` injected after the existing `workspace` import. Helper renames `001_seed.sql` → `001_<slug>.sql`, strips the hand-rolled header up through the first `SET search_path` line + trailing blank, prepends `prelude(schema)` output, and surfaces `{renamed, path, prelude_injected}` via the scaffold's return dict (new `canonical_migration` key). Skip path returns `{renamed: False, skipped: <reason>}` when `001_seed.sql` is absent or the template header shape drifted — never silent. Updated `TestSqlTemplatesIntegration` to:
- Assert filename matches `001_<slug>.sql` and `001_seed.sql` is GONE (renamed, not duplicated).
- Assert scaffold result advertises `canonical_migration.renamed = True` + `prelude_injected = True`.
- New `test_migration_header_is_canonical_prelude` asserts `content.startswith(prelude(schema))` verbatim AND that the legacy `<NAME> schema / -- Schema:` comment block is gone.
- New `test_migration_filename_uses_slug` (light-weight redundant check that the suite's filename assertion fires).

### Phase 2 — Verify + close

- [x] `pytest mcp/noctusai/tests/test_scaffold.py -q` — 50/52 green (2 pre-existing TestSlugPlaceholder failures unrelated to this scope; verified by `git stash` baseline).
- [x] Smoke: invoke `scaffold_product` against a temp slug, assert the emitted `001_<temp-slug>.sql` contains `prelude()` output.
- [x] Tick all sub-tasks + Improvements blocks + §11 close.

**Smoke output:** `scaffold_product(slug='smoke-test-canonical-emit-XYZ', schema='smoke_schema', worktree_path=<this-worktree>)` produced `<worktree>/products/smoke-test-canonical-emit-XYZ/backend/migrations/001_smoke-test-canonical-emit-XYZ.sql`; first 12 lines = exact `prelude("smoke_schema")` output; `text.startswith(prelude("smoke_schema"))` returns True; legacy `001_seed.sql` not present. `canonical_migration` return: `{renamed: True, path: <full path>, prelude_injected: True}`. Smoke side-effects (start.sh / docker-compose.yml / products/core/migrations/) reverted before commit.

## 7. Open questions

- None — Engineer U's audit is unambiguous.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [x] New scaffolds emit `001_<slug>.sql` (not `001_seed.sql`).
- [x] New scaffolds' `001_<slug>.sql` headers come from `prelude(<schema>)`.
- [x] Existing products UNCHANGED (no backfill — verified by `git status` showing only `scaffold.py` + `test_scaffold.py` in scope).
- [x] Test suite green (TestSqlTemplatesIntegration 5/5; pre-existing TestSlugPlaceholder failures unrelated).

## 10. How to use this plan

Single-engineer dispatch. Pattern is locked by Engineer U's audit — pure mechanical scaffold-emission swap.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer U's imobi P2 close (commit `31a0833`) surfaced N=3 recurrence on `001_seed.sql` filename + N=10 on hand-rolled prelude blocks. Scaffold-tool enhancement; pure MCP-toolkit work. | claude-opus-4-7 |
| 2026-05-10 | **Phase 0 + 1 + 2 shipped.** `_canonicalize_seed_migration(target, slug, schema)` helper added module-level in `mcp/noctusai/tools/noctus/dev/scaffold.py` via libcst codemod; called inside `scaffold_product` at step 1.b (right after `shutil.copytree(...)`, before brief-write + mechanical substitution + LLM rewrites). Helper renames `001_seed.sql` → `001_<slug>.sql` and replaces the hand-rolled header with `noctusai_lib.sql.prelude(schema)` output. New return-dict key `canonical_migration` surfaces `{renamed, path, prelude_injected}`. Tests: `TestSqlTemplatesIntegration` updated (slug-based filename assertion + legacy filename rejection) + 2 new tests for canonical prelude header + slug filename. Smoke verified under `worktree_path`. Existing 10 products' migrations unchanged. | engineer-abe6a997092085ab2 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
