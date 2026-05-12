# Proposals & Improvements

> How the NoctusAI dev toolkit records "things that need human review." Two
> systems cooperate: **improvements** (per-project, narrative) and
> **proposals** (per-project-folder or keeper-root, triageable). Both signals
> are valuable; merging them would collapse two audiences into one soup. This
> doc defines the boundary and the flow between them.
>
> **Terminology note (2026-04-19):** NoctusAI uses *project* for what other
> teams call a "plan" — the focused design-and-execution doc driving a piece
> of work. `*-PROJECT.md` files live next to the code they drive; the former
> `*-PLAN.md` naming is deprecated for new files (existing ones may be
> renamed in follow-up passes).
>
> Cross-reference: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md`
> (live-ticking + phase-header + retrospective mechanics) and
> `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` (the MCP dev toolkit surface).

---

## 1. The two systems

### Improvements — the per-project retrospective

- **Lives in:** the project file itself (`**Improvements:**` blocks inside each phase) → aggregated into `improvements.md` next to the project file by `noctus.dev.improvements`.
- **Scope:** one project. Retained for the life of the project document.
- **Shape:** free-form bullets, written fast, in the voice of the agent who just built the step.
- **Purpose:** narrative. What *implementing this phase* taught us — friction, refactor candidates, edge cases the project didn't anticipate, shortcuts accepted.
- **Audience:** a future agent (often a new Claude session) returning to rework or extend that specific project's phase.
- **Lifecycle:** no accept/reject. The retrospective is a log, not a queue.

### Proposals — the triageable queue

- **Lives in:**
  - **Project-originated proposals:** `projects/<project-slug>/proposals/` — one folder per project.
  - **Keeper-originated (compliance) proposals:** `products/<product>/proposals/` — scoped to the product the detector flagged.
  - **Evaluations (A/B agent vs. LLM):** `products/<product>/proposals/evaluations/<ts>-<slug>/` — scoped to the evaluated product.
- **Scope:** single improvement-bundle (project) or single compliance issue (keeper).
- **Shape:** structured template (`templates/PROPOSAL-TEMPLATE.md`).
- **Purpose:** actionable, triageable records that a reviewer accepts or rejects and a future agent executes.
- **Audience:** any agent opening the queue to triage or execute accepted items.
- **Lifecycle:** `pending` ⇒ `accepted` ∨ `rejected`, with reasons. Dedup by title slug + key entity.

**Why keep them separate:** improvements are in-flow capture (fast, mid-step); proposals are synthesis artifacts (rich, end-of-phase or end-of-detection). Collapsing both into one store would either force ceremony onto quick-capture bullets (killing flow) or drown the triage queue in unprocessed observations.

---

## 2. The capture-then-synthesize protocol (per project phase)

### Step 1 — during step implementation: capture

As each sub-task of a phase is being built, the in-session agent drops short improvement bullets into the phase's `**Improvements:**` block in the project file. No ceremony, no template — just bullets. The attention belongs to the step being built; capture must be frictionless.

These are **step-individual-related objects** — specific, observation-scoped, in-the-act notes. Examples:
- `"The X cache is a flat dict — switch to LRU when Y grows past 100 entries."`
- `"Missing coverage: no test for the 'provider swapped mid-request' edge case."`
- `"_reset_for_testing is publicly exposed; move to a testing/ submodule."`

**Improvements are specific.** Never write "do more tests" — name the exact observation. Generic bullets produce useless proposals.

### Step 2 — end of phase, before flipping the header to ✅: synthesize ONE proposal

When every sub-task in the phase is ticked **and before** the phase header flips to `✅`, the agent:

1. **Reads the entire `**Improvements:**` block** accumulated during the phase.
2. **Considers the whole project context** — not just this phase: how do these improvements interact with each other? What other phases do they touch? Is there a project-level insight that emerged from assembling the phase?
3. **Authors ONE phase proposal** from `templates/PROPOSAL-TEMPLATE.md`, bundling the improvements as independently-executable items inside.
4. **Files via `noctus.dev.file_proposal(project="<project-slug>", ...)`** — the `project` argument puts the proposal in `projects/<project-slug>/proposals/`.

**Not one proposal per improvement — ONE bundled proposal for the phase.** Each improvement within the bundle retains individual execution (the reviewer schedules them separately) but the proposal itself is a single coherent context-transfer vehicle.

### Step 3 — flip header + regenerate retrospective

After the phase proposal is filed:

1. Flip the phase header to `✅`.
2. Run `python mcp/noctusai/cli.py --improvements <project-file.md>` to regenerate `improvements.md` next to the project file (retrospective).
3. Log the phase completion in §11 Change Log.

---

## 3. What the phase proposal carries

Beyond the standard template fields (severity, effort, affected products, acceptance criteria), a project-phase proposal includes:

- **`Origin:` `project:<project-slug>:phase-<N>`** — ties it to the source phase.
- **`## 1. Context`** — what the phase built + why these improvements were raised in its wake. Set the stage for the receiving agent.
- **`## 2. Situation`** — the real state of the phase's output right now (facts, no advice).
- **`## 3. Proposed Solution`** — framed as a bundle:
  - `§3.1 Linkage` — why this set of improvements fits this phase's situation (project-level insight lives here).
  - `§3.2 Application instructions` — each bundled improvement is one sub-item with: title, brief linkage, concrete steps, risks, independence note (independent, or "depends on improvement #N").
  - `§3.3 Seed APIs involved` — aggregated across the bundle.
  - `§3.4 Risks` — aggregated bundle-level warnings.
  - `§3.5 Alternatives considered` — bundle-level or per-improvement where relevant.
- **`## 4. Effects`** — aggregated across the bundle: behavior / risk profile / ergonomics / coverage.
- **`## 5. Acceptance Criteria`** — bundle-level (validate passes, tests pass, docs updated) + per-improvement items if specific verification is needed.

### Why this shape

The proposal is the **context-transfer vehicle**. The agent who lived the phase authors it once with full situational awareness; the reviewer / executing agent inherits that awareness through the proposal text. Bundling preserves context across all the phase's improvements without forcing N separate contextualizations.

### Speed when filing

The heavy structural work lives in the template. The authoring agent's job is to **feed it** — the bundle synthesis is fast because the improvements were already captured during steps. If a section is genuinely not applicable, write `N/A — {{one-line why}}` rather than padding.

---

## 4. Non-project proposal origins

Not every proposal comes from a project phase. Keeper (`noctus.dev.review`) files proposals for compliance-detector findings. `noctus.dev.lgpd_flag` records LGPD concerns that sometimes escalate to proposals. The pattern works the same: structured template, context-rich, triageable. The `Origin:` field distinguishes:

- `project:<slug>:phase-<N>` → `projects/<slug>/proposals/` **or** `products/<product>/projects/<slug>/proposals/` — the MCP tool resolves the slug to whichever location holds the project folder (see `project-execution.md §1`). Authors pass only the slug; the tool picks the path.
- `keeper:noctus.dev.validate:<product>` → `products/<product>/proposals/` (product-scoped)
- `lgpd:noctus.dev.lgpd_flag:<label>` → `products/<product>/proposals/` (product-scoped) or a dedicated origin folder when the volume grows

Keeper proposals remain **one-per-issue** (different aggregation rule from projects), because each compliance finding is an independent problem the detector surfaced separately.

### Promoting a project improvement to a keeper-style proposal

Sometimes an improvement captured inside a phase bundle affects multiple products or the seed itself — it outgrows the project's context. The **promote** pattern:

1. Keep the improvement in the phase bundle (it's part of the phase's story).
2. Also file a separate root-level proposal (source: `project:<slug>:phase-<N> (promoted)`) so the platform queue sees it.
3. Note the promotion in both proposals for discoverability.

Use sparingly — most improvements live happily inside the phase bundle.

---

## 4b. Apply-inline-then-delete (DEFAULT methodology on this repo)

**Every phase-end proposal on this repo follows this lifecycle. This is not a user preference — it is the default protocol all agents must apply before handing a phase back.** The upstream "file + leave pending" lifecycle described elsewhere is not used here.

Mechanics (mandatory):

1. Synthesize + file the phase proposal (§2 Step 2 above).
2. For each bundled item:
   - **If it can be applied right now** (low-risk, in-scope, self-contained) → **apply it in the same session**. Do not leave it for later.
   - **If it cannot be applied** (needs its own project, requires user direction, touches scope the current phase didn't audit) → capture the deferral explicitly in:
     (a) the phase's `**Improvements:**` block or the next phase's concrete sub-tasks, AND
     (b) the §11 Change-Log entry naming where the deferred item now lives (new project slug + folder path, backlog note, etc.).
     **Deferred items that reference a follow-up project MUST create that project folder** — `projects/<slug>/PROJECT.md` scaffolded from `templates/PROJECT-TEMPLATE.md`. A prose reference to a project that doesn't exist as a file is a broken pointer.
3. **Delete the proposal file** once every item is either applied or properly deferred with a live pointer. Keep `.gitkeep` so the folder persists in git.
4. Verify the folder is clean (`ls -la <project>/proposals/` → only `.gitkeep`).
5. The §11 Change-Log entry records: applied items (with one-line what-changed each) + deferred items (with one-line where-it-lives-now each). This is the surviving audit trail.

**Why this is the default:** `PROJECT.md §11` + the phase blocks ARE the durable record on this repo. The proposal file's queue function (accept / reject, schedule, batch triage) is redundant with the live-ticked project doc. Leaving proposals sitting in the folder makes the file tree look messier than the real project state, and an un-read queue isn't a queue — it's debt.

**What to do if an item genuinely cannot be applied AND cannot be properly deferred** (no clear project home, not a known-issue note, scope unclear): stop and ask the user. Do not leave the item as prose inside a deleted proposal — that vanishes the context.

---

## 4d. Auto-improvement (DEFAULT — skip the proposal artifact for routine in-scope work)

**Per user directive 2026-05-02:** *"please implement improvements found then go on with the next phase. Also update our methodology with this new 'auto-improvement' method. just tell me they were implemented, no need to ask so we gain time."*

This **amends** §2 / §4b. The previous protocol required filing a `noctus.dev.file_proposal` artifact at every phase close, then applying inline, then deleting the file. The new default is tighter: **for routine in-scope improvements the agent applies them immediately at phase close — no proposal file is created at all, no user prompt is issued.**

When the auto-improvement path applies (default for most phase closes):

1. At end of phase, read the `**Improvements:**` block.
2. For each item, decide: in-scope ∧ low-risk ∧ self-contained?
   - **Yes** ⇒ apply in this same session, inline, before the next phase starts.
   - **No** ⇒ defer with a live pointer (next-phase sub-task, follow-up project scaffolded from `templates/PROJECT-TEMPLATE.md`, backlog note). Same deferral rules as §4b.
3. Update the phase's `**Improvements:**` block in-place to mark each item as **applied** or **deferred → <destination>**. The block becomes the audit trail; no separate proposal file is created.
4. Add the §11 Change-Log entry capturing what was applied / what was deferred.
5. Continue to the next phase **without prompting the user**.

When to **still** file a formal `noctus.dev.file_proposal` artifact:

- Items that are out-of-scope for the current phase AND need scheduling (not just a follow-up project).
- Items that need explicit reviewer / human approval before applying (e.g. cross-team, security-sensitive, public-API-breaking).
- Items large enough that the bundle itself needs a discussion / triage cycle.
- Items that span multiple deliverables and should be queued for batch review.

When the formal-proposal path applies, the §4b apply-inline-then-delete mechanics still hold.

**Why this is the default**: filing a proposal file just to delete it the same session was ceremony. The `**Improvements:**` block + §11 entry IS the durable audit trail. Removing the proposal-file step recovers turn-time without losing the trail.

**What does NOT change**: §4c end-of-work summary still runs. §6 ↔ §11 self-check still runs. Three-way sync (KB ↔ CLAUDE.md ↔ memory) still runs. Phase-by-phase cadence still holds (one phase, then pause for "continue") — auto-improvement applies to **closing the current phase**, ¬ user-permission to start the next.

**Anti-pattern**: auto-applying an item that wasn't actually in-scope ("the agent decided"). The in-scope filter is load-bearing — if you're unsure whether an item is in-scope, defer it.

---

## 4c. End-of-work summary (DEFAULT — every agent, every deliverable)

**Every reply that concludes non-trivial work MUST include a short, explicit, list-shaped summary of what was applied and what was deferred.** Non-trivial means: a phase closure, a proposal application, a migration, a multi-step fix, a framework extension. Short conversational answers to questions are exempt.

Shape:

```
## Summary
- <artifact / file path>: <one-line what changed>
- <artifact / file path>: <one-line what changed>
- <deferred item>: <one-line why + where it's tracked next (project path / backlog)>

Verification: <one line — test counts, build results, keeper output>
```

Rules:

- **Applied items AND deferred items are both listed.** The deferred list is as important as the applied list — it tells the user what to expect next and names where the follow-up lives (new project, backlog, next phase). A deferred item without a named follow-up home is a broken pointer; fix it before summarizing.
- **Per-item line stays short** — one line, ~120 chars. Link file paths where useful.
- **Verification is ONE line**, not a paragraph. Test counts, build pass/fail, keeper output. If nothing to verify, skip the line.
- **No process narration.** "First I did X, then Y..." belongs in the diff, not the summary.
- **No padding.** If genuinely nothing deferred, omit the deferred line.

**Why it's default:** the user reads this final message as a real-time dashboard. Silent finishes ("done.") and verbose multi-paragraph narratives both break the signal. The list shape lets the user scan in seconds and redirect quickly if something is wrong.

**Combined with § 4b:** the agent must apply inline + delete before writing the summary. The summary's "applied" list mirrors the items the agent just applied (and then deleted from the proposal file). The deferred list names where those items now live.

---

## 5. Workflow summary

```
During phase execution:
  step finished → improvement bullet → **Improvements:** block (live-ticked)
  step finished → improvement bullet → **Improvements:** block (live-ticked)
  step finished → improvement bullet → **Improvements:** block (live-ticked)
  all sub-tasks ticked
  ─────────────────────────────────────────────────────────────
  SYNTHESIS (end of phase)
  ─────────────────────────────────────────────────────────────
  read all improvement bullets
  consider whole-project context
  fill templates/PROPOSAL-TEMPLATE.md — ONE bundled phase proposal
  file via noctus.dev.file_proposal(project="<slug>", ...)
     → lands in projects/<slug>/proposals/  OR
                products/<product>/projects/<slug>/proposals/
     (the MCP tool picks whichever folder contains the project — pass just the slug)
  phase header flips to ✅
  noctus.dev.improvements regenerates improvements.md (retrospective)
  change-log entry added
  pause for user
```

---

## 6. Doc-modification protocol (meta — how to update THIS doc)

When extending or correcting any rule in this doc (or any KB / CLAUDE.md rule), follow the **KB-first protocol**:

1. **Land KB changes first** — update the KB file that holds the long-form rule. If creating a new KB file, update `KNOWLEDGE-BASE/INDEX.md` in the same change.
2. **Then update CLAUDE.md** — the short behavioral rule + pointer into the KB.
3. **Never the reverse.** CLAUDE.md is the pointer layer; pointing into KB content that doesn't exist yet strands the pointer. (Order: KB → CLAUDE.md ↔ memory.)

The `verify-kb-sync.sh` pre-commit hook catches dangling pointers but do not rely on it — the hook is a safety net, not the protocol. The protocol is ordering.

Announce the order when presenting a multi-file doc plan: "KB → then CLAUDE.md." The user will flag regressions.

---

## 7. Common failure modes

- **One proposal per improvement** (old protocol, corrected 2026-04-19) — fragments the phase context. File ONE bundled phase proposal, list individual improvements inside.
- **Filing a proposal mid-step** — don't. Capture bullets live, synthesize at phase-end.
- **Improvement block used to preview the next phase** — improvements are about the *just-completed* phase. Upcoming work is in §6 of the project.
- **Generic improvements** ("do more tests") — specificity or don't capture. Generic bullets produce useless proposals.
- **Bundled improvements without independence notes** — the reviewer can't schedule execution without knowing dependencies. Every bundled improvement states "Independent: yes" or "Depends on: #N".
- **Proposal without `Origin:`, `## Context`, or `## Situation`** — the receiving agent can't inherit situational awareness. Reject and re-author.
- **Touching CLAUDE.md before the KB** — violates the KB-first protocol. KB first, always.
