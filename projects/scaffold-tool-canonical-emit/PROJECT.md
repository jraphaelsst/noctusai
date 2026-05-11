# scaffold-tool-canonical-emit — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 📋 **READY FOR EXECUTION.** Filed under user signal "create projects for deferrals/parks that happen along the way." Engineer U's `imobi-scheduling-bot-creation` Phase 2 close (commit `31a0833`) surfaced N=3+ recurrence on `noctus.dev.scaffold_product` emitting non-canonical artifacts. Mechanical MCP-tool enhancement.
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

- [ ] Re-grep `mcp/noctusai/tools/noctus/dev/scaffold.py` for the migration-emission site. Catalog the current template + filename construction.
- [ ] Confirm `noctusai_lib.sql.prelude(schema)` shape — read source + tests; verify it's safe to call from scaffold's context.

### Phase 1 — Refactor scaffold emission

- [ ] Substitute slug into filename: `001_{slug}.sql`.
- [ ] Replace hardcoded prelude block with `prelude(schema)` call at write time.
- [ ] AST-first (libcst). NEVER sed/regex.
- [ ] Update scaffold tests at `mcp/noctusai/tests/test_scaffold.py` — assert filename + prelude content.

### Phase 2 — Verify + close

- [ ] `pytest mcp/noctusai/tests/test_scaffold.py -q` — green.
- [ ] Smoke: invoke `scaffold_product` against a temp slug, assert the emitted `001_<temp-slug>.sql` contains `prelude()` output.
- [ ] Tick all sub-tasks + Improvements blocks + §11 close.

## 7. Open questions

- None — Engineer U's audit is unambiguous.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [ ] New scaffolds emit `001_<slug>.sql` (not `001_seed.sql`).
- [ ] New scaffolds' `001_<slug>.sql` headers come from `prelude(<schema>)`.
- [ ] Existing products UNCHANGED (no backfill).
- [ ] Test suite green.

## 10. How to use this plan

Single-engineer dispatch. Pattern is locked by Engineer U's audit — pure mechanical scaffold-emission swap.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer U's imobi P2 close (commit `31a0833`) surfaced N=3 recurrence on `001_seed.sql` filename + N=10 on hand-rolled prelude blocks. Scaffold-tool enhancement; pure MCP-toolkit work. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
