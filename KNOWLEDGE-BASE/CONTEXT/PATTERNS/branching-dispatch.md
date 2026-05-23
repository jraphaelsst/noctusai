# Branching-dispatch — the parallel-agent runbook

> **One-liner.** Decompose a task into **file-disjoint** subtasks, run one engineer agent per subtask **in parallel, each in its own worktree/branch**, then the architect collects the signals, detects + resolves collisions (incl. semantic duplicates git can't see), lands the reconciled result on the **integration branch** — **never on `main`** until 100% resolved.

This is the **operations runbook** (the actionable sequence). The deep reference — push semantics, recovery, long-running maintenance, the full collision-class derivation — lives in [[branching-and-merging]] (runbook ↔ reference, same split as [[containerization]] ↔ [[containerization-operations]]).

**Direction of absorption (one-way, into noc).** noc's branching methodology is the **richer, primary** system — the 1851-line [[branching-and-merging]] reference plus collision-class-at-dispatch, wave-gating, overlay-divergence patch safety, and `dispatch_preflight`. We **absorbed** exactly **three crystallizations** from the smaller `knowledge-extractor` sibling repo (2026-05-23, its `doc/branching-dispatch.md`, proven on its audit-m1..m7 / absorb-m1..m7 waves): **(1)** semantic-duplicate collision detection, **(2)** the honest `--no-ff` reconciliation commit, **(3)** the tight runbook *form*. Everything else here is noc's own, marked **[noc]**. noc is source-of-truth; KE contributed three sharp bits, nothing more.

---

## When to use it (trigger phrases)

"**dispatch** agents", "**branch** agents / this", "**branching-dispatch**", "run these in **parallel**", "work on all of that at the same time".

**Don't dispatch a single coherent unit** — the [[branching-and-merging]] §18.2.1 **inline cutoff** binds: `<100 LoC ∧ <3 files ∧ single-phase` → architect does it inline; 2+ small file-disjoint tasks ride ONE compound brief. Dispatch is for **multiple genuinely independent subtasks** that amortize the ~45–60k engineer contextualization tax.

---

## Branch model

| Branch | Role | Rule |
|---|---|---|
| `main` (`origin/main`) | 🔒 **Frozen.** | NEVER commit/merge/push without explicit per-action consent. Gated until 100% resolved. |
| `feat/<project>` | **Integration branch** — the working "fake-main"; all reconciled work converges here. | Commit/merge freely; PR → `main` only at close. |
| `feat/<project>-<slice>` | **One worker branch per subtask** (DASH form — see §2 ⚠). | Forked from the integration tip; own worktree; deleted after merge. |

---

## Roles ([noc] = [[branching-and-merging]] § Roles)

- **Architect** = the main session. Decomposes, dispatches, **collects signals, detects collisions, reconciles, verifies**, lands on the integration branch, cleans up, gates `main`. Does NOT do the subtask work.
- **Engineers** = dispatched subagents, one per file-disjoint slice, isolated worktree, focused brief (inherit [noc] `.claude/agents/engineer-default.md`).

---

## The protocol

### 1 · Decompose into file-disjoint subtasks
Each slice owns a **disjoint file-set**. Overlapping sets are the #1 collision source — design them out: prefer **new files per agent**; **at most ONE agent edits any given existing file**. **[noc]** classify each slice's edit-set vs the parallel-active set at *dispatch* time ([[branching-and-merging]] §21 collision-class): **C1 file-disjoint** → parallel-clean · **C2 same-file-additive** → brief additive-only · **C3 substantive-overlap** → re-scope to a sibling file OR sequence into a later wave. **[noc]** wave-gate dependencies ([[branching-and-merging]] §18): a slice that consumes another's output dispatches only after that one merges.

### 2 · Create isolated worktrees + parallel branches
From the integration branch:
```bash
git worktree add -b feat/<project>-<slice> ../noc-wt-<slice> feat/<project>   # DASH, not slash
```
One per slice, deterministic branch name. The harness `Agent isolation: "worktree"` flag is the built-in alternative.

> **⚠ Branch-naming — worker branches use the DASH form `feat/<project>-<slice>`, never the slash form `feat/<project>/<slice>`.** Git cannot create a nested ref under an existing **leaf** ref: if the integration branch is literally `feat/<project>`, then `feat/<project>/<slice>` fails with `cannot lock ref … 'feat/<project>' exists`. (KE avoided this by using *distinct* prefixes — `methodology-dev` integration + `feat/<name>` workers.) Either use the dash form OR name the integration branch distinctly (`<project>-integration`). **N=3, 2026-05-23** — all three engineers on `seed-deploy-config-contract` hit it and self-corrected to the dash form.
>
> **⚠ Harness `isolation: "worktree"` forks from `main`/`origin/main`, not your current working-branch HEAD.** So the worktrees do NOT carry commits that live only on the integration branch (e.g. an uncommitted-elsewhere PROJECT.md or a same-session methodology absorb). Consequences: (a) **briefs MUST be self-contained** (inline the full API/spec — don't rely on the engineer reading the integration-branch PROJECT.md); (b) `dispatch_preflight project_slug=…` is moot for these engineers (the doc isn't on their base); (c) each slice branch is `main`-based → merge it onto the **integration tip** (`--no-ff`), which is a strict superset.
>
> **⚠ Cross-tree overlay leak — verify true disk at integration.** The harness file overlay can leak an engineer's in-progress edits into the **main checkout's** working tree (a `M`/`??` on a file the engineer "owns" elsewhere), and that leak may DIFFER from the engineer's *committed* branch. The committed+pushed branch is source-of-truth: `git diff origin/<slice-branch> -- <file>` to compare, then **discard the working-tree leak** (`git checkout --` / `rm` the untracked) and merge the branch. Seen 2026-05-23 (`compliance.py` + `deploy-config-contract.md` leaked into main; recovered by discard-leak + merge-branch). Strict instance of [[harness-overlay-worktree-divergence]].

### 3 · Dispatch in parallel
Send all `Agent` calls **in a single message** so they run concurrently. Each brief carries the **Worker Contract** (below).

### 4 · Collect the signal
Each engineer reports **branch name · HEAD hash · files changed**. **[noc] overlay-divergence safety:** the engineer ALSO writes a `/tmp/<slice>.patch` early and pastes grep-proof of the on-disk change — `Edit`/`Write` can succeed against a harness overlay while the worktree stays clean ([[harness-overlay-worktree-divergence]]); the architect verifies true disk from a separate Bash context before trusting the signal.

### 5 · Evaluate + detect collisions — TWO types
```bash
git diff --name-status feat/<project> feat/<project>-<slice>
```
- **(a) Path-overlap** — two branches touch the same file. Git flags it at merge.
- **(b) Semantic-duplicate [the sharp one]** — *different paths, same content* (two agents each author a registry / bibliography / helper). **Git will NOT flag this — the architect must.** Read the deliverables, not just the file list.

### 6 · Merge — `--no-ff`, provenance-preserving
```bash
git merge --no-ff feat/<project>-<slice> -m "Merge feat/<project>-<slice>: <summary>" \
  -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```
`--no-ff` keeps each agent's commits intact so history shows **what each agent contributed**. (FF/concat-clean per [[branching-and-merging]] §10.4 is the alternative when slices are provably C1 and provenance doesn't matter; for collision-prone parallel work, prefer `--no-ff`.)

### 7 · Reconcile — in a dedicated commit, honest history
Resolve collisions/duplicates/conflicts in a **separate reconciliation commit** on the integration branch — **keep the agents' original commits intact**. The history should honestly show the collision **and** the fix (no-silent-errors applied to git history). Example: pick one canonical file, port unique entries from the duplicate, fix cross-links, delete the stray.

### 8 · Verify ([noc] finish-the-session)
Tests/builds green for touched code (`pytest` / `vite build`); KB sync (`--verify-kb-sync`) + symbology drift if docs changed; three-way sync for any methodology change. Report outcomes faithfully.

### 9 · Clean up
```bash
git worktree remove ../noc-wt-<slice> && git worktree prune
git branch -d feat/<project>-<slice>   # safe: already merged
```

### 10 · Gate `main`
PR/push the integration branch → `main` **only when** every slice is merged, every collision (incl. semantic) resolved, verify is green, and you're 100% sure. Per-action consent ([[branching-and-merging]] §4.3 / [noc] never-auto-push).

---

## Worker Contract (paste into every engineer brief)

- Work **only** inside your worktree path; `pwd` + `git branch --show-current` before editing — wrong branch ⇒ STOP.
- Touch **only your assigned files** (the disjoint set). Never edit another agent's files.
- Follow CLAUDE.md (seed-first, AST-first, no silent errors, symbol-first docs).
- Write `/tmp/<slice>.patch` **early** (survives the ~600s watchdog); paste on-disk grep-proof of your change.
- Stage **only your files by explicit path** — never `git add .` / `-A`. Commit on your worker branch; message ends with the `Co-Authored-By` trailer.
- **Never** touch `main` or the integration branch, switch branches, or push to `main`.
- Final message reports: **branch · HEAD hash · files changed** (+ the patch path).

---

## Safety rules (non-negotiable)

1. 🔒 `main` untouched without per-action consent; gated until 100% resolved.
2. File-disjoint sets per agent; **architect owns collision detection (incl. semantic-dup) + the reconciliation commit**.
3. Explicit-path `git add` everywhere; never `-A`.
4. Verify (tests + links + sync gates) before "done"; faithful reporting.
5. **[noc]** run `noctus.dev.dispatch_preflight` before dispatch (fork-base + collision + env-pin + project-doc-phantom checks); keep a root `findings.md`.

→ Deep reference: [[branching-and-merging]]. Pre-dispatch tooling: [[dev-toolkit-scaffolders]] (`dispatch_preflight` / `salvage_worktree` / `findings`). Collision-class derivation: [[branching-and-merging]] §21.
