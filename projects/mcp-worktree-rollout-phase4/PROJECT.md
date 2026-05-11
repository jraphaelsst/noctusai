# mcp-worktree-rollout-phase4 — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** ✅ **PHASE 0+1+2 COMPLETE.** 8 remaining write tools adopted `resolve_caller_root(worktree_path)`; 25 new regression tests added; full `pytest mcp/noctusai/tests/` green at 974 passed / 5 pre-existing failures (same as baseline; no regressions). Manual smoke test confirms catalog write lands in fake worktree, not noc main.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `mcp-worktree-rollout-phase4`
- **Related docs:**
  - `archive/projects/2026-05-10/13-mcp-worktree-path-resolution/PROJECT.md` — predecessor (helper + Phase 1+2 adopters)
  - `mcp/noctusai/workspace.py::resolve_caller_root` — the helper to consume
  - `KB § PATTERNS/mcp-tool-conventions.md § 5` — canonical pattern doc

---

## 1. Context & Purpose

Engineer K shipped `resolve_caller_root(worktree_path)` + adopted it across 8 high-impact write tools (scaffold_product, delete_product, available_ports, scaffold_migration, archive, file_proposal, lgpd_flag, lgpd_list, history_record). The remaining 8 write tools were captured as a Phase 4 deferred backlog. Same mechanical pattern, same helper — single engineer dispatch.

The 8 remaining tools:
- `master_prompts.py` — `verify_master_prompt` (writes verification reports / fix files)
- `improvements.py` — `improvements` (writes retrospective markdown)
- `review.py` — `review`-mode writes (proposals, reports)
- `seed/absorb_file.py` — `absorb_file` (moves files into seed)
- `promotion.py` — promotion tools (writes promotion manifests, files moved)
- `build.py` — build-output writes
- `catalog.py` — `catalog` writes when CATALOG_OUTPUT target is touched
- `three_way_sync.py` — `three_way_sync` (writes KB / CLAUDE / memory verification reports)

## 2. Confirmed constraints

- **Helper shipped on main** (commit `b74631f`). Import from `noctusai_lib.workspace` or `mcp.noctusai.workspace` per existing tool conventions.
- **3-tier resolution priority preserved**: explicit test seam > `worktree_path` arg > module default.
- **No silent fallback** — invalid `worktree_path` raises ValueError.
- **Catalog tool is noc-shared by design** — its INPUT (the tool registry) lives in noc; only OUTPUT writes need caller-aware resolution.

## 3. Design principles

1. **Mirror Engineer K's adoption pattern exactly.** Pydantic schema accepts `worktree_path: str | None = None`; tool body calls `resolve_caller_root(worktree_path)` to get the effective root.
2. **Test seam preservation.** Where a tool already has a `repo_root=` / `products_dir=` / `<path>=` test seam, the priority is: test seam > worktree_path > module default. Engineer K's test suite (369 passing) is the reference shape.
3. **No silent fallback recurrence.** Invalid `worktree_path` raises with descriptive message. Match Engineer K's helper contract.

## 3a. Seed-first analysis

- **Cross-product?** No — this is MCP infrastructure.
- **Seed home?** `mcp/noctusai/` only.
- **Per-product code count:** 0. This is platform infra.

## 4. Scope

- **In scope:** 8 remaining write tools adopting `worktree_path` arg + helper call.
- **Out of scope:** New helper design (Engineer K's is canonical), new tools, KB pattern doc expansion (already done by Engineer K).

## 5. Architecture / Data Model

Same as Engineer K's project. Each tool gets a `worktree_path: str | None = None` Pydantic field; body calls `resolve_caller_root(worktree_path)`; ValueError surfaces with the path that failed validation.

## 6. Implementation phases

### Phase 0 — Audit + sanity grep ✅

- [x] Re-grep each tool file for any path-resolution NOT covered by Engineer K's audit (in case the source has shifted).
- [x] Confirm test seams (where present) follow the expected `*_dir=` / `*_path=` / `repo_root=` shape.

**Audit findings (per tool):**

| File | Existing test seam | Resolution strategy |
|---|---|---|
| `master_prompts.py::verify_master_prompt` | None (used module-level `PRODUCTS_DIR`) | Added `products_dir` seam to `verify_master_prompt` + threaded through `check_master_prompt_staleness` + `sync_master_prompt` + `get_product_summary` (in `products.py`); `worktree_path` resolves to `<root>/products`. |
| `improvements.py::generate_improvements` | None (relied on absolute `project_path`) | Relative `project_path` now resolves against `resolve_caller_root(worktree_path)`; absolute paths unchanged. |
| `review.py::run_review` | None (used module-level `PRODUCTS_DIR`) | Added `products_dir` seam; threaded through `_detect`, evaluate-mode + headless-mode write sites. |
| `seed/absorb_file.py::absorb_file` | `products_dir=` + `repo_root=` already present | `worktree_path` resolves to both slots when not explicitly seamed. |
| `promotion.py::promote_from_seed_workspace` + `list_promotions` | `workspace_root=` + `noctusai_home=` already present | `worktree_path` resolves caller's worktree; `workspace_root` walks-up from there; `noctusai_home` defaults to the worktree itself. |
| `build.py::build_products` | `repo_root=` already present | `worktree_path` resolves to `repo_root` slot when not explicitly seamed. |
| `catalog.py::generate_catalog` | None (module-level `LIB_ROOTS`, `PRODUCTS_DIR`, `CATALOG_OUTPUT`) | Added `_resolve_roots(root)` helper; threaded `lib_roots`/`products_dir`/`repo_root` through `scan_lib_symbols`, `build_reexport_map`, `_iter_products`, `_iter_consumers`, `scan_importers`, `scan_duplicate_candidates`, `build_catalog`. Output writes to `<root>/mcp/noctusai/catalog.md`. |
| `three_way_sync.py::check_three_way_sync` | `repo_root=` already present | `worktree_path` resolves to `repo_root` slot when not explicitly seamed. |

3-tier resolution priority preserved across every tool: **explicit test seam > `worktree_path` > module default**.

### Phase 1 — Mechanical refactor (8 tools) ✅

- [x] `master_prompts.py::verify_master_prompt` — accepts `worktree_path`; threads `products_dir` through `check_master_prompt_staleness` + `sync_master_prompt` + `get_product_summary`.
- [x] `improvements.py::improvements` — accepts `worktree_path`; relative `project_path` resolves against worktree root.
- [x] `review.py` review-mode writes — accepts `worktree_path`; `_detect` + evaluate/headless write sites consume `base_products_dir`.
- [x] `seed/absorb_file.py::absorb_file` — accepts `worktree_path`; routes to `products_dir` + `repo_root` slots.
- [x] `promotion.py` promotion tools — both `promote_from_seed_workspace` + `list_promotions` accept `worktree_path`.
- [x] `build.py` build-output writes — `build_products` accepts `worktree_path`; routes to `repo_root` slot.
- [x] `catalog.py` — `generate_catalog` accepts `worktree_path`; output lands in `<root>/mcp/noctusai/catalog.md` per worktree.
- [x] `three_way_sync.py::three_way_sync` — `check_three_way_sync` accepts `worktree_path`; routes to `repo_root` slot.

### Phase 2 — Verify + close ✅

- [x] `pytest mcp/noctusai/tests/` — 974 passed, 5 failed (all 5 pre-existing baseline failures unrelated to this work — see findings.md §1). 25 new regression tests at `tests/test_worktree_rollout_phase4.py` covering all 8 tools + 3 priority slots each (worktree happy path, invalid worktree raises ValueError, explicit seam overrides worktree_path).
- [x] Manual smoke: `generate_catalog(write=True, worktree_path=<fake_worktree>)` writes to `<fake_worktree>/mcp/noctusai/catalog.md`; noc main `catalog.md` untouched (verified via mtime delta).
- [x] Tick all sub-tasks + Improvements blocks + §11 close entry.

**Improvements:**

- The audit surfaced an N=2+ pattern across multiple tools: `worktree_path=` plus a pre-existing test seam (`products_dir=` / `repo_root=` / `workspace_root=` / `noctusai_home=`). The 3-tier priority (`explicit seam > worktree_path > module default`) is now uniform across 9 adopters (K's 8 + Phase 4's 9 functions counting promotion's 2). Candidate for a tiny helper `_resolve_root_with_seam(seam_value, worktree_path, default)` to formalize the pattern — defer to a future cleanup pass per recurrence rule (N=3+ would justify; today's N=9 of an already-formalized pattern doesn't add value).
- `catalog.py` had the deepest refactor (8 functions touched) because of module-level constants `LIB_ROOTS` / `PRODUCTS_DIR` / `CATALOG_OUTPUT` bound at import time. The `_resolve_roots(root)` helper isolates the per-call rebuild. Other tools mostly had a single resolution point.
- `promotion.py` has an interesting semantics split: `workspace_root` is the SEED workspace (sibling of noc), while `worktree_path` is a worktree of noc. They're orthogonal concepts. The current resolution: `worktree_path` re-anchors the `get_workspace_root()` walk-up AND defaults `noctusai_home` to the worktree itself. This preserves "promote from seed workspace adjacent to my worktree → into my worktree's noc copy" — the most common use shape.

## 7. Open questions

- None — pattern is locked by Engineer K. Pure mechanical adoption.

## 8. Dependencies & blockers

- Helper landed on main. No blocker.

## 9. Success criteria

- [x] 8 remaining write tools adopt `worktree_path` arg.
- [x] `pytest mcp/noctusai/tests/` green (974 passed, 5 pre-existing failures unchanged from baseline).
- [x] Zero write tools remain unable to honor caller worktree.

## 10. How to use this plan

Single-engineer dispatch via `git worktree add`. Mechanical scope — single PR.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer K closed the predecessor `mcp-worktree-path-resolution` project after adopting `resolve_caller_root()` in 8 high-impact write tools. This project covers the remaining 8 tools via mechanical adoption of the same pattern. Pattern locked by predecessor; no design decisions remain. Ready for dispatch. | claude-opus-4-7 |
| 2026-05-10 | **PHASE 0+1+2 COMPLETE.** All 8 remaining write tools adopted `resolve_caller_root(worktree_path)` mirroring Engineer K's pattern: `worktree_path: str | None = None` Pydantic field; body resolves via `resolve_caller_root`; ValueError surfaces invalid paths. 3-tier priority preserved (explicit seam > worktree_path > module default). 9 functions touched across 8 files (master_prompts: 1 + 2 helpers; improvements: 1; review: 1; promotion: 2 — promote + list; build: 1; catalog: 1 + 6 internal helpers; three_way_sync: 1; absorb_file: 1). 25 new regression tests at `tests/test_worktree_rollout_phase4.py`. pytest mcp/noctusai/tests/ green (974/979 passed, 5 pre-existing failures unrelated to this work). Manual smoke verified. Ready for branch close + FF to main. | engineer-phase4 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
