# Autonomous Operator Pattern — Project Document

> **This is a living document, not a rigid checklist.**
>
> **Project slug:** `autonomous-operator-pattern` — lives at `projects/autonomous-operator-pattern/` (cross-cutting platform-infra; affects every orchestration-heavy project going forward).

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 1 (documentation rollout) in progress — pattern shipped, working agreements landed
- **Owner / stakeholders:** USER · architect (Claude) · operator (Claude subagent)
- **Related docs:**
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/autonomous-operator-via-subagent.md` (the pattern)
  - `.claude/agents/orchestrator-operator.md` (the agent definition)
  - `/Users/rapha/.claude/projects/-Users-rapha-Documents-repository-NoctusAI-noctusai/memory/feedback_autonomous_operator_via_subagent.md` (working agreement)
  - `KB § PATTERNS/branching-and-merging.md § 16, 18`
  - `KB § PATTERNS/master-tree-parallel-batches.md`

---

## 1. Context & Purpose

The architect-vs-engineer role split (`feedback_branching_first_orchestration`) keeps the architect with the user during ideation while engineers build in worktrees. But the **mechanical work between user turns** — `git fetch / cherry-pick / push / archive` for each engineer — still happens in the architect's main session, draining the user-facing context budget on no-ideation work.

Three prior options exist (A — inline, B — `/loop`, C — per-task subagent); all three have failure modes when dispatch-heavy work coincides with user-conversation thinking. **Option D — autonomous operator via subagent** is the fusion: single Claude session preserves cross-turn memory; `ScheduleWakeup` tick fires between user turns; the architect spawns an `orchestrator-operator` subagent that drains a markdown inbox in its own isolated context; the architect's main context stays clean for user thinking.

The win: the architect can be deep in user-conversation ideation while 5+ engineer branches cherry-pick + push in the background, all within one Claude session, with full auditable outbox.

---

## 2. Confirmed constraints

- **Architect stays with the user** — the architect's main context is the bottleneck; mechanical work must NOT drain it. *(Why Option A fails for dispatch-heavy phases.)*
- **Single Claude session** — no separate `/loop` process. *(Why Option B is rejected: cross-session memory gap defeats user-thinks-with-architect.)*
- **Specialized subagent per tick, not per task** — one operator drains the entire inbox per ScheduleWakeup tick. *(Why Option C is rejected: per-task briefs add overhead the inbox shape already amortizes.)*
- **Markdown-file inbox/outbox** — durable across ticks, human-readable, git-trackable. *(Rules out in-memory queues; survives session restarts even though we're optimizing for one-session.)*
- **FF-merge-to-main is architect-only** — operator never touches main. *(Preserves the project-close gate from `feedback_orchestrator_role`.)*
- **ScheduleWakeup cadence is adaptive** — 15min idle / 5min dispatch-heavy. *(Wasting context on always-on 1min polling is silent-error shape.)*

---

## 3. Design principles

1. **Operator drains; never extends.** The operator's only job is processing the inbox. Scope extension (`engineer requests Wave 2 → operator dispatches Wave 2`) is forbidden. New decisions land back on the architect.
2. **Inbox is the API.** Architect → operator communication is the inbox file. Operator → architect communication is (a) inbox state mutation, (b) outbox append, (c) single return summary. No other channels.
3. **Isolated context per tick.** Each `orchestrator-operator` invocation starts fresh; the operator does not inherit the architect's conversation. The inbox + outbox + agent definition are the entire shared state.
4. **Failure is loud + non-retried.** Operator never retries a failed task. Outbox the verbatim tail; architect triages on the next user turn.
5. **Audit by design.** Every drained task lands in the outbox. Architect reads outbox at next user turn (or on user demand: "what did the operator do while we talked?"). No silent operator actions.

---

## 3a. Seed-first analysis

Run the six-question checklist:

1. **Is the contract identical for every product?** YES — Option D is a cross-cutting orchestration pattern, not product-bound. Lives in `.claude/agents/` and `KB § PATTERNS/`.
2. **Is the data source product-specific?** NO — the inbox/outbox shape is universal; tasks reference whatever product/worktree they target.
3. **Is the placement product-specific?** NO — pattern lives at repo root + `.claude/agents/`; consumed by any project that wants dispatch-heavy orchestration.
4. **Is the visibility / permission rule the same?** YES — every architect + operator pair follows the same scope guards.
5. **Does the seam already exist in seed?** NO — this is the seam. `.claude/agents/orchestrator-operator.md` is the new seed surface; `KB § PATTERNS/autonomous-operator-via-subagent.md` is the documentation seam.
6. **Default-on or opt-in?** OPT-IN — only dispatch-heavy projects pay the inbox-plumbing cost. Default = inline (Option A). Decision tree in `§ When to use D` of the pattern doc.

**Litmus — per-product code count this design requires:**

- [x] **0 lines** — pure cross-product / platform-infra concern; lives in `.claude/agents/` + KB. Products inherit by referencing the pattern, no per-product code.

**Phase plan implications:** §6 phases work entirely in `.claude/agents/` + KB + CLAUDE.md routing + memory + projects/. No product walkthrough. Pattern is correctly cross-cutting.

---

## 4. Scope

**In scope:**
- New `.claude/agents/orchestrator-operator.md` (agent definition).
- New `KNOWLEDGE-BASE/CONTEXT/PATTERNS/autonomous-operator-via-subagent.md` (pattern doc).
- CLAUDE.md §3 row routing dispatch-heavy projects to the pattern doc.
- `KNOWLEDGE-BASE/INDEX.md` pattern row.
- This `PROJECT.md`.
- Memory entry `feedback_autonomous_operator_via_subagent.md` + MEMORY.md index line.

**Out of scope (for now — with reason):**
- Inbox/outbox auto-rotation when files grow large — defer until we have empirical bloat data. *(YAGNI.)*
- Multi-operator parallelism (two operators per tick) — explicitly forbidden in v1. *(One operator per tick is the contract; multi-operator coordination overhead would defeat the purpose.)*
- Cross-session inbox persistence across Claude session restarts — Option D is single-session by design. *(That's Option B's job.)*
- Generic `ScheduleWakeup` triggers beyond inbox-drain — limit Option D's wakeups to the inbox path. Other autonomous triggers (e.g. "watch for engineer-branch push") are future work.

---

## 5. Architecture / Data Model

### File layout

```
.claude/agents/orchestrator-operator.md          ← agent definition (YAML frontmatter + body)
KNOWLEDGE-BASE/CONTEXT/PATTERNS/
  └── autonomous-operator-via-subagent.md        ← pattern doc

# Per-project (created when Option D is adopted by a project):
<repo-root or master-tree-root>/
  ├── dispatcher-inbox.md                        ← pending/in-progress/done/failed tasks
  └── dispatcher-outbox.md                       ← append-only audit log
```

### Task shape (inbox)

```markdown
## <task-id>
- **Kind:** dispatch-engineer | validate-worktree | cherry-pick-and-push | archive-project
- **State:** pending | in-progress | done | failed
- **Args:** <bullet list>
- **Queued by:** architect <timestamp>
- **Brief:** <one-sentence>
```

### Tools the operator uses

- `Bash` — git operations + build/test commands.
- `Read` — inbox, briefs, repo state.
- `Write` / `Edit` — outbox append, inbox state mutation.
- `Agent` — dispatch engineer subagents.
- `mcp__noctusai__noctus_dev_archive` — archive completed projects.

---

## 6. Implementation phases

### Phase 1 ✅ — Pattern rollout (documentation + agent definition)

**Improvements:** none identified — Phase 1 is design + documentation; Phase 2 (pilot) is the calibration phase where findings will surface.

- [x] Write `.claude/agents/orchestrator-operator.md` with YAML frontmatter + per-task playbook + outbox convention + git ownership rules + failure handling
- [x] Write `KNOWLEDGE-BASE/CONTEXT/PATTERNS/autonomous-operator-via-subagent.md` (A vs B vs C vs D comparison + 8-step flow + cadence + when-to-use + setup recipe + anti-patterns)
- [x] Add CLAUDE.md §3 row routing dispatch-heavy projects to the pattern doc
- [x] Add KNOWLEDGE-BASE/INDEX.md pattern row
- [x] Write this PROJECT.md
- [x] Write memory entry + MEMORY.md index line

### Phase 2 — Pilot adoption (calibration via first real use)

- [ ] Identify the next dispatch-heavy project (likely a wave-based parallel-batch master-tree)
- [ ] Plumb `dispatcher-inbox.md` + `dispatcher-outbox.md` at the master-tree root
- [ ] Run the first 3 ticks; capture findings in master-tree `findings.md` (5 categories)
- [ ] Calibrate ScheduleWakeup cadence (15min idle / 5min dispatch-heavy may need adjustment)
- [ ] Calibrate tick-budget ceiling (per Open Question 9.1)
- [ ] Decide cross-tick concurrency rule (per Open Question 9.2)

### Phase 3 — Methodology folding (post-pilot)

- [ ] Synthesize pilot findings into pattern doc + memory entry updates
- [ ] If pilot reveals a recurrence (the operator agent applies to a 2nd project shape), file the formalization decision per the recurrence rule
- [ ] If pilot reveals a gap (the agent definition needs a new task `Kind`), update `.claude/agents/orchestrator-operator.md` and the pattern doc together (three-way sync)
- [ ] Update `feedback_autonomous_operator_via_subagent.md` with pilot lessons

---

## 7. Open questions

1. **Tick budget ceiling.** What's the right max tasks-per-tick? Conjecture: 5 cherry-picks OR 1 engineer dispatch. Calibrate during first pilot. *(Phase 2.)*
2. **Cross-tick concurrency.** If a wakeup fires while the previous operator subagent is still running, what happens? Conjecture: architect's tick handler defers the new tick by checking outbox vs inbox state. Confirm during first parallel-wave dispatch. *(Phase 2.)*
3. **Inbox/outbox archival.** When does the file pair move to `projects/<slug>/archive/`? Conjecture: at project close, alongside the project doc. Confirm via first archival. *(Phase 3.)*
4. **TWO-SESSION-DOC-2 coordination.** A sibling engineer dispatched this turn drafted A/B/C docs. INDEX.md + CLAUDE.md collisions are possible at commit time. *(Coordinate at commit — likely no actual collision since our additions are non-overlapping rows.)*

---

## 8. Dependencies & blockers

- **Agent tool availability.** Operator uses the `Agent` tool to dispatch engineers; requires the tool to be exposed to the subagent's tools list. *(Handled in `.claude/agents/orchestrator-operator.md` YAML.)*
- **MCP `noctus_dev_archive` availability.** Operator uses for `archive-project` task. *(Available in current MCP toolkit.)*
- **ScheduleWakeup primitive.** Architect-side wakeup scheduling depends on the harness exposing this. *(Confirmed available in current harness.)*

---

## 9. Success criteria

- The `orchestrator-operator` agent is defined and discoverable from the architect's session.
- The pattern doc explains A vs B vs C vs D clearly enough that the next architect picks the right option without re-asking.
- CLAUDE.md §3 routes dispatch-heavy work to the pattern doc.
- INDEX.md lists the pattern.
- Memory entry exists + MEMORY.md indexes it.
- First pilot project (Phase 2) successfully drains an inbox with ≥3 mechanical tasks via the operator, with full outbox audit + clean architect main context.

---

## 10. How to use this plan

- **Phase-by-phase by default.** Phase 1 ships the pattern; Phase 2 waits for a real dispatch-heavy project to adopt.
- **Commit Phase 1 outputs together.** All 6 files land in one branch — `autonomous-operator-via-subagent-doc-2026-05-11`. Architect FF-merges to main when ready (literal last step per `KB § PATTERNS/project-execution.md`).
- **Phase 2 is event-driven.** When the next dispatch-heavy master-tree starts, that project's PROJECT.md cross-references this one + adopts the inbox/outbox plumbing.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Initial project drafted; Phase 1 deliverables shipped — agent definition + pattern doc + CLAUDE.md row + INDEX row + memory entry + this doc | Engineer AUTONOMOUS-OPERATOR-D-2 |
