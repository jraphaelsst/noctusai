# mcp-worktree-rollout-phase4 — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 📋 **READY FOR EXECUTION (dispatchable, mechanical refactor).** Filed under user signal "create projects for deferrals/parks that happen along the way." Engineer K's `mcp-worktree-path-resolution` close (commit `b74631f`) shipped the helper + 8 high-impact write tools; this project completes the rollout to the remaining 8 write tools.
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

### Phase 0 — Audit + sanity grep

- [ ] Re-grep each tool file for any path-resolution NOT covered by Engineer K's audit (in case the source has shifted).
- [ ] Confirm test seams (where present) follow the expected `*_dir=` / `*_path=` / `repo_root=` shape.

### Phase 1 — Mechanical refactor (8 tools)

- [ ] `master_prompts.py::verify_master_prompt` — accept `worktree_path`, call helper, propagate to write site.
- [ ] `improvements.py::improvements` — same.
- [ ] `review.py` review-mode writes — same.
- [ ] `seed/absorb_file.py::absorb_file` — same.
- [ ] `promotion.py` promotion tools — same (this one moves files; preserve git mv semantics).
- [ ] `build.py` build-output writes — same.
- [ ] `catalog.py` — IF CATALOG_OUTPUT write target is per-caller (verify in Phase 0). Catalog INPUT is noc-shared and stays so.
- [ ] `three_way_sync.py::three_way_sync` — same.

### Phase 2 — Verify + close

- [ ] `pytest mcp/noctusai/tests/` — green; Engineer K's 369 baseline preserved + any new tests for these 8 sites.
- [ ] Manual smoke: call one write tool from a fake worktree dir with `worktree_path=` arg; confirm output lands in the fake worktree.
- [ ] Tick all sub-tasks + Improvements blocks + §11 close entry.

## 7. Open questions

- None — pattern is locked by Engineer K. Pure mechanical adoption.

## 8. Dependencies & blockers

- Helper landed on main. No blocker.

## 9. Success criteria

- [ ] 8 remaining write tools adopt `worktree_path` arg.
- [ ] `pytest mcp/noctusai/tests/` green.
- [ ] Zero write tools remain unable to honor caller worktree.

## 10. How to use this plan

Single-engineer dispatch via `git worktree add`. Mechanical scope — single PR.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer K closed the predecessor `mcp-worktree-path-resolution` project after adopting `resolve_caller_root()` in 8 high-impact write tools. This project covers the remaining 8 tools via mechanical adoption of the same pattern. Pattern locked by predecessor; no design decisions remain. Ready for dispatch. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
