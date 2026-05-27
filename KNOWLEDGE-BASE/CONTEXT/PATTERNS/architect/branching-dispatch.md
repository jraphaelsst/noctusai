# Branching-dispatch — the parallel-agent runbook

> **Front-door.** The *parallel* mode of the unified [[branching]] methodology (the §0 primitive at scale = N engineers). Read [[branching]] first for the decision spine, the worktree-sensitivity map, and the known-errors bump catalog; this doc is the parallel-mode runbook.

> **One-liner.** Decompose a task into **file-disjoint** subtasks, run one engineer agent per subtask **in parallel, each in its own worktree/branch forked from `dev`**, then the architect collects the signals, detects + resolves collisions (incl. semantic duplicates git can't see), lands the reconciled result on **`dev`** (the persistent integration branch) — **never on `main`** (production; reached only by the explicit, consent-gated `dev → main` deploy, [[branching-and-merging]] §0.2).

This is the **operations runbook** (the actionable sequence). The deep reference — push semantics, recovery, long-running maintenance, the full collision-class derivation — lives in [[branching-and-merging]] (runbook ↔ reference, same split as [[containerization]] ↔ [[containerization-operations]]).

**Direction of absorption (one-way, into noc).** noc's branching methodology is the **richer, primary** system — the 1851-line [[branching-and-merging]] reference plus collision-class-at-dispatch, wave-gating, overlay-divergence patch safety, and `dispatch_preflight`. We **absorbed** exactly **three crystallizations** from the smaller `knowledge-extractor` sibling repo (2026-05-23, its `doc/branching-dispatch.md`, proven on its audit-m1..m7 / absorb-m1..m7 waves): **(1)** semantic-duplicate collision detection, **(2)** the honest `--no-ff` reconciliation commit, **(3)** the tight runbook *form*. Everything else here is noc's own, marked **[noc]**. noc is source-of-truth; KE contributed three sharp bits, nothing more.

---

## When to use it (trigger phrases)

"**dispatch** agents", "**branch** agents / this", "**branching-dispatch**", "run these in **parallel**", "work on all of that at the same time".

**Don't dispatch a single coherent unit** — the [[branching-and-merging]] §18.2.1 **inline cutoff** binds: `<100 LoC ∧ <3 files ∧ single-phase` → architect does it inline; 2+ small file-disjoint tasks ride ONE compound brief. Dispatch is for **multiple genuinely independent subtasks** that amortize the ~45–60k engineer contextualization tax.

---

## Branch model ([[branching-and-merging]] §0)

| Branch | Role | Rule |
|---|---|---|
| `main` (`origin/main`) | 🔒 **Blessed release line** (sacred); production is the further `main → prod` promote the VPS tracks ([[branching-and-merging]] §0.2). | NEVER push/merge without explicit per-action consent, and **only to release**. Pre-push hook hard-blocks pushes to `main`/`prod` unless `NOCTUS_ALLOW_MAIN_PUSH=1` (sanctioned override). `dev → main` = the release gate. |
| `dev` (`origin/dev`) | **Persistent integration branch + the everyday default** — the working "fake-main"; all reconciled work converges here. GitHub default branch. | Commit/merge/push **freely** (own work). This is the everyday landing ref; `main` is deploy-only. |
| `feat/<project>` *(optional)* | **Per-project staging integration** for a large multi-wave project — cut FROM `dev`, merged back to `dev` at close. | Use only when a project needs its own integration buffer; otherwise workers land **straight on `dev`**. |
| `feat/<project>-<slice>` | **One worker branch per subtask** (DASH form — see §2 ⚠). | Forked from the active integration ref (**`dev`**, or the project staging branch if one is in use); own worktree. Engineer **only commits** here; the **architect** merges it to `dev` (step 6) + deletes it. |

> **`dev` is the default resting state.** The architect dispatches FROM `dev`, resolves merges ON `dev`, and **always returns the primary checkout to `dev`** after inspecting any worker branch (§ Safety rules 6). `main` never appears in everyday dispatch — only in the explicit `dev → main` deploy step.

---

## Roles ([noc] = [[branching-and-merging]] § Roles)

- **Architect** = the main session. Decomposes, dispatches, **collects signals, detects collisions, reconciles, verifies**, lands on the integration branch, cleans up, gates `main`. Does NOT do the subtask work.
- **Engineers** = dispatched subagents, one per file-disjoint slice, isolated worktree, focused brief (inherit [noc] `.claude/agents/engineer-seed.md`). **Engineers only stage + commit on their own worker branch — they never merge, switch branches, or push to `dev`/`main`/`prod`.** All integration (merge, reconcile, push) is the architect's job.

---

## The protocol

### 1 · Decompose into file-disjoint subtasks
Each slice owns a **disjoint file-set**. Overlapping sets are the #1 collision source — design them out: prefer **new files per agent**; **at most ONE agent edits any given existing file**. **[noc]** classify each slice's edit-set vs the parallel-active set at *dispatch* time ([[branching-and-merging]] §21 collision-class): **C1 file-disjoint** → parallel-clean · **C2 same-file-additive** → brief additive-only · **C3 substantive-overlap** → re-scope to a sibling file OR sequence into a later wave. **[noc]** wave-gate dependencies ([[branching-and-merging]] §18): a slice that consumes another's output dispatches only after that one merges.

**[noc] Scope a slice against its SIBLINGS before dispatch.** Before briefing an engineer to change a tool/helper/predicate, grep for SIBLING/DUPLICATE implementations + doc references of the thing being changed (a tool whose docstring claims "parity" with another · a duplicated predicate · KB refs). A change scoped to ONE copy silently breaks an undocumented-to-the-brief twin. Bit 2026-05-24: a `cleanup_worktrees.py` merged-base edit broke its documented parity with `mole.py` (same predicate, second copy) ⇒ reverted, re-done as a unify. The under-scope is an estimate-off-evidence miss at *dispatch* time (`KB § 01-PHILOSOPHY.md § Estimate off evidence`) — open the would-be-touched surface AND its twins, not just the one named file.

### 2 · Create isolated worktrees + parallel branches
From `dev` (the integration branch — or the project staging branch if one is in use):
```bash
git worktree add -b feat/<project>-<slice> ../noc-wt-<slice> dev   # fork FROM dev; DASH not slash
```
One per slice, deterministic branch name. The harness `Agent isolation: "worktree"` flag is the built-in alternative — but see the ⚠ below (it does NOT fork from `dev`).

> **⚠ Branch-naming — worker branches use the DASH form `feat/<project>-<slice>`, never the slash form `feat/<project>/<slice>`.** Git cannot create a nested ref under an existing **leaf** ref: if you fork off a `feat/<project>` **staging** branch, then `feat/<project>/<slice>` fails with `cannot lock ref … 'feat/<project>' exists`. Forking off **`dev` is immune** (dev isn't a `feat/*` leaf — this is one more reason to land workers straight on `dev`). When a staging branch is used: dash form OR a distinct name (`<project>-integration`). **N=3, 2026-05-23** — all three engineers on `seed-deploy-config-contract` hit it and self-corrected to the dash form.
>
> **⚠ Harness `isolation: "worktree"` forks from `main`/`origin/main` (the repo default), NOT from `dev` or your current HEAD.** Now that `dev` is the base, this divergence matters MORE — the auto-worktree will lack any commit that lives only on `dev`. **Prefer manual `git worktree add … dev`.** If you must use the harness flag: (a) **briefs MUST be self-contained** (inline the full API/spec — don't rely on the engineer reading a `dev`-only PROJECT.md); (b) `dispatch_preflight project_slug=…` is moot (the doc isn't on their base); (c) each slice branch is `main`-based → merge it onto the **`dev` tip** (`--no-ff`), which is a strict superset.
>
> **⚠ Cross-tree overlay leak — verify true disk at integration.** The harness file overlay can leak an engineer's in-progress edits into the **main checkout's** working tree (a `M`/`??` on a file the engineer "owns" elsewhere), and that leak may DIFFER from the engineer's *committed* branch. The committed+pushed branch is source-of-truth: `git diff origin/<slice-branch> -- <file>` to compare, then **discard the working-tree leak** (`git checkout --` / `rm` the untracked) and merge the branch. Seen 2026-05-23 (`compliance.py` + `deploy-config-contract.md` leaked into main; recovered by discard-leak + merge-branch). Strict instance of [[harness-overlay-worktree-divergence]].

### 3 · Dispatch in parallel
Send all `Agent` calls **in a single message** so they run concurrently. Each brief carries the **Worker Contract** (below).

### 4 · Collect the signal
Each engineer reports **branch name · HEAD hash · files changed**. **[noc] overlay-divergence safety:** the engineer ALSO writes a `/tmp/<slice>.patch` early and pastes grep-proof of the on-disk change — `Edit`/`Write` can succeed against a harness overlay while the worktree stays clean ([[harness-overlay-worktree-divergence]]); the architect verifies true disk from a separate Bash context before trusting the signal.

### 5 · Evaluate + detect collisions — TWO types
Inspect each slice **without switching** the primary checkout off `dev`:
```bash
git diff --name-status dev feat/<project>-<slice>
```
- **(a) Path-overlap** — two branches touch the same file. Git flags it at merge.
- **(b) Semantic-duplicate [the sharp one]** — *different paths, same content* (two agents each author a registry / bibliography / helper). **Git will NOT flag this — the architect must.** Read the deliverables, not just the file list.

### 6 · Merge — onto `dev`, `--no-ff`, provenance-preserving
On `dev` (`git switch dev` first; return to `dev` is the resting state anyway):
```bash
git merge --no-ff feat/<project>-<slice> -m "Merge feat/<project>-<slice>: <summary>" \
  -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```
`--no-ff` keeps each agent's commits intact so history shows **what each agent contributed**. (FF/concat-clean per [[branching-and-merging]] §10.4 is the alternative when slices are provably C1 and provenance doesn't matter; for collision-prone parallel work, prefer `--no-ff`.)

### 7 · Reconcile — in a dedicated commit, honest history
Resolve collisions/duplicates/conflicts in a **separate reconciliation commit** on `dev` — **keep the agents' original commits intact**. The history should honestly show the collision **and** the fix (no-silent-errors applied to git history). Example: pick one canonical file, port unique entries from the duplicate, fix cross-links, delete the stray.

### 8 · Verify ([noc] finish-the-session)
Tests/builds green for touched code (`pytest` / `vite build`); KB sync (`--verify-kb-sync`) + symbology drift if docs changed; three-way sync for any methodology change. Report outcomes faithfully.

### 9 · Salvage-before-delete, THEN clean up
A worktree delete is the worktree analogue of archiving a project ⇒ it mirrors `archive`'s learn-before-archive ([[storage-hygiene]] § 2.3). **Before removing an engineer's worktree, the architect SALVAGES it** — the merge moved the *code* to `dev`, but the worktree's *durable knowledge* (engineer `findings.md` / return-notes / bugs found / follow-ups) is lost on delete unless extracted. Run the four-leg ritual:
1. **Extract learnings → KB/memory** (discipline leg) — any reusable pattern/gotcha/recurrence/follow-up the engineer surfaced lands in its durable home BEFORE the delete (`appended ≠ extracted`).
2. **Record recovery pointer** — branch+SHA → the tracked `project-history/worktree-salvage.ndjson` (mechanical).
3. **mole worktree-sweep** — storage hygiene before the delete.
4. **Remove** the worktree + delete the merged branch.

Tear down **through the tool** so legs 2–3 are mechanical and the learnings checkpoint is surfaced — **never a bare hand-typed `git worktree remove`** (it skips all three salvage legs — the 2026-05-25 architect-post-merge drift):
```bash
# preferred: the tool records the recovery pointer + surfaces the learnings checkpoint
noctus.dev.task_branch action=cleanup slug=<project>-<slice> confirm=True
# (equivalently: noctus.dev.mole mode=sweep scope=worktrees force=True, or cleanup_stale_worktrees)
```

### 10 · Land on `dev`; push `dev`. `main` is a separate, explicit deploy
Once every slice is merged onto `dev`, every collision (incl. semantic) resolved, and verify is green: **push `dev`** (`git push origin dev` — your own work, freely). That completes the dispatch. **`main` is NOT touched here.** It advances only by the explicit, user-requested, consent-gated `dev → main` deploy ([[branching-and-merging]] §0.2: `NOCTUS_ALLOW_MAIN_PUSH=1 git push origin dev:main`, FF-only, after CI-green + `predeploy_check` + prod live-probe). Default end-of-dispatch state = work on `dev`, `main` untouched.

---

## Worker Contract (paste into every engineer brief)

- Work **only** inside your worktree path; `pwd` + `git branch --show-current` before editing — wrong branch ⇒ STOP.
- Touch **only your assigned files** (the disjoint set). Never edit another agent's files.
- Follow CLAUDE.md (seed-first, AST-first, no silent errors, symbol-first docs).
- Write `/tmp/<slice>.patch` **early** (survives the ~600s watchdog); paste on-disk grep-proof of your change.
- Stage **only your files by explicit path** — never `git add .` / `-A`. Commit on your worker branch; message ends with the `Co-Authored-By` trailer.
- **Never** touch `main`, `dev`, `prod`, or another slice's branch; never switch the primary checkout or push to `main`/`prod`. Work stays on your worker branch.
- Final message reports: **branch · HEAD hash · files changed** (+ the patch path).

---

## Safety rules (non-negotiable)

1. 🔒 `main` is **production** — untouched without explicit per-action consent, and only to deploy. The pre-push hook hard-blocks pushes to `main` unless `NOCTUS_ALLOW_MAIN_PUSH=1`. Everyday work lands on `dev` ([[branching-and-merging]] §0).
2. File-disjoint sets per agent; **architect owns collision detection (incl. semantic-dup) + the reconciliation commit**.
3. Explicit-path `git add` everywhere; never `-A`.
4. Verify (tests + links + sync gates) before "done"; faithful reporting.
5. **[noc]** run `noctus.dev.dispatch_preflight` before dispatch (fork-base + collision + env-pin + project-doc-phantom checks); keep a root `findings.md`.
6. **Always return to `dev`.** The architect dispatches FROM `dev`, reconciles ON `dev`, and returns the primary checkout to `dev` after inspecting any worker branch — `dev` is the default resting state. Inspect branches read-only (`git diff dev …`, `git show <branch>:<path>`) rather than switching; concurrent active work uses isolated worktrees (§9a), never a shared switch.

→ Deep reference: [[branching-and-merging]]. Pre-dispatch tooling: [[dev-toolkit-scaffolders]] (`dispatch_preflight` / `salvage_worktree` / `findings`). Collision-class derivation: [[branching-and-merging]] §21. The **self**-case (an agent isolates *itself* per writing task instead of dispatching engineers — peer terminal-agents on one checkout): [[self-branching-mode]] (`noctus.dev.task_branch`).
