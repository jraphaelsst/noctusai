# Branching and Merging Methodology

> **What this is.** The end-to-end git-workflow methodology for NoctusAI. Two halves shipped 2026-05-03:
>
> - **Branching** (§§1-9, 11-14) — the structural solution to authorship-violation pressure. When parallel-agent commits sit in your unpushed range, you cannot push from local main without sweeping up their work. Branch from `origin/main`, isolate your commits, push the branch (or fast-forward to main when ready). Also the workflow shape for parallel projects under seed-workspace, multi-session work, speculative experiments, and PR-shape review.
> - **Merging** (§10) — the companion methodology for what happens when fast-forward push fails (origin/main moved past your branch base), when N branches converge on main, when same-line conflicts need resolution, when a branch accumulates integration debt, and when a merge goes wrong. Builds on `git merge` as the safety net (`KB § 01-PHILOSOPHY.md § Safety nets capture failures`).
>
> **What this replaces.** Ad-hoc decisions like "should I just `git push --force` to bypass the parallel-agent commits?", "how do I rescue this bad merge?", "which branch goes first?" — all of which are destructive or unanswered without the methodology. Branching + merging together = a complete answer to the multi-agent git-workflow question.
>
> **Cross-references.** `KB § PATTERNS/project-execution.md § 2.10 Commit + push authorship discipline` (the rule branching solves), `KB § 01-PHILOSOPHY.md § Safety nets capture failures` (foundational principle that anchors §10 Merging), `feedback_commit_only_own_work.md`, `feedback_branching_methodology.md`, `feedback_merging_methodology.md`, `KB § PATTERNS/master-tree-parallel-batches.md` (parallel-agent collision context), `feedback_parallel_agent_collision_protocol.md`.

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

## 10. Merging methodology

The companion methodology to branching. Covers what to do when `git push origin <branch>:main` fails as non-fast-forward (origin/main moved past your branch base), when N branches converge on main, when same-line conflicts need resolution, when a branch sits long enough to accumulate integration debt, and when a merge goes wrong.

**Why merging matters (the second-class problem branching alone doesn't solve).** Branching prevents **authorship-violation pushing** (you'd push another agent's commits along with yours because they sit in your unpushed range). Merging prevents **same-line content overwriting** (agent A writes line 50, agent B writes a different version of line 50 — without merging, second-write-wins silently destroys first-write). Both are real failure modes. Auto-merge handles non-conflicting changes (different files, different lines) — `work1 + work2 = work1+2` works automatically there. Same-line conflicts require resolution discipline, which is what this section codifies.

### 10.1 Build on `git merge`, don't replace it

`git merge` is the **safety net** per `KB § 01-PHILOSOPHY.md § Safety nets capture failures`. The mechanical tool handles the auto-mergeable cases (different files, different lines, fast-forward chains) without methodology intervention. The methodology rides ON TOP of `git merge`, adding process discipline for the cases mechanics can't resolve alone:

- **Ordering** — when 2+ branches both want to land, who goes first? Mechanics: silent first-write-wins. Methodology: §10.3.
- **Same-line conflicts** — auto-merge can't resolve. Methodology: §10.4.
- **Long-running branches** — auto-merge gets harder as divergence grows. Methodology: §10.5.
- **Bad merges** — once a wrong merge lands, recovery is needed. Methodology: §10.6.

**Anti-pattern: bespoke merge logic that bypasses `git merge`.** Don't build custom diff-and-apply scripts to avoid `git merge`'s 3-way machinery. The 3-way merge is correct; what we add is the discipline around when/how to invoke it. Bypassing the safety net = bypassing the methodology's foundation.

### 10.2 Non-fast-forward integration

When `git push origin <branch>:main` is rejected as non-FF, your branch base is no longer ancestral to `origin/main`. Someone else's commits landed in between. You have two options:

**Option A — Rebase your branch onto new `origin/main`** (preferred for short-running branches with few commits):

```bash
git fetch origin
git checkout <your-branch>
git rebase origin/main
# resolve any conflicts (§10.4)
git push origin <your-branch>:main   # retry the FF push
```

`rebase` re-applies your branch's commits on top of new `origin/main`. History stays linear (no merge commit). Each of your commits gets a NEW hash (the rebase creates new commits with the same content but new parent pointers). The mental model: "move my work to sit on top of where main is now."

When to use rebase:
- Branch has ≤5 commits.
- Linear history is preferred (no merge-commit clutter).
- No other agent has your branch checked out (rebase rewrites history; if they have your old commits, they'll see divergence).
- Your commits are clean and self-contained (each one applies independently onto the new base).

**Option B — Merge `origin/main` into your branch** (preferred for long-running branches or when preserving history of integration points matters):

```bash
git fetch origin
git checkout <your-branch>
git merge origin/main
# resolve any conflicts (§10.4)
# git push origin <your-branch>:main  # this still fails — see caveat
```

`merge` creates a merge commit on your branch that reconciles your work with new `origin/main`. History shows the integration explicitly. **Caveat:** merging `origin/main` INTO your branch doesn't make the FF push to main work — the merge commit is on your branch, but `origin/main` still doesn't have your branch's commits. You'd need a normal merge from main's side, which means PR-shape review (§10.3) or letting the orchestrator merge via the merge button.

When to use merge:
- Branch has many commits or has been alive across multiple sessions.
- Multiple agents may have your branch checked out (rebase would invalidate their copies).
- Integration history matters (audit trail of "branch X integrated main at point Y").
- You want the final main history to show "this work came in as a unit" (the merge commit is the boundary).

**Conflict-free path (the common case).** If your branch and `origin/main` touched different files, OR same files but different lines, both rebase and merge auto-complete. No methodology intervention needed. `work1 + work2 = work1+2`. The safety net (`git merge`'s 3-way machinery) carried it.

**Conflict path.** If same-line conflicts surface, see §10.4.

**Real example (this repo, 2026-05-03).** Three parallel-agent commits sat in unpushed range while `phase-detector-and-enrichment-loop` shipped: `7ef0f16` (B0+B1), `db29d44` (B2), `21d84a4` (B3). All on local main, none on `origin/main`. When `phase-detector-and-enrichment-loop`'s branch tip was fast-forward-pushed to main, `origin/main` advanced. The parallel agent now has those 3 commits on their local main as **diverged from new origin/main**. Their next push triggers non-FF. They run `git fetch + git rebase origin/main` — git auto-merges (no file overlap with the methodology branch's content), drops the duplicates of my originals via patch-id, and the rebase completes clean. Then `git push origin main` succeeds.

**Decision flowchart:**

```
git push origin <branch>:main → REJECTED (non-FF)
          ↓
  Branch ≤5 commits, no other agents have it checked out, linear history wanted?
    YES → rebase (§10.2 Option A)
    NO  → merge (§10.2 Option B) + open PR for the orchestrator-merge step
          ↓
  Conflicts during rebase/merge?
    NO  → push succeeds, done.
    YES → §10.4 Conflict resolution discipline.
```

**Anti-pattern: `--force` push to bypass non-FF.** Forbidden on main. `--force` rewrites remote history, invalidates everyone else's local clones, silently destroys their unpushed work. The non-FF rejection IS the safety net telling you "someone else has work here you don't"; bypassing it skips the integration step entirely.

### 10.3 Multi-branch convergence

When N≥2 branches all want to land on main concurrently. The mechanical truth: only one can fast-forward at a time. Once the first lands, every other branch becomes non-FF and needs §10.2 to reconcile.

**The queue-pattern.** Branches don't merge in parallel — they queue. Order is determined by some negotiated rule:

- **First-commit-wins** — whichever branch ships its work to remote first goes first. Default in this repo.
- **Smallest-first** — when two branches differ greatly in scope, the smaller one merges first to minimize the integration window for the larger.
- **Owner-priority** — when both branches have the same owner, that owner picks the order (they have full context). Cross-owner: negotiate or surface to the user.
- **Critical-first** — when one branch is a hotfix (security, production breakage), it jumps the queue regardless of other rules.

**Per-branch sequence:**

```
Branch A and Branch B both ready to land on main.
    ↓
Negotiate order (default: first-shipped wins) → A goes first.
    ↓
A: orchestrator fast-forward push: `git push origin A:main` → SUCCESS, origin/main now at A's tip.
    ↓
B: now non-FF. Run §10.2 (rebase or merge).
    ↓
B: rebase succeeds (no conflicts) → fast-forward push B → SUCCESS.
    OR
B: rebase has conflicts → §10.4 → resolve → push.
```

The mental model: **branches converge serially, not concurrently.** The merge button is single-threaded by mechanical necessity.

**Branch-of-branch (chained branches).** When project Y depends on project X's work that hasn't merged yet, Y's branch can be based on X's branch instead of `origin/main`:

```bash
git checkout -b project-y origin/project-x   # base on X's branch, not main
# ... do Y's work ...
```

When X merges to main, Y becomes "based on something now-merged into main." Y can rebase onto new origin/main:

```bash
git fetch origin
git rebase origin/main   # Y's commits replay on top of new main (which now includes X's content)
```

**Anti-pattern: chained branches deeper than 2.** Branch C based on branch B based on branch A is a recipe for cascading rebases. Each layer adds rebase complexity. Keep chains shallow; promote intermediate branches to main as soon as they're ready, even if they're not "feature-complete" yet.

**Parallel-projects-under-seed-workspace use case.** This is exactly what multi-branch convergence is for: each project gets its own branch, branches accumulate independently, they queue at the merge step. The orchestrator (per §12) is the queue manager — sees all in-flight branches, decides ordering, merges one at a time. Other agents wait for their turn (or rebase preemptively if they want to be ready when their turn comes).

**Coordination via the patterns log (master-tree case).** When branches are part of a master-tree-parallel-batches project (`KB § PATTERNS/master-tree-parallel-batches.md`), the master root's `live-patterns-log.md` is the coordination surface. Each batch's branches land in order by batch number; mid-batch parallelism happens within a batch but the cross-batch ordering is sequential.

**PR-shape review workflow.** GitHub provides this institutionally: each branch opens a PR; reviewers comment; the merge button is gated on review approval. Mapped to our orchestrator-merge model (§12): the orchestrator IS the reviewer + merger. The PR is the artifact making the branch's contents externally visible during review (vs. the branch ref alone, which doesn't auto-open a review surface). Use PRs when:

- Multiple agents (or human reviewers) need to inspect the branch before merge.
- The work spans enough surface that diff-by-diff review benefits from the GitHub UI (file tree, comment threads, suggested changes).
- The work needs to wait on something external (CI, a code-owner sign-off, a stakeholder).

For single-orchestrator-merge work (most projects in this repo), `git push origin <branch>:main` is the FF-merge action; the PR step is optional. The branch ref on remote is enough for the orchestrator's fresh-eyes pass.

### 10.4 Conflict resolution discipline

The hardest part of merging — and the part where most data loss happens. Auto-merge already covered the easy cases; this section is about same-line collisions where git asks "ours, theirs, or some combination?"

**The 3-way merge concept.** When a conflict surfaces, git has three references:

- **`base`** — the common ancestor of your branch and the branch you're merging in. The shared starting point.
- **`ours`** — what your branch says the line(s) should be. Your changes since `base`.
- **`theirs`** — what the other branch says. Their changes since `base`.

A conflict means: `base → ours` and `base → theirs` both modified the same lines. Git can't pick automatically. The conflict marker shape:

```
<<<<<<< HEAD
ours version
=======
theirs version
>>>>>>> origin/main
```

(Substitute the branch names appropriately; for `git rebase`, `HEAD` is THEIRS-from-the-rebase-perspective and the incoming branch is OURS — confusingly inverted vs `git merge`. Always check `git status` to confirm which is which during a rebase.)

**Read the base, not just ours and theirs.** The conflict markers show ours + theirs. The base is invisible by default. To see the original (base) version: `git show :1:<file>` (1=base, 2=ours, 3=theirs in git's 3-way index). Reading the base is critical when your version and theirs both look reasonable in isolation but were both meant as different evolutions of the same starting point.

**File-type heuristics** — for our repo specifically, conflict resolution preferences by file type:

| File type | Resolution heuristic | Notes |
|---|---|---|
| **KB docs** (`KNOWLEDGE-BASE/**/*.md`) | **Concatenate sections.** When both branches added new subsections to the same parent doc, keep both — they're additive almost always. When both edited the same paragraph, read the base and produce a unified version that respects both intents. | Methodology docs grow additively; conflicts here are usually false positives from concurrent additions, not real disagreements. |
| **CLAUDE.md / CLAUDE/<topic>.md** | **Same as KB — additive.** Two new bullets both belong; merge by alphabetical or topical order, not first-write-wins. | Auto-loaded surface; budget discipline applies (`feedback_context_budget_discipline.md`) — if the merged file is too long, that's a separate concern, surface it in the project-close pass. |
| **MCP tool registrations** (`mcp/noctusai/tools/**/__init__.py`) | **Alphabetical merge** — the `register(server)` calls are alphabetical by convention. Both new registrations belong; sort and dedupe. | Don't drop one to keep the other; both are real tools. |
| **Migration files** (`products/<x>/backend/migrations/*.sql`) | **NEVER conflict — sequence numbers prevent it.** If conflict surfaces, both branches assigned the same sequence number, which is the bug. Re-number the later one and update its `down_revision` references. | Migration sequencing is a coordination concern, not a merge concern. The conflict is a symptom; the fix is the renumber. |
| **Test files** (`tests/**`) | **Union most of the time.** Both new tests belong; both new assertions in the same test usually belong. Same-line conflicts in test setup are the same as production-code conflicts: read the base, find the unified version. | Tests grow additively; "we both added a test for the same case" isn't a conflict, it's a redundancy — pick the better one and delete the other. |
| **Production code (Python / TypeScript)** | **Read the base. No automatic heuristic.** Same-line conflicts in production code are real disagreements about behavior. Resolve by understanding both intents and producing a version that satisfies both — or surface to user if intents conflict. | Don't pick "ours" because you wrote it; don't pick "theirs" to be polite. Pick what the base + the union of intents asks for. |
| **Config (`.env.example`, `package.json`, `pyproject.toml`)** | **Manual review** — config conflicts often hide environmental assumptions. Read the base; understand each side's intent; produce a config that works for both. | The lock-files (`package-lock.json`, `yarn.lock`) are auto-regenerated; conflict-resolve by deleting the file and re-running `npm install` / `yarn install`. |

**Avoiding lost commits during interactive merges.** When a `git merge` or `git rebase` enters interactive mode (conflicts present, prompting for resolution), the most common data-loss patterns are:

1. **`git rebase --skip` without reading the diff.** Skip drops the current commit entirely. If you skip thinking it's a duplicate but it actually has unique changes, those changes are gone (recoverable via `git reflog` per §10.6, but you have to know to look). Always read the commit being skipped first: `git show HEAD` (during rebase, HEAD is the commit being applied).
2. **`git checkout --ours <file>` or `--theirs <file>` on a multi-line conflict.** The `--ours` / `--theirs` shortcut takes the ENTIRE file from one side, discarding the other. Useful for binaries or for files where you genuinely want one version verbatim; data-loss disaster when the file has both your changes and theirs that should coexist. Only use these shortcuts on files where you've read both versions and confirmed one is fully replaceable.
3. **`git reset --hard` mid-merge.** Discards all merge state including any work you did to start resolving. If you need to abort, use `git merge --abort` (resets to pre-merge state safely) or `git rebase --abort`.

**When to abort.** Sometimes the merge or rebase reveals that the strategy was wrong (e.g. you tried to rebase a 50-commit branch and the conflicts are accumulating; a merge would have been cleaner). Abort, re-strategize:

```bash
git merge --abort        # if mid-merge
git rebase --abort       # if mid-rebase
# pre-merge state restored; pick the other strategy from §10.2.
```

**Worked example — same-line conflict on a KB doc.** Imagine two branches both edit `KB § PATTERNS/project-execution.md § 2.7 Recurrence rule`:

- Branch X added: "**N=4+ → INVESTIGATE TIME-WINDOW** — 4 instances in the same week is a different signal from 4 instances over six months."
- Branch Y added: "**N=2 → triage immediately**, do not defer. Deferral is silent debt."
- Both inserted at line 42 of the section.

Conflict surfaces:

```
<<<<<<< HEAD (ours = Branch Y)
**N=2 → triage immediately**, do not defer. Deferral is silent debt.
=======
**N=4+ → INVESTIGATE TIME-WINDOW** — 4 instances in the same week is a different signal from 4 instances over six months.
>>>>>>> origin/main (theirs = Branch X)
```

Resolution: KB-doc heuristic = concatenate. Both additions belong. Read base (no `N=4+` clause; no `triage immediately` emphasis). Produce union:

```markdown
**N=2 → triage immediately**, do not defer. Deferral is silent debt.
**N=4+ → INVESTIGATE TIME-WINDOW** — 4 instances in the same week is a different signal from 4 instances over six months.
```

Both clauses now in the doc. The intent of both branches preserved. This is the canonical KB-doc conflict pattern.

**Anti-patterns:**

- **Picking "ours" by default.** Treats the conflict as a contest you have to win. Most KB / test / config conflicts are additive false-positives; "ours" loses real work.
- **Resolving without reading the base.** Without the base, ours-vs-theirs is two competing claims. With the base, you see the evolution and can produce the unified path.
- **Resolving silently and committing the merge without flagging it.** Per `feedback_no_silent_errors.md`, conflict resolutions should be visible in the commit message — quote the file + the resolution strategy ("KB-doc concat" / "test union" / "manual unified" / "preferred theirs after reading base"). Future-you (and other agents) can audit.

### 10.5 Long-running branch maintenance

A branch that sits unmerged for a while accumulates **integration debt** — the gap between the branch's content and main grows; rebases get harder; conflicts get more likely; the eventual merge gets riskier. The methodology for keeping long-running branches healthy.

**Rebase cadence.** Two reasonable defaults:

- **Daily** — at the start of each session, before doing new work on the branch, run `git fetch origin + git rebase origin/main`. Catches small divergence cheaply; spreads conflict resolution across many small steps instead of one big one at merge time.
- **On-each-main-push** — when notified that main has advanced (parallel agent pushed, or you watch a notification feed), rebase opportunistically. Higher-frequency than daily; lower discipline cost than waiting until merge time.

For most branches in this repo: **daily is the default**. Single-session features rarely need to outlive a session, so the daily rebase happens before the eventual merge naturally. Multi-session work + parallel-agent activity warrants the daily cadence to amortize integration cost.

**Integration debt thresholds.** When does a branch become more cost than benefit?

| Debt signal | Action |
|---|---|
| Branch is >7 days old | Mandatory rebase + assess: is the work still relevant given what's landed on main? |
| Branch has >50 commits | Consider squashing (next sub-section) to make the eventual merge cleaner. |
| Rebase produces >5 conflicts in one pass | Pause work; surface to user; consider whether the branch should be rebased or whether main has moved in a direction that invalidates the branch's premise. |
| Branch is on a methodology that has since been amended | Read the new methodology; update the branch's plan to match; potentially abandon if the methodology change made the branch's approach wrong. |
| Branch's feature/project file references a closed parent project | Re-base the work conceptually — the parent's outputs may be on main now and the branch can simplify. |

**Squashing for cleanup.** Long branches with many small "wip" / "fix typo" / "tweak" commits can be squashed before merge to keep main's history clean:

```bash
# Interactive rebase to squash commits
git rebase -i origin/main
# Mark commits with "s" (squash) or "f" (fixup) in the editor
# Save → git replays with the squashes applied
```

When to squash: many micro-commits that don't represent meaningful units of work. Don't squash:
- Distinct phase commits (each phase is a meaningful unit; squashing destroys the audit trail).
- Commits that survived in §11 change logs as historical references.
- Commits that other agents may have rebased their work onto (squashing rewrites history; their commits would diverge).

**When to abandon a branch.** Sometimes the work on a branch becomes obsolete — main moved in a direction that makes the branch's approach wrong, or the user changed direction, or the methodology changed. Abandon ≠ delete:

1. **Read the branch's content** — even if the approach is wrong, the analysis often has lasting value. Capture in `feedback_*.md` memory or as a retrospective note in the project's PROJECT.md §11.
2. **Document the abandonment** in the project's §11 with reason ("methodology X superseded the approach", "user changed direction at session 4", etc.).
3. **Delete the local branch** — `git branch -D <branch-name>`.
4. **Optionally delete the remote branch** — `git push origin --delete <branch-name>`. Or leave it with a `-abandoned` suffix as audit history.

**Anti-patterns:**

- **Letting branches sit indefinitely.** "I'll rebase it eventually" — eventually never comes. Set a calendar item or use the daily-rebase cadence.
- **Squashing distinct phase commits to "clean up history."** Destroys the audit trail. Phases are meaningful units; preserve them.
- **Abandoning silently.** A deleted branch with no §11 entry is lost work + lost reasoning. Document why before deleting.
- **Treating divergence as failure.** Long-running branches diverge from main by design — the question is whether the divergence is being maintained (rebasing) or accumulating (rotting). Maintenance is the methodology.

### 10.6 Recovery from bad merges

Sometimes a merge goes wrong — the resolution was incorrect, the wrong commit was kept, important work got dropped, the merge introduced a regression that's now on main. Recovery is possible but the order of operations matters.

**`git reflog` is your time machine.** Every operation that moves HEAD (commits, merges, rebases, resets, checkouts) is recorded in reflog with a hash + the action that produced it. Even "destroyed" commits live in reflog for ~90 days by default before garbage collection.

```bash
git reflog                      # see the last ~30 actions on HEAD
git reflog --all                # see actions on all refs (branches, HEAD)
```

When something went wrong, **start with `git reflog` BEFORE any destructive operation**. Find the hash of the state you want to return to. Then choose the right recovery operation.

**Recovery patterns by failure mode:**

| Failure | Recovery |
|---|---|
| Just merged the wrong branch into main locally (not pushed yet) | `git reset --hard ORIG_HEAD` — `ORIG_HEAD` is git's auto-set "the state before the last merge/rebase." Pre-merge state restored. |
| Merge resolved a conflict the wrong way (not pushed yet) | `git reset --hard <hash-from-reflog-pre-merge>` then redo the merge with the correct resolution. |
| Pushed a bad merge to main (origin diverged from intent) | DO NOT `--force` push. Two safe options: (a) `git revert -m 1 <bad-merge-commit>` creates a NEW commit that undoes the bad merge — clean history shows "we merged X then reverted X"; (b) reset main locally to pre-bad-merge, cherry-pick correct work onto it, then negotiate with the team about a force-push window (last resort). Almost always (a). |
| Rebase squashed a commit you wanted to keep | `git reflog` to find the pre-rebase HEAD; `git reset --hard <hash>` to restore; redo the rebase carefully. |
| Lost work because of `--ours` / `--theirs` shortcut | `git reflog` for the pre-merge HEAD; check out that hash; cherry-pick the lost work onto the current branch. |
| Force-pushed over someone else's work (catastrophic) | If they have local copies: they can re-push (but your force-push will fight again — first negotiate). If no local copies exist: the work is gone (reflog is per-clone, so their reflog has it but yours doesn't). **Prevention >> recovery here**. |

**`git reset --hard ORIG_HEAD` deserves special mention.** Git auto-sets `ORIG_HEAD` to the pre-operation HEAD whenever you run `git merge`, `git rebase`, `git pull`, `git cherry-pick`. If the operation produced unwanted state, `git reset --hard ORIG_HEAD` is the canonical undo. It's safe — you can verify with `git log ORIG_HEAD..HEAD` what would be lost first.

**When to ask for help (humans are the safety net for the methodology, just as `git merge` is the safety net for the rules).** The methodology has gaps; humans are the meta-safety-net. Ask the user / a senior teammate when:

- The recovery operation involves `--force` push or `--force-with-lease` and you're not 100% certain you understand the impact on other clones.
- The bad state has already been pushed to main and reverted on multiple clones; reconciling the multi-clone state is beyond your context.
- `git reflog` shows operations you don't recognize (suggests another agent / process did something on your local repo without your knowledge).
- The work that needs recovery is irreplaceable and the recovery path has any non-zero chance of making it worse.

**Anti-patterns:**

- **Trying recovery without `git reflog` first.** Operating blind. Reflog is the map; running operations without it is navigating without a compass.
- **`--force` push to "fix" a bad merge.** Almost always wrong. Use `git revert -m 1 <merge-commit>` instead — preserves history, doesn't invalidate other clones.
- **`git reset --hard` mid-merge to "start over".** That discards merge state including any work-in-progress resolution. Use `git merge --abort` instead.
- **Ignoring a bad merge because "it's already on main, can't undo now."** It can be undone via revert (above). The longer it sits, the more downstream commits build on top, the more painful the revert. Catch it fast.
- **Recovering silently.** A recovery commit deserves a clear message: what went wrong, what was recovered, how the original mistake will be prevented. Per `feedback_safety_nets_become_learnings.md` — failures captured become learnings; silent recovery destroys the learning.

---

## 11. Branch-per-project workflow

**The shift (2026-05-03 extension to the branching methodology).** The previous "commit per phase to main, push at project close" rule (`feedback_no_auto_commit.md` + `feedback_no_auto_commit.md`) is amended for projects/features that ship via branches:

- **Phase commits go to the project's branch**, not main.
- **Push at project close happens on the branch**, branch-to-branch first (`git push -u origin <branch>`), then orchestrator-merges branch tip to main (§12).
- **Main is the integration target**, not the active workspace.

**Why.** Working on a branch isolates phase-by-phase work from main. If anything goes wrong mid-project (collision, regression, scope change), main is unaffected. The branch can be discarded, rewound, or rebased without touching shared state. Agents working in parallel on different branches don't step on each other.

**When this applies.**
- Branch when filing a project OR a feature. Both warrant the isolation overhead.
- One-line direct fixes (typo, broken link, dependency bump that's clearly safe) can still go straight to main without branching — those don't earn filing either, so they don't earn branching.
- Discriminator: **"would I file this?"** Yes → branch. No → direct.

**The new commit cadence:**

```
At project/feature filing → create branch from origin/main first (§13)
At end of phase 1        → commit on branch (no push)
At end of phase 2        → commit on branch (no push)
... etc
At final deliverable     → commit on branch + push branch to branch (`git push -u origin <branch>`)
At orchestrator-merge    → fast-forward push branch tip to main (§12)
```

The two pushes are functionally distinct: the **branch-to-branch push** makes the work remotely visible (and durable across machine loss). The **fast-forward push to main** is the integration step.

### 11.1 Master-tree branching adaptation

**The shape.** When the user invokes a **master-tree project** (orchestrator project that derives N child projects, executable in parallel or serial — see `KB § PATTERNS/master-tree-parallel-batches.md`), the branching shape is hierarchical:

- **Master-tree branch** = `<master-tree-project-slug>`. Branched from `origin/main`.
- **Each child branch** = `<child-project-slug>`. Branched from the **master-tree branch**, NOT from origin/main.

Children land back on the master-tree branch (FF or merge per §10.2). The master-tree branch eventually lands on origin/main when the whole tree closes. Branching mirrors the project hierarchy.

**Recipe:**

```bash
# Master-tree project filed
git checkout -b <master-tree-slug> origin/main
# File projects/<master-tree-slug>/PROJECT.md
git add projects/<master-tree-slug>/
git commit -m "docs(projects): file <master-tree-slug> [<master-tree-slug> Phase 0]"
git push -u origin <master-tree-slug>

# Child A filed (derived from master)
git checkout -b <child-a-slug> <master-tree-slug>   # branch from master, NOT origin/main
# File projects/<master-tree-slug>/<child-a-slug>/PROJECT.md (or wherever the master-tree puts children)
# OR file the child as a top-level project per master-tree-parallel-batches.md conventions
git add <paths>
git commit -m "docs(projects): file <child-a-slug> [<child-a-slug> Phase 0]"
git push -u origin <child-a-slug>

# Child B filed (also derived from master)
git checkout -b <child-b-slug> <master-tree-slug>
# ... same shape ...

# Children execute their phases on their own branches (per §11)
# Children land back on master:
git checkout <master-tree-slug>
git merge <child-a-slug>   # or git push origin <child-a-slug>:<master-tree-slug>
# repeat for each child as it closes

# Master closes → master-tree branch tip lands on origin/main
git push origin <master-tree-slug>:main   # orchestrator's fast-forward push
```

**Why hierarchical (and not "everything from origin/main"):**

1. **Children inherit the master's filing context.** When child A is branched from master, it sees the master-tree's PROJECT.md, the live-patterns-log, the absorption catalog — everything the master committed. Branching from origin/main would lose that.
2. **Children land back as a unit.** When master merges to origin/main, it carries all its children's content (which are already merged into master). Origin/main sees one coherent integration of the whole tree, not N separate landings.
3. **Cross-pollination respects the tree.** Per `KB § PATTERNS/master-tree-parallel-batches.md`, children share findings via the master root's scratchpad. Hierarchical branching ensures children see updates to the scratchpad as the master commits them.

**Trigger phrases:**
- "master-tree this <work>"
- "create a master tree for <work>"
- "spawn a master-tree project covering <X, Y, Z>"
- "let's run X, Y, Z as a master-tree" (multiple children explicitly named)

**Naming convention** (consistent with §5 + master-tree-parallel-batches §8):
- Master: `<topic>-rollout` (e.g. `products-wiring-rollout`, `methodology-consolidation-rollout`).
- Child: `<topic>-<child-scope>` (e.g. `personal-finance-wiring`, `erp-imobiliario-wiring`). Child slugs are independent of master slug; they don't repeat the master's prefix unless it's natural.

**Branch-of-branch chain depth.** §10.3 warns against chains deeper than 2. Master-tree branching is exactly the 2-deep boundary case (origin/main → master → children). It works because each level has clear ownership (master = orchestrator; children = their own working agents). Going 3 deep — child-of-child — would violate the §10.3 warning AND the master-tree pattern itself (master-trees don't have grand-children; they have either children or nothing).

**Anti-patterns:**

- **Branching children from origin/main instead of master.** Children miss the master's context (filing, scratchpad, absorption catalog updates). They become orphans whose findings won't reach sister children.
- **Master-tree without explicit children.** A master-tree branch with no children is just a regular project branch. Don't use master-tree branching for solo projects — use plain branch-per-project (§11).
- **Renaming master mid-flight.** The master branch's name is the durable handle children depend on. Renaming forces every child to update its base. If the master needs renaming, do it at master close (when no children are open).
- **Master close before all children close.** Master can't fast-forward to main while children are still in-flight on the master branch. Wait for all children to merge into master, THEN master → main.

**The split.** Two roles, mapped to two perspectives:

- **Working agent.** Subagent spawned via Task (or the CLI agent acting as implementer). Holds narrow project/feature context. Owns: phase implementation, phase commits to branch, branch-to-branch push.
- **Orchestrator.** CLI agent in the user's session-spanning conversation. Holds session-wide context (multiple projects, system-wide methodology, recent commits, parallel-agent activity). Owns: branch creation triggers (§13), final review pass after the working agent finishes, fast-forward push of branch tip to main.

**Why the split.** The working agent rationalizes its design as it implements — that's how implementation works. Blind spots and integration concerns are easier to spot from outside the implementation context. The orchestrator's "fresh eyes" pass at merge time catches things like: scope creep, methodology slips that snuck past the working agent, missing three-way sync, missing improvements-block, KB pointers that didn't get updated, files staged by accident. It's a structural audit, not a content review.

**This is the GitHub PR model, made explicit.** The working agent = PR author; the orchestrator = maintainer who merges. GitHub institutionalizes this role separation — PRs require a reviewer, the reviewer is (typically) not the author, the merge button is gated on review approval. The pattern works in GitHub for the same reason it works here: implementer + integrator = two vantage points, structurally separated, integration risk caught at merge time rather than at next-session-start time.

**The rule does not depend on GitHub-as-a-tool — it depends on the role separation.** If we ran this methodology on a single dev's laptop with no remote at all, we'd still need an integrator. Without one, the implementer self-merges and the merge-time review pass is skipped (or rather, conflated with implementation, which is exactly the failure mode the split is designed to prevent). GitHub provides the institutional shape; the methodology codifies the shape so it works wherever we are.

**Practical implication:** if you ever read this doc in a context where GitHub isn't being used (different forge, no remote, multi-machine peer setup, future tooling we haven't picked yet), the orchestrator-merge step still applies. Whoever holds the integrator role does it. The role doesn't dissolve because the tool changed.

**How it works.**

```
User: "branch this — file the X feature"
  ↓
Orchestrator: creates branch <slug> from origin/main (§13)
              files <slug>.md (feature) or PROJECT.md (project)
              spawns working agent via Task (or implements directly)
  ↓
Working agent: implements, commits per phase to branch
               pushes branch to branch on close
               returns control to orchestrator
  ↓
Orchestrator (fresh-eyes pass):
  - reviews diff: `git diff origin/main..origin/<branch>`
  - re-runs verification: tests, KB sync, kb-counts
  - checks authorship: every commit on branch is the working agent's
  - checks scope: didn't drift from feature/project description
  - checks methodology: 3-way sync done, improvements block filled, etc.
  ↓
If clean → fast-forward push branch tip to main
If issues → push back to working agent (or fix inline if trivial)
```

**Why subagents work for this — the mechanism, not the model.** A subagent spawned via Task gets a fresh context — it reads KB/CLAUDE on startup but has no working memory of the conversation that produced its task. From its perspective: it's handed a brief, does the work, returns a result. Same model, different session contexts.

**The deeper rationale (why this mechanism produces better merges) — locked here so the methodology survives model-behavior shifts and future Claude versions:**

1. **Implementation rationalizes its own design.** When an agent is deep in a task, it builds a coherent narrative around its choices ("I added X because of Y because of Z"). That narrative is self-reinforcing — the agent's working context is full of the reasons it made each choice. From inside that context, design slips look like "obvious solutions." From outside, they look like slips.
2. **Different vantage points expose different blind spots.** The working agent sees the project's internal coherence; the orchestrator sees the project's fit with everything else (other in-flight work, methodology drift, KB/memory state, naming collisions, integration risks). Neither vantage point dominates — they're complementary.
3. **The cost of catching an integration issue at merge time is much lower than at the next session start.** Merge-time catch: the working agent's branch hasn't been integrated yet; the issue is contained. Next-session catch: the issue is already on main; reverting takes ceremony, fixing-in-place leaves history confusing. Cheaper to check before merging.
4. **The mechanism is robust to model variation.** If Claude's default behavior changes in a future version (more conservative, less conservative, different blind spots), the orchestrator-as-reviewer pattern still works — it doesn't depend on Claude's specific tendencies. It depends on the **structural separation** of "agent-doing-the-work" from "agent-merging-the-work." Two of any sufficiently capable instance, given different contexts, produce different review surfaces. The methodology survives the model.

**Therefore:** even when subagent capability improves to the point that "a subagent could merge its own work safely," the orchestrator-merge step stays. Not because the subagent can't, but because the structural-separation benefit doesn't go away. Merges remain the orchestrator's job.

**When orchestrator and working agent are the same Claude instance, by necessity** (no subagent was spawned — user works directly with the CLI agent on a small enough task that delegation is overhead): the mechanism is preserved by **mode-switching**. Take a literal pause + separate turn between implementation-mode and review-mode. Re-read the diff as if you'd just walked in. Less rigorous than separate-session, more rigorous than merge-on-autopilot. Same principle: two passes, different vantage points, same artifact.

---

## 13. Branch-creation as project/feature trigger

**Trigger phrases.** When the user says any of:
- `"branch this"`
- `"branch <topic>"`
- `"create another branch for <X>"`
- Extended phrasing that asks for a branch (the user may use 2 words or a full sentence; both count)

…the agent's response sequence is:

1. **Create the branch FIRST** — `git checkout -b <slug> origin/main`. The slug is the project/feature name (which is also the branch name; one source of truth).
2. **File the project (or feature) on the branch** — copy `templates/PROJECT-TEMPLATE.md` for projects, write `<slug>.md` directly for features.
3. **Then start implementing** — phase by phase, per the standard project-execution methodology, with all phase commits going to the branch (§11).

**Why this order.** Branch-first prevents the slip pattern of "started editing files on main, then realized this should have been a branch, now my history is mixed." Hard ordering. The trigger-phrase shape mirrors the existing "interrogate user → file project → implement" cadence; this just adds branch creation as step 0.

**Slug naming convention** (consistent with §5):
- `<project-slug>` for projects → branch name `<project-slug>` or `<project-slug>-shipped` if cherry-pick-and-ship pattern
- `<feature-slug>` for features → branch name `<feature-slug>`
- Cross-cutting topics (no project/feature attached): `<topic>` directly

**Anti-pattern: implicit branching.** Don't branch silently because you "felt like it." Branching is triggered by an explicit user phrase (or, rarely, by the methodology rule itself when the agent detects parallel-agent commits in unpushed range — that's the one auto-branching case, codified in §1).

---

## 14. Pre-work fetch protocol

**Before any agent starts substantive work on a scope** (project, feature, multi-file change), run:

```bash
git fetch origin
git branch -a                                # list all local + remote branches
git log --all --oneline -20                  # recent commits across all branches
# For each file the work will touch:
git log --all --oneline -- <file-path>      # who touched this file, on which branch
```

**If a parallel agent is already working on overlapping scope** (an active branch touches files in your scope, OR there are recent commits on main from another agent that touch your scope):

1. **Don't start your edits on the colliding files yet.** Work on the **next steps** of your project that DON'T overlap.
2. **Wait for the parallel agent to commit first** on the colliding scope. Their commit becomes the new base.
3. **Then merge their work into your branch** (`git merge origin/main` or `git rebase origin/main`).
4. **Only then start your edits on the previously-colliding files** — they now build on the merged base, not race against it.
5. **Recurse if the next steps also collide.** Each round: do non-colliding work, wait, merge, then attack the colliding scope.

**Why merging (instead of "commit after, hope it works"):**

Without this protocol, two agents touching the same file commit in parallel, then one of them pushes first and wins. The second agent either: (a) silently overwrites the first (their `git push` clobbers — bad), or (b) gets blocked by a non-FF rejection and has to recover (better, but reactive). The pre-work fetch + merge-after-collision protocol solves it **proactively**: the second agent KNOWS about the first agent's work BEFORE editing, builds on top of it, and the merge is automatic for non-conflicting changes (or methodology-driven for same-line conflicts, per §10 TBD).

**Mental model:** `work1 + work2 = work1+2` is the desired outcome. Without merging, you get `work2` (second-write-wins). With merging, you get the union. The merging methodology (§10) covers the conflict-resolution case; this section covers the proactive coordination.

**Cost.** ~5 seconds of fetch + scan at agent startup. Mandatory for branched work; recommended for direct-to-main work touching shared files.

**Companion to.** `feedback_parallel_agent_collision_protocol.md` (the after-the-fact "STOP, wait, continue" protocol when collisions DO happen). The pre-work fetch protocol is the proactive complement: catch them before they happen.

### 14.1 Phase-state verification before dispatch

**The rule (added 2026-05-04 from Batch 1A first-dispatch slip).** Before dispatching a subagent on an in-flight project, the orchestrator MUST verify the target's actual phase-state — not rely on the project's status header narrative alone.

**Recipe:**

```bash
# Inside the target project's PROJECT.md:
grep -c '^- \[x\]' projects/<slug>/PROJECT.md   # count of ticked sub-tasks
grep -c '^- \[ \]' projects/<slug>/PROJECT.md   # count of unticked sub-tasks
# OR more focused per-phase:
sed -n '/^### Phase /,/^### Phase \|^---/p' projects/<slug>/PROJECT.md | grep '^- \['

# Tail the §11 change log for the most recent close entry:
awk '/^## 11\./,EOF' projects/<slug>/PROJECT.md | head -50
```

The status header (`Status: ⏳ Reactivated — execution in progress`) is **narrative**, often written in past tense referring to a past session, and can lag the actual state by sessions. **Phase-state in §6 (`- [x]` ticks + phase header icons) and the §11 change log are the source of truth.**

**Why this matters:** dispatching a subagent on an already-closed project is a no-op cost (subagent's session burned for nothing) AND it muddies orchestrator-merge mechanics. Caught 2026-05-04 on Batch 1A: orchestrator dispatched session-review-baseline thinking Phases 2+ remained; subagent correctly identified all 4 phases had shipped in prior commits + reported back.

**Cost:** ~30 seconds of verification per dispatch.

**Anti-patterns:**

- **Reading only the status header.** Narrative; can be stale.
- **Reading only the first N lines of PROJECT.md.** Phase-state lives further in (§6); status header lives in metadata.
- **Trusting the master plan's per-node status field.** Can also be stale if the master plan was assembled across sessions.

**Companion** to: `KB § 01-PHILOSOPHY.md § Branching-first orchestration` (orchestrator's full-responsibilities list — phase-state verification is now part of step 1 "plan + chunk").

### 14.2 Prerequisite-merge verification before follow-up dispatch (NEW 2026-05-10)

**The rule.** When dispatching follow-up subagents from `origin/main` whose work depends on a closed project's commits, the orchestrator MUST verify those commits ARE on `origin/main` BEFORE dispatching. Branch closure that pushes to `origin/<project-branch>` (in-flight push) is NOT enough — `origin/main` lags until the orchestrator's fast-forward push lands. Follow-up branches pre-created from `origin/main` will start from a base that lacks the closed project's work.

**How it surfaced.** AdConnect MVP closed 2026-05-10; pushed to `origin/adconnect-mvp-implementation`; archived to `archive/projects/2026-05-10/01-adconnect-mvp-implementation/`. Orchestrator then pre-created 6 follow-up branches via `git push origin origin/main:refs/heads/<slug>` — but `origin/main` was still at the pre-MVP `51db601` (last actual main commit). Engineer C (`adconnect-test-conftest-distributor-binding`) needed AdConnect's tests + auth wiring to do the conftest binding; engineer correctly identified the gap and self-recovered via `git merge adconnect-mvp-implementation` into the project worktree branch as the prerequisite base. Methodology gap: should have FFed to main FIRST.

**Recipe — pre-dispatch prerequisite check:**

```bash
# Before pre-creating follow-up branches from origin/main:
git fetch origin

# 1. Confirm the project's close commits are on origin/main:
git log origin/main..origin/<project-branch> --oneline   # any output means main is BEHIND
# Empty output = main has the close commits = safe to dispatch.

# 2. If main is behind: FF push BEFORE pre-creating follow-up branches.
git push origin origin/<project-branch>:main           # FF push to main
git fetch origin                                         # re-sync
git log origin/<project-branch>..origin/main --oneline  # should match (now identical)

# 3. NOW pre-create follow-up branches:
git push origin origin/main:refs/heads/<follow-up-1> \
                origin/main:refs/heads/<follow-up-2> ...
```

**The structural answer.** Two choices for orchestrators after closing a project + before dispatching N follow-ups:

- **Choice A (clean) — FF push to main FIRST.** The project's close commits land on main; follow-up branches start from a base that includes them. Required when N≥2 follow-ups depend on the closed work.
- **Choice B (deferred) — pre-flag the cross-branch dependency in every brief.** Follow-up engineers fetch the project branch + merge it into their own branch as their prerequisite base. Add to brief: "*Your worktree's base will be `origin/main` which currently lacks the `<project>` close commits. Before starting, run `git fetch origin <project-branch> && git merge origin/<project-branch>` to bring them in.*" Document the engineer-side merge in the brief verbatim.

**Choice A is preferred** when no merge-time review is pending on the project. Choice B is the carve-out when the orchestrator is intentionally holding the project's main-merge for further review. Default to Choice A; choose B explicitly with rationale.

**Anti-patterns:**

- **Pre-creating follow-up branches BEFORE FFing the prerequisite project.** Follow-ups silently start from a stale main; engineers either self-recover (paying merge-cost they shouldn't have to) or hit cross-branch dependency surprises mid-flight.
- **Confusing "branch pushed to remote" with "merged to main".** A pushed in-flight branch makes work visible but does NOT update main. `origin/<branch>` ≠ `origin/main`.
- **Trusting "engineer will figure it out" instead of pre-flagging.** Some engineers correctly self-recover (Engineer C 2026-05-10) but others may STOP-and-report (the §16.7 fallback) and burn dispatch capacity. The brief should pre-resolve the dependency, not delegate it.

**Companion** to: `§ 16.7 Worktree-base mismatch` (engineer-side recovery via worktree-base preamble) — §14.2 is the orchestrator-side prevention of the same class of gap (prerequisite-merge before dispatch). Together: orchestrator verifies main has prerequisites, AND brief preamble lets engineers recover if it doesn't.

---

## 15. Exploratory branching — branch-and-compare and merge-upfront

Two patterns for using branches as decision-making tools rather than just isolation tools. Triggered by user phrasing, not by detection. Both build on top of the standard branching mechanics in §§1-9.

### 15.1 Branch-and-compare (parallel experimentation)

**Trigger phrases.** "branch 2 things and compare", "let's try both A and B", "spike both approaches", "experiment with X vs Y", "A or B?", "what's cleaner — X or Y?", "let's see how each plays out."

**The shape.** When the user wants to compare alternatives, each approach gets its own branch from `origin/main`. Both are implemented in isolation. Comparison happens after both ship. User picks winner (or asks for hybrid).

```bash
# Approach A
git checkout -b <topic>-approach-a origin/main
# implement A
git add <paths>
git commit -m "<topic> approach A: <description>"
git push -u origin <topic>-approach-a

# Approach B (back to clean baseline)
git checkout -b <topic>-approach-b origin/main
# implement B
git add <paths>
git commit -m "<topic> approach B: <description>"
git push -u origin <topic>-approach-b

# Comparison (orchestrator role)
git diff origin/<topic>-approach-a..origin/<topic>-approach-b --stat
git log origin/<topic>-approach-a --oneline
git log origin/<topic>-approach-b --oneline
# Run tests on each branch independently
# Surface comparison to user
```

**Comparison criteria** (the orchestrator presents these):
- **Diff size** — which approach touches fewer / more files? Smaller is often better for review, but not always for cleanliness.
- **Test results** — both branches must pass the existing test baseline. If A passes and B fails, that's the comparison; not all tradeoffs are subjective.
- **Methodology fit** — does one approach require more carve-outs (accept-with-rationale) than the other?
- **Future maintenance** — which one is easier to extend? Read both implementations as if you were going to add a sibling feature next session.
- **Readability** — same intent, but one approach reads more naturally?
- **Performance / cost** — when measurable, run benchmarks on both.
- **User experience** — when UI is involved, screenshot or describe both flows.

**Folding the winner back to main.**

After user picks winner (say, A):

```bash
# Orchestrator fast-forward push of winner to main
git push origin <topic>-approach-a:main
# Mark loser branch as abandoned (or delete it)
git branch -m <topic>-approach-b <topic>-approach-b-abandoned
git push origin <topic>-approach-b-abandoned
git push origin --delete <topic>-approach-b
```

The loser branch should preserve its work as audit history (rename with `-abandoned` suffix; don't just delete). The reasoning that produced approach B is durable — capture in `feedback_*.md` if there's a learning, or in a §11 entry on the next related project.

**When user asks for a hybrid.** "Take A's structure but B's API" → that's a NEW branch from origin/main (or from the chosen base) implementing the hybrid. The original A and B branches stay as audit references; the hybrid is the actual ship.

**When to use this pattern:**
- Multiple distinct approaches that conflict (can't easily merge into one branch).
- Want to see both running before deciding.
- Cost of running both is acceptable (small-to-medium scope work; not 5-day refactors).
- Comparison criteria are clear (or being discovered through the comparison itself).

**Anti-patterns:**
- **Branching only one alternative.** Defeats the comparison. If you commit to seeing both, see both.
- **Comparing while one is still in flight.** Wait for both to ship. Comparing half-done work biases to whichever is closer to done.
- **Picking based on which one was implemented first.** Implementation order is not a comparison criterion; the implementation is.
- **Deleting the loser branch immediately.** Lose the audit trail. Use `-abandoned` suffix.

### 15.2 Branch-and-merge-upfront (synthesis)

**Trigger phrases.** "merge them upfront", "what if we did both", "let's combine A and B", "hybrid", "union of approaches", "take the best of both."

**The shape.** Both approaches go on a single branch as the union. Compared against `origin/main` baseline, not against alternatives. Shipped if the union holds.

```bash
git checkout -b <topic>-combined origin/main
# implement A's contribution
# implement B's contribution
# verify the union is coherent — they don't fight each other; tests pass; surface area makes sense
git add <paths>
git commit -m "<topic> combined: <A summary> + <B summary>"
git push -u origin <topic>-combined

# Orchestrator review against origin/main baseline
git diff origin/main..origin/<topic>-combined --stat
# Tests pass? Methodology slips? KB pointers all resolve?
# If clean, fast-forward push to main
git push origin <topic>-combined:main
```

**When the union doesn't hold.** Sometimes the synthesis surfaces that A and B genuinely conflict (their integrations fight each other; combined surface is incoherent; tests interact in unexpected ways). When this happens:
1. Document the conflict on the branch (what about A and B clashed).
2. Surface to user: "merge-upfront didn't hold; here's why" with concrete file/line evidence.
3. Either (a) drop the synthesis and go to branch-and-compare instead, or (b) re-design the integration so they don't fight.

**When to use this pattern:**
- Both approaches have merit AND don't fundamentally conflict.
- The union is better than either alone.
- Cheaper to combine than to run both separately.
- Examples: combining two sets of methodology improvements, merging two feature subsets, layering a refactor over a new feature.

**Anti-patterns:**
- **Forcing synthesis when A and B genuinely conflict.** If you find yourself adding `if approach_a:` / `else_approach_b:` toggles, you're not synthesizing — you're parameterizing. Go back to branch-and-compare.
- **Merging upfront without checking that A and B don't break each other.** Run the test suite as part of the synthesis commit, not as an afterthought.
- **Treating the combined branch as "two commits in one."** Each contribution should be a clean, reviewable unit. If the synthesis is messy, split into two commits on the same branch (one per approach), then tests pass on the union.

### 15.3 Choosing between the two patterns

| Scenario | Pattern |
|---|---|
| Approaches are mutually exclusive (architectural choice — A or B but not both) | **Branch-and-compare** |
| Approaches are independent improvements that can both ship | **Branch-and-merge-upfront** |
| Implementation cost of running both is high (>1 session each) | **Branch-and-compare** with a shorter spike on each first |
| Implementation cost is low and union has clear value | **Branch-and-merge-upfront** |
| User explicitly says "compare" / "vs" / "or" | **Branch-and-compare** |
| User explicitly says "both" / "hybrid" / "union" / "combine" | **Branch-and-merge-upfront** |
| Ambiguous user phrasing | Surface the choice — "compare both, or combine?" — before branching |

**Default when ambiguous: ask.** The two patterns produce very different artifacts; picking the wrong one means redoing the work or running unnecessary spikes. Cheap to ask once; expensive to commit to the wrong pattern.

**Companion to.** `KB § 01-PHILOSOPHY.md § Estimate off evidence` (the orchestrator's review of branch-and-compare results IS the evidence that grounds the user's pick); §11 Branch-per-project (each branch follows the per-project workflow); §12 Orchestrator role (the orchestrator runs the comparison, not the working agent — fresh-eyes vantage point).

---

## 16. Git worktree for true parallel agents

**The problem.** Multiple subagents working on different branches in the SAME git worktree contend for the checkout state. When subagent A runs `git checkout -b branch-A` and subagent B runs `git checkout -b branch-B` simultaneously in the same repo directory, the second checkout overrides the first's worktree mid-flight — uncommitted work gets stashed, files swap to the wrong branch, the orchestrator's working state shifts under it. Caught 2026-05-04 on the first parallel-execution attempt: the projects-cleanup subagent's checkout displaced the orchestrator's uncommitted Phase 0 file (correctly auto-stashed by the subagent per its briefing, but the contention itself is the failure mode).

**The mechanical truth:** git is single-worktree by default. Only one branch can be checked out per worktree. Parallel agents on different branches need separate worktrees.

### 16.1 Recipe

**For the orchestrator, before parallel dispatch:**

```bash
# Set up a sibling worktrees directory (gitignored — see §16.4)
mkdir -p ../noctusai-worktrees

# Per subagent: create a worktree on the subagent's branch
git worktree add ../noctusai-worktrees/<subagent-branch-name> origin/main
# Optionally specify the branch creation: -b <new-branch>
git worktree add -b <subagent-branch-name> ../noctusai-worktrees/<subagent-branch-name> origin/main
```

The subagent's brief includes the absolute path to its worktree:

```
Your working directory: /Users/rapha/Documents/repository/NoctusAI/noctusai-worktrees/<subagent-branch-name>
Your branch is already checked out there. Do not `git checkout` to a different branch in this worktree.
All your edits, commits, and pushes happen from this directory.
```

The subagent operates in its own filesystem; the orchestrator's main worktree is untouched.

**After the subagent's branch merges to main:**

```bash
git worktree remove ../noctusai-worktrees/<subagent-branch-name>
# Cleanup: removes the worktree dir + its administrative files.
```

If a worktree has uncommitted changes, `git worktree remove` refuses by default. Pass `--force` only if you've confirmed the subagent's work is fully committed + pushed (i.e. nothing in the worktree is unsaved).

### 16.2 When to use worktrees

**Required:**
- Dispatching 2+ subagents on different branches in a single `Task` tool-use turn (the parallelism case branching-first methodology is built for).

**Not needed:**
- Single subagent (no contention possible).
- Sequential subagent dispatch (one finishes + reports before the next starts; orchestrator's worktree state is between dispatches, not during).
- Orchestrator-direct work (orchestrator doing everything itself; no subagents).

### 16.3 Worktree naming

Mirror the branch naming convention (§ 5):
- `../noctusai-worktrees/<project-slug>` for projects.
- `../noctusai-worktrees/<feature-slug>` for features.
- `../noctusai-worktrees/<topic>` for cross-cutting work.

The worktree's directory name and the branch name match, so `cd ../noctusai-worktrees/<X>` always lands in the right branch's filesystem.

### 16.4 Cleanup discipline

After a worktree's branch lands on main and is merged + closed:

```bash
git worktree remove ../noctusai-worktrees/<branch-name>
```

Worktrees not auto-cleaned. Lingering worktrees consume disk space + clutter `git worktree list` output.

**Add to `.gitignore` (or rely on default if `noctusai-worktrees/` is outside the repo):** if the worktrees directory is INSIDE the repo (not recommended), gitignore it. The recipe in §16.1 puts worktrees alongside the main repo (sibling), which is automatically outside git's tracking.

### 16.5 Anti-patterns

- **Dispatching N subagents into the same worktree.** Race-prone. Even if today they happen to interleave cleanly, tomorrow one will stomp another. Always worktree-add for parallel.
- **Leaving worktrees lingering after close.** Disk waste + grep results from stale checkouts pollute future searches.
- **`git worktree remove --force` without verifying clean state.** Drops uncommitted work silently. Confirm `git status` clean in the worktree first.
- **Worktrees on the SAME branch as another worktree.** Git refuses by default (a branch can be checked out in only one worktree at a time). If you genuinely need this, you misunderstand the use case — branches are 1:1 with worktrees.

### 16.6 Develop our own wrapper later

User directive 2026-05-04: *"a git worktree, then we develop our own based on the git worktree work, yea?"* — start with vanilla `git worktree`; build NoctusAI-specific tooling on top once we've validated the workflow. Follow-up project (TBD): `noctus.dev.dispatch_parallel(briefs)` — orchestrator passes N subagent briefs; tool sets up worktrees, dispatches subagents, monitors, collects findings. Out of scope today; tracked when the gap surfaces N=2+.

### 16.7 Worktree-base mismatch — the `Agent` tool's `isolation: "worktree"` gap (NEW 2026-05-10)

**The mechanical truth.** When the orchestrator dispatches a subagent via the `Agent` tool with `isolation: "worktree"`, the harness creates the worktree from `main` (or `origin/main` — whichever the harness defaults to), **NOT from the orchestrator's current branch tip.** If the orchestrator is mid-project on a feature branch with N unmerged commits, the engineer's worktree starts from a state that lacks those commits — the project's in-flight work is invisible to the engineer.

**How it surfaced.** AdConnect MVP Implementation (2026-05-10), 8 engineer dispatches in 4 waves on branch `adconnect-mvp-implementation`. Confirmed across 6+ engineers: dispatched worktrees opened to a state several commits behind the orchestrator. Engineers E, G, H self-recovered via `git reset --hard <orchestrator-tip-sha>`. Engineer F correctly STOPPED rather than fabricate. Engineer D's stale-base attempt regressed `001_<product>.sql` from 841 lines back to 79 — caught at merge time, rejected.

**Why this is a structural gap, not a one-off.** The `isolation: "worktree"` parameter is harness-controlled; we cannot change its base-resolution behavior. The fix has to live in OUR dispatch layer — the brief composition. Every engineer brief MUST carry a worktree-base verification preamble that names the orchestrator's HEAD SHA + the recovery directive.

**The orchestrator-side fix — brief preamble (mandatory clause).**

Every engineer dispatch brief MUST include this preamble verbatim, with the orchestrator's CURRENT branch + HEAD SHA filled in:

> ## Worktree base verification (FIRST — before any work)
>
> Your worktree was created via `Agent` tool's `isolation: "worktree"`, which initializes from `main`, NOT from the orchestrator's branch. The orchestrator is mid-project on branch `<orchestrator-branch>` at commit `<orchestrator-tip-sha>`. Your worktree may be missing in-flight commits.
>
> **Run these checks first:**
> 1. `git rev-parse HEAD` — record your worktree's starting SHA.
> 2. `git log --oneline -5` — confirm the most recent commits.
> 3. If your starting SHA ≠ `<orchestrator-tip-sha>`: `git fetch origin && git reset --hard <orchestrator-tip-sha>` (or `git reset --hard origin/<orchestrator-branch>` if the orchestrator pushed first). Verify with `git log --oneline -3`.
> 4. If you cannot match the orchestrator-tip SHA (it doesn't exist in your worktree because the orchestrator hasn't pushed), **STOP and report back** — do NOT fabricate a base. The orchestrator will push the branch and re-dispatch.
>
> Only then proceed with the work below.

**Step 0 — environment hydration (NEW 2026-05-10).** Briefs that touch frontend code or run `vitest` / `vite build` MUST also instruct the engineer to run `bash scripts/bootstrap/bootstrap-worktree.sh` FIRST (idempotent; ~0.2s no-op on a hydrated worktree, 30-90s on a fresh one). Fresh worktrees inherit `.git` but NOT `.gitignored` `node_modules/` — the script `npm ci`s (or `npm install`s when no lockfile) every frontend (seed/lib/frontend, seed/framework/frontend, products/*/frontend) and prints a Python recap. N=5+ confirmed (Engineers G, Q, AA, N, S — 2026-05-10) burning ~5-10 min each on the env-parity dance. Filed under `projects/worktree-bootstrap-script/PROJECT.md`; lives at `scripts/bootstrap/bootstrap-worktree.sh`. Skip only when the brief is purely-backend AND won't trigger vitest in CI.

**The engineer-side recovery recipe.** When an engineer detects the mismatch:

```bash
# 1. Verify the orchestrator's tip SHA exists locally:
git cat-file -e <orchestrator-tip-sha> 2>/dev/null && echo "exists" || echo "missing"

# 2a. If exists locally: hard-reset.
git reset --hard <orchestrator-tip-sha>

# 2b. If missing locally: fetch the orchestrator's branch first.
git fetch origin <orchestrator-branch>
git reset --hard origin/<orchestrator-branch>

# 3. Verify alignment.
git log --oneline -3
git status  # should be clean
```

**Pre-dispatch directive — push the branch FIRST (companion).** When dispatching engineers, the orchestrator SHOULD push the branch BEFORE composing briefs, so engineers can recover via `git fetch origin <branch> && git reset --hard origin/<branch>` regardless of whether the orchestrator's local commits are visible to the engineer's worktree. *Trade-off:* pushing exposes in-flight work to the remote earlier, but the recovery path becomes mechanical rather than dependent on the harness's local-commit propagation. Adopt the push-first variant for branches with 2+ engineer dispatches.

**Anti-patterns:**
- **Brief omits the preamble.** Engineer's worktree silently starts from `main`; engineer's edits land on a stale base; merge collapses or regresses orchestrator's work (Engineer D 001 regression — 841 → 79 lines, caught only at merge review).
- **Brief hard-codes the wrong SHA.** Engineer resets to a stale tip; same shape as omitting. Always read `git rev-parse HEAD` AT brief-composition time.
- **Engineer fabricates a base when the SHA isn't reachable.** Silent error; the brief's STOP-and-report directive prevents this. Caught Engineer F correctly stopping.
- **Skipping the preamble for "small" tasks.** Even one-file edits land on stale base if the worktree opens behind. The preamble is cheap (10 lines, ~50 words). Always include.
- **Push-first variant skipped for 2+ dispatches.** The orchestrator's local-only branch tip may not be reachable from the engineer's worktree even via fetch (depends on harness behavior). When dispatching 2+ engineers, push first.

**Companion to** `§ 17.6 Engineer-brief Write-authorization` (both clauses live in the same dispatch-brief preamble; both override default behaviors that would otherwise silently fail). Both are **architect-side** structural fixes for **engineer-side** harness defaults.

**Three-way-synced 2026-05-10**: KB §16.7 (this section) + `CLAUDE/projects.md` rule pointer + `feedback_worktree_base_verification.md` memory entry.

---

## 17. Knowledge tracking during orchestration

When the orchestrator dispatches subagents (parallel or serial), maintain a durable `findings.md` file at the orchestrator's project / feature root. Subagent reports contribute to it as they complete. At project close, `findings.md` is the orchestration's knowledge artifact.

### 17.1 What goes in findings.md

Five categories (the user's framing — *"errors, mistakes, slips, lessons and stuff"*):

```markdown
# <project-slug> — Orchestration Findings

## Errors encountered
- <date> · <subagent-name>: <error-or-failure>; root cause = <X>; recovery = <Y>.

## Mistakes / slips
- <date> · <subagent-name or orchestrator>: <slip-description>; caught by <Z>; lesson = <W>.

## Lessons learned (durable rules)
- <rule>; applicable when <conditions>; cross-reference to KB if amended.

## Interesting findings (surprises, discoveries)
- <finding>; surprised because <prior-assumption-was>.

## Knowledge pieces (durable patterns)
- <pattern-name>: <one-line description>. Example: <ref>.
```

### 17.2 Distinct from sibling tracking files

| File | Scope | Format | Lifetime |
|---|---|---|---|
| `phase_learnings.db` (SQLite) | Per-phase, per-project | Structured rows | Local-only; gitignored |
| `live-patterns-log.md` | Master-tree per-batch | Append-only table | In master-tree project |
| `cross-product-absorption-catalog.md` | Master-tree per-pattern | Triage register | In master-tree project |
| **`findings.md` (NEW §17)** | **Orchestration meta-record across the whole project** | **Free-form categorized markdown** | **In project / feature root, archived with project** |

`findings.md` is the meta-record — what HAPPENED across the work, especially the unexpected stuff. The other three are atomic / per-batch / per-pattern.

### 17.3 When to maintain findings.md

**Default-on for:**
- Projects (every project's root carries a findings.md by close).
- Master-tree orchestration (alongside the existing live-patterns-log.md + absorption catalog).
- Any orchestrator dispatch of 2+ subagents.

**Optional for:**
- Trivial features (typo fixes, one-line tweaks).
- Single-orchestrator-direct work with no surprises.

If the orchestrator chooses to skip findings.md (trivial work), log a learning to `phase_learnings` SQLite saying "no findings.md needed for <work> — trivial, no surprises." That way the absence is explicit, not silent.

### 17.4 Orchestrator's append cadence

- **At each subagent report:** orchestrator extracts interesting findings from the subagent's response; appends to findings.md.
- **At each surprise:** mid-flight discovery → append immediately (don't batch — the freshness of the moment is the value).
- **At project close:** orchestrator does a final pass — synthesizes lessons + cross-references to KB amendments — and the file lands in archive (project-close → archive per § 11.2 of project-execution.md).

### 17.5 Anti-patterns

- **Orchestrating without a findings.md.** Slips evaporate; the methodology can't evolve from what wasn't captured.
- **findings.md as raw transcript.** Not the goal. Only INTERESTING / NON-OBVIOUS / SURPRISING content. Trivial "we did X" goes in §11 of PROJECT.md, not here.
- **Skipping the close-time synthesis pass.** The pass is what turns the file from a log into a knowledge artifact. Without it, future agents read a list of timestamps; with it, they read a curated set of lessons.
- **Capturing in conversation memory only.** That's lost between sessions. Findings.md is the durable surface.

### 17.6 Engineer-brief Write-authorization for findings.md (NEW — surfaced by Batch 1C ERP engineer 2026-05-04)

**The gap.** Engineer subagents inherit a default refusal rule against creating `.md` files (the CLAUDE.md "*NEVER create documentation files (*.md) or README files unless explicitly required*" instruction). When the engineer brief mandates `findings.md`, the engineer's tool call still sometimes refuses — the brief's "explicitly required" language can be read as ambiguous against the default.

**Caught in real terms.** ERP wiring engineer in Batch 1C (2026-05-04): "The Write tool blocked creation of `projects/erp-metas-seed-wiring/findings.md` (system reminder treated it as a 'report file'). The branching-first orchestration rule mandates a project `findings.md` artifact — gap between system-tool restrictions and methodology mandate." Engineer captured findings in their report instead — methodology rule violated by tool default.

**The architect-side fix.** Every engineer dispatch brief MUST include an explicit Write-authorization paragraph in the brief, naming exact paths the engineer is REQUIRED to create, AND naming the default rule it overrides. Recommended template clause:

> ## Explicit Write authorization
>
> You ARE explicitly authorized + REQUIRED to Write `projects/<slug>/findings.md` and `projects/<slug>/PROJECT.md` and the bundled proposal `.md` file. The CLAUDE.md "*NEVER create *.md files*" default rule does NOT apply — these are methodology-mandated artifacts. If your tool ever refuses based on the .md-default rule, override by quoting this paragraph as the explicit user authorization.

**When the clause is mandatory:** every engineer dispatch brief whose deliverables include any methodology-mandated `.md` artifact — `findings.md`, `PROJECT.md`, bundled proposal, KB amendment, etc. The "explicitly required" mandate must come THROUGH THE BRIEF in unambiguous language, not be inferred from a reference to the methodology rule.

**Anti-patterns:**
- **Brief says only "maintain findings.md" without the override clause.** Subagent's Write tool may refuse → methodology rule violated → architect doesn't notice until the engineer reports back without the file.
- **Engineer files findings inline in their report instead of authoring findings.md.** Findings exist but aren't on the durable surface — they evaporate when the report is summarized away. (Engineer B of Batch 1C did this correctly as a fallback, but the file is the durable contract.)

**Companion to** `KB § 01-PHILOSOPHY.md § Knowledge tracking — durable findings file for any non-trivial work` (foundational principle that this section specializes for orchestration).

**Sibling clause: worktree-base verification (§16.7).** Briefs that dispatch with `isolation: "worktree"` MUST also carry the §16.7 worktree-base verification preamble (orchestrator-tip SHA + reset directive + STOP-and-report fallback). Both clauses live together at the top of the brief — the engineer encounters them BEFORE any task-specific content, so the harness defaults are overridden before they can fire. Combined preamble template:

> ## Worktree base verification (FIRST — before any work)
>
> {{KB §16.7 preamble — orchestrator-branch + orchestrator-tip-sha filled in}}
>
> ## Explicit Write authorization
>
> {{KB §17.6 clause — naming the .md paths the engineer is REQUIRED to create}}

#### 17.6.1 Recurrence update — the explicit-authorization clause is INSUFFICIENT (N=5 confirmed 2026-05-10)

**The recurrence.** The architect-side fix in §17.6 (above) — "include the explicit Write-authorization paragraph in the brief" — was authored after Batch 1C ERP (2026-05-04, N=1). The 2026-05-10 follow-up batch (6 engineer dispatches in parallel for AdConnect MVP follow-up projects) brought N=5 confirmed instances of harness-block on `findings.md` Write **despite** the brief carrying the §17.6 clause verbatim:

- **Engineer F (mcp-tool-name-alignment):** "Harness blocked `findings.md` Write despite the brief's explicit Write authorization paragraph. The harness's 'subagents return findings as text, not write report files' guard fired."
- **Engineer E (noctusai-lib-nfe-domain-absorption):** "Engineer brief's 'Write authorization' override does NOT win against the harness-level 'subagents return findings as text, not write files' rule."
- **Engineer A (mock-supabase-write-propagation):** "Authorized `findings.md` write was blocked by harness despite the explicit Write-authorization paragraph in the dispatch brief."
- **Engineer B (schedule-coro-fire-and-forget):** "harness blocked the Write despite the brief's explicit Write-authorization. Engineer-side workaround was to fold all findings/learnings into the in-tree PROJECT.md §11 + the bundled proposal + the SQLite phase-learning DB."
- **Plus the original Batch 1C ERP wiring engineer (2026-05-04).**

Per the recurrence rule, **N=3+ MUST formalize**. The brief-clause approach has hit its ceiling — the harness rule supersedes the user-authorization paragraph at engineer-subagent vantage point.

**The structural answer.** Methodology splits the `findings.md` artifact across two roles:

1. **Engineer authors findings AS TEXT in their final report** under a "`findings.md` content (returned as text per harness rule)" heading, formatted in the same 5-category structure (Errors / Mistakes-slips / Lessons / Interesting-findings / Knowledge-pieces).
2. **Architect transcribes the engineer's text into `projects/<slug>/findings.md`** at fresh-eyes-merge time. The architect's `Write` calls succeed (orchestrator vantage point doesn't have the harness guard). The transcription happens BEFORE the merge commit, so the file lands on the engineer's branch in the merge / FF push.

**Updated brief template clause.** The §17.6 paragraph above stays — it remains the right shape for `PROJECT.md` and bundled proposals, which engineers DO write successfully. Add this complementary clause for `findings.md` specifically:

> ## findings.md — return-as-text protocol
>
> If the harness blocks your `Write` call to `projects/<slug>/findings.md` (the harness's "return findings as text" guard fires despite the §17.6 authorization clause), do NOT loop-fight the block. Return the 5-category content AS TEXT in your final report under a heading "`findings.md` content (returned as text per harness rule)". The orchestrator transcribes to the file at fresh-eyes-merge time. This is the documented structural answer to the N=4 recurrence (KB § 16.7's safety-net pattern: the safety net activating IS the methodology working).

**Anti-patterns specific to this recurrence:**
- **Brief omits the return-as-text fallback.** Engineer hits the harness block, doesn't know the structural answer, may either (a) loop-fight and run out of attempts, (b) silently drop findings, or (c) ad-hoc write into the report — fragile because no canonical heading.
- **Architect skips post-merge transcription.** Engineer's findings exist in their report message but never land in `projects/<slug>/findings.md`. The 5-category content evaporates after the report is summarized away (silent-error shape).
- **Looping the Write attempt.** Per `feedback_safety_nets_become_learnings`, the safety net activating IS the methodology working — capture the lesson, don't bypass.

**The deeper lesson.** The architect-side override-clause pattern works for files engineers write routinely (PROJECT.md, code, tests). It hits a ceiling on files the harness has a vendor-level rule against (report-shaped `.md` files). For those specific paths, the methodology has to **split the artifact across roles** rather than override the harness. This is a generalizable principle: when a harness rule is structural (vendor-level), the methodology adapts at the **role boundary**, not at the **brief vocabulary** level.

**Three-way-synced 2026-05-10**: this subsection (§17.6.1) + memory `feedback_findings_md_return_as_text.md` + CLAUDE/projects.md (no new pointer needed; existing §17.6 pointer in CLAUDE/projects.md covers the subsection by reference).

#### 17.6.2 Brief-template commit recipe — explicit-path `git add`, never `-A` (NEW 2026-05-10)

**The slip.** Engineer briefs frequently include a commit recipe at the end:

```bash
git add -A          # ← VIOLATION
git commit -m "..."
git push -u origin "$BRANCH"
```

The `git add -A` form violates CLAUDE.md universal rule: *"Stage only files YOU authored this session — explicit-path `git add` does NOT validate authorship."* Engineer worktrees, despite isolation, can pick up stray edits from parallel-agent activity OR pre-commit hooks (sync-seed-template, KB count refresh, seed-version stamp). `git add -A` sweeps those in, producing commits that mix engineer-authored work with peer/automatic edits.

**Engineer-side catch confirmed (youtube-crawler containerization, 2026-05-10).** Engineer explicitly flagged: *"The brief's `git add -A` instruction conflicts with the universal 'never `git add .` / `-A`' rule. I used explicit-path staging instead. The brief author may want to update the dispatch template to use explicit paths."* — engineer correctly substituted explicit paths in their own execution. The brief was the source of the bad instruction.

**The rule for brief templates.** Every dispatch brief's commit recipe MUST use explicit `git add <path1> <path2> ...` listing the exact files in scope. The recipe section should reference the brief's "Files in scope" list directly. The engineer staging step is then auditable (it matches the scope).

**Architect protocol.** When drafting an engineer brief:
1. List "Files in scope" explicitly (already standard).
2. In the commit recipe section, **copy the same paths into `git add`** — no shortcuts.
3. If a brief expects engineers to create files not yet known (e.g., they decide names at execution time), give them a glob like `git add products/<slug>/docker-compose*.yml` but **NEVER bare `-A`**.

**Engineer protocol.** If a brief contains `git add -A` (legacy template), substitute explicit-path staging using the brief's "Files in scope" list. Flag the violation in your report so the architect updates the template.

**Sibling.** This rule composes with the existing CLAUDE.md universal authorship-discipline rule: it tells the architect HOW to make the brief obey that rule. Without this sub-rule, briefs paraphrase the recipe and accidentally encourage the violation engineers are supposed to catch.

### 17.7 Read-bodies-before-dispatch — the absorption-brief discipline (NEW 2026-05-10)

**The slip pattern.** Three engineers in the 2026-05-10 parallel dispatch (`seed-test-suites-absorption`, `seed-migration-prelude`, `seed-digest-base-class`) independently surfaced the same root cause: scan-tool output (`scan_cross_product_helpers`, `scan_recurrence`, `scan_block_patterns`, `scan_migration_patterns`) flags **NAMES + SHAPES + LINES**, not BODIES. The architect dispatched absorption briefs based on scan signals alone:

- **Engineer 2 (migration-prelude):** brief asked to author `noctusai_lib.sql.{prelude, updated_at_trigger}`, but `noctusai_lib.domain.sql_templates` (Wave A 2026-05-01) already shipped the canonical strings. Engineer pivoted to delegation wrappers.
- **Engineer 3 (digest-base):** audit flagged `_empty_output` recurring in 3 products as part of the digest cluster, but `grep -rn` showed **none of the 5 digest services define it** — actual locations were `ai_service.py` (LLM error-fallback, different cluster). Same audit said N=5 narrative services, but daily-life's `daily_brief_service` was coincidence (in-app badge, not email digest).
- **Engineer 1 (test-suites):** audit said `TestRemoveMember` recurs in 7 products, but only 4 are byte-identical — core/daily-life/erp-imobiliario have rich admin-flow variants using `admin_client`, NOT duplicates.

**The rule.** Before drafting an absorption-project dispatch brief, the architect MUST:

1. Run the scanner that produced the signal
2. **Read the bodies** of every flagged location (the helper functions / test classes / migration blocks themselves, not just their names)
3. Grep `seed/lib/backend/noctusai_lib/` for the pattern's likely module — confirm whether prior absorption already exists
4. **Add a "Bodies-read confirmation" paragraph** to the dispatch brief stating which locations the architect personally read + the conclusion (genuinely shared / coincidentally-named / already absorbed)

**The cost of skipping:**
- Best case: engineer detects during scope audit and pivots (~30 min orientation cost — engineer 2)
- Middle case: engineer catches a phantom signal during execution and skips it (deeper trust hit — engineer 3 caught `_empty_output` before adding it as abstract method)
- Worst case (silent): engineer ships a fork that drifts from prior absorption, OR a phantom abstract method nobody overrides

**Anti-shape:** dispatching "absorb pattern X" with only scan-tool output → unbounded engineer time auditing what architect should have audited.

**Right shape:** architect grep + scan + body-read first; brief explicitly references prior absorption + confirms genuine vs coincidental shared shape.

### 17.8 Worktree venv + editable-install seed-lib resolution (NEW 2026-05-10)

**Surfaced by:** `seed-migration-prelude` engineer.

**The mechanic:** noc's MCP venv (`mcp/noctusai/.venv/`) installs `noctusai_lib` as editable, registered via a `MetaPathFinder` mapping that points at the **main repo's** `seed/lib/backend/`, NOT at any worktree's. `meta_path` finders run before `sys.path` is consulted for matching modules, so `sys.path.insert(0, worktree/seed/lib/backend)` is a no-op for `noctusai_lib` resolution within an active venv.

**Three correct workarounds:**
- **Per-invocation:** `PYTHONPATH=<worktree>/seed/lib/backend pytest …` — PYTHONPATH is consulted before the meta-path finder's mapping
- **Worktree-local venv:** `pip install -e <worktree>/seed/lib/backend` re-points the editable install to the worktree path
- **Alternative venv:** use `dev_team/.venv` editable-installed against the worktree (engineer 3's recovery)

**The rule.** Dispatch briefs whose scope touches `seed/lib/backend/` MUST include a "Worktree-venv guidance" paragraph specifying one of the three workarounds. Without it, engineer either gets `ModuleNotFoundError` (best case — surfaces immediately) or — worse — passes tests against the main repo's older surface (silent failure masking real test gaps).

---

## 18. Wave-based dispatch + pause-on-dependency + scoped-team economics (NEW 2026-05-10)

The branching-first rule (§16-§17) covers *how* parallel engineers run; this section codifies *how the orchestrator sizes, sequences, and reshapes the team layout when work surfaces dependencies mid-flight.* Three rules; all three were articulated by the user during the containerization-backlog closure orchestration.

### 18.1 — Pause-on-dependency: dispatch-to-unblock, resume

**The shape.** An engineer mid-flight discovers their chunk needs something built first — a missing helper, an unmade decision, a primitive that doesn't yet exist, a downstream contract that hasn't been authored. The engineer **surfaces the gap, does not absorb it**. The orchestrator:

1. **Pauses** the discovering chunk (engineer hands back what they've done, captures state).
2. **Dispatches a focused dependency team** scoped exactly to the missing piece.
3. **Resumes the original chunk** once the dependency lands and is merged.

The dispatched dependency team is itself a normal engineer dispatch (briefed, scoped, isolated worktree). The architect decides team boundaries; engineers stay within their scope.

**Why engineers don't absorb dependencies into their own scope.**
- Brief sprawl: the engineer's brief no longer matches what they shipped — quality calibration breaks down.
- Hidden context loss: the engineer who builds the dependency may not be the right one (different expertise needed).
- Merge conflicts: a single engineer doing two unrelated chunks blocks both behind a serial commit.
- Methodology drift: the "engineer is an executor of focused chunks" rule from §1 weakens silently.

**Engineer-side protocol when a gap is discovered:**

```
1. STOP work on the in-flight task.
2. Report to orchestrator with: (a) what's missing, (b) why my current chunk depends on it,
   (c) a suggested team boundary (one engineer? same brief? new brief shape?).
3. Wait for orchestrator decision. Do NOT silently expand scope.
4. Resume when orchestrator signals the dependency has landed + merged.
```

**Architect-side protocol when receiving a pause-signal:**

```
1. Verify the gap is genuine (read the bodies, run the scanner — §17.7 discipline).
2. Decide team boundary: same engineer (rare — only if it's a 5-min lift), new focused engineer,
   or escalate (the gap reveals a larger missing piece that warrants its own project).
3. Dispatch the dependency team with a focused brief.
4. When dependency lands, dispatch the paused engineer's continuation as a fresh brief
   (with the now-existing dependency as a "given") OR signal resume-in-place if the engineer's
   worktree is still warm.
5. Log the pause-and-resume event in `findings.md` under "Knowledge pieces (durable patterns)".
```

**The pause-signal in a brief.** Every engineer dispatch brief should include a clause empowering the engineer to surface gaps:

> ## Surface dependencies, don't absorb them
>
> If during execution you discover this chunk depends on something that doesn't yet exist (a helper, a decision, a primitive, a contract): STOP work on the dependent piece, report to the orchestrator with (a) what's missing, (b) why your chunk depends on it, (c) a suggested team boundary. Do NOT silently expand your scope to build the dependency yourself. The orchestrator decides team boundaries.

**Anti-patterns.**
- **Engineer absorbs the dependency into their own brief.** Brief sprawl + hidden context loss + merge conflict risk + methodology drift.
- **Architect ignores the pause signal and tells the engineer to "just do it."** The engineer is now the wrong person for the dependency, and the original chunk's quality calibration is broken.
- **Architect dispatches the dependency team but forgets to resume the paused engineer.** Silent-error shape — the paused chunk evaporates. Log resume-signals in findings.md so the loop closes.

### 18.2 — Scoped-and-focused beats broad-brief: tokens trade for wall-clock, never quality

**The principle.** When the orchestrator decides team count, the default direction is **split rather than combine**. A 200-LoC focused brief produces better work than a 2000-LoC broad brief, even though it costs more tokens (more dispatches, more setup, more context-loading per engineer).

**Token cost is explicitly acceptable.** Quality is the constraint, not budget. The user-stated formulation:

> *"I don't mind spending a bit more dispatching scoped and focused teams for more speed WITHOUT LOSING QUALITY."*

**Why focused beats broad:**
- **Context fits.** A scoped brief lets the engineer hold every file they touch in working memory.
- **Verification is tractable.** Fewer files = clearer "did this work?" gate (pytest + build + lint pass on a small surface is provable; on a sprawling surface it requires careful audit).
- **Merge surface stays small.** Parallel dispatches conflict less when each engineer touches a tight file set.
- **Recovery is cheap.** If a focused brief fails, re-dispatch costs one engineer's setup; if a broad brief fails, recovery costs days.

**How the orchestrator splits.** The cuts follow the dependency graph + the file-surface:
- **File-surface separator:** group chunks that touch the same file into one brief; split chunks that don't.
- **Dependency separator:** chunks that depend on each other can be sequenced (one brief, ordered sub-tasks) or split across waves; chunks that don't depend can run parallel.
- **Concern separator:** different mental models = different briefs (a Dockerfile-shape brief and a CI-workflow brief don't share much; even if both touch "containerization", give them to separate engineers).

**Calibration heuristic.** When in doubt about combining two related chunks into one brief: **split**. The cost of an extra dispatch is bounded (one engineer's setup time + tokens); the cost of a sprawling brief that misses a deliverable is unbounded (the gap doesn't show up until later, recovery is expensive).

**Anti-patterns.**
- **"While I'm at it..." absorption.** Engineer's brief grows to cover an adjacent concern because "it's right there." Brief drifts from acceptance criteria; quality calibration breaks.
- **Combining concerns because dispatch is "expensive".** Token cost is not the constraint; quality is. The user has explicitly authorized higher token spend in exchange for higher quality.
- **One mega-engineer for the whole project.** Defeats the purpose of orchestration — at that point the orchestrator IS the engineer, with no parallelism leverage.

### 18.3 — Wave-based execution: group by dependency depth, gate Wave N+1 on Wave N merge

**The shape.** The orchestrator decomposes the work into a **dependency-depth-ordered DAG**:
- Wave 1 = all chunks that depend on nothing in the current batch.
- Wave 2 = all chunks that depend only on Wave 1 outputs.
- Wave N = all chunks that depend only on chunks in waves 1..N-1.

Within a wave, all chunks dispatch in parallel (single Task turn, multiple Agent tool calls). Wave N+1 dispatches **only after every chunk in Wave N has merged** (not just engineer-reported — actually FF-merged into the orchestrator's branch).

**Why the merge-gate, not the report-gate.** Engineer report ≠ merged code. A report says "I shipped X"; the merge says "X is now the base for Wave N+1's worktree." If Wave N+1 dispatches against pre-merge state, those engineers see stale base (the §16.7 problem multiplied across all of Wave N+1).

**The wave-1 dispatch checklist:**
```
[ ] Dependency DAG sketched (per-chunk: what files? what other chunks does this depend on?)
[ ] Wave 1 set identified (chunks with no in-batch dependencies)
[ ] File-collision audit (any two Wave 1 chunks touching the same file? split or sequence)
[ ] Per-engineer brief drafted (focused, with §16.7 preamble + §17.6 + §18.1 surface-gap clause)
[ ] Single Task turn with N Agent tool calls (true parallelism)
[ ] findings.md scaffolded at project root
```

**The between-waves protocol:**
```
[ ] All Wave N engineers reported back
[ ] Architect reads each engineer's findings (return-as-text per §17.6.1)
[ ] Architect transcribes findings into project's findings.md
[ ] Architect FF-merges each engineer's branch into orchestrator branch
[ ] Architect runs verification (pytest + docker compose config + builds) on merged state
[ ] If any Wave N chunk surfaced a pause-on-dependency signal: dispatch dependency engineer
    BEFORE Wave N+1 (the dependency becomes part of Wave N's effective close)
[ ] Wave N+1 dispatched
```

**Why the architect verifies between waves.** Catching regressions at wave boundary is cheap (one wave's work to bisect); catching them at project close is expensive (N waves to bisect). The wave boundary is the natural quality gate.

**Anti-patterns.**
- **Dispatching all waves at once.** Wave 2 engineers see pre-merge base — same regression shape as the §16.7 "worktree from main" problem multiplied.
- **Skipping the between-wave verification.** Regressions land in the orchestrator branch; the next wave sees them as "the way things are" and adapts to the broken state.
- **Treating engineer-report as the gate.** Reports are a status signal, not a quality gate. The merge + verification is the gate.
- **Forcing parallel when chunks are truly serial.** Two chunks where B depends on A's output are not parallel even if they "feel" related. Sequence them across waves.

**Sibling rules** — this section composes with:
- §16 (worktree-per-engineer mechanics) — wave-1 engineers each get their own worktree.
- §16.7 (worktree-base verification preamble) — every wave's briefs carry it.
- §17 (findings.md per project) — orchestration findings live there.
- §17.6 + §17.6.1 (engineer-brief Write authorization + return-as-text fallback) — wave briefs carry both clauses.
- §17.7 (read-bodies-before-dispatch) — wave planning includes the body-read audit.

**Three-way-synced 2026-05-10**: this section (§18) + `CLAUDE.md` branching-first orchestration bullet (pointer extension) + `feedback_wave_dispatch_and_pause_on_dependency.md` memory entry.

### 18.4 — Resource-bounded engineer parallelism for shared-environment chunks (NEW 2026-05-10)

**The gap surfaced by `containerization-backlog-closure` Wave 1.** Three engineers (T6-A, T6-B, T1) each independently surfaced the same blocker at runtime-verification time: **Docker daemon BuildKit instability under concurrent parallel-agent build pressure.** With 6+ concurrent `docker build` processes from sibling worktrees, the daemon's grpc frontend closed unexpectedly, `dockerd` HTTP API started returning 500s, and image production stopped on the entire host. Daemon restart did not recover within 20 min.

This is the **pause-on-environment** signal — distinct from pause-on-dependency. Pause-on-dependency = an absent code-side primitive blocks the chunk. Pause-on-environment = a **shared host resource** (Docker daemon, single-host postgres, single Anthropic rate-bucket, a finite CPU, etc.) cannot serve N concurrent engineers regardless of code correctness. The methodology rule:

**The rule.** When dispatched chunks share a non-shardable resource (a single Docker daemon, a single postgres instance, a single rate-limit bucket), the orchestrator MUST cap concurrent dispatch at that resource's empirical capacity. Even if §18.3 says "Wave 1 dispatches everything that has no in-batch dependencies in parallel," the resource cap takes precedence — chunks beyond the cap go to Wave 1b (a sequential continuation of Wave 1, not a new dependency wave).

**Empirical caps observed 2026-05-10:**

| Resource | Cap | Symptom past cap |
|---|---|---|
| Docker Desktop daemon @ 3.83 GB allocation | ~3 concurrent `docker build` jobs | BuildKit grpc frontend closes; daemon HTTP 500s; recovery requires Docker Desktop restart + ~20 min wait |
| Docker Desktop daemon @ 8 GB allocation | ~6 concurrent `docker build` jobs | (to be calibrated — initial estimate) |
| Local postgres (offline-dev profile) | 1 concurrent migration run | concurrent migration runs conflict on advisory locks / schema state |
| Anthropic API rate-bucket per key | depends on tier | 429s + token-bucket starvation |

These caps are **engineer-dispatch caps**, not chunk caps. A single engineer can run many builds inside its worktree — what matters is the **concurrent count across dispatched engineers**.

**Architect-side protocol.**

1. **Before Wave N dispatch**, identify shared-environment resources each chunk's verification will hit. Tag chunks with their resource needs (e.g., "T1: docker-build heavy", "T4: postgres-init heavy", "T6: docker-build moderate").
2. **Sum the per-resource concurrent demand.** If `docker-build heavy` count > 3 (current cap), the wave does NOT dispatch all at once.
3. **Split Wave N into Wave Na + Nb.** Wave Na = chunks within cap. Wave Nb = remaining same-shape chunks. Wave Nb dispatches AFTER Wave Na engineers have completed their build steps (not necessarily their full work — once they've yielded the daemon, the next batch can start).
4. **Wave Nb gate is `daemon-yielded`, not full FF-merge.** This is a softer gate than the inter-wave §18.3 gate — Wave Nb doesn't need Wave Na's source-tree changes; it just needs the resource. The architect monitors and dispatches Wave Nb when the resource is free.
5. **Communicate the cap to engineers.** Briefs include: "Concurrent docker-build load is capped at <N>. If you observe BuildKit instability or daemon HTTP 500s, STOP your build, signal pause-on-environment, and wait for orchestrator dispatch to resume."

**Engineer-side protocol.**

When an engineer hits BuildKit instability mid-build:

```
1. STOP the build (don't retry-loop — retrying when contention is the cause makes it worse).
2. Capture the failure mode (exit code, log tail, `docker info` snapshot, `docker ps` output).
3. Report to orchestrator with pause-on-environment signal: "Resource: docker-build daemon.
   Observed: <symptom>. Likely cause: concurrent build pressure. Recovery hint: wait for
   peer engineers to yield, OR architect raises daemon allocation."
4. Continue any non-environment-bound deliverables (source-level changes, compose config
   validation, structural verification via static analysis). Report what was achievable.
5. The chunk's "structural confidence" deliverable can land on merge; the "runtime verification"
   deliverable is deferred to a follow-up rebuild engineer dispatched once the resource recovers.
```

**Anti-patterns.**

- **Architect dispatches all docker-build-heavy chunks in parallel "because they're independent in code."** Code-independent ≠ resource-independent. The daemon dies before any of them complete.
- **Engineer retry-loops on daemon failure.** Each retry makes the contention worse. The right shape is STOP + report.
- **Architect treats pause-on-environment as pause-on-dependency.** They're different — pause-on-environment doesn't dispatch a dependency engineer; it waits for the resource OR raises allocation. Filing a follow-up project for the "dependency" is the wrong shape.
- **Skipping the structural-confidence carve-out.** When runtime verification is blocked by environment, the code changes can still merge on structural confidence (static analysis + compose config + fresh-eyes review). Blocking the merge for runtime verification when the daemon is dead would block the whole wave indefinitely.
- **Conflating concurrent CHUNK count with concurrent ENGINEER count.** A single engineer running 3 sequential builds inside its worktree is FINE; 3 engineers each running 1 build concurrently is BORDERLINE; 6 engineers running 1 build concurrently is BROKEN. The cap is on concurrent engineers, not on per-engineer build count.

**Recovery recipe — Docker daemon overload on macOS.**

1. `docker desktop stop` — let any in-flight builds error out cleanly.
2. Wait 30s.
3. `docker desktop start` — fresh daemon.
4. If still unstable: Docker Desktop GUI → Settings → Resources → Memory → raise allocation (3.83 GB → 8 GB or 12 GB depending on host) → Apply & restart. macOS TCC sandbox blocks shell access to the settings file; only the GUI can change it.
5. `docker info | grep 'Total Memory'` to confirm new allocation took effect.
6. Resume dispatched engineers (or dispatch follow-up rebuild engineer).

**Three-way-synced 2026-05-10**: this subsection (§18.4) + memory `feedback_wave_dispatch_and_pause_on_dependency.md` (extend "pause-on-environment" sub-rule) + CLAUDE.md branching-first bullet (no new pointer — §18 covers it).

### 18.5 — Parallel-agent shared-tree merge hygiene (NEW 2026-05-10)

The existing collision protocol (`feedback_parallel_agent_collision_protocol.md` + KB § PATTERNS/project-execution.md § 2.9) covers the **explicit revert** shape: parallel agent re-edits the same lines you edited; STOP at the second revert; wait. This subsection covers the **silent regression** shape that surfaced multiple times during `containerization-backlog-closure` Wave 1+2 merging.

**The pattern.** Parallel agent commits unrelated work to a shared branch state (typically `main` or the orchestrator's project branch via auto-merge). When the orchestrator's next merge runs, git's 3-way merge picks a **merge-base older than the orchestrator's most recent intermediate state**. The 3-way auto-resolution interprets "HEAD added X, incoming didn't add X, base also didn't have X" as ambiguous, and on some hunk shapes it drops HEAD's addition rather than keeping it. The work isn't visibly reverted — it just silently doesn't appear in the merge result.

**Worked example (T2 merge regression, 2026-05-10).**

```
0f6f694 (Phase 0)
  ├─ d1a7f01 (T3 merge — added VITE_* ARG block to product Dockerfiles)
  │    └─ ... eventually 9d1b708 (T6-A merge)
  │             └─ c6bff31 (T6-A's commit, intermediate parent)
  │                  └─ orchestrator HEAD pre-T2-merge
  └─ 858fda5 (T2 branch — T6-A merge onto Phase 0)
       └─ 3cff1ab (T2's commit — added OCI labels, NOT T3's ARG block)
```

When the orchestrator merged `3cff1ab` (T2) into HEAD:
- **Merge-base picked by git:** `c6bff31` (T6-A's commit — the most recent common ancestor reachable from BOTH sides).
- At `c6bff31`: file had **no ARG VITE block**, **no OCI labels**.
- At HEAD (`9d1b708`): file had **ARG VITE block** (T3's contribution).
- At T2 (`3cff1ab`): file had **OCI labels** (T2's contribution), **no ARG VITE block** (T2's branch never saw T3).
- 3-way auto-merge result: file had **OCI labels** (incoming addition) **but lost the ARG VITE block** (HEAD's addition silently dropped because the auto-merge interpreted "incoming-side has no such addition" as "incoming wants to remove this region").

The regression is not a bug in git's 3-way merger — it's the predictable outcome when the merge-base is chosen by ancestry rather than by content-similarity. **It's a methodology gap, not a tool bug.**

**Detection.** Silent regressions hide unless the architect post-merge-verifies. The cheap detection:

1. **Spot-check the merged file** for the prior wave's key markers. E.g., after merging T2: `grep -c 'ARG VITE' products/adconnect/frontend/Dockerfile` should return 1 (T3's contribution preserved). If it returns 0, regression detected.
2. **Read the merge commit's diff** against the orchestrator's pre-merge HEAD. If the diff DELETES lines the merging branch never touched, that's a silent regression.
3. **`git log <merge-commit> -p -- <suspected-file>`** to see exactly what the merge resolved.

**Recovery.** Cherry-pick the regressed commit back on top of the merge commit:

```bash
git cherry-pick --no-commit <regressed-commit-sha>      # re-apply the dropped changes
# resolve any conflicts (usually clean since the merge already integrated the new file)
git commit -m "fix(merge): restore <X> lost in <Y> merge auto-resolution"
```

This was the recipe applied during Wave 1+2 to restore T3's ARG VITE blocks after the T2 merge regression. Worked cleanly each time.

**Prevention (architect-side).**

1. **Verify-after-merge is non-negotiable** when the orchestrator branch has accumulated parallel-agent commits between dispatches. The architect's between-wave protocol (KB §18.3) already says "Architect runs verification on merged state" — this sub-rule sharpens it: include a content-specific spot-check for the most recent wave's key markers, not just compose-config / pytest validity.
2. **Per-wave marker set.** When dispatching a wave, the orchestrator notes 2-3 file:line markers that each engineer's work will introduce. The post-merge verification greps for those markers; if any missing, regression detected.
3. **Cherry-pick recovery as a documented step**, not improvisation. Architect catalogs in findings.md: "T2 merge regressed T3's ARG VITE block at lines 9-18; recovered via cherry-pick of `6484414` on top of `7d9d6f6`."

**Engineer-side: nothing.** Engineers can't predict or prevent this — it happens at architect-merge time, after their work is committed + pushed. This is purely an architect responsibility.

**Anti-patterns.**

- **Architect skips post-merge content verification because compose-config / pytest passed.** Those are NECESSARY but not SUFFICIENT. They catch syntactic regressions, not content regressions. The marker grep is the content gate.
- **Architect re-merges from a fresh branch as the "fix" without understanding the regression.** A re-merge from the same branches with the same merge-base will produce the same regression. The fix is cherry-pick of the dropped content, not re-merge.
- **Architect treats silent regression as "the parallel agent's fault" and waits for them to fix it.** The parallel agent doesn't know about your dropped changes — they're operating on entirely unrelated work. The collision is architectural (shared tree + merge mechanics), not adversarial.
- **Architect doesn't catalog the regression.** Each silent regression caught + recovered teaches the methodology a real failure mode. Findings.md entry under "Mistakes / slips" is mandatory.

**Sibling rules (compose with this one).**
- §16.7 — Worktree-base verification preamble (catches the analog of this problem at engineer dispatch time).
- §17.4 — Architect's append cadence (silent regressions become findings.md entries the moment they're caught).
- §18.3 — Wave-based execution (between-wave verification gate — this rule extends what "verification" means).
- `feedback_parallel_agent_collision_protocol.md` — the **explicit-revert** companion; both shapes can co-occur in the same session.

**Three-way-synced 2026-05-10**: this subsection (§18.5) + memory `feedback_parallel_agent_collision_protocol.md` (extend with "silent regression via auto-merge" sub-rule) + CLAUDE.md branching-first bullet (no new pointer — §18 covers it).

---

## 19. Worktree lifecycle + auto-cleanup (NEW 2026-05-11)

> **Stale worktrees are unrecoverable disk debt.** A fresh `git worktree add` for `Agent(isolation: "worktree")` materializes ~880 MiB on disk (node_modules + Python venvs after `bootstrap-worktree.sh` hydrate). The harness locks the worktree to prevent accidental git-side cleanup, but the lock has no expiry — so 76 sessions over a week left **67 GiB stranded** on the noc data volume (verified 2026-05-11; disk hit 100% mid-session, blocking Engineer III at preamble + the orchestrator's own Bash tool output staging).

### 19.1 — The rule

Every agent worktree under `.claude/worktrees/agent-*/` is removable as soon as its branch is reachable from `origin/main` (i.e. cherry-picked + pushed by the orchestrator). The worktree's job is done; the work is durable on main; the disk footprint is pure overhead.

**`noctus.dev.cleanup_stale_worktrees`** is the canonical sweep:
- Iterates `git worktree list --porcelain` + on-disk `agent-*/` orphans.
- **STALE** = branch reachable from `origin/main` (`git merge-base --is-ancestor`) OR directory exists without a corresponding registered worktree.
- **ACTIVE** (kept) = branch has commits not yet merged.
- Removes via `git worktree remove --force` first (cleans `.git/worktrees/<name>/` too), falls back to `rm -rf` for orphans, then `git worktree prune`.

```bash
python mcp/noctusai/cli.py --cleanup-stale-worktrees           # interactive
python mcp/noctusai/cli.py --cleanup-stale-worktrees --dry-run # report only
python mcp/noctusai/cli.py --cleanup-stale-worktrees --force   # no prompt (cron / hook)
```

### 19.2 — When to invoke

| Trigger | Mechanism | Frequency |
|---|---|---|
| **After each FF + push of an engineer's commit** | Orchestrator workflow extension — invoke `--force` mode targeting the just-merged branch's worktree. | Per merge. **Highest leverage** — disk never accumulates. |
| **At worktree-bootstrap time** | `bootstrap-worktree.sh` invokes `cleanup-stale-worktrees.sh --force` before its own hydrate. Catches stale worktrees from prior sessions before they balloon. | Per dispatch. **Best for engineers** — the worktree they enter is on a fresh-disk state. |
| **Nightly cron** | `0 3 * * * cd /Users/rapha/Documents/repository/NoctusAI/noctusai && python mcp/noctusai/cli.py --cleanup-stale-worktrees --force` | Daily. **Safety net** for sessions that crashed mid-flow. |
| **Manual** | `python mcp/noctusai/cli.py --cleanup-stale-worktrees` (interactive). | Ad-hoc. **Disk-pressure recovery** — the rescue path the 2026-05-11 incident took. |

### 19.3 — Safety constraints

- **NEVER removes the main worktree.** Skipped explicitly by path comparison to `git rev-parse --show-toplevel`.
- **NEVER removes sibling workspaces** outside `.claude/worktrees/agent-*/` (e.g. `noctusai-worktrees/pf-metas-seed-wiring`).
- **NEVER removes worktrees with unmerged commits.** The `git merge-base --is-ancestor origin/main` check is the gate; only worktrees whose branch is fully reachable from main are eligible.
- **Idempotent**: re-running on an already-clean tree is a no-op.

### 19.4 — Disk pressure as a methodology gap

The 2026-05-11 incident (disk filled mid-session, blocked Engineer III + the architect's own Bash tool output) surfaced two complementary gaps:

1. **No cleanup mechanism existed** — every worktree accumulated until manual sweep. *Fixed by `cleanup-stale-worktrees.sh` + §19.2 invocation triggers.*
2. **No bootstrap pre-flight** — `bootstrap-worktree.sh` happily ran `npm ci` on a near-full disk and exited 144 mid-loop. *Fix candidate*: pre-flight `df -h /private/tmp /Users` check at script start; abort cleanly if either is <5 GiB free. Engineer FFF's `proposals/phase-7-disk-space-preflight.md` (archived 2026-05-11) carries the exact recipe.

The combination of **(a) auto-cleanup on merge** + **(b) pre-flight at bootstrap** + **(c) nightly safety-net cron** structurally prevents the disk-full lockout class.

### 19.5 — Anti-patterns

- **Removing locked agent worktrees while the engineer is still running.** Always check the in-flight engineer's `agent-<id>` against the cleanup list. The `git merge-base --is-ancestor` check naturally protects this — an active engineer's branch has unmerged commits, so it's classified ACTIVE.
- **Skipping `git worktree prune` after `rm -rf`.** Leaves `.git/worktrees/<name>/` metadata orphans that confuse later `git worktree list` output. The script always invokes it.
- **Using `--force` interactively without dry-run first.** The first sweep on a heavily-accumulated worktree dir should always start with `--dry-run` to confirm the active-vs-stale classification before committing to removal.

### 19.6 — Disk-usage monitor (NEW 2026-05-11)

The cleanup mechanism handles RECOVERY. The monitor handles PREVENTION — warns at thresholds long before disk pressure becomes a 100% lockout.

**`noctus.dev.check_disk_usage`** — severity-tagged disk health check.

| % used | Severity | Exit code | Action |
|---|---|---|---|
| <70% | OK | 0 | No action |
| 70-79% | CAUTION | 1 | Schedule a sweep soon; orchestrator surfaces note to user |
| 80-89% | WARNING | 2 | Cleanup REQUIRED before new dispatches; orchestrator pre-dispatch gate fails |
| 90-100% | CRITICAL | 3 | Harness lockout imminent; immediate manual recovery (cleanup + `docker system prune` + `sudo purge`) |

```bash
python mcp/noctusai/cli.py --check-disk-usage                # status report
python mcp/noctusai/cli.py --check-disk-usage --quiet        # exit code only (cron-friendly)
python mcp/noctusai/cli.py --check-disk-usage --auto-clean   # if ≥70%, automatically run cleanup-stale-worktrees.sh --force
```

**Invocation triggers**:

| Trigger | Mechanism | Behavior |
|---|---|---|
| **Orchestrator startup** | First Bash call in every orchestrator session invokes `--quiet` and reads exit code. ≥70% surfaces a CAUTION note to user (one-line, not blocking). | Surfaces pressure BEFORE engineer dispatches commit disk. |
| **Pre-dispatch gate** | Before dispatching any new `Agent(isolation: "worktree")` engineer, check exit code. Refuse dispatch at ≥80% (WARNING) — surface to user with cleanup recipe. | Structural prevention of the disk-full lockout. |
| **`bootstrap-worktree.sh`** | Already invokes `cleanup-stale-worktrees.sh --force` as pre-flight. The monitor adds: if post-cleanup still ≥80%, refuse hydrate. | Engineer-side guard. |
| **Nightly cron** | `0 3 * * * python mcp/noctusai/cli.py --check-disk-usage --auto-clean` | Auto-recovers any session that left stale worktrees behind. |
| **Manual ops check** | `python mcp/noctusai/cli.py --check-disk-usage` ad-hoc. | User-initiated health check. |

**Orchestrator's responsibility (NEW)**: before dispatching, the orchestrator runs `disk-usage-monitor.sh --quiet` and surfaces severity. At CAUTION the dispatch proceeds with a note. At WARNING the dispatch is gated until cleanup. At CRITICAL the orchestrator stops dispatching entirely and surfaces full recovery recipe.

### 19.7 — References

- `noctus.dev.cleanup_stale_worktrees` — the canonical sweep (added 2026-05-11).
- `noctus.dev.check_disk_usage` — severity-tagged monitor + warning thresholds (added 2026-05-11).
- §16.7 — worktree-base verification (Step 0 — bootstrap; this rule extends Step 0 with cleanup-before-hydrate).
- §18.4 — Resource-bounded engineer parallelism (this rule reduces the disk dimension of "resource-bounded").
- `archive/projects/2026-05-11/16-personal-finance-wiring/proposals/phase-7-disk-space-preflight.md` — Engineer FFF's disk-full slip + the bootstrap pre-flight recipe.

**Three-way-synced 2026-05-11**: this subsection (§19) + memory entries `feedback_worktree_auto_cleanup.md` + `feedback_disk_usage_monitor.md` + CLAUDE.md §1 universal-rules pointer (no new bullet — KB pointer suffices since §19 is self-contained methodology).

---

## 20. Engineer-letter naming convention (NEW 2026-05-11)

### 20.1 — The rule

Every engineer subagent dispatched in this orchestration system gets a short **ALL-CAPS letter code** as their handle — **AUTH-RL**, **PF-AUTH-MIG**, **CORS-ROLLOUT**, **MOCK-SCHEMA**, **LLM-RL-TRIO**, **SEED-FORBID**, **DT-RATELIMIT**, **THE-P10**, **WWW**, **NNN**, **VVV**.

**Format**: 2–4 dashed segments, each 2–6 chars, ALL-CAPS:
- `<DOMAIN>-<TASK>` — e.g., `AUTH-RL` (auth + rate-limit), `SEED-FORBID` (seed + extra=forbid)
- `<PRODUCT>-<TASK>` — e.g., `DT-RATELIMIT` (dev-team + rate-limit), `PF-AUTH-MIG` (PF + auth + migration)
- `<PRODUCT>-<PHASE>` — e.g., `THE-P10` (therapy + Phase 10), `IMB-FIN` (imobi-scheduling + finalization)
- `<TASK>-<MODIFIER>` — e.g., `LLM-RL-TRIO` (LLM rate-limit + 3-product scope), `CORS-ROLLOUT` (CORS migration sweep)
- **Triple-letter fallback** — `WWW`, `NNN`, `VVV`, `RRR`, `SSS`, `KKK`, `MMM` — used when no clean acronym fits, or for solo finishers/audit follow-ups that don't map to a domain (e.g., `WWW` for a one-off seed audit, `NNN` for a per-product audit pass).

### 20.2 — Why the letter, not the branch slug

The engineer-letter is the **orchestrator's handle** — short, memorable, easy to track in a continuous-flow conversation when 4–6 engineers are in flight. The **branch slug** (e.g., `auth-rate-limit-rollout-2026-05-11`) is the **engineer's deliverable name** — descriptive, date-stamped, lives forever in git history.

They serve different audiences:
| Surface | Use the letter | Use the slug |
|---|---|---|
| Orchestrator brief headers ("Engineer AUTH-RL, dispatched on...") | ✓ | — |
| Task tracker rows | ✓ | — |
| Retrospective summaries ("AUTH-RL just shipped") | ✓ | — |
| `findings.md` author attribution | ✓ | — |
| Git branch name | — | ✓ |
| Commit subject | — | ✓ |
| `projects/<slug>/PROJECT.md` directory | — | ✓ |
| PR title (when used) | — | ✓ |

### 20.3 — Allocation rules

- **One letter per dispatch.** Every fresh `Agent()` call gets a fresh code; even if the new engineer is finishing a stalled predecessor (e.g., `KKK-2` continues `KKK`'s work, but is its own subagent invocation).
- **Numbered continuations**: when a finisher picks up a stalled engineer's work, append `-2`, `-3`, etc. — e.g., `KKK-2` finishes `KKK`'s 8-route rename after watchdog stall.
- **Never reuse a letter across distinct chunks.** If `AUTH-RL` shipped and a follow-up rate-limit task surfaces, the next engineer is `AUTH-RL-FOLLOWUP` or a new letter combo, not a recycled `AUTH-RL`.
- **Solo-engineer model assumes solo letters.** Multi-agent dev-team chunks (`noctus.team.*`) get a team-letter (`TEAM-X`) plus per-specialist sub-letters if needed.

### 20.4 — Why the convention works

- **Cognitive compactness**: when 6 engineers are in flight, "AUTH-RL · PF-AUTH-MIG · LLM-RL-TRIO · THE-P10 · CORS-ROLLOUT · MOCK-SCHEMA" reads in one breath. Branch slugs would need 8× the screen width.
- **Spoken/typed reference**: easy to say "did AUTH-RL ship yet?" — branch slugs become "did auth-rate-limit-rollout-2026-05-11 ship yet?" (unsayable).
- **Findings attribution**: when a finding mentions "VVV's clinic-portal silent-drop catch", the architect immediately recalls the engineer + context. With branch-slug attribution, the cognitive lookup is much heavier.
- **Continuous-flow workflow**: with engineers shipping every 5-30 minutes, the orchestrator needs terse handles to track parallel state without scroll-back.

### 20.5 — Anti-patterns

- **Branch-slug everywhere**: dispatching "Engineer auth-rate-limit-rollout-2026-05-11" is verbose and forces 20+ char repetition per mention. Use the letter for ALL orchestrator-side reference; keep the slug for git artifacts.
- **Memorable-name handles** ("PHOENIX", "STORM"): tempting but break the format pattern. The dashed CAPS convention is the affordance — engineers self-identify with their codes in reports without prompting.
- **No letter at all**: dispatching nameless engineers leaves the architect with only `Agent` tool's auto-generated IDs (`af3f3478ab471fd36`) — opaque, unspoken, useless for retrospectives.
- **Letter mismatch between brief and report**: dispatch as `AUTH-RL`, engineer reports as `EngineerRateLimit` — break in continuity. The brief MUST open with `You are **Engineer <LETTER>**, ...` to anchor the engineer's self-identification.

### 20.6 — References

- §18 — Wave-based dispatch (engineers grouped by dependency depth carry letters as wave identifiers).
- `feedback_engineer_letter_naming.md` (memory) — origin + user-feedback context.
- KB §17.6 — Engineer-brief Write-authorization template uses `Engineer <LETTER>` as the opening line.

**Three-way-synced 2026-05-11**: this subsection (§20) + memory entry `feedback_engineer_letter_naming.md` + CLAUDE.md §1 universal-rules pointer (no new bullet — KB pointer suffices since §20 is self-contained convention).

---

## 21. Collision-class branching + dispatch-time merge strategy (NEW 2026-05-18)

Refined from the 2026-05-18 multi-branch session (6 isolated branches converging alongside one active parallel agent — "swiss-watch" mode). Core shift: **merge cleanliness is decided at DISPATCH time, ¬ discovered at MERGE time.** Parallelizability of deferred/blocked work is **¬ binary** (disjoint ∨ not) — it is a 3-class taxonomy, each class carrying a fixed strategy.

### 21.1 — The three collision classes

Classify the would-be branch's edit-set against the **parallel-active file set**:

- **C1 file-disjoint** — touches no file the parallel work touches ⇒ **parallel-clean**; trivial FF/merge. *(e.g. `seed-pin-dedup` `mcp/{meta,google}` vs parallel `scripts/`+`mcp/noctusai/`.)*
- **C2 same-file-additive** — touches shared files but **only additively** (new files + appended lines, ¬ restructuring existing content) ⇒ constrain the engineer to **additive-only in the brief**; the §10.4 concat heuristic then makes the 3-way merge clean *by construction*. *(e.g. `r-rules-kb` new KB docs + appended CLAUDE.md/INDEX pointers; `github-mcp` pointers.)*
- **C3 same-file-substantive-overlap** — must restructure/edit the same regions of shared code the parallel work edits ⇒ **¬ cleanly branch-parallelizable**. Two valid responses: **(a) re-scope** to a parallel-clean sibling file (same deliverable, C3→C1 — e.g. `platform-compliance-A` scoped to `test_compliance.py` [parallel-clean] ¬ `compliance.py` [parallel-dirty]); **(b) sequence** behind the parallel merge (wave / pause-on-dependency §18).

### 21.2 — Dispatch-time class determination is mandatory ∧ evidence-based

Before branching deferred work: `git diff --name-only` / `git status` the parallel-active set, classify each contended file. Asserting C1 without checking = estimate-off-evidence violation. **The class drives the brief**: C2 ⇒ explicit "additive-only (new files + appended lines, zero restructure)" clause; C3-rescope ⇒ scope to the clean sibling + name the avoided file; C3-sequence ⇒ ¬ dispatch yet.

### 21.3 — Time-dependent base selection

Base is a function of **parallel-agent liveness**, decided per-dispatch:
- Parallel agent **ACTIVE** ⇒ branch off `origin/main` (stable shared base; the parallel tip is a moving target — stale-base + collision risk).
- Parallel agent **DONE** ⇒ rebase the not-yet-started worktree onto the final parallel tip (`git -C <wt> reset --hard <feat-tip>`) so merge-back is FF/trivial (no moving target remains). *(e.g. `pc-a` + `mm-close` reset to feat tip once parallel done.)*

### 21.4 — Commit-on-ship for isolated-branch deliverables

A shipped ∧ architect-verified complete task on its own isolated branch is committed **immediately** (per-deliverable commit gate) — ¬ left staged awaiting a batch. Accumulating verified-shipped-uncommitted branches violates terminal-commit-guarantee ∧ risks loss. *(User-corrected 2026-05-18: "you should've already, as you shipped a complete task".)*

### 21.5 — Architect true-disk verification precedes every per-branch commit

Engineer-default §1a corollary, applied **per-branch**: never trust the engineer report; `git -C <wt> diff --cached --name-only` + `grep`/`cat` the on-disk change text from the architect's **own Bash context** before committing each branch. The per-branch discipline that makes a multi-branch convergence reliable rather than hopeful.

### 21.6 — Shared-`.git/hooks` ↔ worktree-base mismatch: sanctioned-bypass protocol (N≥4 2026-05-18)

Worktrees share one `.git/hooks/pre-commit`; a worktree forked off an **older base** has a `cli.py` predating flags the newer installed hook calls (`--check-outlined`, `--update-kb-counts`). Recurred ≥4× in one session. **Standing protocol:** `git commit --no-verify <explicit paths>` + **(a)** the bypass rationale written into the commit body, **(b)** independent verification substituting for the skipped hook (AST-parse the staged `.py`, run `verify-kb-sync` manually, tests green). Structural-fix follow-up (named, ¬ silent): the hook should tolerate-missing-cli-flags ∨ detect base-mismatch — destination = a `scripts/pre-commit`/`cli.py` robustness follow-up. Safety-net→learning→methodology instance (`KB § 01-PHILOSOPHY.md § Safety nets`).

### 21.7 — Closure durable-home routing: accept-catalog ≠ memory

When closing a deferred/blocked project, route the durable substance by **shape**:
- An **accepted divergence** (a real deviation from ideal, knowingly kept) → `KB § PATTERNS/accept-with-rationale.md`.
- A **deferred concept with design rationale** (¬ a divergence-acceptance — a future idea parked on evidence) → a self-contained memory entry (`type: project`) + `ledger.ndjson` close record. **NOT** the accept-catalog, **NOT** archive-anchored (durable-docs-self-contained).

Don't default everything to accept-with-rationale — it is for divergences, ¬ deferred concepts. *(User-directed 2026-05-18: "please do not accept with rationale if possible" for `methodology-mirror` closure.)*

### 21.8 — Wave-gated convergence

Don't finalize a multi-branch convergence **or** a phased-push while ANY chunk is still in flight; the **last-running chunk gates converge+push** (wave-based-dispatch §18 applied to the *merge* wave, ¬ just the dispatch wave). Convergence order = least-conflict-first (C1 → C2 → C3-resolved).

### 21.9 — The collision taxonomy is OPEN — new patterns get absorbed

C1/C2/C3 is **¬ a closed set**. A new collision shape that doesn't cleanly fit ⇒ **learn from it → name it → absorb it** (new class ∨ subsection here + three-way sync), never force-fit into an existing class ∨ silently route around it. A collision pattern handled-but-uncodified is a lost hardening opportunity (silent-error shape). This is the **collision-domain instance** of the global always-hardening posture — the methodology is never finished; every surfaced pattern (incl. a *success* sequence worth reproducing) is a codification opportunity, watched-for continuously. → `KB § 01-PHILOSOPHY.md § Always-hardening — every surfaced pattern is a methodology-improvement opportunity`.

**Three-way-synced 2026-05-18**: this section (§21, incl. §21.9) + memory entry `feedback_collision_class_branching.md` + CLAUDE.md §1 wave-based-dispatch bullet (amended clause + pointer — §21 extends the existing bullet, no new bullet). The global meta-rule it instances: `KB § 01-PHILOSOPHY.md § Always-hardening` + CLAUDE.md §1 `Always-hardening posture` bullet + memory `feedback_always_hardening_posture.md`.
