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

**Why merging matters (the second-class problem branching alone doesn't solve).** Branching prevents **authorship-violation pushing** (you'd push another agent's commits along with yours because they sit in your unpushed range). Merging prevents **same-line content overwriting** (agent A writes line 50, agent B writes a different version of line 50 — without merging, second-write-wins silently destroys first-write). Both are real failure modes. Branching is the today-shipped half; merging is the wish. Auto-merge handles non-conflicting changes (different files, different lines) — `work1 + work2 = work1+2` works automatically there. Same-line conflicts require resolution discipline, which is what the merging methodology will codify.

Until then: when fast-forward push fails (§4.2), STOP and surface to the user. Do not attempt manual merging without methodology support — it is the highest-risk git operation we run, and ad-hoc resolution is how merge bugs and lost commits happen.

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
