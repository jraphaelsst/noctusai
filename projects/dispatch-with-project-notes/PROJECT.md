# Dispatch-with-PROJECT-and-notes — Project Document

> **This is the dogfood project** — the work that codified the dispatch-with-PROJECT-and-notes pattern IS structured per the pattern itself. Future agents reading this find both the meta-pattern (in `KB § PATTERNS/common/dispatch-with-project-and-notes.md`) and a worked example (this file) of how to write a §4a Dispatch routing section.

- **Created:** 2026-05-26
- **Last updated:** 2026-05-26
- **Status:** ⏳ Phase 1 in progress (the methodology slice is shipping in feat/dispatch-with-project-notes)
- **Owner / stakeholders:** rapha (user) · architect (tech-lead, this session)
- **Related docs:** `KB § PATTERNS/common/dispatch-with-project-and-notes.md` · `KB § PATTERNS/architect/proposals-and-improvements.md` (legacy) · `KB § PATTERNS/common/methodology-codification-pipeline.md` (s1→s4 contract) · `templates/PROJECT-TEMPLATE.md` (updated §4a)
- **Project slug:** `dispatch-with-project-notes`

---

## 1. Context & Purpose

The user surfaced (2026-05-26 evening): *"agents go s1→s2→s3→s4 — provide roadmaps for them to follow upon dispatch. they evaluate if they have better options and surface to the tech lead. tech lead approves and adapts route, or rejects with rationale. This should also be thought as a structural pattern of execution agents should follow."*

The proximate signal was the s4-keeper-without-s3-codification gap that `check_codification_pipeline_health` flagged the same session — 4 codifications shipped (lenses-trailer, prod-cache-container, ci-embedding-cache-gate, prod-deploy-safety-gates) with s4 keepers but no s3-codified ledger entries. The deeper signal: agents (and inline-empersonated lenses) skip codification stages silently because nothing structurally requires them to mark each one.

The win: a tech-lead writes ONE structured PROJECT.md (with §4a Dispatch routing) and engineers/inline-lenses read it as the canonical brief. Routes-not-taken stop duplicate surfacing. Codification expectations stop silent skipping. Surface notes catch alt-route disagreements BEFORE they ship.

---

## 2. Confirmed constraints

- **Reuse existing infra, don't invent parallel** — *(user: "adapt proposals, keep project structure. We reutilize something we already have to harden the methodology.")* — drove the decision to add `kind` to `noctus.dev.file_proposal` rather than build a notes/ subdir.
- **Block-on-surface (not proceed-then-review)** — *(user via AskUserQuestion: "pause and wait tech lead's answer")* — drove `engineer-default §1c` mandate to STOP + file + WAIT.
- **Directory project shape** — *(user via AskUserQuestion: "Directory (Recommended)")* — confirmed the existing `projects/<slug>/` convention is correct; no flat-form pivot.
- **Start small items in parallel** — *(user via AskUserQuestion: "Start small items now (Recommended)")* — drove the parallel pgvector + s3 backfill while methodology slice was designed.

---

## 3. Design principles

1. **Concept layer over file format** — `kind` is the concept-layer dimension; proposal file format stays unchanged. Three kinds (phase / surface / delivery) all use the same `templates/PROPOSAL-TEMPLATE.md`.
2. **Block-on-surface, not proceed-then-review** — engineer-side block is cheap (one round-trip); a wrong-route commit is expensive (revert + rationale + re-dispatch).
3. **Existing infra wins** — `projects/<slug>/proposals/` already exists; reuse it rather than invent `notes/`.
4. **PROJECT.md is the brief** — dispatched engineers read PROJECT.md (not a bespoke brief); the brief is ~15 lines pointing at PROJECT.md per `dispatch-engineer-tuning`.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every project?** YES — every multi-slice project benefits from §4a; small inline-only projects can have a trivial §4a with one row.
2. **Is the data source product-specific?** NO — methodology lives in `templates/` + `KB § PATTERNS/` + `.claude/agents/` + `CLAUDE.md`. No per-product wiring.
3. **Is the placement product-specific?** NO — universal (every project gets §4a).
4. **Is the visibility / permission rule the same?** YES — every engineer + lens reads the same PROJECT.md.
5. **Does the seam already exist in seed?** YES — `noctus.dev.file_proposal` + `noctus.dev.set_proposal_status` + `projects/<slug>/proposals/` directory layout. The `kind` parameter is the seam extension.
6. **Default-on or opt-in?** OPT-IN at template level (existing projects don't auto-gain §4a until refactored); DEFAULT-ON for new PROJECT.md from `templates/PROJECT-TEMPLATE.md`.

**Litmus:** 0 lines per-product — pure methodology layer. ✅

---

## 4. Scope

**In scope (Phase 1 — the slice that's shipping now):**
- Update `templates/PROJECT-TEMPLATE.md` with §4a Dispatch routing
- Update `templates/PROPOSAL-TEMPLATE.md` with `Note kind:` field + per-kind guidance
- Extend `proposals.py` with `kind` parameter + new `adapted` status + `project=` scoping for status updates
- Author `KB § PATTERNS/common/dispatch-with-project-and-notes.md`
- Add CLAUDE.md §1 one-liner
- Update `engineer-default.md` (§1b, §1c, §3 return shape additions)
- Update `backend-engineer` / `frontend-engineer` / `devops-engineer` composes-with pointers
- Add INDEX.md tree + catalog entries
- Backfill 4 s3-codified ndjson entries
- Install `pgvector` Python package

**Out of scope (deferred):**
- `check_project_has_dispatch_routing` keeper — s4 promotion happens only after recurrence proves the pattern works (N=1 today).
- Migrating existing `projects/<slug>/PROJECT.md` files to add §4a — opt-in; touched on next contact (fix-on-contact rule).
- A `noctus.dev.list_notes` MCP variant scoped to project + kind — covered by existing `list_proposals` for now; revisit if friction surfaces.
- Per-kind keeper validation (e.g., delivery note must include `Codification events emitted:` block) — defer until recurrence.

---

## 4a. Dispatch routing (REQUIRED — the slice-to-engineer map)

> Dogfood reference — this project applied the new §4a section to itself.

### 4a.1 Slice → Lens table

| Slice / Phase | Lens | Files (or globs) | Time-box | Dispatched as |
|---|---|---|---|---|
| W1-A pgvector install | architect-inline | venv only | 5 min | inline (single command) |
| W1-B s3 backfill | architect-inline | `project-history/auto-improvement.ndjson` | 10 min | inline (single python heredoc) |
| W2-A PROJECT/PROPOSAL templates | architect-inline (backend-engineer lens) | `templates/PROJECT-TEMPLATE.md` · `templates/PROPOSAL-TEMPLATE.md` | 30 min | inline-empersonation |
| W2-B `proposals.py` tool adapt | architect-inline (backend-engineer lens) | `mcp/noctusai/tools/noctus/dev/proposals.py` | 30 min | inline-empersonation |
| W2-C KB pattern doc | architect-inline (compliance-reviewer lens) | `KB § PATTERNS/common/dispatch-with-project-and-notes.md` · `KB § INDEX.md` | 20 min | inline-empersonation |
| W2-D CLAUDE.md §1 + engineer docs | architect-inline (compliance-reviewer lens) | `CLAUDE.md` · `.claude/agents/engineer-default.md` · `backend-engineer.md` · `frontend-engineer.md` · `devops-engineer.md` | 30 min | inline-empersonation |
| W3 verify + commit + push | architect-inline (tech-lead) | (verification commands) | 15 min | inline |

*Inline-only because: shared-state cross-surface (template ↔ tool ↔ KB ↔ CLAUDE.md ↔ agents need coherent voice + same-commit propagation). Dispatching to subagents would multiply merge-conflict risk for negligible parallelism gain.*

### 4a.2 Codification expectations per slice

| Slice | s1 detected | s2 to memory | s3 KB+CLAUDE.md | s4 keeper | Why |
|---|---|---|---|---|---|
| W1-A pgvector install | no | no | no | no | drift-fix-on-contact (not a methodology event) |
| W1-B s3 backfill | no | no | yes (4× backfill) | no | the backfill IS the s3 event for prior s4 ships |
| W2-A templates | yes (pattern emerging) | no | yes (template carries the rule) | no | the template IS the codified contract |
| W2-B proposals.py | no | no | no | no | tool extension follows the s3 codification |
| W2-C KB pattern | no | no | **yes** (this slice's flagship s3 event) | no | the canonical reference |
| W2-D CLAUDE.md + agents | no | no | yes (CLAUDE.md §1 mirror) | no | sync mirror |
| W3 verify/commit | no | no | no | no | pure delivery |

*s4 keeper deferred — N=1 today; promote when recurrence shows the pattern earns it.*

### 4a.3 Routes-not-taken (pre-rejected)

| Route | Why rejected |
|---|---|
| Build a parallel `projects/<slug>/notes/` directory | Reuse existing `proposals/` — user explicitly: "adapt proposals, keep project structure". |
| Rename `noctus.dev.file_proposal` → `noctus.dev.file_note` | Back-compat break; legacy `phase` callers exist. The `kind` parameter is the seam. |
| Build per-kind keeper validators NOW | N=1; methodology-in-pilot (Stage 3) per `methodology-codification-pipeline.md`. Promote keeper on recurrence. |
| Flat project file shape (`projects/<slug>-PROJECT.md`) | User explicitly chose Directory (Recommended); existing convention is already directory-shaped. |
| Proceed-then-review for surface notes | User explicitly: "pause and wait tech lead's answer". Block-on-surface preserves file-disjoint commit hygiene. |
| Dispatch the methodology slice to parallel subagents | Cross-surface shared-state would amplify merge-conflict risk; coherent-voice constraint per `parallelization-first-orchestration § inline`. |

### 4a.4 Notes — surface + delivery

- This phase produces a delivery note (filed at end of W3) at `projects/dispatch-with-project-notes/proposals/architect-inline-<ts>-delivery-<slug>.md`.
- No surface notes filed mid-flight (no alt routes emerged — the user's ask was prescriptive enough that route-finding wasn't needed).

---

## 5. Architecture / Data Model

Methodology slice — no new data model or API. File-system surfaces touched:

```
templates/
  PROJECT-TEMPLATE.md           ← +§4a section (60+ lines)
  PROPOSAL-TEMPLATE.md          ← +**Note kind:** field, +per-kind guidance HTML comment

mcp/noctusai/tools/noctus/dev/
  proposals.py                  ← +VALID_NOTE_KINDS, +kind param on file_proposal,
                                   +VALID_NOTE_STATUSES (adds "adapted"),
                                   +project= scoping on update_proposal_status,
                                   +rationale-trailer on all non-default statuses

KNOWLEDGE-BASE/
  CONTEXT/PATTERNS/common/
    dispatch-with-project-and-notes.md  ← NEW canonical reference
  INDEX.md                              ← +tree entry, +catalog row

CLAUDE.md                       ← +§1 one-liner (after scoped-auto-improvement)

.claude/agents/
  engineer-default.md           ← +§1b Read PROJECT.md first,
                                   +§1c Surface notes — STOP + file + BLOCK,
                                   +§3 codification-events + delivery-note lines
  backend-engineer.md           ← +Composes-with pointer
  frontend-engineer.md          ← +Composes-with pointer
  devops-engineer.md            ← +Composes-with pointer

project-history/
  auto-improvement.ndjson       ← +4 s3-codified backfill entries

projects/dispatch-with-project-notes/  ← NEW (this folder)
  PROJECT.md
  proposals/                    ← will hold the delivery note at end
```

---

## 6. Implementation phases

### Phase 1 — Methodology slice ⏳

- [x] pgvector pip install (W1-A)
- [x] 4× s3-codified ndjson backfill (W1-B)
- [x] PROJECT-TEMPLATE.md §4a added (W2-A)
- [x] PROPOSAL-TEMPLATE.md `Note kind:` field added (W2-A)
- [x] proposals.py `kind` parameter + `adapted` status + project-scoped status update (W2-B)
- [x] KB pattern doc authored (W2-C)
- [x] INDEX.md tree + catalog row (W2-C)
- [x] CLAUDE.md §1 one-liner (W2-D)
- [x] engineer-default §1b + §1c + §3 updates (W2-D)
- [x] backend-engineer / frontend-engineer / devops-engineer composes-with pointers (W2-D)
- [x] PROJECT.md for this slice (W2-A — dogfood)
- [ ] Run keeper gates (kb_sync, check_claude_md_router, check_seven_way_sync, check_agent_kb_alignment) (W3)
- [ ] Run impacted pytest (W3)
- [ ] Commit + push feat/dispatch-with-project-notes (W3)
- [ ] File delivery note (W3 — closes the loop)

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips ✅: replace with the methodology improvements spotted this phase, or write "none identified."_

---

## 7. Open questions

1. **Should the delivery note's "Codification events emitted" block be parsed by `check_codification_pipeline_health` directly** (so emitting a delivery note WITH s3 events auto-feeds the ledger)? — *deferred until recurrence; today the engineer/lens writes both the note AND the ndjson entry.*
2. **Should a `noctus.dev.list_notes` MCP variant exist** (scoped to project + kind)? — *deferred; existing `list_proposals` covers product scope; project-scoped listing is a follow-up.*

---

## 8. Dependencies & blockers

None — methodology slice, no external dependencies.

---

## 9. Success criteria

- [ ] CLAUDE.md §1 contains the dispatch-with-PROJECT-and-notes rule
- [ ] `KB § PATTERNS/common/dispatch-with-project-and-notes.md` exists + referenced from INDEX.md
- [ ] `templates/PROJECT-TEMPLATE.md` ships §4a
- [ ] `templates/PROPOSAL-TEMPLATE.md` ships `Note kind:` field
- [ ] `noctus.dev.file_proposal(kind="surface", project=<slug>, ...)` works end-to-end (creates a `<agent>-<ts>-surface-<slug>.md`)
- [ ] `noctus.dev.set_proposal_status(status="adapted", reason=..., project=<slug>, filename=...)` works
- [ ] All keeper gates green
- [ ] Pushed to `dev` (feat/dispatch-with-project-notes merged FF)

---

## 10. How to use this plan

Standard contract — but this project is its own first consumer (dogfood). The delivery note filed at W3 closes the loop and validates the round-trip.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-26 | Initial draft + Phase 1 executed inline-empersonation | architect (tech-lead) |
