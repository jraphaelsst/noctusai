# Harness Overlay ⊥ Worktree Divergence

> **The harness file overlay can report `Edit`/`Write`/`Read` success while the on-disk git worktree stays clean — the work lives only in the overlay and is lost when the agent ends. The agent's OWN `git status`/`grep` are served the same diverged overlay, so naive self-verification passes falsely.**
>
> Only a *separate* Bash context that reads true disk reliably catches this. A salvage `git commit` that says "nothing to commit" is the divergence tell.

---

## 1. The rule (R6)

The harness maintains a file overlay. `Edit` / `Write` / `Read` can all report success against the overlay while the **on-disk git worktree stays clean**. The work exists only in the overlay; it is **lost** when the agent process ends. Critically: the agent's own `git status` / `git diff` / `grep` are served the **same diverged overlay** — so a naive in-agent self-check confirms work that does not exist on disk. Self-verification from inside the diverged context is not verification.

Before any "ready" / "done" return that claims an on-disk change:

1. After staging, run `git -C <worktree> diff --cached --name-only` ∧ `git -C <worktree> status --porcelain` — the files MUST appear.
2. `grep` / `cat` the **actual on-disk file** for the change marker — ¬ an `Edit` "success" message.
3. Disk clean despite `Edit` "success" ⇒ divergence ⇒ **re-author via Bash** (`python -c` / libcst for `.py`; heredoc for SQL/prose) ∧ re-verify on disk.
4. Paste the literal `git diff --cached --name-only` + a `grep -c <marker> <file>` proof line in the return. "Report says done" is ¬ evidence; on-disk `grep` is.

## 2. Why — the evidence

The connector-MCP project hit ≥2 real lost-work incidents from this exact divergence:

- **DOCS-CONSUME-2** — caught the divergence, recovered by re-authoring via a Bash heredoc, and shipped.
- **SW-RLS** — did **not** catch it; its deliverable vanished **twice**, costing two re-dispatches.

Only the **architect's separate Bash context** (which reads true disk, outside the engineer's overlay) reliably caught the divergence. The tell that surfaced it: a salvage `git commit` reporting *"nothing to commit"* on a worktree the engineer reported as fully staged.

## 3. How to apply

**Engineer side** (`.claude/agents/engineer-seed.md § 1a`):
- After staging, prove on disk: `git diff --cached --name-only` + `grep -c <marker> <file>` against the **actual file**, not the Edit success message.
- On divergence: do ¬ loop-fight the overlay. Re-author the change via Bash (`python -c` / libcst for code; heredoc for prose/SQL) and re-verify on disk.
- Never return "ready" on the strength of an `Edit` "success" alone.

**Architect side:**
- Verify every salvaged worktree from your **own separate Bash context** (true disk) before committing. NEVER trust the engineer's report ∨ the engineer's self-check block.
- A divergence-clean worktree ⇒ do **¬** loop-redispatch (the divergence recurs) → apply the well-specified change **architect-inline** from the reliable context.
- The salvage `git commit` saying "nothing to commit" is the divergence signature — treat it as the tell, not a no-op.

## 4. Relationship to other rules

- **Strict instance of *codebase is source of truth*** (CLAUDE.md §1) — the on-disk tree is authoritative; the overlay (like a doc/summary/report) is derived and can drift. R6 is the harness-mechanic case of that rule.
- **Companion to the worktree-base preamble** (`KB § PATTERNS/architect/branching-and-merging.md § 16.7`) — §16.7 is the *stale-base* harness gap (worktree forks from main); R6 is the *overlay-divergence* harness gap (edits never reach disk). Both are harness-default failures our dispatch/verification layer must structurally defeat.
- **Operationalized by the dev toolkit** — `noctus.dev.salvage_worktree` exists precisely to give the architect a reliable true-disk salvage path for the divergence this rule names.
- **Instance of *no silent errors*** — "verification ✓" while disk is clean is the canonical unverified-checkmark.

s1 (DOCS-CONSUME-2 + SW-RLS lost-work incidents) → s2 (memory `feedback_harness_overlay_worktree_divergence`) → **s3 (this doc + CLAUDE.md pointer + INDEX.md; engineer-seed § 1a is the standing-protocol surface)**. s4 is not a `check_*` keeper (a code detector cannot see overlay-vs-disk divergence — the divergence is exactly what hides itself from in-context tooling); the codification surface is the engineer-seed protocol block + architect salvage discipline, not a static-analysis detector.

## 5. Anti-patterns

- **Trusting `Edit`/`Write` "success" as proof of an on-disk change.** The success is overlay-true, possibly disk-false. Grep the file.
- **Self-`git status` from inside the diverged agent.** Same overlay, same lie. Verification must come from a separate Bash context (architect-side) ∨ from re-authoring via Bash + on-disk re-grep (engineer-side).
- **Loop-redispatching a divergence-clean worktree.** The divergence recurs. Apply the change architect-inline from the reliable context instead.
- **Returning "ready" without the literal `git diff --cached --name-only` + `grep -c` proof lines.** "Report says done" is not evidence.

---

> **Note on R6 codification surface:** the durable home for R6 includes `.claude/agents/engineer-seed.md § 1a` (the standing engineer protocol every dispatch reads). This pattern doc is the KB-depth s3 layer; the engineer-seed block is the operational enforcement surface. (The connector-MCP project flagged the engineer-seed §1a edit as needing explicit user authorization because it is harness-blocked agent self-modification; the rule statement itself ships at memory + CLAUDE.md + this doc independent of that edit's authorization.)

**Memory:** `feedback_harness_overlay_worktree_divergence`. **CLAUDE.md:** §1 (codebase-source-of-truth bullet; *Anti-divergence on-disk verification*). **Companion:** `.claude/agents/engineer-seed.md § 1a`, `KB § PATTERNS/architect/branching-and-merging.md § 16.7`, `noctus.dev.salvage_worktree`.
