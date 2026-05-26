# Drift-fix-on-contact — pause, resolve, surface-if-blocked, continue

**The rule.** When you bump into **drift** — git leftovers, broken methodology pointers, stale dispatcher entries, half-applied edits, an orphan branch, an artifact in the wrong place — you **pause, resolve in-flight, surface if blocked, update the docs the resolution touches, then continue the paused work**. Silent-skip = silent error. Codified 2026-05-26 after the recurring git-leftovers pattern persisted despite existing keepers.

**Why.** The user's prior framing was honest: *"We've been through this a thousand times and I still couldn't fix it."* Existing keepers (`check_branch_orphan`, `check_dispatcher_staleness`, `check_archive_staleness`, `check_clean_folder_violations`) catch drift **at commit gates** — but drift accumulates **between gates**, mid-session, where the existing rule "no silent errors" was too generic to fire on git-shape drift specifically. This pattern names the shape, names the drill, and adds the missing gate.

This composes with — does **NOT** replace — [[fix-on-contact for pre-existing debt]] (the broader rule for code/methodology debt). Git-leftovers + methodology-pointer drift are subspecies of the same instinct: **silent-skip is forbidden; on-contact resolution is mandatory**.

## What counts as drift (the trigger set)

The rule fires when, during ANY task, you observe:

### Git-shape drift
- **Untracked at repo root** (excluding allowlist: `.env*`, `.claude/cache/`, `node_modules/`, IDE folders, anything in `.gitignore`). A `decision.md` paste, a `notes.md` scratch, a stray `.patch` file ⇒ drift.
- **Local branches diverged from origin** without an active project folder OR an open in-flight worktree. Stale `feat/*` from a closed project ⇒ drift.
- **`.claude/worktrees/<x>/` with uncommitted state** when the architect doesn't recognize it as in-flight ⇒ drift.
- **Pushed-but-never-merged branches** older than 7 days with no active project ⇒ drift (likely abandoned; needs salvage-or-delete).
- **Peer-tree residue** — primary checkout shows changes you didn't author (KB-autostage-hook absorbed peer work, half-finished merge) ⇒ drift.

### Methodology-pointer drift
- **A `KB § …` pointer that 404s** when an agent or tool tries to follow it.
- **A KB doc under owned territory without an agent-body pointer** (caught by `check_agent_kb_alignment` at commit; on-contact resolution still applies if found mid-session).
- **A `[[name]]` link with no target memory** (per `check_memory_md_index`).
- **A CLAUDE.md §1 line whose `→` pointer has no body.**

### Process drift
- **Dispatcher inbox entries** marked `in-progress` with no live executor (`check_dispatcher_staleness`).
- **A project folder** with no PROJECT.md update for >7 days and no archive entry.
- **An archive entry** older than D-2 still sitting in `archive/` (per `feedback_archive_clean_trigger`).

## The on-contact drill (the 5 steps)

```
1. PAUSE     stop the in-flight task — drift first.
2. RESOLVE   one of: absorb (into KB/memory/proper folder)
                    delete (regenerable / transient / known-stale)
                    salvage (record recovery pointer, then delete)
                    fix (the broken pointer / missing reference)
3. SURFACE   if blocked (ambiguous ownership, peer in-flight, irreversible) →
             stop, name the blocker, ask the user.
4. DOC       the resolution touches docs? Update them same commit
             (3-way-sync: KB ↔ CLAUDE.md ↔ memory).
5. CONTINUE  resume the paused work. The original task lands as planned.
```

**The "doc" step is non-negotiable.** If your resolution discovered a missing keeper, a gap in a procedure, a phrasing fix in a KB doc — codify it in the same commit. Drift-fix without doc-update is half-resolution: the same drift returns next session.

## Worked examples

### Example 1 — untracked `decision.md` at root (2026-05-26)
**Observed.** A `decision.md` table dropped at `/` during the keeper-pattern-cache project session. Untracked. Content: a 9-row decision log for the cache schema.
**On-contact resolution.** (a) Verified the decisions were already absorbed into `KB § PATTERNS/keeper-pattern-cache.md` (they were). (b) **Delete** — transient working notes, no durable value beyond the absorbed pattern. (c) No doc update needed (KB already covered it).
**Doc surface added in this codification pass.** This worked-example block — the next paste-buffer artifact gets the same drill applied because the pattern is now in KB.

### Example 2 — broken `KB § PATTERNS/<owned>` pointer surfaced by an agent
**Observed.** A backend-engineer dispatch follows `KB § PATTERNS/seed-fake-real-adapter.md` and gets a 404 (file renamed, pointer not updated).
**On-contact resolution.** (a) Stop. (b) Find the new path (`git log --all -- '*seed-fake*'`). (c) Fix the agent body pointer. (d) Run `noctus.dev.kb_sync` to surface any other dangling pointers. (e) If found ⇒ batch-fix all in this commit (same-shape drift = same-commit fix). (f) Continue the original backend dispatch.

### Example 3 — peer-tree residue from KB-autostage hook
**Observed.** Primary checkout shows 7 staged KB files you didn't author — the KB-autostage hook absorbed a peer's mid-flight work under your scoped commit.
**On-contact resolution.** (a) `git reset --soft HEAD^` to undo the over-broad commit. (b) Re-stage scoped explicit paths only. (c) `git commit --no-verify <paths>` with rationale in the message ("KB-autostage hook bypass — peer mid-flight on KB/<other>"). (d) Verify `git show --stat HEAD` shows only your authored files. (e) Surface the bypass to the user. (f) Continue.

### Example 4 — methodology rule discovered without doc-write
**Observed.** You're implementing a feature and notice that two products keep needing the same shape (N=2 → triage). You apply the fix locally and move on.
**On-contact resolution.** **STOP.** N=2 → triage is itself a methodology rule. Either (a) formalize now if the change is small (3-way-sync: KB pattern + CLAUDE.md §1 bullet + memory) OR (b) accept-with-rationale entry. Silent-fix-and-move-on IS the drift this rule forbids.

## Detection — the keeper (`check_git_leftovers`)

A new keeper (severity `high`) scans for the git-shape drift at every commit gate:

| Check | Surface | Fix-on-contact action |
|---|---|---|
| Untracked at repo root | `git status --porcelain` filter for `??` at depth 1 | Apply step 2 (absorb / delete / move) |
| Local branches diverged from origin | `git branch -vv` outside allowlist | Salvage + delete if abandoned |
| Worktree uncommitted | per-worktree `git status` | Architect-attention OR cleanup-via-task_branch |
| Stale archive | `archive/` D-3+ entries | `scripts/archive-clean.sh --force` (per `feedback_archive_clean_trigger`) |

The keeper composes with the existing `check_branch_orphan` / `check_dispatcher_staleness` / `check_archive_staleness` — those run on commit; this one catches the **gaps between them** (notably untracked-at-root + worktree-uncommitted, which were uncovered).

## Detection — the skill (first-action residue sweep)

[[noc-self-branch]] adds a §0 step: **before** `task_branch action=start`, run the residue sweep. The skill is where the rule lives operationally:

```
0. Residue sweep — git status --porcelain || noctus.dev.scan_remediation_markers || git branch -vv
   If drift found → apply the on-contact drill BEFORE starting the new worktree.
   The clean tree is the precondition for clean parallel work.
```

## Anti-patterns

- **"I'll deal with it later."** Later = next session = silent-error compounding. Resolve in-flight.
- **Silent delete.** Deleting drift without a salvage check throws away signal. Salvage (record pointer) THEN delete, even for things you think are transient — the salvage ledger is the recoverable insurance.
- **Resolve-without-doc-update.** The drift recurred *because* the doc didn't catch it; resolving without updating the doc keeps the drift one-session-away.
- **Bulk-defer drift to a "cleanup session."** Drift cleanup as a separate project is the recurring shape this rule forbids — the keeper-catalog grows by accretion, not bulk-purges.
- **Resolve on shared `dev`.** Drift resolution is still a writing task — [[self-branching-mode]] applies. Self-branch first; resolve in the worktree; integrate.

## Composes with

[[fix-on-contact for pre-existing debt]] (parent rule; this pattern is its git-shape + methodology-pointer specialization) · [[no silent errors]] (universal ancestor) · [[storage-hygiene]] (the salvage-before-delete leg) · [[self-branching-mode]] (resolution still self-branches) · [[noc-self-branch]] (the operational §0 residue sweep) · [[keeper-check-before-docing]] (drift-fix that touches a gated doc must query the keeper cache upfront) · [[agent-context-architecture]] (broken `owns_kb` pointers fall under this rule).
