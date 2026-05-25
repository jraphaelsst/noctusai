# Worktree-sensitivity guard — Project Document

> Living document. Filed 2026-05-25 as the Stage-4 (`s3 → s4`) follow-up of the unified-branching-methodology session. Zero-context-readable.

- **Created:** 2026-05-25
- **Last updated:** 2026-05-25
- **Status:** 📋 Filed / ready (deferred Stage-4 codification — not yet started)
- **Owner / stakeholders:** joaoraphaelsst
- **Related docs:** `KB § PATTERNS/branching.md` §2 (the worktree-sensitivity map — the s3 doc this codifies) · `KB § PATTERNS/compliance-regression-baseline.md` (working-tree-sensitivity section) · `KB § PATTERNS/methodology-codification-pipeline.md` (the s1→s4 path) · memory `feedback_unified_branching_worktree_sensitivity`
- **Project slug:** `worktree-sensitivity-guard` (at `projects/` — cross-cutting MCP-toolkit hardening)

---

## 1. Context & Purpose

noc tools that scan the **working tree** (`check_all_products` via `PRODUCTS_DIR.iterdir()`, `noctus.dev.validate`, `scan_*`, `noctus.hound.scan`, `kb_sync` auto-counts, `test_outline_typescript_corpus`, `noctus.graph.build`) read whatever is on disk — including a **peer agent's uncommitted files** on a shared/busy multi-terminal checkout. That produces **phantom regressions**: a scan/gate reports a NEW high/critical (∨ recurrence ∨ drift) that is NOT in committed `origin/dev` — it is a sibling's in-flight file. Bit 2026-05-25: an agent reported `test_all_products_compliant` + `test_real_products_pass_validate` "failing"; on a clean `origin/dev` worktree both were green. The s3 rule ("verify on a clean worktree before chasing") is now documented in `branching.md` §2 — this project is the s4 enforcement so the rule fires deterministically instead of relying on agent discipline.

---

## 2. Confirmed constraints

- **Codification depth** — docs-now-then-keeper, user-chosen 2026-05-25. *(The s3 docs shipped this session; this project is the deferred s4 — do not jump s3→s4 on a fresh pattern; route deliberately, recurrence-gated.)*
- **Warning, not a hard block** — the guard SURFACES contamination (the reading may still be wanted intentionally); it must not block a legitimate scan. *(A false-positive hard-block would be worse than the phantom it prevents.)*
- **MCP-first** — the guard is a `noctus.dev.*` capability (preflight/`task_branch`), never a `scripts/` one-off (`KB § PATTERNS/mcp-first-scripts.md`).

---

## 3. Design principles

1. Detect, don't decide — emit a structured `WARN` naming the peer-uncommitted files under the scanned path; let the agent re-verify on a clean worktree.
2. Reuse the existing signal — `git status --porcelain <scanned-path>` is the whole predicate; no new state.
3. Compose, don't fork — wire into `dispatch_preflight` (pre-dispatch) and/or `task_branch` (pre-scan), the existing worktree-lifecycle tools.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** YES — working-tree contamination is platform-wide; the predicate is product-agnostic.
2. **Is the data source product-specific?** NO — it reads `git status` of the whole checkout.
3. **Is the placement product-specific?** NO — it lives in the MCP toolkit (`mcp/noctusai`), the platform-wide home for `check_*`/preflight.
4. **Is the visibility / permission rule the same?** YES — uniform.
5. **Does the seam already exist?** YES — `noctus.dev.dispatch_preflight` ∧ `noctus.dev.task_branch` are the existing worktree-lifecycle seams; extend one/both.
6. **Default-on or opt-in?** DEFAULT-ON (warning-level; informational, never blocking).

**Litmus — per-product code count:** **0 lines.** Pure cross-cutting MCP-toolkit tooling. **§6 phases work in the toolkit, not per-product** (correct).

---

## 4. Scope

**In scope:**
- A pure predicate (e.g. `peer_uncommitted_under(path) -> list[str]`) over `git status --porcelain`, colocated test.
- Emit a `WARN` from `dispatch_preflight` (pre-dispatch) when the scanned set has peer-uncommitted files.
- Optional: a `task_branch`-adjacent advisory before a working-tree scan is run on the shared primary checkout.

**Out of scope (for now):**
- Hard-blocking a scan — explicitly rejected (§2); warning only.
- Auto-re-running scans in a clean worktree — too heavy; the agent decides.
- A new standalone MCP tool — prefer composing the existing preflight/lifecycle seams unless N≥2 consumers emerge.

---

## 5. Architecture / Data Model

- Predicate in `mcp/noctusai/tools/noctus/dev/` (alongside `dispatch_preflight`'s logic): `git status --porcelain -- <path>` → list of dirty/untracked paths NOT authored by the current task. Colocated `Test*` (seed real dirty/clean trees in a tmp git repo; assert the predicate; per `KB § PATTERNS/testing.md`).
- Wire the WARN into `dispatch_preflight` output (it already aggregates pre-dispatch checks) + document in `KB § PATTERNS/dev-toolkit-scaffolders.md`.

---

## 6. Implementation phases

### Phase 1 — Predicate + test
- [ ] `peer_uncommitted_under(path)` pure fn + colocated `Test*` (tmp-git-repo fixtures: clean ⇒ ∅, dirty/untracked ⇒ listed).

### Phase 2 — Wire into preflight
- [ ] `dispatch_preflight` emits a `WARN` (never blocks) listing contaminating paths when the dispatch's scanned set is dirty.
- [ ] Doc-sync: `dev-toolkit-scaffolders.md` + `branching.md` §2 (note s4 landed) + `methodology-codification-pipeline.md` worked-example row + memory update — three-way sync.

### Phase 3 — Optional task_branch advisory
- [ ] Pre-scan advisory in the `task_branch`/scan path (only if Phase 2 proves insufficient).

---

## 9. Success criteria
- A working-tree scan run on a checkout with peer-uncommitted files under the scanned path surfaces a deterministic `WARN` naming those files (no false-block).
- Colocated test asserts the predicate (regression-test-the-detector).
- Three-way sync complete; `branching.md` §2 + `compliance-regression-baseline.md` updated to note s4 landed.

---

## 11. Change log

| 2026-05-25 | Project filed as the s4 follow-up of the unified-branching-methodology session (s3 docs shipped: `branching.md` spine + worktree-sensitivity map + bump catalog). Deferred per user choice (docs-now-then-keeper). | unified-branching session |
