# {{PROJECT_NAME}} — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project document evolves. Revise phases, fold in
> optimizations, update the Change Log. A project that survives execution
> unchanged is either trivial work or ignored information. See
> `CLAUDE.md → Engineering Philosophy → Projects are living documents`.
>
> **Before drafting or revising this project document: interrogate the user first.** Ask
> clarifying questions, confirm constraints, surface edge cases. Never assume.
> Document each answer in §2 so future agents inherit the reasoning.
>
> **Write for a zero-context reader.** Assume the next agent to pick up this
> project has not seen the conversation that produced it. Inline context in §1,
> quote the user in §2, name files with paths in §5, pair every §7 Open Question
> with an evidence-backed recommendation, and make §10 commands copy-paste
> ready. Full guidance in `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md §10`.
>
> **Symbol-first authoring.** Use the doc-symbology glossary by default for §6 phase headers, §11 change-log entries, and any dense-bullet section — `KB § PATTERNS/doc-symbology.md`. Lossless-swap test gates every prose→symbol swap. Phase status: `✅` shipped · `⏳` in-progress · `❌` failed · `🔒` blocked on dependency · `🅿️` blocked on user. Triage outcomes: `[F]` formalize · `[R]` refactor · `[A]` accept-with-rationale. Codification stages: `s1` emerges → `s2` memory → `s3` KB+CLAUDE.md → `s4` keeper detector. Recurrence: `N=2` ⇒ triage; `N≥3` ⇒ MUST formalize.
>
> **Terminology:** NoctusAI uses *project* for what other teams call a "plan"
> (the design-and-execution doc for a focused piece of work). This template
> replaces the former `PLAN-TEMPLATE.md`. Existing `*-PLAN.md` files may still
> exist until renamed in follow-up passes — treat them as projects regardless.

- **Created:** {{YYYY-MM-DD}}
- **Last updated:** {{YYYY-MM-DD}}
- **Status:** {{e.g. "Design locked → Phase 1 ready" / "Phase 3 in progress" / "Done"}}
- **Owner / stakeholders:** {{USER}} · {{OTHERS}}
- **Related docs:** {{KB paths, linked *-PROJECT.md files, MASTER-PROMPT.md, external refs}}
- **Project slug:** {{lowercase-dash-separated. Lives at one of three locations driven by scope: `projects/<slug>/` (cross-product / platform-infra / not-yet-a-product migrations), `products/<product>/projects/<slug>/` (single-product), or `core/projects/<slug>/` (core control-plane: auth, SSO, billing, orgs). Follow the `<subject>-<intent>` convention and scope→location rule in `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md §1 and §8` (intents: `migration`, `expansion`, `wiring`, `gap`, `refactor`, `hardening`, `rollout`, `consolidation`, `baseline`). Pick slug AND location before writing the file — renaming / moving later churns proposal paths.}}

---

## 1. Context & Purpose

{{One or two paragraphs. Answer: why does this project exist? What's the problem or opportunity? Who feels the pain today? What does the win look like?}}

---

## 2. Confirmed constraints

Things the user told us that shape the design. **Document non-obvious answers** — future agents inherit the reasoning, not just the outcome. Prefer the format:

- **{{topic}}** — {{answer}}. *({{why this matters / what it rules out}})*

Examples:
- **Hierarchy** — 3 tiers: owner → leaders → agents. *(Rules out flat model; drives RLS design.)*
- **Cadence** — biweekly closing rolls up to monthly. *(Periods table needs parent-child relation.)*
- **Privacy** — leaders must never see other teams' numbers. *(Drives per-team RLS policies.)*

---

## 3. Design principles

How we're approaching *this specific problem* (beyond the platform-wide `CLAUDE.md` rules).

1. {{PRINCIPLE — e.g. "No double entry: actuals derive from existing ERP entities via triggers"}}
2. {{PRINCIPLE}}
3. {{PRINCIPLE}}

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

> **Rule.** EVERY project — not just cross-product ones — runs the seed-first checklist (`KB § GUIDES/seed-first-design.md`) BEFORE phase planning, and records the conclusions here. *Why every project:* the seed is the skeleton of every product, so even a single-product change might have a pattern/component/helper better placed in seed. Single-product projects whose answers all point at product-specific still fill §3a (it's the explicit confirmation that the design is correctly product-bounded). **No replication framing in §6** — if your phase plan walks through products one by one, the design is wrong; restart from this section. Future agents must deliver projects already seed-thought, not refactored after the fact.

Run the six-question checklist (`KB § GUIDES/seed-first-design.md § The seed-first checklist`):

1. **Is the contract identical for every product?** {{YES / NO + brief reasoning}}
2. **Is the data source product-specific?** {{YES — per-product hooks; container is seedable / NO — uniform data}}
3. **Is the placement product-specific?** {{YES — domain-bound (e.g. CampaignDetail tab) / NO — universal (e.g. /settings/ai)}}
4. **Is the visibility / permission rule the same?** {{YES — uniform gate / NO — product-specific}}
5. **Does the seam already exist in seed?** {{YES — `seam-name` at `path` / NO — new seam needed}}
6. **Default-on or opt-in?** {{DEFAULT-ON — universally beneficial; opt-out via flag / OPT-IN — sometimes-applicable}}

**Litmus — per-product code count this design requires:**

- [ ] **0 lines** — pure cross-product concern; lives entirely in seed. Products inherit from the factory. *(Most cases.)*
- [ ] **1 line** — opt-out flag or opt-in component prop. Acceptable when justified.
- [ ] **A small section** — product-specific data wiring around a seed-shaped container (e.g. `<DigestCard prose={useProductSpecificHook().data}/>`). Acceptable for product-specific data sources.
- [ ] **Multiple files / pages / mounts per product** — STOP. Re-design.

**Phase plan implications:** state explicitly here whether §6 phases work in seed (correct) or walk through products (wrong). If the latter, restart §3a.

---

## 4. Scope

**In scope:**
- {{capability}}
- {{capability}}

**Out of scope (for now — with reason):**
- {{deferred item}} — {{why deferred: future phase? cost too high? needs product validation first?}}
- {{deferred item}} — {{reason}}

---

## 4a. Dispatch routing (REQUIRED — the slice-to-engineer map)

> **Rule.** Every PROJECT.md doubles as a dispatch brief. The tech-lead writes this section *before dispatching any slice* so the engineer (or inline-lens) knows their slice boundaries, which specialist `owns_kb` the work, what codification surfaces to expect, and which routes the tech-lead has already pre-rejected. Without §4a, dispatches drift (engineers infer scope, surface as drift-found, scope-expand, or skip codification stages). With §4a, the engineer reads ONE section and knows what's theirs. **`KB § PATTERNS/common/dispatch-with-project-and-notes.md`** is the canonical reference.
>
> **Block-on-surface.** If during execution an engineer (or inline-lens) sees a better route than the dispatched one, they STOP, write a **surface note** (`noctus.dev.file_proposal kind="surface"`), and wait for the tech-lead to approve / reject / adapt with rationale. They do NOT proceed on un-approved divergence. This is the "agents don't get lost" gate.

### 4a.1 Slice → Lens table

| Slice / Phase | Lens | Files (or globs) | Time-box | Dispatched as |
|---|---|---|---|---|
| {{Phase 1 / W1-A}} | {{backend-engineer / frontend-engineer / devops-engineer / architect-inline / security-advisor / compliance-advisor}} | {{paths}} | {{e.g. 2h}} | {{Agent dispatch / inline-empersonation / advisor consult}} |
| {{Phase 2 / W1-B}} | {{…}} | {{…}} | {{…}} | {{…}} |

*Inline-empersonation: tech-lead applies the named lens's discipline + `owns_kb` until the slice's commit, then switches. Same as dispatch but no subagent — used below the cutoff (<100 LoC ∧ <3 files) or when shared-state demands a single coherent voice. See `KB § PATTERNS/architect/parallelization-first-orchestration.md`.*

### 4a.2 Codification expectations per slice

For each slice, mark which codification stages the tech-lead expects to land. Agents log the marked stages explicitly in their **delivery note** so `check_codification_pipeline_health` stays fed.

| Slice | s1 detected | s2 to memory | s3 KB+CLAUDE.md | s4 keeper | Why |
|---|---|---|---|---|---|
| {{Phase 1}} | {{yes/no}} | {{yes/no}} | {{yes/no}} | {{yes/no}} | {{e.g. "pattern recurs N≥3; lift to KB"}} |
| {{Phase 2}} | {{…}} | {{…}} | {{…}} | {{…}} | {{…}} |

*Pipeline: `s1 emergent` (recurrence detected) → `s2 memory` (logged in `MEMORY.md` index entry) → `s3 codified` (KB pattern + CLAUDE.md §1 one-liner) → `s4 keeper` (`check_*` function with severity). Skipping a stage silently is what `check_codification_pipeline_health` flags. Agents emit `s2/s3/s4` events to `project-history/auto-improvement.ndjson` via the codification log (or surface the gap in their delivery note if they couldn't).*

### 4a.3 Routes-not-taken (pre-rejected by tech-lead)

| Route | Why rejected |
|---|---|
| {{e.g. "Use Redis instead of pgvector for cache"}} | {{e.g. "Redis lacks vector type; double-store would drift; pgvector already in the stack"}} |
| {{…}} | {{…}} |

*This is where the tech-lead writes down the routes they've already considered and ruled out, so the dispatched engineer doesn't waste a turn surfacing them. Empty when truly no obvious alternatives exist — write `N/A — single viable path` rather than dropping the table.*

### 4a.4 Notes — surface + delivery

Every slice produces a **delivery note** (`noctus.dev.file_proposal kind="delivery" project="<slug>"`) at the end. A **surface note** (`kind="surface"`) is filed in-flight when the engineer sees a better route and BLOCKS until the tech-lead responds. Both kinds land in `projects/<slug>/proposals/` (the existing per-project folder — proposals = the file format; notes = the concept layer that maps to it). Filename convention: `<agent>-<ts>-<kind>-<slug>.md`.

**Delivery-note contents (minimum):**
- What landed (files + tests + acceptance hit/missed)
- Codification events emitted (s1/s2/s3/s4 — match §4a.2 expectations)
- `drift-found:` + `scoped-improvement:` (the engineer-seed two-leg footer — durable)
- Routes-not-taken that the engineer encountered + chose-not-to-surface (rationale)

**Surface-note contents:**
- Proposed alternative route (what + why)
- Linkage to §4a.1 slice scope (which boundaries it expands / contracts)
- Risk assessment (additive / breaking / cross-slice impact)
- Wait for tech-lead `noctus.dev.set_proposal_status` → `accepted` (re-dispatch with adapted brief) or `rejected` (continue original brief with rationale logged).

---

## 5. Architecture / Data Model

*Keep this section if the plan involves new data, APIs, or components. Delete if the plan is purely process-oriented.*

{{Concrete tables / API shapes / file paths / UI structure. Diagrams or ASCII sketches welcome. Specify which existing code is extended vs new.}}

---

## 6. Implementation phases

Phases are **suggestive, not strict.** Reorder, split, merge, or discover new phases as work progresses.

**Phase status-icon convention** (established by the METAS project at `products/erp-imobiliario/projects/erp-metas/PROJECT.md`). Every phase header ends with a trailing status icon — or none, if the phase hasn't been started. Sub-task checkboxes (`- [ ]` / `- [x]`) remain unchanged:

| Icon | Meaning |
|---|---|
| _(none)_ | Pending — not started |
| ⏳ | In progress / partially done (some sub-tasks blocked or deferred) |
| ✅ | Complete — every sub-task is ticked |
| ❌ | Blocked or failed — explain in the Change Log + Open questions |

A parenthetical comment may follow the icon to explain state (e.g. `✅ (shipped 2026-04-18)` or `⏳ (UI deferred to Phase N)`). Flip to `✅` **only after every sub-task inside is ticked.**

**Improvement capture happens during steps. Proposal authoring happens at end of phase.** Two distinct moments:

**During step implementation (speed — step-individual observations).** As each sub-task is built, drop short specific bullets into the phase's `**Improvements:**` block. No ceremony. The attention belongs to the step. These are step-individual-related objects — small, specific, observation-scoped. The point is to capture while the context is fresh, not to produce the final artifact.

**After every sub-task is ticked, BEFORE flipping the phase header to `✅` — synthesize ONE proposal per phase.** The in-session agent reads ALL the accumulated improvement bullets together, considers the **whole project context** (not just the phase — how do these improvements interact with each other and with other phases?), and files **one phase proposal** via `noctus.dev.file_proposal(project="<project-slug>", ...)`. The proposal lands in the project's own `proposals/` folder — at `projects/<slug>/proposals/` (root projects) or `products/<product>/projects/<slug>/proposals/` (product-scoped). The MCP tool resolves the slug automatically; pass only the slug.

**The phase proposal bundles the phase's improvements.** Each improvement within the bundle:
- Has its own brief title + linkage + application steps + risks
- States whether it is independently executable (or depends on another bundled improvement)
- Can be triaged and scheduled by the reviewer **separately**, even though the bundle is accepted / rejected as a whole

**Why one-per-phase (not one-per-improvement):** the improvements share the same phase context. Bundling preserves that context once, and all bundled items inherit it — the proposal becomes a single coherent context-transfer vehicle rather than N fragmented ones. Individual execution is preserved by the bundle's internal structure.

**Why synthesize at phase-end (not during steps):** during step execution the agent should focus on the step. Quick bullets are the capture mechanism. The rich synthesis — reading the whole block, consulting the project context, filling the template — happens once, after the phase is complete.

**Then** flip the phase header to `✅`, log the completion in §11 Change Log, and run `python mcp/noctusai/cli.py --improvements <this-project>.md` to regenerate `improvements.md` next to this project file.

Full protocol in `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md`.

---

This block is **not** a preview of upcoming phases. The project itself already lists those. Writing "Phase 3 will add X" in an improvements block duplicates what's in §6 and waters down the signal. Keep improvement blocks about the *just-completed phase's own implementation*.

**What goes into the `**Improvements:**` block (captured during steps):**
- Refactor candidates you saw but didn't take
- Edge cases discovered but not covered
- Tech debt taken on deliberately (with rationale)
- Performance / memory concerns
- Shortcuts the implementation took
- Missing tests / coverage gaps
- Specific observations about the code you just wrote

**What stays out:**
- Tasks for future phases — those are in §6
- Generic "do more tests" — only specific, actionable observations
- Praise / self-congratulation ("this went well")

If you genuinely found nothing worth flagging, write a one-line block saying so: `**Improvements:** none identified.` (and no phase proposal is needed). This distinguishes "I thought about it and there's nothing" from "I forgot".

`improvements.md` is the project's **retrospective knowledge base** — when a future iteration reworks any phase, the improvement notes gathered during the original build are the first thing to read. The **phase proposal** in the project's `proposals/` folder (at whichever of the two locations the project lives) is the platform-wide triage queue for the same content, reorganized around execution. Running both tools is **mandatory** — skipping either orphans the signal.

> **OBLIGATORY — every phase ships an `**Improvements:**` block, and it MUST be filled.** Each phase below is scaffolded with the block pre-seeded with the greppable placeholder `NOC-FILL-IMPROVEMENTS`. Before you flip a phase to `✅`, **replace** that placeholder with the real content (the improvements spotted this phase, or the literal `**Improvements:** none identified.` when there genuinely were none). The block is *never optional* and **must not remain the placeholder** — `check_phase_state_consistency` Rule 5 fails a `✅` phase whose block still contains `NOC-FILL-IMPROVEMENTS` (find unfilled blocks anytime with `grep -rn NOC-FILL-IMPROVEMENTS`). "None identified" is a real, valid fill; the placeholder is not.

### Phase 1 — {{Phase name, e.g. "Foundation (migration + core models)"}}
- [ ] {{task}}
- [ ] {{task}}

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`: replace with the methodology improvements spotted this phase, or write "none identified." Never ship this placeholder (keeper Rule 5 blocks it)._

### Phase 2 — {{Phase name}}
- [ ] {{task}}

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`: replace with the methodology improvements spotted this phase, or write "none identified." Never ship this placeholder (keeper Rule 5 blocks it)._

### Phase 3 — {{Phase name}}
- [ ] {{task}}

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`: replace with the methodology improvements spotted this phase, or write "none identified." Never ship this placeholder (keeper Rule 5 blocks it)._

*(Add phases as needed — each new phase carries the same pre-seeded `**Improvements:**` placeholder. Add the status icon to the phase header when state changes.)*

---

### Example — a completed phase

```
### Phase 1 — Foundation ✅

- [x] Create module X
- [x] Write tests
- [x] Wire into factory

**Improvements:**
- `X` uses a flat list for its cache; switch to LRU when Y grows past Z entries.
- `_reset_for_testing` is publicly exposed; move to a `testing` submodule in a future rework.
- Missing coverage: no test for the concurrency-across-orgs scenario.
- We chose exception-swallowing on Tier 1 failure — log at WARN if we revisit.
- The module + tests + factory wiring are three separate import hops; a `register_X()` helper in the factory would close the loop for future similar modules.

*Phase proposal filed:* `<project-folder>/proposals/claude-opus-4-7-20260418-phase-1-foundation-bundle.md` (where `<project-folder>` is `projects/<slug>/` for root projects or `products/<product>/projects/<slug>/` for product-scoped) — bundles the five improvements above; each is independently executable and the proposal names dependencies where they exist.
```

### Example — a partially-done phase (some sub-tasks deferred)

```
### Phase 2 — Teams & membership ⏳ (UI deferred pending UX confirmation)

- [x] Backend CRUD + service layer
- [x] Tests (22 assertions)
- [ ] UI: drag-and-drop team editor — blocked on UX decisions
- [ ] Seed existing teams — blocked on auth profiles

**Improvements:**
- Membership change reconciles leader papel automatically — works but surprising. Document in MASTER-PROMPT.
```

---

## 7. Open questions

Unresolved items. Each should be tagged with *when it needs an answer* (which phase) and *who answers* (user, stakeholder, or "to discover during build").

1. **{{Question}}** — needs answer before {{phase}} / decided by {{whom}}.
2. **{{Question}}** — deferred until Phase {{N}}.

---

## 8. Dependencies & blockers

External things the plan hinges on. Be explicit — surprises here cost the most.

- **{{Dependency}}** — {{e.g. "Owner must run migration in Supabase SQL editor before Phase 2 tests can pass"}}
- **{{Dependency}}**

---

## 9. Success criteria

What does "done" look like? Measurable, verifiable.

- {{Criterion — e.g. "All three test layers pass (unit + integration + e2e)"}}
- {{Criterion — e.g. "Owner can set a goal and see it cascade to teams through the UI"}}
- {{Criterion — e.g. "MVP usable in production at the pilot agency by YYYY-MM-DD"}}

---

## 10. How to use this plan

- **Single source of truth for progress.** Update as you work.
- **Live-tick tasks as they complete.** Flip `- [ ]` → `- [x]` the moment a task is done and save the file — do not batch at end of phase. The user watches this file as a live dashboard.
- **Phase-by-phase by default.** Execute one phase, then pause and wait for the user to say "continue" / "next phase" / "do phase N". Do not auto-advance to the next phase. The user overrides this with explicit throughput instructions like "ram through 1-3" or "run all backend phases".
- **Check off items, don't delete them.** Strike through or move to the Change Log if removed.
- **Revise the plan when your understanding changes** — rewrite phases, split/merge tasks, reshuffle priorities. A stale plan misleads.
- **Commit plan changes with the code.** They evolve together.
- **Interrogate before designing / revising.** Ask the user first. Never assume. Capture each Q→A in §2 so the reasoning outlives the conversation.
- **Optimization-spotting is expected.** A phase you thought needed 4 tasks may need 2. Shrink it.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| {{YYYY-MM-DD}} | Initial plan drafted from `templates/PLAN-TEMPLATE.md` after interrogation of {{USER}} | {{AUTHOR}} |
