# Feature — delete-product-cascading

> **What this is.** Inverse of `noctus.dev.scaffold_product`. Cascades a product deletion through every registration surface the scaffold tool writes to: `public.products` row (deactivate-not-DELETE for audit integrity), `start.sh` PRODUCTS array, and optionally the `products/<slug>/` folder. Establishes the **symmetry rule**: every registration surface that scaffold_product writes to must have a matching unregistration in delete_product, otherwise dangling state silently piles up.

- **Created:** 2026-05-05
- **Owner:** rapha
- **Trigger:** User directive — *"add explicitly to the seeding system, that whenever i ask to delete a product, all its registries must also be deleted and the start script updated."*

## Rule (durable methodology)

When a product is deleted via `noctus.dev.delete_product(slug, remove_directory=False)`:

1. **Dashboard deactivation.** Emit `products/core/backend/migrations/NNN_deactivate_<slug>_product.sql` containing `UPDATE public.products SET ativo = false WHERE slug = '<slug>';`. Operator applies via Supabase MCP `apply_migration`. **Why deactivate not DELETE:** preserves the row for audit trails / foreign-key references; flips visibility on the dashboard via the `ativo` flag. Re-scaffolding the same slug later does NOT auto-reactivate — the seed-row insert uses `ON CONFLICT (slug) DO NOTHING`. A deliberate REACTIVATE migration is required to bring it back. Intentional friction.

2. **start.sh unregistration.** Surgical removal of the slug's line from the `PRODUCTS=()` array between `# BEGIN_PRODUCTS_REGISTRY` / `# END_PRODUCTS_REGISTRY` sentinels. Other entries preserved untouched. Idempotent on slug-not-found.

3. **Optional folder removal.** `remove_directory=False` by default. Safety default: a typo'd slug must NOT `rm -rf` shipped product code. Caller opts in explicitly. When `True`, `shutil.rmtree(products/<slug>/)` runs (idempotent on already-gone folder).

`RESERVED_RANGES` (`mcp/noctusai/tools/noctus/dev/scaffold.py`) is **intentionally not modified** by `delete_product`. Deleted-product ports stay reserved as historical record so the same port can't be silently re-issued to a future scaffold. Manual edit of the table is required to free the slot — surfaced as a `next_steps` line in the tool's return.

## Symmetry rule (the durable methodology)

> Every registration surface that `scaffold_product` writes to MUST have a matching unregistration in `delete_product`. Adding a new registration without the inverse is the same shape as a silent-error: the inverse op silently no-ops on that surface and leaves dangling state.

When future projects add a new registration surface to `scaffold_product` (e.g., Cloudflare config when the CF migration lands), the same project also extends `delete_product` with the matching unregistration AND adds a regression test asserting both directions work.

## Files touched

- `mcp/noctusai/tools/noctus/dev/scaffold.py`:
  - `_unregister_from_start_sh` — inverse of `_register_in_start_sh`; same sentinel regex; surgical line removal.
  - `_emit_products_deactivate_migration` — mirror of `_emit_products_seed_row_migration`; same NNN-advance + skip-when-no-core-migrations semantics.
  - `_remove_product_directory` — `shutil.rmtree` with idempotency on missing folder.
  - `delete_product` — top-level function. Default `remove_directory=False` for safety.
  - MCP registration: `noctus.dev.delete_product` tool with `slug` + `remove_directory: bool` parameters.
- `mcp/noctusai/tests/test_scaffold.py`:
  - `TestDeleteProduct` — 8 tests covering each side-effect + idempotency + skip conditions.
  - `TestDeleteProductRespectsTestSeam` — 2 hygiene regression guards (mirror of `TestScaffoldRespectsTestSeam`).

## Test coverage (10 new tests, 34/34 pass)

- **`test_emits_deactivate_migration`** — NNN advances; SQL shape correct.
- **`test_removes_start_sh_entry`** — only target slug removed; other entries intact; sentinels preserved.
- **`test_default_skips_directory_removal`** — folder still on disk; opt-in hint surfaced in next_steps.
- **`test_removes_directory_when_opted_in`** — `remove_directory=True` rmtree's.
- **`test_idempotent_when_slug_not_registered`** — never-existed slug → migration emits (UPDATE matches 0 rows, harmless), start.sh untouched.
- **`test_skips_when_no_core_migrations_dir`** — template-workspace shape — surfaces skip reason.
- **`test_skips_when_start_sh_absent`** — surface skip reason.
- **`test_skips_when_sentinels_missing`** — surface skip reason.
- **`test_no_real_start_sh_writes_under_tmp_seam`** — hygiene guard.
- **`test_no_real_core_migration_writes_under_tmp_seam`** — hygiene guard.

## Sub-tasks

- [x] `_unregister_from_start_sh` helper.
- [x] `_emit_products_deactivate_migration` helper.
- [x] `_remove_product_directory` helper.
- [x] `delete_product` top-level function with safety default.
- [x] MCP tool registration.
- [x] `TestDeleteProduct` (8 cases).
- [x] `TestDeleteProductRespectsTestSeam` (2 hygiene guards).
- [x] All 34 scaffold tests pass; no real-file pollution.
- [x] Memory updated (`feedback_scaffold_auto_registers_products.md` covers both halves now).
- [x] MEMORY.md index line covers create + delete in one entry.

## Out of scope (deferred)

- **REACTIVATE migration generator** — when a deleted product needs to come back, an explicit migration is required. Could become `noctus.dev.reactivate_product(slug)` but no current need; deferred until a real reactivation case surfaces.
- **RESERVED_RANGES auto-prune** — currently manual. Considered & rejected: the historical-record property is more valuable than the automated cleanup. Reserve-once-keep-forever matches port-allocation reality.
