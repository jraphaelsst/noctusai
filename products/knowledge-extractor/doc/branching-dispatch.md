# Branching-Dispatch — parallel multi-agent dev workflow

> **One-liner.** Decompose a task into independent subtasks, run one agent per
> subtask **in parallel, each on its own isolated branch/worktree**, then a
> supervisor evaluates the deliverables, detects and resolves collisions, and
> lands the reconciled result on the integration branch — never on `main`.

This is the canonical way we develop in this repo. It was proven on the
methodology-enrichment task (modules 8–10, schema, references, citations) and is
documented here so it's repeatable.

---

## When to use it (trigger phrases)

Invoke this workflow when the user says any of:

- "**dispatch** agents / a task", "**branch** agents / a task"
- "**branching-dispatch**" (by name)
- "run these in **parallel**" / "work on all of that at the same time"

If the work is a single coherent unit (e.g. writing one doc), do NOT dispatch —
just do it directly on the integration branch. Branching-dispatch is for
**multiple genuinely independent subtasks**.

---

## Branch model

| Branch | Role | Rule |
|---|---|---|
| `main` | **Frozen safety net.** Holds the preserved original. | 🔒 NEVER touch — no commit, merge, push — without explicit per-action consent (CLAUDE.md §1). |
| `methodology-dev` | **Integration branch** (our working "fake-main"). All real work converges here. | Commit/merge freely; this is where reconciled deliverables land. |
| `feat/<name>` | **One parallel worker branch per subtask.** | Created from `methodology-dev`; lives in its own worktree; deleted after merge. |

> "Push to `methodology-dev`" = land the reconciled result on `methodology-dev`.
> There is no git remote yet, so "push" means commit/merge locally. If a remote
> is later added: pushing `methodology-dev` is fine; pushing/merging `main`
> requires explicit consent every time.

---

## Roles

- **Supervisor** = the main session (you, the orchestrator). Decomposes, dispatches,
  evaluates, detects collisions, reconciles, verifies, lands on `methodology-dev`,
  cleans up. Does NOT do the subtask work itself.
- **Worker agents** = dispatched subagents, one per subtask, each isolated.

---

## The protocol (step by step)

### 1 · Decompose into disjoint subtasks
Split the task so each subtask owns a **disjoint set of files**. Overlapping file
sets are the #1 source of collisions — design them out. Prefer: new files per
agent; at most ONE agent edits any given existing file.

### 2 · Create isolated worktrees + parallel branches
From `methodology-dev`:

```bash
git worktree add -b feat/<name> ../ke-wt-<name> methodology-dev
```

One per subtask. (The harness `isolation: "worktree"` agent flag is the built-in
alternative, but it fails if git was initialized **mid-session** — as here — so we
create worktrees manually, which also gives us deterministic branch names.)

### 3 · Dispatch agents in parallel
Send all `Agent` calls **in a single message** so they run concurrently. Each
agent prompt MUST include the **Worker Agent Contract** (below).

### 4 · Collect the signal
Each agent reports `git branch --show-current`, `git rev-parse HEAD`, and the files
it changed. That commit-per-branch is the **signal** the supervisor evaluates.

### 5 · Evaluate + detect collisions
Before merging, for each branch:

```bash
git diff --name-status methodology-dev feat/<name>
```

Look for: (a) **path overlaps** (two branches touching the same file), and
(b) **semantic duplicates** (different paths, same content — e.g. two agents each
writing a bibliography). Git won't flag (b) — the supervisor must.

### 6 · Merge
Merge each branch into `methodology-dev` with `--no-ff` (preserves provenance —
history shows what each agent contributed):

```bash
git merge --no-ff feat/<name> -m "Merge feat/<name>: <summary>" \
  -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### 7 · Reconcile
Resolve collisions/duplications/conflicts in a **dedicated reconciliation commit**
on `methodology-dev` (keep the agents' original commits intact — the history should
honestly show the collision and the fix). Example: pick one canonical file, port
unique entries from the duplicate, fix cross-links, delete the stray.

### 8 · Verify
- Project rules hold: anonymized (no names/brands), atemporal (no result numbers).
- Cross-links resolve; no broken references.
- If code changed: `cd backend && pytest` is green (docs-only changes skip this).

### 9 · Clean up
```bash
git worktree remove ../ke-wt-<name>     # per worktree
git worktree prune
git branch -d feat/<name>               # safe: already merged
```

---

## Worker Agent Contract (paste into every dispatched agent)

- Work **only** inside your assigned worktree path; verify with `pwd` and
  `git branch --show-current` before editing. If on the wrong branch, STOP.
- Touch **only your assigned files** (the disjoint set). Never edit another agent's files.
- Follow project rules (CLAUDE.md): language/voice match the corpus; anonymized + atemporal; DRY; no silent gaps; cite sources.
- Stage **only your files by explicit path** — never `git add .` / `-A`.
- Commit on your worker branch; message ends with the `Co-Authored-By` trailer.
- **Never** touch `main` or `methodology-dev`, switch branches, or push.
- Final message MUST report: branch name, HEAD hash, files changed.

---

## Safety rules (non-negotiable)

1. 🔒 `main` is never touched without explicit per-action consent.
2. Disjoint file sets per agent; supervisor owns collision detection + reconciliation.
3. Explicit-path `git add` everywhere; never `-A`.
4. Verify (rules + links + tests) before declaring done; report outcomes faithfully.
5. The reconciliation commit is the supervisor's job, on `methodology-dev`, after merges.
