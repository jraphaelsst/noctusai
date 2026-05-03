# Master-Tree Parallel Batches — Pattern

> **What this is.** A multi-product orchestrator project ("master-tree") that sequences N≥2 sister projects sharing the same methodology, executing same-shape phases as **synchronized parallel batches** rather than serially. Cross-pollination happens **live** during a batch (agents share findings as they surface) and is consolidated at sync-gates between batches.
>
> **What this replaces.** The earlier serial-rollout pattern (`run child A to ✅ → harvest lessons → run child B to ✅`). The harvest-gate model assumed lessons could only flow once a child closed. The parallel-batch model is the same idea pulled forward in time: lessons flow continuously while children execute in lockstep.
>
> **When to apply.** N≥2 sister projects whose phase shape aligns for at least 60% of the work AND whose findings are likely to recur across products (cross-cutting helpers, gap-table patterns, RLS holes, DTO drift). When alignment is below 60%, prefer the serial-rollout pattern. When products diverge fundamentally, file independent projects without a master.
>
> **Cross-references.** `KB § PATTERNS/project-execution.md § 2.7 The recurrence rule` (the underlying discovery mechanic), `§ 2.6 Active robustness review` (eyes-open during batches), `§ 2.5 Phase 0 audits` (each child still runs its own), `§ 8 Slug naming` (master uses `-rollout` intent), `feedback_master_tree_parallel_batches.md` (working agreement).

---

## 1. Why parallel batches

When a methodology is being applied to N products, two things tend to be true:

1. **Same-shape phases benefit from same-time reasoning.** Inventorying gaps in PF and ERP simultaneously is cheaper than inventorying them in series — the agents hold the same mental model in active context, the same `noctusai_scan_*` queries run for both products, and the absorption catalog grows with N data points instead of waiting for one child to close.
2. **Recurrence is the highest-value signal.** When PF Phase 0 finds a candidate helper at N=1 and ERP Phase 0 (running concurrently) confirms it at N=2, the recurrence rule fires immediately. In the serial model, that signal arrives at PF Phase 7 close at the earliest.

The master-tree exists to:
- **Sequence batches** (not children).
- **Share artifacts** that span products (live patterns log, cross-product absorption catalog, design-batch aggregator).
- **Run sync-gates** between batches that consolidate findings before the next batch starts.
- **Carve out divergence** — when a batch maps cleanly to product A but ERP needs three batches to cover the same surface, the master flags the divergence and runs the divergent batch in parallel with degraded shape-sharing (process synchronicity, not shape synchronicity).

The therapy pilot (`therapy-platform-wiring`) already proved this microcosmically: Phase 0 dispatched 4 parallel Explore agents to enumerate routers, hooks, migrations, and seed-lib exports in one wall-clock unit. The master-tree generalizes that mechanic across phases.

---

## 2. Structure

### 2.1 Batches replace passthrough phases

In the serial-rollout master, master-phases were passthroughs to children. In the parallel-batch master, **batches are the unit**. Each batch corresponds to a same-shape phase across all participating children.

```
Batch B0  ── PF Phase 0  ║  ERP Phase 0   (Discovery + inventory)
Batch B1  ── PF Phase 1  ║  ERP Phase 1   (Seed seam absorption)
Batch B2  ── PF Phase 2  ║  ERP Phase 2   (Tier A: known regressions)
Batch B3  ── PF Phase 3  ║  ERP Phase 3   (Tier B: DTO normalization)
Batch B4  ── PF Phase 4  ║  ERP Phase 4   (Tier C: scaffolding + RLS)
Batch B5* ── PF Phase 5  ║  ERP Phases 5–8 (DIVERGENT — see §4)
Batch B6  ── PF Phase 6  ║  ERP Phase 9   (Public + auth)
Batch B7  ── PF Phase 7  ║  ERP Phase 10  (End-to-end verification)
```

Each batch has three explicit moments: **pre-batch sync-gate**, **execution** (parallel), **post-batch consolidation**.

### 2.2 Pre-batch sync-gate (open the batch)

Before any child agent dispatches, the master:

1. **Re-reads the live patterns log** + cross-product absorption catalog. New entries from the previous batch shape this batch's plan.
2. **Folds new seed gifts into both children's plans.** If a sister project (e.g. therapy) shipped a helper since the last batch, the master edits both children's PROJECT.md to consume it (`§5.1 Inherited seed seams` table updates).
3. **Aggregates design questions across children.** The master surfaces ONE combined design batch to the user (e.g. "PF and ERP both need a Pattern A decision; here are the differences"). One sign-off serves both children.
4. **Confirms shape alignment** — does this batch run as a parallel-shape batch or as a divergent batch (§4)? Logged in the master's §11.

### 2.3 Execution — the parallel mechanic

The master dispatches per-product subagents (Explore for read-only scans; general-purpose for code edits) **in a single tool-use turn** so they run concurrently. Each subagent:

- Owns its product's checkbox-state in the child PROJECT.md (live-tick).
- Posts findings to the **live patterns log** as it discovers them (append-only file at the master's root).
- Reads the live patterns log on every meaningful pause — when its sibling has flagged a recurrence, this agent looks for the same in its product **before walking away from the file**.
- Files **inline-applied improvements** in its child §11 (no separate proposal file per `feedback_apply_inline_delete_proposals`).

The master agent (this Claude session) is the **orchestrator + sync-gate keeper**. It does not edit product code directly during batches; it orchestrates the children's subagents and consolidates their outputs at the gates.

### 2.4 Post-batch consolidation (close the batch)

When both children's batch-tasks are ✅:

1. **Walk the patterns log.** Promote any candidate that hit N≥2 across the children to `formalize` in the cross-product absorption catalog. File a seed-absorption follow-up project for each (or apply inline if the helper is small enough).
2. **Update both children's §11.** Each child gets a §11 entry with a back-pointer to the master's batch number. The master's §11 also gets an entry summarizing the batch's cross-cutting findings.
3. **Update both children's `improvements.md`** via `noctus.dev.improvements`.
4. **Run KB sync** (`bash scripts/verify-kb-sync.sh`) if any KB pages were touched by the batch.
5. **Create per-batch local commit** in the master scope (no push). The children's per-phase commits land alongside, scoped to each child's diff.
6. **Pause for user signal** before opening the next batch — same phase-by-phase cadence as a single project, just at the batch level.

---

## 3. Live shared artifacts

The master-tree owns three append-only files at its project root:

### 3.1 `live-patterns-log.md`

Append-only. Every meaningful finding from any child during any batch lands here as a one-line entry:

```markdown
| Timestamp | Batch | Product | Finding | Suggested action |
|---|---|---|---|---|
| 2026-05-04 14:23 | B0 | PF | `_resolve_user_id` recurrence in 3 services | candidate for absorption catalog |
| 2026-05-04 14:31 | B0 | ERP | same recurrence in 7 services — N≥2 confirmed | promote to `formalize` |
| 2026-05-04 14:45 | B0 | both | Pattern A path-mismatch confirmed on 11 routers (PF: 3, ERP: 8) | bundle for design batch |
```

The agents read this file on every meaningful pause. The master reads it at every sync-gate. This is the **shared scratchpad** — the medium through which the parallel agents collaborate.

### 3.2 `cross-product-absorption-catalog.md`

Per-row durable register of helper / DTO / mapper candidates with recurrence count + triage outcome (`pending` / `formalized` / `accepted-with-rationale` / `deferred-with-named-followup`). Entries graduate based on N=2 promotion rule. At project close, every row has a non-`pending` outcome (per master Phase-N close-out criteria).

### 3.3 `design-batch-aggregator.md`

When a child surfaces a design question that almost certainly affects the sibling, it lands here instead of in the child's §7. The master batches design Qs from both children, surfaces ONE combined sign-off to the user at the pre-batch gate, then folds answers back into both children's §7. Reduces user-interruption count from 2N to ~N.

---

## 4. Divergent batches

When children's phase shapes don't align (e.g. PF has one product-specific phase covering scheduler + yfinance + AI-indicator wiring; ERP has four phases covering admin + leader+agent + portal-cliente + integrations), the batch that spans the divergence is a **divergent batch**.

Divergent batch rules:

1. **Process synchronicity, not shape synchronicity.** Both children execute their respective phase(s) concurrently. Findings still flow through the live patterns log. But the master does NOT enforce "same checkboxes both sides."
2. **The wider child commits inside the divergent batch.** If ERP needs 4 phases and PF needs 1, ERP closes 4 phases in its child PROJECT.md inside this single master-batch. PF closes 1. The batch closes when both are done.
3. **The next non-divergent batch waits for both.** Sync-gate logic still applies. The master does not race ahead with PF into the next batch while ERP is mid-divergent.
4. **The master logs the divergence in §11** with a back-pointer to which sub-phases mapped to which.

Divergent batches are the longest in wall-clock time; they're also where cross-pollination is most valuable, because the wider child often surfaces patterns the narrower child didn't think to look for.

---

## 5. Agent collaboration mechanics

### 5.1 Per-batch dispatch shape

```
Master agent (this Claude session)
    ├── Pre-batch sync-gate (read live-patterns-log, fold gifts, aggregate Qs, surface to user)
    ├── Dispatch [Explore/general-purpose × N children] in ONE tool-use turn
    │     ├── Child A subagent: works in products/<A>/, posts to live-patterns-log
    │     └── Child B subagent: works in products/<B>/, posts to live-patterns-log
    ├── Receive both subagents' results
    ├── Post-batch consolidation (walk patterns log, promote N≥2, update §11s)
    └── Pause for user signal → next batch
```

The single tool-use turn is critical: per `CLAUDE.md → § Using your tools`, parallel subagents only run concurrently when dispatched in the same message.

### 5.2 What subagents share

- **Findings** (via live-patterns-log).
- **Recurrence flags** — when subagent A flags a candidate at N=1, subagent B is briefed to look for it in its product.
- **Seed-absorption candidates** — populate the catalog as they surface, not at batch close.

### 5.3 What subagents don't share

- **Product-specific code edits.** Each subagent owns its product's edits exclusively. Cross-edit coordination is the master's job at the sync-gate.
- **Child PROJECT.md ownership.** Subagent A live-ticks child A's PROJECT.md only. Same for B.
- **Test execution.** Each subagent runs tests for its product. Seed-test runs are deduplicated (whichever subagent touches seed runs the seed test pass; the other agent is briefed of the result).

### 5.4 Briefing the subagents

Per-batch prompts to subagents must include:

1. **Batch number + child's specific phase number** in that batch.
2. **The live-patterns-log path** + instruction to read it before starting and after every meaningful pause.
3. **The absorption-catalog path** + instruction to append candidates as they surface.
4. **The sibling's product** + a one-paragraph summary of what the sibling agent is doing in parallel, so cross-pollination is intentional.
5. **The sync-gate exit criteria** — "your batch closes when these specific child-phase sub-tasks are ✅ AND you've appended at least N findings to the live-patterns-log (or quoted the command that confirms zero findings)."

---

## 6. Sync gates — pre / mid / post

### 6.1 Pre-batch gate (before dispatch)

- [ ] Live-patterns-log read; new entries from previous batch folded into this batch's plan.
- [ ] New seed gifts (from sister projects that shipped since last batch) folded into both children's `§5.1 Inherited seed seams`.
- [ ] Design Qs aggregated across children; ONE combined Q-batch surfaced to user.
- [ ] Shape alignment confirmed (parallel-shape vs. divergent).
- [ ] Subagent prompts drafted with all five briefing items (§5.4).

### 6.2 Mid-batch gate (called when one subagent flags a recurrence)

When child A's subagent posts a recurrence flag to live-patterns-log at N=1:

- [ ] Master reads the entry.
- [ ] Master sends a **brief** message to child B's subagent (via SendMessage / agent continuation) — "look for this same pattern in your product before continuing."
- [ ] Child B's subagent confirms (N=2 → promote to absorption catalog) or refutes (logs the absence; stays at N=1).
- [ ] Master records the resolution in live-patterns-log + absorption catalog.

Mid-batch gates are lightweight. They do NOT pause execution; they are interrupt-driven, not poll-driven.

### 6.3 Post-batch gate (before closing the batch)

- [ ] Both children's batch-tasks are ✅.
- [ ] Live-patterns-log walked; absorption catalog updated; N≥2 candidates promoted.
- [ ] Both children's §11 entries written.
- [ ] Both children's `improvements.md` regenerated.
- [ ] KB sync run (if any KB pages touched).
- [ ] Per-batch local commit in master scope (children's commits land alongside).
- [ ] **Pause for user signal** before next batch.

---

## 7. End-of-rollout discipline

When the final batch closes:

1. **Catalog triage close-out.** Every row in `cross-product-absorption-catalog.md` lands on `formalized` / `accepted-with-rationale` / `deferred-with-named-followup`. No row may close as `pending` or `open`.
2. **Migration of catalog content.** `formalized` rows trigger seed-absorption follow-up projects. `accepted-with-rationale` rows are migrated to `KB § PATTERNS/accept-with-rationale.md` (durable register, survives folder deletion). `deferred` rows point at named follow-up projects (file the missing PROJECT.md if not yet filed).
3. **Final cross-product retrospective.** Each child files `<slug>-lessons.md` at its own root. Master files `rollout-retrospective.md` summarizing batch-by-batch shape: which batches benefited most from parallelism, which were divergent, which surfaced the most absorption candidates, which had the most user-aggregated Qs.
4. **Close-out commit + push.** Master's per-phase commits + children's per-phase commits stage and push at the literal last step (per `feedback_no_auto_commit`). This is the single push gate for the whole rollout.

---

## 8. Anti-patterns

- **Racing one child ahead.** "PF is faster, let's run PF Batch 3 while ERP is still on Batch 2." NO — sync-gates depend on lockstep. Race-aheads invalidate cross-pollination.
- **Skipping the live-patterns-log.** "I'll just remember the findings." NO — the log is durable and survives the agent's context window. It is also the medium through which the sibling agent reads your findings.
- **Filing per-child design Qs at user.** When two children both surface the same Q, the master aggregates. Two separate sign-off rounds for the same Q is user-aggravation theater.
- **Treating divergent batches as a failure mode.** They aren't — most cross-cutting platforms have at least one. The carve-out is part of the pattern, not a rule violation.
- **Dispatching subagents in separate messages.** Two messages = two serial sessions. One message with multiple Agent tool uses = parallel execution. Get the message structure right or the parallelism is fictional.
- **Master agent editing product code during a batch.** The master orchestrates; the subagents execute. When the master edits product code, it pollutes the sync-gate's notion of "what changed in this batch" and confuses the §11 attribution.
- **Forgetting the sibling project (e.g. pilot).** A pilot that ships seed gifts mid-rollout is an input, not a child. The master must fold its outputs into both children's `§5.1 Inherited seed seams` at every pre-batch gate.

---

## 9. Worked example — `products-wiring-rollout` (2026-05-03)

The master orchestrates `personal-finance-wiring` (7 phases) + `erp-imobiliario-wiring` (10 phases). The therapy pilot (`therapy-platform-wiring`, 11 phases, currently at Phase 1 ✅) is an input that ships seed gifts (`fetch_user_identities` shipped Phase 1; pagination DTO proposed Phase 3).

Batch mapping:

| Batch | PF phase | ERP phase | Shape | Therapy supplier |
|---|---|---|---|---|
| B0 | P0 (Discovery) | P0 (Discovery) | Parallel-shape | Live patterns log seeded with therapy's Patterns A-G |
| B1 | P1 (Seed absorption) | P1 (Seed absorption) | Parallel-shape | `fetch_user_identities` consumed by both |
| B2 | P2 (Tier A 404/405) | P2 (Tier A 404/405) | Parallel-shape | — |
| B3 | P3 (Tier B DTO) | P3 (Tier B DTO) | Parallel-shape | Pagination DTO consumed by both if shipped |
| B4 | P4 (Tier C RLS) | P4 (Tier C RLS) | Parallel-shape | — |
| B5 | P5 (Scheduler+yfinance+AI) | P5+P6+P7+P8 (Admin+Agent+Portal+Integration) | **Divergent** | — |
| B6 | P6 (Public+auth) | P9 (Public+auth) | Parallel-shape | — |
| B7 | P7 (E2E verification) | P10 (E2E verification) | Parallel-shape | Final close + lessons + push |

Live artifacts in `projects/products-wiring-rollout/`:
- `live-patterns-log.md`
- `cross-product-absorption-catalog.md`
- `design-batch-aggregator.md`
- `rollout-retrospective.md` (filed at B7 close)

Reference: `projects/products-wiring-rollout/PROJECT.md`.

---

## 10. When NOT to use this pattern

- **Single-product project.** No parallelism axis exists; use the standard per-project shape.
- **Children with <60% shape alignment.** Most batches would be divergent; the parallelism overhead exceeds the benefit. Use serial-rollout instead.
- **Children whose deliverables conflict.** When child A's edits to seed-lib would block child B's progress (or vice versa), serial execution is mandatory; parallelism would create collisions per `KB § PATTERNS/project-execution.md § 2.9`.
- **Children at very different maturity.** A scaffolded child + a Phase-7-of-10 child cannot run lockstep batches. Run the mature child to ✅ first, then file the rollout for the remaining children.
- **One-shot exploratory work.** When the goal is "see what we find" rather than "apply this methodology N times," batches are over-structured. Use direct subagent dispatch without the master-tree apparatus.
