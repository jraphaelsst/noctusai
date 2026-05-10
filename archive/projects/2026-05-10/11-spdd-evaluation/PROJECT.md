# Project: SPDD Methodology Evaluation

**Status:** DEFERRED — not yet started. Captured for later evaluation; not under active execution. Do NOT begin phases without explicit user signal.

**Slug:** `spdd-evaluation`
**Scope:** cross-cutting / platform-level (methodology)
**Owner:** rapha
**Captured:** 2026-05-09
**Trigger:** user requested archival of SPDD article research + merge analysis as evaluation candidate; explicitly deferred ("not gonna deal with this right now").

---

## 1 · One-line summary

Evaluate whether **Structured-Prompt-Driven Development (SPDD)** — a Thoughtworks methodology centered on a 7-part REASONS Canvas + two-way prompt↔code sync — should partially merge into the repo's existing **CDD+TDD** methodology, or be rejected.

## 2 · Source material

- **External:** https://martinfowler.com/articles/structured-prompt-driven/ (Wei Zhang & Jessie Jie Xia, Thoughtworks Global IT Services, 28 April 2026)
- **Companion repo cited in article:** `gszhangwei/token-billing`
- **Tooling cited in article:** `openspdd` CLI

## 3 · Artifacts in this folder

| File | What it contains |
|---|---|
| `PROJECT.md` | This index. |
| `spdd-article-summary.md` | Full faithful summary of the SPDD article (REASONS Canvas, 6-step workflow, anti-patterns, fitness assessment, anti-patterns, billing-engine example, full Q&A). |
| `merge-analysis.md` | First-pass analysis: what SPDD adds vs. what CDD+TDD already covers, candidate elements worth borrowing, candidate elements to reject, risks of adoption mid-validation of branching-first orchestration, decision points + open questions for future evaluation. |

## 4 · How to resume

1. Read `spdd-article-summary.md` to refresh on SPDD itself.
2. Read `merge-analysis.md` for the candidate-merge thinking.
3. Decide: full reject / partial-borrow (which pieces?) / formalize as a real project.
4. If formalizing, copy `templates/PROJECT-TEMPLATE.md` and replace this thin marker; route through the standard project-execution methodology.

## 5 · Why deferred

- Repo is mid-validation of branching-first orchestration methodology (memory: `feedback_TEMP_methodology_validation_in_progress`). Adding another methodology layer mid-validation is risky.
- No N=2 / N=3 evidence yet that the gaps SPDD would close are recurring in this repo. Per the **DRY recurrence rule**, formalization without evidence is premature.
- User signal explicit: "not gonna deal with this right now."
