# Two-Session Architect/Operator Pattern — Project Document

> **This is a living document.** Phase 0 design is locked. The pattern itself is methodology-in-pilot; the next phase is the user's real-run validation. Findings flow into `findings.md` and back into `KB § PATTERNS/two-session-architect-operator.md`.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 0 ✅ — design complete; Phase 1 (user pilot) ready.
- **Owner / stakeholders:** joaoraphaelsst (user) · architect (Claude Session A) · operator (Claude Session B)
- **Related docs:**
  - `KB § PATTERNS/two-session-architect-operator.md` (the pattern, authored alongside this project)
  - `KB § PATTERNS/branching-and-merging.md § 16-18` (parent methodology — branching-first orchestration)
  - `KB § 01-PHILOSOPHY.md § Branching-first orchestration` + `§ Roles: Architect + Engineers`
  - `KB § PATTERNS/project-execution.md § 2.10` (commit-only-own-work — the rule the §4 git-ownership separation defends)
  - Sibling project — `projects/autonomous-operator-via-subagent-pattern/PROJECT.md` (Option D, single-session variant; see `KB § PATTERNS/two-session-architect-operator.md § 11` for trade-off table)
  - Memory: `feedback_branching_first_orchestration.md`, `feedback_orchestrator_role.md`, `feedback_TEMP_methodology_validation_in_progress.md`
- **Project slug:** `two-session-architect-operator-pattern` (cross-cutting methodology — lives at `projects/<slug>/`; intent suffix `-pattern` rather than `-rollout` because no products are touched).

---

## 1. Context & Purpose

The branching-first orchestration pattern (`KB § PATTERNS/branching-and-merging.md § 16-18`) already chunks work into **architect** (plans + dispatches + evaluates + stays-with-user) and **engineers** (build chunks in isolated worktrees). In practice, the architect's session accumulates a steady stream of git mechanics tail-work — cherry-picks, FF-merges, pushes, project-close archives, hound/mole sweeps — and these interrupt the user-facing conversation that the architect is supposed to protect.

This project formalizes a **two-session split**: Session A is the Architect (conversation, planning, KB/memory edits, no git); Session B is the Operator (autonomous git mechanics, engineer dispatch execution, tail-work sweeps). They coordinate via two gitignored mailbox files at the repo root — `dispatcher-inbox.md` (architect → operator) and `dispatcher-outbox.md` (operator → architect).

The win: the architect stays available to the user **continuously** while the operator chews through git tail-work in parallel. No more "let me cherry-pick that real quick — back to the design question in 20 minutes."

---

## 2. Confirmed constraints

- **Same repo, two terminal windows** — *(Scope is two top-level Claude Code sessions in the same noc clone, or a sibling seed-workspace + noc; not two physical machines, not two branches of separate clones. Rules out federated multi-repo coordination for now.)*
- **`dispatcher-inbox.md` + `dispatcher-outbox.md` are gitignored** — *(They are transient coordination state, not history. Durable record stays in PROJECT.md / findings.md / §11 Change Log / memory.)*
- **Architect runs zero git commands; operator owns ALL git operations** — *(Strict separation. Carve-out: read-only inspections — `git status`, `git log`, `git diff`, `git branch --show-current` — allowed for both sides. Anything that changes state routes through inbox.)*
- **Memory writes are architect-only** — *(Two writers race on MEMORY.md index lines; concentrating writes preserves coherence. Operator surfaces methodology-gap findings to outbox; architect drafts the `feedback_*.md` entry.)*
- **KB / CLAUDE.md writes are architect-only** — *(Same shape as memory. Operator runs `bash scripts/verify-kb-sync.sh` when the architect signals, but never edits the KB itself.)*
- **The `/loop` autonomous mode is opt-in, not default** — *(Operator may run `/loop 2m` to poll the inbox; user chooses per-session. Destructive ops require explicit per-entry `Auto-execute: yes` flag.)*
- **Coordination with Option D (single-session autonomous subagent) is non-exclusive** — *(Same architect can choose per-batch: high-tempo conversation → two-session; small mechanical tail-work → in-session subagent. Trade-off table at `KB § PATTERNS/two-session-architect-operator.md § 11`.)*

---

## 3. Design principles

1. **Strict git ownership prevents collisions structurally.** The architect's discipline isn't "be careful" — it's "never type `git`". Removing the temptation removes the bug class.
2. **The inbox is a queue, not a log.** Operator clears entries on completion (move to Completed-24h section, then roll out). A growing Pending list = operator is behind = architect pauses dispatches.
3. **The outbox carries context, not just outcomes.** Operator's report includes file count / LoC / key paths / test outcome so the architect can absorb without re-running `git diff`.
4. **Mailbox files are gitignored.** Coordination state is ephemeral. Durability lives in PROJECT.md / findings.md / memory.
5. **The pattern is opt-in per session, per batch.** Decision rubric (5 questions) at `KB § PATTERNS/two-session-architect-operator.md § 10`. ≤2 "yes" → stay single-session.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

Run the six-question checklist (`KB § GUIDES/seed-first-design.md § The seed-first checklist`):

1. **Is the contract identical for every product?** *N/A — this project is platform-methodology, not a product change. No products are touched. The "contract" here is the architect↔operator working agreement, which is uniform by definition.*
2. **Is the data source product-specific?** *N/A — no data source. The "data" is the inbox/outbox mailbox files at repo root, shared by both sessions.*
3. **Is the placement product-specific?** *No — the mailbox files live at repo root (cross-cutting). The pattern itself lives in `KB § PATTERNS/`, which is cross-cutting by definition.*
4. **Is the visibility / permission rule the same?** *Yes — single-user / single-workspace pattern. No multi-tenant or RBAC considerations.*
5. **Does the seam already exist in seed?** *N/A — this is a working-agreement pattern, not a code pattern. The "seam" is the file-system convention of `dispatcher-inbox.md` + `dispatcher-outbox.md` at repo root + a `.gitignore` entry. No seed-lib code needed.*
6. **Default-on or opt-in?** *OPT-IN — the decision rubric at §10 of the KB page governs. The pattern is not auto-applied; it's adopted per session when tempo justifies it.*

**Litmus — per-product code count this design requires:**

- [x] **0 lines** — pure cross-cutting platform methodology; lives entirely in KB + CLAUDE.md routing + memory. Products are not touched; no per-product code.

**Phase plan implications:** §6 phases work in the platform layer (KB, CLAUDE.md routing, repo-root mailbox files, .gitignore) — no per-product walk-through. Seed-first analysis confirms the design is correctly platform-bounded.

---

## 4. Scope

**In scope:**
- KB pattern doc — `KNOWLEDGE-BASE/CONTEXT/PATTERNS/two-session-architect-operator.md` (full pattern: roles, inbox/outbox format, git ownership, memory ownership, MCP ownership, anti-patterns, setup recipe, `/loop` variant, decision rubric).
- `dispatcher-inbox.md` template at repo root (gitignored; with `## Pending` + `## Completed (last 24h)` skeleton + entry-format docstring).
- `KNOWLEDGE-BASE/INDEX.md` table row.
- `CLAUDE.md` §3 routing row for trigger phrases "two sessions" / "second Claude" / "architect/operator split".
- This PROJECT.md.

**Out of scope (for now — with reason):**
- **`dispatcher-outbox.md` template** — not shipped as a file; operator bootstraps via `printf '# Dispatcher Outbox\n\n## Recent\n' > dispatcher-outbox.md` per §8.3 of the pattern. *(Keeping one template file is cleaner; outbox is straightforward enough that a printf bootstrap suffices.)*
- **`.gitignore` edits** — deferred to the architect when wiring in real usage. The pattern's §3.1 declares the files gitignored; the actual `.gitignore` entries get added when the user signs off on the pilot. *(Pre-shipping a `.gitignore` edit risks merging while the pilot is still uncertain; safer to defer.)*
- **Memory entry `feedback_two_session_architect_operator.md`** — deferred per the `feedback_TEMP_methodology_validation_in_progress.md` rule (memory-only, validation-in-progress). Three-way sync triggers at pilot-proven, not at design-complete.
- **Automation tooling** — no MCP tool for `route-to-inbox` or `consume-next-pending`. The mailbox is plain Markdown; the operator reads + writes with standard Read/Edit tools. *(Tooling can be added post-pilot if pain emerges.)*
- **Option D (single-session autonomous subagent)** — separate project at `projects/autonomous-operator-via-subagent-pattern/`. Trade-off table at `KB § PATTERNS/two-session-architect-operator.md § 11` cross-references it.

---

## 5. Architecture / Data Model

**Files this project creates / edits:**

| File | Action | Purpose |
|---|---|---|
| `KNOWLEDGE-BASE/CONTEXT/PATTERNS/two-session-architect-operator.md` | NEW | The full pattern doc — 12 sections covering overview, roles, coordination, git/memory/KB/MCP ownership, anti-patterns, setup, `/loop`, decision rubric, Option D trade-off, living-doc note. |
| `dispatcher-inbox.md` | NEW (at repo root, gitignored) | Mailbox template with `## Pending` + `## Completed (last 24h)` skeleton + entry-format docstring. |
| `KNOWLEDGE-BASE/INDEX.md` | EDIT | Add a new row under "## By topic" pointing at the new pattern page. |
| `CLAUDE.md` | EDIT | Add a §3 routing row: trigger phrases "two sessions" / "second Claude" / "architect/operator split" → read the pattern. |
| `projects/two-session-architect-operator-pattern/PROJECT.md` | NEW (this file) | The project document. |

**No code changes. No migration. No per-product touch.** All artifacts are Markdown.

**Coordination shape (logical view):**

```
┌─────────────────────────────────────────────────────────────────┐
│                       Same noc repo                              │
│                                                                  │
│   ┌─────────────────┐                  ┌─────────────────┐      │
│   │  Session A      │   appends to     │  dispatcher-    │      │
│   │  ARCHITECT      │ ───────────────▶ │  inbox.md       │      │
│   │  - conversation │                  │  (gitignored)   │      │
│   │  - planning     │                  └────────┬────────┘      │
│   │  - KB / memory  │                           │ consumed      │
│   │  - NO git       │                           ▼ top-down      │
│   └────────▲────────┘                  ┌─────────────────┐      │
│            │                           │  Session B      │      │
│            │ reads ────────────────────│  OPERATOR       │      │
│            │                           │  - git ops      │      │
│   ┌────────┴────────┐   appends to     │  - dispatch exec│      │
│   │  dispatcher-    │ ◀──────────────  │  - tail sweeps  │      │
│   │  outbox.md      │                  │  - verify       │      │
│   │  (gitignored)   │                  └─────────────────┘      │
│   └─────────────────┘                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Implementation phases

### Phase 0 — Design ✅ (shipped 2026-05-11)

- [x] Draft KB pattern doc covering all surfaces (roles / coordination / git / memory / KB / MCP / anti-patterns / setup / `/loop` / rubric / Option D / living-doc).
- [x] Author `dispatcher-inbox.md` template at repo root (gitignored).
- [x] Edit `KNOWLEDGE-BASE/INDEX.md` to add new pattern row.
- [x] Edit `CLAUDE.md` §3 to add trigger-phrase routing row ("two sessions" / "second Claude").
- [x] Author this PROJECT.md.

**Improvements:**
- The `.gitignore` entries for `dispatcher-inbox.md` + `dispatcher-outbox.md` are deferred to Phase 1 sign-off rather than shipped now — pre-merging the ignore-rule before the pilot starts risks orphaning the entry if the pattern doesn't pan out. Document the deferral so future agents don't search for missing `.gitignore` lines.
- The `dispatcher-outbox.md` doesn't ship as a separate file — operator bootstraps via `printf`. If the pilot proves the outbox needs more structure (e.g. per-section dividers for `## Recent` / `## Archived`), backfill a template file then.
- The `/loop` cadence (2 min) in §9 is a first guess; expect calibration after 1-2 batches. Likely lands at 1m for high-tempo or 5m for overnight queues.
- The git-ownership strictness (architect runs ZERO git) is aggressive — if the user finds the carve-out (§4.2) is hit more than once per session, soften the rule rather than fight it. The point is collision prevention, not purity.
- No memory entry yet (per `feedback_TEMP_methodology_validation_in_progress.md`) — three-way sync triggers at pilot-proven. Make sure to surface this in the close-of-pilot retrospective so memory doesn't get orphaned.

*Phase proposal filed:* none. This phase ships the design as content; the next moment for proposal authorship is Phase 1 close (after the pilot run surfaces actionable improvements). Marking with `**Improvements:**` block satisfies the phase-state detector without an empty proposal.

### Phase 1 — User pilot (next — gated on user signal)

Phase 1 is the **real-run validation** of the pattern. Trigger: the user decides to adopt the split for a working session (per the §10 rubric, 3+ "yes" answers).

- [ ] User runs the §10 decision rubric and signals adoption.
- [ ] Architect (Session A) launches with the bootstrap prompt (§8.1 of the KB page).
- [ ] Operator (Session B) launches with the bootstrap prompt (§8.2).
- [ ] Operator bootstraps `dispatcher-outbox.md` (§8.3); inbox already exists from Phase 0.
- [ ] First handoff smoke test (§8.4) confirms the loop works.
- [ ] Run for one real working session — at least 3 inbox entries consumed (1 dispatch + 1 cherry-pick + 1 archive or sweep, ideally).
- [ ] Append findings to `projects/two-session-architect-operator-pattern/findings.md` in-flight (slips / errors / lessons / surprises / interesting findings).
- [ ] At pilot close: synthesize findings, decide three-way sync trigger (KB + CLAUDE.md routing already exist; this phase adds the memory entry `feedback_two_session_architect_operator.md` if the pattern proves out).
- [ ] If pattern needs amendments: update KB page § that surfaced the gap, with §11 Change Log entry on this PROJECT.md.
- [ ] If pattern is abandoned: archive this project with `noctus.dev.archive` and a `findings.md` synthesis explaining why.

**Acceptance for Phase 1 ✅:** one full working session run through the split, findings synthesized, three-way sync executed or abandonment-archive completed.

### Phase 2 — Tooling (optional, post-pilot)

Only file Phase 2 if Phase 1 surfaces specific pain points where MCP tools would help. Candidates (defer-with-destination shape):

- [ ] MCP tool `noctus.dev.dispatcher_inbox_append` — append a typed entry from the architect side (validates Type enum + Acceptance field; timestamps automatically).
- [ ] MCP tool `noctus.dev.dispatcher_inbox_consume` — operator-side helper that picks top-most Pending entry and atomically moves it to Completed-24h on success.
- [ ] Pre-commit hook — verify `dispatcher-*.md` files are in `.gitignore` (prevent accidental commit).

*(Don't author Phase 2 in advance; the recurrence rule applies — if the pilot uses the mailbox 3+ times without these tools and the manual shape works fine, don't build them.)*

---

## 7. Open questions

1. **Where does the operator session run when the user is offline (overnight)?** — needs answer before Phase 1 long-running pilot / decided by user. *Recommendation:* `/loop 5m` mode in the operator session, with `Auto-execute: yes` only on explicitly-marked entries; destructive ops still require ask-first per §9 safety rule.
2. **Should the outbox auto-truncate after N days?** — deferred until Phase 1 close / decided by user. *Recommendation:* hand-roll for now (architect deletes stale entries when starting a new session); revisit if the file grows past ~200 lines.
3. **Does the operator session need a different MCP config than the architect (e.g. omit conversational MCPs like `claude_ai_*` connectors)?** — deferred until Phase 2 / decided by user. *Recommendation:* same MCP config initially; the per-session prompts (§8.1, §8.2) discipline the tool-use shape, not the available surface.
4. **What happens when the operator session crashes mid-cherry-pick?** — needs answer during Phase 1 / discover during build. *Recommendation:* the operator's outbox-entry-on-completion shape is the resume mechanism — if outbox shows partial state, next operator turn (or restart) re-reads, completes, then writes outcome. No automatic retry logic in v1; the inbox stays Pending until the operator clears it.

---

## 8. Dependencies & blockers

- **None for Phase 0.** All artifacts are Markdown; no migration, no code, no per-product touch.
- **Phase 1 depends on:** user adopting the split for a real working session (rubric-driven).
- **Phase 1 may surface:** the need to add `.gitignore` entries (the pattern declares the files gitignored — defer to architect when the pilot starts to avoid pre-merging an unproven entry).
- **Cross-project parallel:** sibling project `projects/autonomous-operator-via-subagent-pattern/` (Option D) is being authored in the same turn by Engineer AUTONOMOUS-OPERATOR-D-2. File-level scope is disjoint; INDEX.md + CLAUDE.md row collisions possible — coordinate at commit time per the brief.

---

## 9. Success criteria

- **Phase 0:** KB pattern doc + inbox template + INDEX row + CLAUDE.md row + PROJECT.md all shipped and consistent. (Met as of 2026-05-11.)
- **Phase 1:** One full working session run through the split with at least 3 inbox entries consumed; no git collisions observed; architect reports the conversation time was protected; findings.md has at least 1 entry per of the 5 categories (slips / errors / lessons / surprises / interesting-findings) OR an explicit "none for category X" note.
- **Methodology proven:** at least 3 sessions adopted the split (recurrence-rule N=3) AND no §1-philosophy slips fired during those sessions. Triggers three-way sync — memory entry written, KB page promoted from "methodology-in-pilot" to "established working agreement".

---

## 10. How to use this plan

- **Single source of truth for progress.** Update §6 phase ticks and §11 Change Log as work happens.
- **Phase 1 is user-gated.** Don't auto-advance; wait for the user to signal "let's pilot this".
- **The KB page is the durable artifact** (`KB § PATTERNS/two-session-architect-operator.md`). This PROJECT.md is the project-execution record; the KB page is what other agents read.
- **findings.md belongs at this project root** when Phase 1 runs (`projects/two-session-architect-operator-pattern/findings.md`). Use the 5-category shape per `feedback_knowledge_tracking.md`.
- **At pilot close:** synthesize findings, then decide whether to (a) three-way sync (write `feedback_two_session_architect_operator.md` + MEMORY.md index line), (b) amend the KB page, or (c) archive the project as "tried, didn't fit" with findings preserved.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Phase 0 ✅ — KB pattern doc + inbox template + INDEX row + CLAUDE.md row + this PROJECT.md drafted and staged. Phase 1 (user pilot) ready. | Engineer TWO-SESSION-DOC-2 (re-dispatch after rate-limit on TWO-SESSION-DOC-1) |
