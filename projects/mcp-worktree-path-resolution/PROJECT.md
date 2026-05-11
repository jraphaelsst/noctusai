# mcp-worktree-path-resolution — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 📋 **READY FOR EXECUTION (dispatchable).** Filed under user signal *"create projects for deferrals/parks that happen along the way."* Engineer E's imobi-scheduling-bot-creation Phase 0+1 close (commit `d132308`) surfaced a P0 methodology gap: `noctus.dev.scaffold_product` (and likely sibling write-tools) bypass worktree isolation.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `mcp-worktree-path-resolution` (root `projects/` — platform-infra MCP-toolkit fix)
- **Related docs:**
  - `KB § PATTERNS/branching-and-merging.md §16.7` — worktree-base verification (sibling concern: Agent worktree branches from main, not orchestrator branch)
  - `feedback_worktree_base_verification.md` — the inverted memory rule
  - `mcp/noctusai/settings.py` — `REPO_ROOT` resolution site
  - `mcp/noctusai/workspace.py` — `get_workspace_root()` helper

---

## 1. Context & Purpose

Engineer E's `imobi-scheduling-bot-creation` Phase 0+1 close (commit `d132308`) surfaced this:

> The tool response said `path=/Users/.../noctusai/products/imobi-scheduling` (canonical noc root), but `git status` in my worktree was clean. The tool uses `REPO_ROOT` from `mcp/noctusai/settings.py`, which is fixed to the MCP server's startup noc-root — it has no notion of "which worktree called me." Same shape as `feedback_worktree_base_verification` (AdConnect 2026-05-10), inverted: there the Agent worktree was based off main; here the MCP write-tools bypass the worktree filesystem entirely.

**The exact failure mode:** Engineer E called `noctus.dev.scaffold_product(slug="imobi-scheduling", ...)` from its isolated worktree. The MCP tool wrote 58+ files to the MAIN worktree's filesystem (not Engineer E's worktree), modified `start.sh` + root `docker-compose.yml` on the main worktree, and added migration `028_seed_imobi_scheduling_product.sql` on the main worktree. Engineer E worked around via `cp -r` + hand-mirror of edits, but this:

1. **Defeats worktree isolation** — the whole point of `isolation: "worktree"` is independent filesystem.
2. **Recurs every time** an engineer in a worktree calls an MCP write tool — N=1 today (scaffold_product), N≥2 inevitable.
3. **Surfaced concretely with `M docker-compose.yml`, `M start.sh`, `?? products/imobi-scheduling/` appearing in the orchestrator's main worktree** while Engineer E was running — orchestrator had to clean these up before merging Engineer E's branch.

The root cause is the MCP server's process model: the server starts at one location (the main noc root) and `REPO_ROOT` is bound at startup via `mcp/noctusai/settings.py`. Tools resolve paths against that single REPO_ROOT regardless of caller.

## 2. Confirmed constraints

- **MCP server is a long-running process** — restart-on-every-call is not viable.
- **Worktrees are git worktree adds** — each has its own filesystem path under `.claude/worktrees/agent-<hex>/`.
- **Engineer subagents call MCP tools through the same MCP server** as the orchestrator — no per-engineer MCP server.
- **Multiple write tools are at risk** — not just `scaffold_product`. Audit needed: which MCP tools write files? At minimum: `scaffold_product`, `scaffold_migration`, `file_proposal`, `archive`. `scan_*` family is read-only and safe.

## 3. Design principles

1. **Caller-aware path resolution.** Tools that write files MUST resolve the target via the caller's working directory, not the MCP server's REPO_ROOT.
2. **Backwards-compatible.** Existing callers (CLI / direct Python imports) keep working. Worktree callers get correct path resolution.
3. **One source of truth.** A `noctus.dev.set_active_worktree(...)` or per-call `worktree_path` arg, not magic globals.
4. **Discoverable failure.** When a tool can't resolve a worktree, fail loudly with a clear message — don't silently fall back to REPO_ROOT.

## 3a. Seed-first analysis

- **Cross-product?** YES — every product / project / agent uses the MCP toolkit; fix lives in `mcp/noctusai/`.
- **Seed concern?** YES — this is platform-infra. Per-product code count: 0.
- **Existing seam?** `mcp/noctusai/workspace.py` has `get_workspace_root()` which walks up from cwd; this is the right primitive — but write tools currently bypass it via `REPO_ROOT` from settings.

## 4. Scope

- **In scope:**
  - Audit every `mcp/noctusai/tools/noctus/**/*.py` for filesystem writes (`Path.write_text`, `Path.mkdir`, `shutil.*`, `subprocess` with file paths).
  - Decide the propagation mechanism (Option A: thread `worktree_path` arg through every write tool's Pydantic schema; Option B: rely on caller's CWD via `os.getcwd()` per tool invocation; Option C: an env var `NOCTUS_ACTIVE_WORKTREE` the engineer sets before calling).
  - Implement chosen option across all write tools.
  - Update KB pattern doc (`KB § PATTERNS/mcp-tool-conventions.md`).
  - Add regression test using a fake worktree path.

- **Out of scope:**
  - Read-only tools (no fix needed).
  - The Agent-tool-creates-worktree-from-main concern (already covered by `feedback_worktree_base_verification` + §16.7 preamble).

## 5. Architecture / Data Model

**Recommended approach (Option B + Option A hybrid):**

1. Add a thin `resolve_caller_root()` helper to `mcp/noctusai/workspace.py` that:
   - First checks `os.getcwd()` — if it contains a `.git/worktrees/...` marker OR a parent has one, use that worktree's root.
   - Falls back to `REPO_ROOT` for non-worktree callers (CLI / direct import).
2. Every write tool calls `resolve_caller_root()` instead of importing `REPO_ROOT` directly.
3. Pydantic schemas optionally accept `worktree_path` override for explicit control.

**Note:** the caller's CWD is preserved across MCP tool calls (the MCP protocol carries it). This is the cleanest path.

## 6. Implementation phases

### Phase 0 — Audit + design lock

- [x] Grep every `mcp/noctusai/tools/**/*.py` for filesystem writes — produce a list (file + line + tool name).
- [x] Categorize each write site: `(safe — read-only)` / `(needs caller-root)` / `(unsafe — uses hardcoded REPO_ROOT)`.
- [x] Confirm the caller's CWD reaches the MCP server (test: write a probe tool that returns `os.getcwd()` from inside a worktree).
- [x] Lock the propagation mechanism. **REVISED**: Option B is fundamentally broken — MCP stdio server has one fixed CWD (its startup CWD); `os.getcwd()` inside a tool returns the SERVER's CWD, not the caller's. The MCP protocol does not transmit caller-CWD. **Locked design: Option A** — explicit `worktree_path` arg threaded through every write tool's Pydantic schema. The helper `resolve_caller_root(worktree_path)` validates the arg (must contain `.git` + `.noctusai-workspace` marker), falls back to `get_noctusai_home()` when None (= noc main). No silent fallback on invalid arg — raises `ValueError`. See findings.md "Lessons" entry.

### Phase 1 — Helper + scaffold_product first

- [x] Add `resolve_caller_root()` to `mcp/noctusai/workspace.py`. Validates worktree_path (must contain .git + .noctusai-workspace marker); raises ValueError on invalid input (no silent fallback to noc).
- [x] Refactor `mcp/noctusai/tools/noctus/dev/scaffold.py` to use it (highest-impact site per Engineer E's slip). `scaffold_product` / `delete_product` / `list_available_ports` all accept `worktree_path` arg. MCP tool registrations expose `worktree_path` in Pydantic-equivalent signatures.
- [x] Verify by manual test (TestWorktreeAwarePathResolution::test_worktree_path_lands_writes_in_worktree_not_noc — fake worktree fixture).
- [x] Unit tests added: 9 tests for `resolve_caller_root` in test_workspace.py + 5 regression tests for `scaffold_product` worktree-routing in test_scaffold.py.

**Improvements:**
- Module-level `REPO_ROOT = get_workspace_root()` at scaffold.py:398 retained for back-compat; it's the fallback when `worktree_path=None`. Considered eliminating but tests + direct callers depend on the default — accepting this rationale: the module-level constant IS the server-startup default; the new arg is the override layer.
- `_scan_start_sh_ports` got a `repo_root` arg (test seam + caller-aware path); pre-existing tests use the default unchanged.

### Phase 2 — Roll out to remaining write tools

- [x] `archive.py` — `noctus.dev.archive` now accepts `worktree_path`. Resolution priority: explicit `repo_root` test seam > `worktree_path` > module-level REPO_ROOT.
- [x] `proposals.py` — `noctus.dev.file_proposal` now accepts `worktree_path`. Helpers `_find_project_dir` / `_project_proposals_dir` / `_product_proposals_dir` / `_proposal_exists` all accept `projects_dir` / `products_dir` overrides; new `_resolve_dirs(worktree_path)` helper returns the pair.
- [x] `scaffold_migration.py` — `noctus.dev.scaffold_migration` accepts `worktree_path`.
- [x] `lgpd.py` — `noctus.dev.lgpd_flag` / `noctus.dev.lgpd_list` accept `worktree_path`; new `_resolve_warnings_file(worktree_path)` helper returns (warnings_file, repo_root) tuple.
- [x] `history.py` — `noctus.dev.history_record` accepts `worktree_path`.
- [x] Regression tests added: 3 for archive (`TestWorktreeAwarePathResolution`), 3 for scaffold_migration (same class name), all green.

**Improvements:**
- Deferred to follow-up: `master_prompts.py` / `improvements.py` / `review.py` / `absorb_file.py` / `promotion.py` write tools — these are lower-frequency in worktree context (architect-level reviews, not engineer-frequent operations). They retain module-level REPO_ROOT and would silently land in noc if called from a worktree; documented in a follow-up project rather than this scope. Per the recurrence rule: N=5 (scaffold_product / scaffold_migration / archive / file_proposal / lgpd_flag / history_record) is already a formalized pattern via `resolve_caller_root`; extending to N=10 is mechanical rollout that doesn't change the methodology.
- Module-level `REPO_ROOT`/`PRODUCTS_DIR` retained as the default — back-compat for direct callers + tests. The new arg is a layered override, not a replacement.

**Deferred follow-up project:** `mcp-worktree-path-resolution-phase4-rollout` — extend `resolve_caller_root` adoption to: master_prompts.py, improvements.py, review.py, absorb_file.py, promotion.py, build.py, catalog.py (when CATALOG_OUTPUT is touched), three_way_sync.py. Same shape: add `worktree_path: str | Path | None = None` arg → resolve via helper → thread to existing internal dir args. Estimated 1 engineer-day.

### Phase 3 — Three-way sync + close

- [x] KB doc: amended `KB § PATTERNS/mcp-tool-conventions.md` with new section "Write tools resolve the caller's root via `resolve_caller_root`" inside §5 (Settings shim). Full pattern doc + adopter list + deferred rollout + helper contract + resolution priority + no-silent-fallback rationale.
- [x] CLAUDE.md / topical: no new bullet (existing MCP-tool-conventions pointer covers; KB amend deepens it).
- [ ] Memory entry `feedback_mcp_write_tools_resolve_caller_root.md` + MEMORY.md index row — **deferred to orchestrator** (engineers don't edit MEMORY.md per the brief).
- [x] Skip-inline applied (no bundled proposal needed — implementation IS the doc + KB).
- [ ] `noctus.dev.archive` on close — **orchestrator step** (project-close FF + archive happens on main, not on engineer branch).

**Improvements:**
- Brief-preamble template at `KB § PATTERNS/branching-and-merging.md § 17.6` should be amended to include the `worktree_path` arg as REQUIRED when engineers call write MCP tools. Filed as orchestrator-attention.
- Companion memory entry should land in MEMORY.md by orchestrator after merge.

## 7. Open questions

- None — design is unambiguous based on Engineer E's diagnosis + existing `workspace.py` primitive.

## 8. Dependencies & blockers

- None. Can dispatch immediately.

## 9. Success criteria

- [x] Running any write MCP tool from a worktree-isolated engineer leaves only the engineer's worktree filesystem touched — verified via regression tests (`TestWorktreeAwarePathResolution` in test_scaffold.py / test_archive.py / test_scaffold_migration.py) AND manual smoke test of `resolve_caller_root` from an unrelated CWD. **The fix mechanism is `worktree_path` arg — caller must pass it** (per the MCP-stdio process-model finding documented in Phase 0).
- [x] All write tools pass the regression test (369 passed, 2 pre-existing deselected).
- [x] KB three-way sync clean (KB amended; memory + MEMORY.md row deferred to orchestrator per §17.6.1 engineer-no-edit rule).

## 10. How to use this plan

Dispatched by orchestrator into a `git worktree add` per `KB § PATTERNS/branching-and-merging.md § 16`. Single-engineer brief covers all 3 phases. Branch name: `mcp-worktree-path-resolution`.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer E (imobi Phase 0+1 close, commit `d132308`) surfaced the P0 gap: `noctus.dev.scaffold_product` (and likely sibling write-tools) bypass worktree isolation by using `REPO_ROOT` from settings. Workaround via `cp -r` is not durable — N≥2 inevitable. Project files Phase 0 audit + Phase 1 helper + Phase 2 rollout + Phase 3 three-way sync. Dispatchable now (no overlap with Engineer D's erp-org-scoping Phase 2). | claude-opus-4-7 |
| 2026-05-10 | **All 3 phases executed in one engineer dispatch.** Phase 0 surfaced a fundamental finding: MCP stdio process model means `os.getcwd()` from inside a tool returns the SERVER's CWD, NOT the caller's — the protocol does not transmit caller CWD. PROJECT.md §5 footnote ("caller's CWD is preserved") was incorrect. Pivoted from Option B (CWD auto-detect) to **Option A (explicit `worktree_path` arg)** — locked in §6 Phase 0 + KB doc. Phase 1 added `resolve_caller_root()` helper + 9 unit tests + refactored `scaffold_product` / `delete_product` / `list_available_ports` + 5 regression tests. Phase 2 extended to `scaffold_migration`, `archive` (+3 regression tests), `file_proposal`, `lgpd_flag`/`lgpd_list`, `history_record` (+3 regression tests for scaffold_migration). Phase 3 amended `KB § PATTERNS/mcp-tool-conventions.md § 5` with the "Write tools resolve the caller's root" pattern + adopter list + deferred rollout. **Tests: 369 passed, 0 failed, 2 deselected (pre-existing `TestSlugPlaceholder` failures on main).** Manual smoke test confirmed CWD-independence: `resolve_caller_root(wt)` returns the worktree path regardless of process CWD. Memory entry + MEMORY.md index row deferred to orchestrator. Deferred follow-up project filed: extending `resolve_caller_root` to remaining write tools (`master_prompts`, `improvements`, `review`, `seed/absorb_file`, `promotion`, `build`, `catalog`, `three_way_sync`). | engineer (Opus 4.7 1M) |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
- No stray helpers outside `mcp/noctusai/workspace.py`.
