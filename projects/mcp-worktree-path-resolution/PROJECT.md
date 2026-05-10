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

- [ ] Grep every `mcp/noctusai/tools/**/*.py` for filesystem writes — produce a list (file + line + tool name).
- [ ] Categorize each write site: `(safe — read-only)` / `(needs caller-root)` / `(unsafe — uses hardcoded REPO_ROOT)`.
- [ ] Confirm the caller's CWD reaches the MCP server (test: write a probe tool that returns `os.getcwd()` from inside a worktree).
- [ ] Lock the propagation mechanism (default rec: Option B with optional A override).

### Phase 1 — Helper + scaffold_product first

- [ ] Add `resolve_caller_root()` to `mcp/noctusai/workspace.py`.
- [ ] Refactor `mcp/noctusai/tools/noctus/dev/scaffold.py` to use it (highest-impact site per Engineer E's slip).
- [ ] Verify by running `scaffold_product` from a worktree and confirming output lands in the worktree, NOT the main repo.
- [ ] Unit test using `tmp_path` fixture.

### Phase 2 — Roll out to remaining write tools

- [ ] `archive.py`, `file_proposal.py`, `scaffold_migration.py`, and any others from Phase 0 audit.
- [ ] Each refactor + 1 test.

### Phase 3 — Three-way sync + close

- [ ] KB doc: amend `KB § PATTERNS/mcp-tool-conventions.md` with "MCP write tools resolve caller root" rule.
- [ ] CLAUDE.md / topical: no new bullet (the existing MCP-tool-conventions pointer + this KB amend covers it).
- [ ] Memory entry `feedback_mcp_write_tools_bypass_worktree.md` + MEMORY.md index row.
- [ ] Bundled proposal or apply-inline-then-skip.
- [ ] `noctus.dev.archive` on close.

## 7. Open questions

- None — design is unambiguous based on Engineer E's diagnosis + existing `workspace.py` primitive.

## 8. Dependencies & blockers

- None. Can dispatch immediately.

## 9. Success criteria

- [ ] Running any write MCP tool from a worktree-isolated engineer leaves only the engineer's worktree filesystem touched (verified manually + via test).
- [ ] All write tools pass the regression test.
- [ ] Three-way sync clean.

## 10. How to use this plan

Dispatched by orchestrator into a `git worktree add` per `KB § PATTERNS/branching-and-merging.md § 16`. Single-engineer brief covers all 3 phases. Branch name: `mcp-worktree-path-resolution`.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer E (imobi Phase 0+1 close, commit `d132308`) surfaced the P0 gap: `noctus.dev.scaffold_product` (and likely sibling write-tools) bypass worktree isolation by using `REPO_ROOT` from settings. Workaround via `cp -r` is not durable — N≥2 inevitable. Project files Phase 0 audit + Phase 1 helper + Phase 2 rollout + Phase 3 three-way sync. Dispatchable now (no overlap with Engineer D's erp-org-scoping Phase 2). | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
- No stray helpers outside `mcp/noctusai/workspace.py`.
