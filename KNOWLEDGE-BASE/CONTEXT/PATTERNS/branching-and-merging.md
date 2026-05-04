# Branching (and Merging — TBD) Methodology

> **What this is.** The git-workflow methodology for NoctusAI when you can't push your work directly to `origin/main` — typically because parallel-agent commits sit in your unpushed range. Branching is the **structural solution** to authorship-violation pressure (per `feedback_commit_only_own_work.md` / `KB § PATTERNS/project-execution.md § 2.10`). It is also the workflow shape we'll standardize for **parallel projects under seed-workspace**, multi-session work, speculative experiments, and PR-shape review flows.
>
> **What this replaces.** Ad-hoc decisions like "should I just `git push --force` to bypass the parallel-agent commits?" or "should I revert their commits locally so I can push mine?" Both are destructive shortcuts. Branching is the non-destructive answer.
>
> **What this does NOT cover.** The **merging methodology** for non-fast-forward integration (when `origin/main` has moved past your branch base — e.g. multiple agents pushing concurrently, or your branch sat unpushed long enough that main moved). That's a separate methodology pending. Tracked as a wish in agent memory; this doc gets a §10 follow-up section once the merging half lands.
>
> **Cross-references.** `KB § PATTERNS/project-execution.md § 2.10 Commit + push authorship discipline` (the rule branching solves), `feedback_commit_only_own_work.md`, `feedback_branching_methodology.md` (memory pointer back to this doc), `KB § PATTERNS/master-tree-parallel-batches.md` (parallel-agent collision context), `feedback_parallel_agent_collision_protocol.md`.

---

## 1. Why branch

When two situations are true at once:
1. You have committed work locally that you want on `origin/main`.
2. `git log origin/main..HEAD` shows commits you did NOT author (parallel-agent work landed on local main while you were working).

…you cannot simply `git push origin main`. That would push the parallel-agent's commits along with yours — a direct violation of `feedback_commit_only_own_work.md`. **Branching is the solution.** You isolate your commits onto a separate ref, push that ref, and leave the parallel-agent commits on local main for them to push (or rebase onto the new origin/main when ready).

The same shape generalizes to any situation where your work shouldn't go directly to main:
- Multi-session projects that need durable shared state across agent handoffs.
- Speculative work that may not land (experimental refactors, vendored prototypes, A/B branches).
- Parallel projects under seed-workspace (each project gets its own branch, agents work in isolation, integrations happen at named sync-gates).
- PR-shape review where work is exposed remotely before promotion to main.

---

## 2. When to branch

**Mandatory:**
- Parallel-agent commits live in your unpushed range. Branching is required to respect `feedback_commit_only_own_work.md`.
- Your work targets a remote ref that is NOT main (e.g. a release branch, a long-running feature branch, a sibling agent's branch).

**Strongly recommended:**
- Multi-session project work where the local context might be lost (machine restart, agent handoff, parallel-agent collisions).
- Cross-cutting / risky changes that warrant remote review before promotion.
- Speculative work that may be discarded.

**Not needed (push to main directly is fine):**
- Single-agent session, no parallel-agent commits in unpushed range, work is project-close-ready.
- Pre-existing rule for "Commit per phase, push at project close" applies normally — branching does NOT replace that gate, it composes with it.

---

## 3. How to branch

### 3.1 Branch FROM `origin/main`, not from local main

```bash
git checkout -b <branch-name> origin/main
```

**Why `origin/main`** rather than local main: local main may carry parallel-agent commits, in-flight WIP, or stale state. Branching from `origin/main` guarantees a clean base — your branch starts at exactly what is currently visible on the remote. If the parallel agent later pushes their commits to main, your branch is still independent.

### 3.2 If your work already lives on local main as commits

Cherry-pick those commits onto the new branch:

```bash
# Identify the range — your commits are between <last-non-yours> and HEAD on local main
git log origin/main..main --pretty="%h %an %s"   # find <last-non-yours> = the parallel-agent commit immediately before your first commit

git checkout -b <branch-name> origin/main
git cherry-pick <last-non-yours>..<your-newest-commit>
```

Each cherry-pick creates a NEW commit (different hash from the original, same content). The originals on local main are untouched.

### 3.3 If your work hasn't been committed yet

Work directly on the branch with normal commits:

```bash
git checkout -b <branch-name> origin/main
# ... edit files, run tests ...
git add <explicit-paths>
git diff --cached --name-only   # verify staged set per `feedback_commit_only_own_work.md`
git commit -m "..."
```

### 3.4 Mixed case (some commits on local main, some new work)

Cherry-pick first to populate the branch, then continue with new commits on top.

### 3.5 Verify branch state before pushing

```bash
git log origin/main..HEAD --pretty="%h %an %s"
```

Every commit listed should be yours. Any surprise → STOP and investigate (per `feedback_commit_only_own_work.md` step 4).

---

## 4. Push semantics

### 4.1 Branch-to-branch (default for in-flight work)

```bash
git push -u origin <branch-name>
```

The `-u` sets upstream tracking; future `git push` / `git pull` on this branch use the remote ref by default. The remote branch is independent of `main` — visible to other agents (and on GitHub for PRs / review) but doesn't touch main's history.

### 4.2 Branch-tip-to-main fast-forward (when ready to ship)

```bash
git push origin <branch-name>:main
```

Pushes your branch's tip to remote `main`. **Allowed only when `origin/main` is an ancestor of your branch tip** — i.e. no other commits landed on `origin/main` between when you branched and now. If allowed, git fast-forwards (no merge commit, no risk).

If git rejects with `Updates were rejected because the remote contains work that you do not have locally`, that's the **non-fast-forward case**. Stop. The merging methodology (§10, TBD) covers that path. For now: leave the branch unmerged, surface to user.

### 4.3 Never `--force` push to main

`--force` rewrites remote history, invalidates everyone else's local clones, and silently destroys their unpushed work. Forbidden on main without explicit user authorization (and even then, prefer `--force-with-lease` and triple-check).

### 4.4 What the parallel agent encounters after your fast-forward push to main

When you push branch-tip-to-main while parallel-agent commits sit on their/your local main:
- `origin/main` advances to your branch tip (only your commits).
- Parallel agent's local main is now diverged: it has commits BEFORE the new origin/main (their commits) PLUS your originals (which are duplicates of your cherry-picks now on origin/main).
- When the parallel agent runs `git fetch + git pull --rebase`:
  - Their commits rebase cleanly onto new origin/main IF they don't share files with your branch (zero file-overlap = clean rebase).
  - Your originals on their local main get **detected as already-applied** via patch-id matching and dropped automatically. Newer git defaults to `--empty=drop` which handles this silently.
- Net effect: parallel agent's local main converges with origin/main + their commits on top, minus the duplicates. Clean.

If file-overlap exists, the parallel agent gets normal merge conflicts — same as any rebase. They resolve, push their reconciled state.

---

## 5. Branch naming convention

| Suffix / shape | Meaning | Example |
|---|---|---|
| `<project-slug>-shipped` | Ready for promotion to main; cherry-pick-and-ship pattern | `phase-detector-and-enrichment-loop-shipped` |
| `<project-slug>-wip` | Work-in-progress, not yet ready for promotion | `imobi-scheduling-bot-wip` |
| `<topic>` | Cross-cutting / non-project work | `branching-methodology` |
| `<agent>-<topic>` | Disambiguates when multiple agents work on the same topic in parallel | `claude-typescript-strict-mode-experiment` |

Short, descriptive, lowercase-dash-separated. No timestamps in branch names (the commits themselves carry timestamps). Avoid `feature/` / `bugfix/` prefixes — we don't use that flow; `<project-slug>-<state>` is the canonical shape.

---

## 6. Cleanup

After a branch's work has landed on main:

```bash
# Delete the local branch (safe — work is on main)
git branch -d <branch-name>

# Optionally delete the remote branch (history record is preserved in main; the branch ref is just a pointer)
git push origin --delete <branch-name>
```

The branch ref itself is just a name; deleting it does NOT delete the commits (those are reachable via main now). Keep the branch around if it serves as audit history for the work; delete if the slug is exhausted.

---

## 7. Mental-model upgrade

Three concepts to internalize:

1. **`origin/<branch>` vs. `<branch>`.** `origin/<branch>` is the remote-tracking ref — it's how git records "what `<branch>` looked like on the remote at the last fetch." `<branch>` (no prefix) is your local copy of that branch. They diverge between fetches; `git fetch` updates `origin/<branch>` to match remote without touching your local `<branch>`.

2. **Branching = naming a new history pointer.** A branch is a named ref pointing at a specific commit. `git checkout -b X Y` creates a new ref `X` pointing at the commit `Y` resolves to. Your work moves the ref forward as you commit; the ref `Y` was branched from is unchanged.

3. **Cherry-pick = re-apply a commit's diff as a new commit.** Hashes change; content is the same. Useful for moving commits between branches without rewriting history. Repeated cherry-picks of the same commit onto different bases are normal and safe.

4. **Push to a different remote name.** `git push origin <local-branch>:<remote-branch>` lets you target ANY remote ref name. The fast-forward push to main (§4.2) uses this: `<local-branch>:main`. You're not pushing to "your branch on remote" — you're pushing your local commits to whatever remote ref you specified. Powerful and safe (when fast-forward is checked).

5. **Fast-forward = no merge commit, no risk.** When the remote pointer is an ancestor of your tip, git just moves the pointer forward. No history rewrite, no merge artifact. The only failure mode is "remote has commits you don't" → non-FF → merge methodology kicks in.

6. **Non-FF push requires merging or rebasing first.** Pushing diverged history without resolution is `--force` territory — destructive. The clean path is: fetch, rebase or merge locally, push the reconciled state.

This is the workflow shape for **parallel projects in seed-workspace**: each agent works on its own branch, pushes that branch independently, fast-forwards (or PRs) to main when conflict-free. The mental model is "main is sacred, branches are scratch."

---

## 8. Authorship rule still binds

Branching does NOT relax `feedback_commit_only_own_work.md`. The rule still applies: stage by explicit file paths, verify staged set, verify unpushed-commits authorship before push. Branching is the SOLUTION to authorship-violation pressure (it isolates your work from parallel-agent work); it is not a license to bundle other agents' work into your branch.

If you find yourself cherry-picking another agent's commit onto your branch — STOP. That's not your work. The branching methodology is for ISOLATING your work, not for SWEEPING UP others'.

---

## 9. Anti-patterns

- **Branching from local main when local main has parallel-agent commits.** Defeats the purpose — your branch inherits their commits. Always branch from `origin/main`.
- **`git push --force` to main "to clear up the divergence."** Destroys other agents' work. Forbidden.
- **Cherry-picking another agent's commits onto your branch to "include them in the push."** That's still pushing their work; the branch wrapper doesn't change that. Author-only-own-work.
- **Letting branches sit indefinitely.** Branches that don't get pushed-to-main accumulate divergence; integration cost grows. Aim to ship within one session, or surface that the branch is parked.
- **Naming branches after their commit content** (`fix-bug-in-router-line-127`). Branch names should describe scope, not implementation. Implementation lives in commit messages.
- **Using `git checkout origin/main -- <file>` to discard parallel-agent working-tree changes.** That's destructive. If working tree has parallel-agent WIP, `git stash` is also touchy (stashes their work). The cleanest path: stay on local main, work there, cherry-pick to a branch FROM origin/main when ready to push.

---

## 10. Merging methodology — TBD

The companion methodology covering:
- Non-fast-forward integration (when `origin/main` has moved past your branch base).
- Multi-branch merge ordering (when N branches converge on main).
- PR-shape review workflow (branch → PR → review → merge).
- Conflict resolution discipline (which side wins; how to flag manual resolution; how to avoid losing work in 3-way merges).
- Long-running branch maintenance (rebase cadence, integration debt, when to abandon).

Tracked as a wish in agent memory: `wish_develop_merging_methodology.md`. Once developed, this section gets filled in (or split into a sibling KB doc `KB § PATTERNS/merging.md`) and the wish entry is deleted.

Until then: when fast-forward push fails (§4.2), STOP and surface to the user. Do not attempt manual merging without methodology support — it is the highest-risk git operation we run, and ad-hoc resolution is how merge bugs and lost commits happen.
