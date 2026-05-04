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

---

## 12. Orchestrator vs working-agent role split

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

**Mental model:** `work1 + work2 = work1+2` is the desired outcome. Without merging, you get `work2` (second-write-wins). With merging, you get the union. The merging methodology (§10 TBD) covers the conflict-resolution case; this section covers the proactive coordination.

**Cost.** ~5 seconds of fetch + scan at agent startup. Mandatory for branched work; recommended for direct-to-main work touching shared files.

**Companion to.** `feedback_parallel_agent_collision_protocol.md` (the after-the-fact "STOP, wait, continue" protocol when collisions DO happen). The pre-work fetch protocol is the proactive complement: catch them before they happen.
