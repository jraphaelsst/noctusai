# Persistent-files absorption — promote durable context out of removable surfaces

**The rule.** Persistent files in `projects/<slug>/` and `.claude/worktrees/<slug>/` (PROJECT.md, findings.md, lessons-laden README/notes, accept-with-rationale entries, *.md non-trivial work) MUST be **absorbed into the durable layer (KB / memory / agents / skills / compliance keepers) BEFORE the project is archived or the worktree torn down.** Otherwise the context is lost — projects archive moves out of `projects/`; worktrees `git worktree remove` deletes the dir; both are removable surfaces by design. Codified 2026-05-26.

**Why now.** The pattern recurred this multi-session run: every project / worktree teardown surfaced a small carry-over (a findings.md, a decision rationale, a new keeper, a hard-won bump). The salvage ledger ([[storage-hygiene]] §2.3) records the *recovery pointer* (branch + SHA) — necessary but not enough: the **content** must land in a durable home, not just be recoverable from git history. The user's framing: *"absorb them outside removable context as soon as they surface."*

## The durable destinations (one home per fact, then point)
| Surface | Durable home |
|---|---|
| A new general rule / methodology pattern | `KB § PATTERNS/<x>.md` (+ `CLAUDE.md` §1 one-line bullet + pointer; respect `check_claude_md_router`) |
| A repeatable procedure | `.claude/skills/<noc-x>/SKILL.md` |
| A specialist persona | `.claude/agents/<x>.md` (port from `dev_team/charters/` if applicable) |
| A deterministic, recurrence≥3 contract | `check_*` keeper in `mcp/noctusai/tools/noctus/dev/compliance.py` + colocated test |
| User-given guidance / instance learning | `memory/<feedback_…>.md` + `MEMORY.md` index line |
| Accepted divergence (with reason) | `KB § PATTERNS/common/accept-with-rationale.md` |
| Tools / scripts | `noctus.dev.*` MCP tool ([[mcp-first-scripts]]) |

## When this fires (absorb-on-contact, not at-teardown)
The discipline is **absorb as the insight surfaces, not at teardown**. Teardown is too late — by then context-switch has already cost. Triggers:
- A findings.md entry that names a pattern → absorb to KB the same commit/checkpoint ([[branching-and-merging]] §17.6, §21.4).
- A "we should always X" decision in a PROJECT.md §11 → either a one-line memory entry now OR a KB pattern OR (recurrence ≥3) a keeper.
- A bump diagnosis in [[containerization-operations]] / siblings → append to that doc's codified-bumps catalog same session.
- A new agent / skill / MCP tool the project shipped → registered in `.claude/agents/` / `.claude/skills/` / `compliance.py` BEFORE archive.

## At-teardown checklist (the safety net)
Before `noctus.dev.archive <slug>` (projects) or any worktree removal (manual or via `task_branch cleanup` / `mole sweep` / `cleanup_stale_worktrees`):
1. `findings.md` reviewed: every {slip / error / mistake / lesson / knowledge} entry either codified to a durable home (mark IN-FLIGHT-PROCESSED) or surfaced as a follow-up project with a named destination.
2. `PROJECT.md` §11 (live-patterns-log) reviewed: every concrete decision either absorbed OR cataloged in [[accept-with-rationale]].
3. `proposals/*.md` reviewed: same rule.
4. Recovery pointer recorded in `project-history/worktree-salvage.ndjson` or `project-history/ledger.ndjson` ([[storage-hygiene]] §2.3).
5. **Only then** archive / remove.

## Anti-patterns
- **Salvage-pointer-only** — recording branch+SHA without absorbing the LESSON. Pointer enables recovery; absorption preserves the learning. Both legs fire.
- **Defer "until after archive"** — once archived, the project folder is gone from `projects/`; finding the right pattern in `archive/<date>/<slug>/findings.md` requires knowing to look. Absorption-on-contact removes the lookup.
- **Absorb without the destination** — "I'll write this up later" = silent deferral ([[01-PHILOSOPHY]] no-silent-errors). The destination is named at the moment of surfacing.
- **Bare worktree remove** — skips ALL legs. Use a sanctioned tool (`task_branch cleanup` / `mole sweep` / `cleanup_stale_worktrees`) — see [[branching-dispatch]] §9 (and the in-flight `feat/worktree-sweep-any-subdir` broadening for non-`agent-*` worktrees).

## Future codification (deferred — recurrence-gated)
A `check_persistent_file_absorbed` keeper (Stage-4): scan `projects/<slug>/findings.md` + `PROJECT.md` + `.claude/worktrees/<slug>/findings.md` for entries that look durable (≥100 chars, contains decision/lesson keywords) and warn if the project/worktree is about to archive without those entries being reflected in KB/memory. Predicate is judgment-heavy (warning, not block) — codify when evidence reaches N≥3.

## Composes with
[[storage-hygiene]] §2.3 (the salvage ritual sibling — pointer leg) · [[methodology-codification-pipeline]] (the s1→s4 ladder this rule routes findings through) · [[branching-and-merging]] §17.6 / §21.4 (in-flight processing, commit-on-ship) · [[01-PHILOSOPHY]] (no-silent-errors, fix-on-contact) · [[keeper-check-before-docing]] (the authoring sibling — checks contract BEFORE writing; this rule absorbs context BEFORE removing).
