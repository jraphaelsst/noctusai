# Feature — findings-immediate-implementation

> **What this is.** Promotes "architect evaluates engineer findings locally + applies immediately when applicable" from a temp-validation rule to a durable methodology rule. Default for actionable findings is IMMEDIATE IMPLEMENTATION; deferring an applicable fix is the same shape as silent-error.

- **Created:** 2026-05-04
- **Owner:** rapha
- **Branch:** `findings-immediate-implementation`
- **Trigger:** user directive 2026-05-04 — *"doc that findings should be locally evaluated for immediate implementations when applicable, not just because of the temporary evaluation rule."*

## Scope

Promote the rule from temp-validation status to durable status:

- **`KB § 01-PHILOSOPHY.md § Branching-first orchestration`** — Architect's responsibility #5 expanded with per-case finding-evaluation decisions + IMMEDIATE IMPLEMENTATION default.
- **`CLAUDE.md` §1 branching-first bullet** — adds "engineer findings evaluated locally + applied immediately when applicable" + "deferring an applicable fix = silent-error shape" anti-pattern.
- **Memory:** `feedback_branching_first_orchestration.md` Architect's responsibilities list updated; `feedback_TEMP_methodology_validation_in_progress.md` rule #3 marked PROMOTED + content removed (durable home is now the permanent rule).

## Sub-tasks

- [x] Branch `findings-immediate-implementation` created from origin/main.
- [x] This feature file filed.
- [x] KB § 01-PHILOSOPHY.md updated (Architect's responsibility #5 expanded with full per-case decision matrix + IMMEDIATE IMPLEMENTATION default).
- [x] CLAUDE.md branching-first bullet updated.
- [x] Memory `feedback_branching_first_orchestration.md` Architect's responsibilities list updated (5-point + 7-step structure).
- [x] Memory `feedback_TEMP_methodology_validation_in_progress.md` rule #3 marked PROMOTED.
- [ ] verify-kb-sync.sh green.
- [ ] Commit on branch.
- [ ] Push branch + FF to main.

## Closure

Feature stays at `features/findings-immediate-implementation.md` per features-are-durable rule.
