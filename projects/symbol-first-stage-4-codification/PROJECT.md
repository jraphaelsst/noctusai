# symbol-first-stage-4-codification — Project Document

> **This is a living document, not a rigid checklist.** Revise as we learn.
>
> **Write for a zero-context reader.** Engineer dispatched against this brief
> has not seen the originating conversation.
>
> **Symbol-first authoring.** Use the doc-symbology glossary by default — `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-12
- **Last updated:** 2026-05-12
- **Status:** Design locked → Phase 0 ready (interrogation pending)
- **Owner / stakeholders:** USER (jraphaelsst) · architect
- **Related docs:** `KB § PATTERNS/doc-symbology.md` · `KB § PATTERNS/methodology-codification-pipeline.md` · `feedback_doc_symbology.md` · `feedback_symbol_first_authoring.md`
- **Project slug:** `symbol-first-stage-4-codification` at `projects/symbol-first-stage-4-codification/` (cross-cutting — touches keeper / pre-commit / KB-wide).

---

## 1. Context & Purpose

The doc-symbology methodology is codified through `s3` (KB pattern + CLAUDE.md §1 universal rule + `engineer-default.md §10` inheritance + memory entries). The `s4` keeper detector was intentionally held — memory entry `feedback_doc_symbology.md` says: *"Held at Stage 3 until N=3+ symbol-drift incidents."*

User's 2026-05-12 message — *"please make sure future docs and files will follow the symbology pattern, so we facilitate machine reading and save some tokens"* — IS the third drift signal. The codification ceiling needs to move: `s3` ⇒ `s4`.

The deliverable: a warn-only keeper detector (`check_doc_symbology_drift`) that scans dense-doc paths at pre-commit, flagging undefined symbols and `→` vs `⇒` interchange. Hard enforcement (block) is NOT in scope — the rule is judgment-dependent ("use when lossless"), bimodal-yield finding (`e2dc93e`) shows high yield on bullet/rule surfaces and low on narrative. A blocking detector would produce noise; a warn detector surfaces drift without churn.

## 2. Confirmed constraints

*(populated during §0 interrogation — see project-execution rule)*

- {{Q1 — density threshold per file type (bullet-heavy KB pattern vs narrative MASTER-PROMPT vs PROJECT.md §6+§11)}}
- {{Q2 — scope of dense-doc paths to scan (CLAUDE.md? CLAUDE/*.md? KB/CONTEXT/PATTERNS/*? products/*/MASTER-PROMPT.md? templates/*?)}}
- {{Q3 — warn vs block default + escape hatch (none, or `# symbology: off` inline pragma?)}}
- {{Q4 — `→` vs `⇒` strict interchange detection or accept some prose `→`?}}

## 3. Design principles

- **Warn, don't block.** Pre-commit emits a warning to stderr; commit proceeds. Mirror `mole.sh --artifacts` 2GB warning shape.
- **Judgment-aware.** Skip narrative prose (paragraphs >3 lines without bullet structure); focus enforcement on bullet/rule/header sections where ROI is high.
- **Glossary-driven.** Detector reads symbol set from `KB § PATTERNS/doc-symbology.md` §1 (parsed from the table headers). New symbols added to glossary auto-propagate.
- **Path-scoped.** Only fires on dense-doc paths configured at the top of the detector. Avoids noise on bug-fix comments, error messages, README narrative.

## 3a. Seed-first analysis

This is a methodology/keeper change, not product code. Seed-first analysis: the keeper detector lives at `mcp/noctusai/keeper/checks/check_doc_symbology_drift.py` — same shape as existing `check_*` detectors (e.g. `check_test_status_assertion.py`). No per-product replication.

## 4. Scope

**In scope:**
- New keeper detector `check_doc_symbology_drift` + colocated regression test (per `feedback_regression_test_the_detector.md`)
- Glossary-parser helper (reads `KB § PATTERNS/doc-symbology.md` §1 table, returns symbol set)
- Pre-commit hook integration (warn-only)
- Calibration pass: run detector on existing corpus (CLAUDE.md, CLAUDE/*.md, KB/CONTEXT/PATTERNS/*.md, MASTER-PROMPTs) and record baseline drift count

**Out of scope:**
- Hard-block enforcement (deferred until baseline drift count + user signal)
- Auto-fixing (detector observes; LLM proposes via existing keeper review flow)
- Skill or pre-write hook (separate ergonomic project)

## 5. Architecture / Data Model

- `mcp/noctusai/keeper/checks/check_doc_symbology_drift.py` — new detector
- `mcp/noctusai/keeper/checks/_symbology_glossary.py` — helper parses KB doc, returns `{logic_symbols, status_symbols, stage_symbols, triage_symbols, count_symbols}` sets
- `mcp/noctusai/keeper/tests/test_check_doc_symbology_drift.py` — fixtures: known-drift doc / clean doc / narrative-skip doc / inline-pragma doc
- `scripts/pre-commit` — add detector invocation in warn-mode block

## 6. Implementation phases

### Phase 0 — User interrogation + scope confirmation ⏳

- [ ] Q1-Q4 above answered + recorded in §2
- [ ] Confirm path scope + warn-vs-block default + pragma policy

### Phase 1 — Detector + glossary parser ⏳

- [ ] Implement `_symbology_glossary.py` glossary parser + tests
- [ ] Implement `check_doc_symbology_drift.py` detector + tests
- [ ] Run baseline calibration on existing corpus; record drift count

### Phase 2 — Pre-commit integration + verify on live drift ⏳

- [ ] Wire into `scripts/pre-commit` as warn-only
- [ ] Verify on the baseline drift set — false-positive rate < 10%
- [ ] Update `KB § PATTERNS/doc-symbology.md` + memory entry: `s3` ⇒ `s4` status flip

### Phase 3 — Retrospective + close ⏳

- [ ] Improvements bundle (one proposal max)
- [ ] §11 close + archive

## 7. Open questions

*(see §2 — Q1-Q4)*

## 8. Dependencies & blockers

- `KB § PATTERNS/doc-symbology.md` §1 table must remain machine-parseable (glossary format contract). If symbol additions break the parser, detector emits the parse error, not a drift warning.

## 9. Success criteria

- Detector runs in <500ms on full corpus (pre-commit budget)
- Baseline drift on current corpus is recorded + understood
- False-positive rate ≤10% on calibration set
- KB + memory + CLAUDE.md three-way-synced after Stage flip

## 10. How to use this plan

```bash
# Phase 1 dispatch shape (after Phase 0 interrogation closes):
# Engineer brief points to this file's §6 Phase 1 sub-task list +
# §5 architecture + §3 design principles. Engineer follows engineer-default.md
# protocol; returns short-form report at phase close.
```

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-12 | Project filed. Trigger: user's *"make sure future docs follow the symbology pattern"* — N=3 drift signal that flips memory's "Held at Stage 3" gate. Scope: warn-only `check_doc_symbology_drift` keeper detector + glossary parser + pre-commit wiring. Phase 0 interrogation pending. | Claude Opus 4.7 (architect) |
