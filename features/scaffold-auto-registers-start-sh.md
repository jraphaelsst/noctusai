# Feature — scaffold-auto-registers-start-sh

> **What this is.** Closes the third gap in the "scaffolding auto-registers a product everywhere it has to live" methodology. The first gap (dashboard `public.products` row) was closed earlier — `noctus.dev.scaffold_product` already emits `products/core/backend/migrations/NNN_seed_<slug>_product.sql`. This feature closes the **start.sh** gap: scaffolded products were missing from the local dev runner, so an SSO redirect to `localhost:<frontend_port>` would `ERR_CONNECTION_REFUSED` because the frontend was never started. While here, also fixes a **test-hygiene gap** that the scaffold tests revealed (older tests bypassed the `tmp_path` seam and silently polluted real `start.sh` + `products/core/backend/migrations/`).

- **Created:** 2026-05-05
- **Owner:** rapha
- **Trigger:** SSO login to AdConnect (`localhost:8130/sso?token=...`) failed with ERR_CONNECTION_REFUSED. AdConnect, Dev Team, and Media Scheduling were never added to `start.sh` after their initial scaffold. User directive: *"doc this fix so future products get added to the start script automatically."*

## Findings before the fix

- `start.sh` started only 7 of the 9 platform products. Missing: AdConnect (8007/8130), Dev Team (8009/8123), Media Scheduling (8096/8130).
- `start.sh` shape was 9 hand-written backend/frontend launch blocks per product — N=9 recurrence, well past the DRY threshold.
- AdConnect and Media Scheduling **both** configured frontend port 8130 (collision). AdConnect (shipped) was the original owner; Media Scheduling (WIP) had been scaffolded against a stale RESERVED_RANGES table.
- `RESERVED_RANGES` in `mcp/noctusai/tools/noctus/dev/scaffold.py` did not include AdConnect or Dev Team and listed a "scheduling" 8140 entry that no longer mapped to anything.
- The older `TestScaffold.test_creates_new_product` and `TestSqlTemplatesIntegration` tests omitted the `products_dir=tmp_path` seam — every test run silently created **real** orphan files (`products/core/backend/migrations/0NN_seed_test_scaffold_*_product.sql` from 014 to 039, plus `products/test-scaffold-temp/`). Now extended to leak into `start.sh` once the auto-injection landed.

## Scope (what this feature ships)

1. **Data-driven `start.sh`** — replaces 9 hand-written blocks with a single `PRODUCTS=("slug:Display Name:backend_port:frontend_port" ...)` array + loop. The array is bracketed by `# BEGIN_PRODUCTS_REGISTRY` / `# END_PRODUCTS_REGISTRY` sentinel comments so machine-injection is safe and idempotent.
2. **`scaffold_product` auto-injection** — new helper `_register_in_start_sh` appends a registry entry to `start.sh` between the sentinels. Idempotent (no-op when slug already present); skips gracefully when sentinels missing or `start.sh` absent (e.g., template workspaces). Result surfaced via new `start_sh_registration` key in the tool's return.
3. **`RESERVED_RANGES` truth-up** — adds AdConnect (8007/8130), Dev Team (8009/8123); fixes Media Scheduling frontend (8131 collision → 8140 next aligned slot); removes stale "scheduling" entry.
4. **Media Scheduling 8130→8140 move** — updates `products/media-scheduling/frontend/vite.config.ts` and `products/core/backend/migrations/013_seed_media_scheduling_product.sql` URL field. (013 was untracked; safe to edit in place. Live DB unchanged because `ON CONFLICT DO NOTHING` skips re-inserts; operator can run a follow-up `UPDATE public.products SET url_base='http://localhost:8140' WHERE slug='media-scheduling'` if the row is already present.)
5. **Test-seam migration** — `TestScaffold.test_creates_new_product` and the three `TestSqlTemplatesIntegration` tests now route through `products_dir=tmp_path` + `template_dir=WORKTREE_TEMPLATE`. Stops real-file pollution that all prior runs were silently doing.
6. **Hygiene regression guard** — new `TestScaffoldRespectsTestSeam` class asserts that under the `tmp_path` seam scaffold writes no bytes to real `start.sh` or real `products/core/backend/migrations/`. Future regressions to the leaky pattern fail CI.
7. **Three start.sh-injection tests** — appends-between-sentinels, idempotent on duplicate slug, skips-without-sentinels, skips-when-start-sh-absent.

## Files touched

- `start.sh` — refactored to data-driven loop; sentinel comments around `PRODUCTS` array.
- `mcp/noctusai/tools/noctus/dev/scaffold.py` — `_register_in_start_sh` helper + `_START_SH_REGISTRY_RE`; `RESERVED_RANGES` truth-up; `scaffold_product` calls the helper and surfaces `start_sh_registration` in its return + `next_steps`.
- `mcp/noctusai/tests/test_scaffold.py` — `TestScaffoldRegistersInStartSh` (4 tests), `TestScaffoldRespectsTestSeam` (2 regression guards), `TestScaffold.test_creates_new_product` migrated to tmp_path seam, `TestSqlTemplatesIntegration._scaffold_and_read_migration` migrated to tmp_path seam.
- `products/media-scheduling/frontend/vite.config.ts` — port 8130 → 8140.
- `products/core/backend/migrations/013_seed_media_scheduling_product.sql` — URL `localhost:8130` → `localhost:8140`.
- Cleanup: deleted untracked `products/core/backend/migrations/{014..039}_seed_test_scaffold_*_product.sql` orphans + `products/test-scaffold-temp/` + `products/test-scaffold-sql-temp/` from prior leaky test runs.

## How a new product registers, end-to-end (post-fix)

1. Caller invokes `noctus.dev.scaffold_product(name, slug, schema, backend_port, frontend_port, ...)`.
2. Tool copies the seed template under `products/<slug>/`, substitutes placeholders.
3. Tool emits `products/core/backend/migrations/NNN_seed_<slug>_product.sql` (auto-numbered) — the row that makes the product visible on the noc dashboard.
4. Tool appends `"<slug>:<Display Name>:<backend_port>:<frontend_port>"` to `start.sh` between the registry sentinels — `bash start.sh` now starts the new product alongside the rest.
5. `next_steps` in the return surfaces: apply seed-row migration via Supabase MCP (or skip-with-reason if workspace lacks a `products/core/backend/migrations/`); add to CLAUDE.md product table; add to `vite.config.factory.ts` `PRODUCT_MAP`.

The dashboard row + the start.sh entry are the two **runtime side-effects** that the tool now owns. Earlier methodology described step 1 as the rule; this feature lifts step 2 into the tool too.

## Sub-tasks

- [x] Refactor `start.sh` to data-driven `PRODUCTS=()` array with sentinel comments.
- [x] Add 3 missing products (adconnect, dev-team, media-scheduling) with real configured ports.
- [x] Move media-scheduling frontend off the 8130 collision (→ 8140).
- [x] Update `RESERVED_RANGES` to match reality.
- [x] `_register_in_start_sh` helper + sentinel regex in scaffold.py.
- [x] `scaffold_product` calls the helper; `next_steps` updated.
- [x] Migrate leaky tests (`TestScaffold.test_creates_new_product`, `TestSqlTemplatesIntegration`) to `tmp_path` seam.
- [x] Hygiene regression guard `TestScaffoldRespectsTestSeam`.
- [x] start.sh-injection tests (4).
- [x] Clean up orphan migration files + orphan test products from prior leaky runs.
- [x] All 24 tests pass.
- [x] `bash -n start.sh` syntax check passes.
- [ ] Memory entry `feedback_scaffold_auto_registers_products.md` updated to mention start.sh injection.
- [ ] User restarts `bash start.sh` to pick up the missing AdConnect frontend (immediate symptom fix).

## Methodology rule (durable)

Scaffolding a product auto-registers it in **two** runtime surfaces:

1. **Dashboard** via numbered seed-row migration in `products/core/backend/migrations/NNN_seed_<slug>_product.sql`.
2. **Local dev runner** via the `PRODUCTS` array in `start.sh` (between sentinels).

Both are single-source-of-truth. Editing either by hand stays safe; the tool is idempotent on the shared key (slug). When a future deploy surface is added (e.g., Cloudflare config), it joins this list — same shape: scaffold owns the registration, the surface stays the source of truth, the tool is idempotent.

## Out of scope (deferred)

- **Live DB sync for media-scheduling URL change** — file at `013_seed_..._product.sql` updated to 8140; live DB row may still hold 8130 if previously applied. `ON CONFLICT DO NOTHING` won't fix it. If the row is already there, run a one-off `UPDATE public.products SET url_base='http://localhost:8140' WHERE slug='media-scheduling';` via Supabase MCP. Not done now because we don't know the current live state without a query.
- **CLAUDE.md / KB landscape table sync** — `KB § 02-LANDSCAPE.md` still references the old 8130 for media-scheduling and is missing AdConnect/Dev Team rows. Separate three-way-sync pass.
- **Closure of CF migration project** — paused for this fix; resuming next.
