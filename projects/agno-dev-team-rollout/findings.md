# findings.md — agno-dev-team-rollout

> **Purpose.** What we LEARNED, curated. Per `feedback_knowledge_tracking`. Five categories. Append in-the-moment for surprises (freshness matters); synthesize at close into a curated knowledge artifact.
>
> **Distinct from:**
> - `phase_learnings.db` (atomic per-phase learnings via `noctus.dev.phase_learning_*`)
> - `live-patterns-log.md` (master-tree per-batch raw log of code findings)
> - `PROJECT.md §11` (what-we-DID change log)
>
> **This file** is what-we-LEARNED, curated.

## 1. Errors (things that broke + root cause)

_(empty — append as they happen)_

## 2. Mistakes / slips (things we did wrong + corrective)

- **2026-05-04 — Branch rename collided with parallel-agent activity.** First `git branch -m` was issued without first switching to the target branch + while a parallel agent was simultaneously checking out / committing on the project branch (which they had themselves renamed `agno-dev-team-future-direction` between my `checkout -b` and my next command). Net effect: I ended up on `main` with the staged folder rename, before recovering by switching to `agno-dev-team-rollout`. **Lesson:** the pre-work fetch protocol (`KB § PATTERNS/branching-and-merging.md § 14`) doesn't fully cover branch-name collision when a parallel agent picks the same intuitive name; always `git branch --show-current` before chained git operations.

## 3. Lessons (methodology refinements proven by this work)

- **2026-05-04 — Master-tree pattern fits parallel-engineer dispatch even for single-deliverable decompositions, with explicit fit-declaration.** The KB pattern's "single-product = don't use" rule is correct for the FULL bureaucracy (6 child PROJECT.md files), but the MECHANICS (live-patterns-log, parallel dispatch in single tool-use turn, sync-gates) are valuable independent of product count. This rollout uses adapted master-tree (mechanics yes, child-project bureaucracy no) and declares the adaptation explicitly in §3 of PROJECT.md so a future agent doesn't get confused. **Pending closure** — confirm at B5 whether the adaptation actually delivered speed.

## 4. Interesting findings (non-actionable but worth noting)

_(empty — append as they happen)_

## 5. Knowledge pieces (durable references for future agents)

- **2026-05-04 — agno is the framework. The "team" is OUR composition.** agno provides `Agent`, `Team` (with `mode='coordinate'` / `'collaborate'`), tool-call infrastructure, and provider routing. The 11-specialist topology + sub-teams + per-agent allowlists are NOT agno features — they're our composition on top. Future agents touching `dev_team/` should mentally separate "agno gives us X" from "we built Y."
