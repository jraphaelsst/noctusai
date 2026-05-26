---
name: noc-self-branch
description: Use when starting ANY writing/code task on noc while sharing the checkout with peers — triggers "self-branch", "branch yourself", "branch this", "branch yourself inline", or simply any committable change. The ABSOLUTE rule: never work on `dev`; isolate first.
version: 1.0.0
---

# noc-self-branch — isolate every write off `dev`

🔴 **Absolute rule (user mandate):** NO agent works directly on the `dev` checkout. The FIRST action on any change-producing task is to self-branch. `dev` is a clean idle integration anchor, touched ONLY as a ref at integrate. Reads/chat stay on `dev`.

## Workflow

0. **Residue sweep (drift-fix-on-contact §0).** BEFORE `task_branch action=start`, scan for the recurring git-leftovers drift class (untracked at repo root, worktree-uncommitted state on peer trees). One call: `git status --porcelain` at the primary + glance at `git worktree list --porcelain`. Drift found ⇒ apply the on-contact drill (PAUSE → resolve → surface-if-blocked → update docs → continue) BEFORE forking the new worktree. The clean tree is the precondition for clean parallel work — leftovers absorbed into your fresh worktree become your problem. → `KB § PATTERNS/common/drift-fix-on-contact.md`
1. **Start** — `noctus.dev.task_branch action=start slug=<kebab-task>` (dry-run → `confirm=true`). Forks `.claude/worktrees/<slug>` on `feat/<slug>` off `origin/dev`. Add `wire_env=true` if the slice needs a FE build / vitest in the worktree.
2. **Work + commit IN the worktree** — every Edit/Write/commit happens under `.claude/worktrees/<slug>/`. Confirm `pwd` is the worktree path, never the primary checkout.
3. **Integrate (worktree-explicit — NOT the MCP wrapper when a peer is live):** `git -C <wt> fetch origin && git -C <wt> rebase origin/dev && git -C <wt> push origin HEAD:dev`. Retry on non-FF race; NEVER `--force`. Conflict → abort + surface.
4. **Cleanup** — `noctus.dev.task_branch action=cleanup slug=<slug> confirm=true` (salvages recovery pointer, then removes). Return the primary to `dev` idle.

## Guardrails

- **Cross-tree hazard:** `noctus.dev.*` MCP tools run from the PRIMARY CWD ⇒ `task_branch integrate` can leak a peer's uncommitted files into your worktree. Integrate worktree-explicitly (step 3), not via MCP, whenever a peer is active.
- **REPO_ROOT cross-tree resolution (fixed 2026-05-26, N=3 codified):** `cli.py` / direct python imports invoked from inside a worktree now auto-resolve `REPO_ROOT` to the worktree (via `workspace._detect_worktree_root` — boundary detection on `.claude/worktrees/<slug>/`). Explicit lever for edge cases: `NOCTUSAI_HOME=$PWD python mcp/noctusai/cli.py ...`. Verify the keeper's view matches the worktree before relying on it; if it doesn't, that's a regression on the workspace resolver — surface to the tech-lead.
- Never `git switch`/`reset` the shared `HEAD` under a peer (the §9a 2-day-chaos sin).
- "Inline" (no dispatch) ≠ work-on-`dev` — you still branch. The inline cutoff is size-only and orthogonal.
- A worktree is **invisible to the running env** — unit-green there ≠ live works. Integrate + live-probe before calling a UI feature done.

## Depth
`KB § PATTERNS/common/self-branching-mode.md` (§0 absolute rule, §5a wire_env, §5b cross-tree hazard) · front-door `KB § PATTERNS/common/branching.md`.
