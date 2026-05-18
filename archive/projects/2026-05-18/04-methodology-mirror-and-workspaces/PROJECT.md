# Methodology Mirror + Workspaces — Project Document (REVISED concept)

> **What this project is.** Steps (b) + (c) of the original 2026-05-02
> methodology-extraction trilogy: a **methodology mirror layer** (durable
> cross-session learning store, separate from auto-load) + a **long-lived
> workspaces** abstraction (per-product / per-experiment isolated dev
> environments with full KB at fork time + a promote-to-trunk path).
>
> **What it is NOT (any more).** The original 11-question structural
> investment. Substantial portions of the workspaces design space have been
> *naturally addressed* by other shipped methodology infrastructure since
> 2026-05-02. This concept is now narrower: it owns only the **mirror
> layer** (clean-sheet) and the **long-lived-product-fork** shape (distinct
> from per-engineer-chunk worktrees). Step-(b) and step-(c) remain
> **scoped-deferred** until Q11 reactivation triggers fire.
>
> **Run-by.** Concept-only scoping doc. Not executing. No engineer
> dispatched against this PROJECT.md until the user reactivates per §7
> Q11.

- **Created:** 2026-05-02 (original concept)
- **Folder previously deleted:** 2026-05-03 via close-gate Wave 2 commit `38ab384`
- **Concept refreshed:** 2026-05-11 (by Engineer MCB-CLOSE per parent batch Phase 4.d REVISE decision)
- **Status:** 📐 **SCOPED — concept revised, deferred pending Q11 trigger.** Two clean-sheet pieces survive: mirror layer (b-step) + long-lived-product-fork workspaces (c-step). Auto-load measurement (22% static + 35-50% effective) durable from step-(a) close.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `methodology-mirror-and-workspaces`
- **Parent batch:** `projects/main-core-migrations-batch/PROJECT.md` Phase 4.d (closed 2026-05-11 — this PROJECT.md is the **REVISED concept** artifact)
- **Related artifacts:**
  - Snapshot of original concept: `.claude/snapshots/projects-2026-05-03_024603/projects-root/methodology-mirror-and-workspaces/PROJECT.md` (470-line 11-Q original)
  - Tier-4 surfacing decision doc: `archive/projects/2026-05-11/63-tier4-concept-trio-surfacing/PROJECT.md` (§5.3 contains the architect's read in full)
  - Step-(a) close measurement: `KB § PATTERNS/seed-workspace.md § Why the inherited surface is not trimmed`

---

## 1. Context & Purpose

**The 2026-05-02 trilogy was:**

- **(a) Step (a) — trim the methodology surface.** Shipped 2026-05-02. CLAUDE.md → router, KB on-demand, MEMORY.md indexed. **22% static + 35-50% effective per-turn token savings** (measurement at original §7 Q11). This step's value was *immediate*: the workflow stopped being constrained day-to-day.
- **(b) Step (b) — methodology mirror.** A durable cross-session learning store distinct from auto-load. The premise: some patterns are valuable but not auto-load-justified; some safety-net catches need to survive longer than a session's `findings.md`. A mirror layer = a place to write/read methodology evidence without paying the auto-load tax.
- **(c) Step (c) — long-lived workspaces.** Per-product or per-experiment dev environments with full KB at fork time + a structured promote-to-trunk path. **Different shape from per-engineer-chunk worktrees** (which are ephemeral, single-task, per-LETTER-coded engineer).

**What changed between 2026-05-02 and 2026-05-11:**

The methodology evolved organically. Several pieces of the workspaces design space were *naturally addressed* by infrastructure shipped for adjacent reasons:

1. **`git worktree add` per engineer** (KB § PATTERNS/branching-and-merging.md §16) — workspace isolation at the *chunk* level. Solves Q6 "workspace lifecycle" at per-engineer-chunk granularity, not per-product.
2. **`.claude/worktrees/agent-*/` ephemeral workspaces + cleanup script** (memory entry `feedback_worktree_auto_cleanup.md`) — Q6 lifecycle solved a different way. Auto-cleanup of stale agent-* folders catches the disk-cost dimension that Q6 didn't.
3. **Template workspace** (`KB § PATTERNS/template-workspace.md`) + promotion manifest — exactly the "starter-kit bundle" + "promote-to-trunk" shape Q5 was sketching, applied to a different use case (sibling-product spinout, not methodology variants).
4. **Seed workspace** (`KB § PATTERNS/seed-workspace.md § Why the inherited surface is not trimmed`) — Q7 ("doc-aware: full KB or scoped") **settled structurally**. The seed workspace inherits all 8 noc surfaces via read-only symlinks, *trim none*. This was the right answer to Q7's design recommendation.
5. **Two-session architect/operator pattern** (`KB § PATTERNS/two-session-architect-operator.md`) — a different shape that absorbed part of Q3's "where the mirror physically lives" — Session B operator's inbox/outbox at repo root is *not* a mirror layer per se, but is the same kind of "durable side-channel that survives session boundaries."

**What survives as clean-sheet** (the actual remaining scope of this project):

- **Step-(b) mirror layer.** Nothing in trunk has replicated this. The durable cross-session methodology evidence store remains an open design — `phase_learnings.db` SQLite is the closest analog but is per-phase atomic, not curated long-form. `findings.md` is per-project, not cross-session. `accept-with-rationale.md` is decision-register, not evidence store.
- **Step-(c) long-lived product fork.** Distinct from per-engineer ephemeral worktrees. A workspace that survives across sessions and serves as a *permanent product home* (the (B) direction in original Q1) is still unmodeled. Per-engineer-chunk worktrees are *temp dev forks rebasing to trunk* (the (A) direction); a permanent-home shape would be additive.

---

## 2. Confirmed constraints

- **Q11 reactivation triggers must fire before execution.** Three named triggers from the original §7:
  1. Auto-load surface creeps back up *post-trim* — index entries grow, KB pointers explode, methodology re-bloats. Trigger = "the step-(a) win has eroded."
  2. Routine multi-product sessions — the user works across N products in a single session frequently enough that per-product context-switching becomes a constraint trunk methodology can't absorb.
  3. Methodology-variant testbeds — the team wants to A/B test methodology changes without polluting trunk's evolution path.
- **NO triggers fired as of 2026-05-11.** MEMORY.md is currently 35.2KB exceeding 24.4KB index limit per session reminder, BUT the prescribed methodology response is *index trimming*, not workspace isolation reactivation. Trigger #1 was for *post-trim* creep, not "the index has grown."
- **Concept-only scoping.** This PROJECT.md is a placeholder + survival path. Do not execute. No engineer dispatched until user reactivates.
- **Refresh-not-rewrite.** The original 11-Q § 7 is preserved in `.claude/snapshots/projects-2026-05-03_024603/projects-root/methodology-mirror-and-workspaces/PROJECT.md`. This revision narrows scope; it does not erase the original design.

---

## 3. Design principles (revised)

1. **Q11 evidence-driven, not calendar-driven.** Reactivation is gated on observable methodology constraint, not "it's been N weeks."
2. **Don't re-implement what trunk shipped naturally.** Per-engineer worktrees, template/seed workspaces, archive cleanup, two-session architect/operator pattern, autonomous-operator-via-subagent — these all absorbed parts of the original 11-Q design space. Mirror layer + permanent-home workspace are the residual clean-sheet pieces.
3. **Mirror layer ≠ auto-load.** The mirror's whole point is durable cross-session evidence that DOES NOT pay the auto-load tax. Anything that would otherwise live in MEMORY.md but is "too low-traffic" or "too narrative" belongs in the mirror.
4. **Permanent-home workspace ≠ per-engineer ephemeral.** Different lifecycle, different ownership, different promote-to-trunk cadence.

---

## 3a. Seed-first analysis

N/A — methodology-tooling project, not product code. Per-product code-count litmus: **0** lines.

---

## 4. Scope (revised)

**In scope (deferred until Q11 fires):**

- **Step (b) — mirror layer.** Design a durable cross-session methodology evidence store. Read/write API, storage shape, integration with `phase_learnings.db` + `findings.md` + `accept-with-rationale.md` (the three existing learning artifacts).
- **Step (c) — long-lived product fork.** Design the (B)-direction workspace shape (permanent product home) as additive to (A)-direction per-engineer worktrees. Promote-to-trunk cadence, drift-management policy.

**Out of scope:**

- Anything already shipped naturally: per-engineer worktrees, seed/template workspaces, archive cleanup, two-session pattern.
- The 8 original §7 questions whose answers settled structurally during 2026-05-03 → 2026-05-11.
- Step (a) — already shipped 2026-05-02; not in scope for any revision.

---

## 5. Files (forward-looking — not yet authored)

- `KB § PATTERNS/methodology-mirror.md` (if step-(b) executes)
- `KB § PATTERNS/long-lived-product-fork.md` (if step-(c) executes)
- `noctusai_lib.testing.mirror` or equivalent module (if step-(b) needs runtime code)
- `scripts/promote-product-fork.sh` (if step-(c) needs tooling parallel to template workspace's promotion manifest)

---

## 6. Implementation phases

**Status: SCOPED, NOT EXECUTING.** Phase 0 + onward are sketches only; do not execute without Q11 trigger + fresh §7 round.

### Phase 0 — Trigger evaluation + scope confirmation 🅿️ (blocked on Q11)

- [ ] Confirm one of Q11's three reactivation triggers has fired (with evidence — auto-load surface measurement re-taken, or routine multi-product session pattern documented, or methodology-variant testbed user-requested).
- [ ] Re-read the original 11-Q § 7 in snapshot; mark which questions still need answering (Q7 settled, Q6 partially-absorbed, others mostly intact).
- [ ] Run §7 interrogation round on the revised narrow scope (mirror + permanent-home).

### Phase 1 — Step (b) mirror layer design 🅿️ (deferred)

- [ ] Design the storage shape (SQLite extension to `phase_learnings.db` vs. separate `methodology-mirror.db` vs. on-disk NDJSON like `project-history/ledger.ndjson`).
- [ ] Design the read/write API (MCP tool surface vs. CLI vs. both).
- [ ] Integration with `findings.md` (per-project curated) + `accept-with-rationale.md` (decision register) + `phase_learnings.db` (atomic per-phase).
- [ ] Pilot one cross-session pattern absorption to validate the shape.

### Phase 2 — Step (c) permanent-home workspace design 🅿️ (deferred)

- [ ] Define (B)-direction workspace shape — permanent product home distinct from per-engineer ephemeral worktrees.
- [ ] Promote-to-trunk cadence and drift-management policy.
- [ ] Tooling parity with template workspace's promotion manifest, if applicable.

### Phase 3 — Project close 🅿️ (deferred)

- [ ] Confirm Phase 1 + Phase 2 shipped + KB pages live.
- [ ] Fold outcomes into parent batch §11 (if batch still open) or `KB § PATTERNS/methodology-codification-pipeline.md` (if batch closed).
- [ ] Final commit + push (literal last step).
- [ ] Delete this folder.

---

## 7. Open questions (revised — narrow)

The original 11-Q § 7 is preserved in snapshot. **Revised narrow §7** for the residual scope:

1. **Q11 reactivation evidence.** What concrete observation justifies re-opening this project? *Default recommendation:* re-measure auto-load surface (CLAUDE.md + MEMORY.md tokens) periodically; reactivation fires if post-trim auto-load surface exceeds the 2026-05-02 baseline by ≥15%. Routine multi-product sessions (≥3 products touched per session) for ≥2 consecutive weeks also qualify. Methodology-variant testbed remains a discretionary trigger.
2. **Mirror layer storage shape.** SQLite extension to `phase_learnings.db` OR separate store OR on-disk NDJSON? *Default recommendation:* SQLite extension if the access pattern is per-session-query; NDJSON if the access pattern is render-to-prose. *Note:* `project-history/ledger.ndjson` is precedent for the NDJSON shape and is now load-bearing — building on it is cheaper than parallel SQLite.
3. **Mirror layer scope discipline.** What belongs in the mirror vs. MEMORY.md vs. KB? *Default recommendation:* MEMORY.md = always-loaded index; KB = on-demand authoritative reference; mirror = durable cross-session evidence that doesn't justify either. Examples: a slip-once-then-fixed memory entry that's no longer load-bearing but is valuable for "have we seen this before?" queries.
4. **Permanent-home workspace overlap with seed workspace.** Is there meaningful daylight between a long-lived product fork (this project's c-step) and a sibling seed workspace (KB § PATTERNS/seed-workspace.md)? *Default recommendation:* both consume noc whole; the distinguishing axis is *lifecycle ownership* (seed workspace = sibling product home; permanent product fork = methodology-variant testbed or pre-trunk staging). Surface at Phase 2 §7.

---

## 8. Dependencies & blockers

- **Q11 reactivation trigger un-fired** — primary blocker. No execution starts without trigger evidence.
- **MEMORY.md index trimming** — orthogonal task that may incidentally reduce trigger pressure without solving the underlying methodology question. Surfaced as a separate small follow-up by Tier-4 surfacing doc §5.3.(c).
- **Seed workspace + template workspace settling** — both shipped recently; they should season for a few months before "permanent product home" is designed (to avoid re-implementing what they'll absorb naturally).

---

## 9. Success criteria

- Q11 trigger fires + user reactivates → fresh §7 → Phase 0 → execution.
- OR Q11 stays un-fired indefinitely → this PROJECT.md remains the durable survival path for the design intent; no execution needed.
- Either outcome is acceptable. The original step-(a) win (22% static + 35-50% effective token savings) is durable regardless.

---

## 10. How to use this plan

```bash
# Read this revised concept
cat projects/methodology-mirror-and-workspaces/PROJECT.md

# Original 11-Q concept (snapshot, read-only)
cat .claude/snapshots/projects-2026-05-03_024603/projects-root/methodology-mirror-and-workspaces/PROJECT.md

# Tier-4 surfacing doc that informed this revision
cat archive/projects/2026-05-11/63-tier4-concept-trio-surfacing/PROJECT.md

# Re-measure auto-load surface (Q11 trigger #1 evaluation)
python mcp/noctusai/cli.py --token-budget CLAUDE.md
python mcp/noctusai/cli.py --token-budget MEMORY.md

# If trigger fires — run revised §7 + Phase 0
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-02 | Original concept filed (11-Q § 7; 470 lines). Steps (b) + (c) of the methodology-extraction trilogy; step (a) shipped same day with 22% static + 35-50% effective token savings. | Claude Opus 4.7 |
| 2026-05-03 | Folder deleted via close-gate Wave 2 commit `38ab384`; original concept preserved in snapshot `.claude/snapshots/projects-2026-05-03_024603/`. Status flipped to concept-deferred pending Q11 reactivation. | Claude Opus 4.7 |
| 2026-05-11 | Tier-4 concept-trio surfacing doc (`archive/projects/2026-05-11/63-tier4-concept-trio-surfacing/`) §5.3 surfaced: Q11 triggers NOT fired; substantial portions of original 11-Q design space naturally addressed by other shipped infrastructure (per-engineer worktrees, ephemeral .claude/worktrees, template workspace + promotion manifest, seed workspace, two-session architect/operator pattern). Recommendation: REVISE concept narrower + LEAVE-DEFERRED. | Engineer TIER4-SURFACE (Claude Opus 4.7) |
| 2026-05-11 | **Concept REVISED per parent batch Phase 4.d decision.** Scope narrowed to two clean-sheet residuals: (b) mirror layer (durable cross-session methodology evidence store, distinct from auto-load) + (c) long-lived product fork (permanent product home, distinct from per-engineer ephemeral worktrees). 8 of 11 original §7 questions settled structurally or absorbed by other shipped infrastructure; revised §7 has 4 narrow questions. Status flipped from concept-deferred to **SCOPED — deferred pending Q11 trigger**. Folder recreated at `projects/methodology-mirror-and-workspaces/` (live, not archived) as durable survival path. | Claude Opus 4.7 (Engineer MCB-CLOSE) |
