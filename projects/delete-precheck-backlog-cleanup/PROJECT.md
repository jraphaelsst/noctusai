# delete-precheck-backlog-cleanup — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 📋 **READY FOR EXECUTION (dispatchable).** Filed under user signal "create projects for deferrals/parks that happen along the way." Engineer J's `delete-precheck-seed-lift` Phase 0 grep surfaced 6 additional callsites of the same anti-pattern shape that the seed-lib helper (now shipped) consolidates. Mechanical refactor — single engineer dispatch.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `delete-precheck-backlog-cleanup`
- **Related docs:**
  - `archive/projects/...//delete-precheck-seed-lift/` (when archived) — predecessor; ships the helper this project consumes.
  - `seed/lib/backend/noctusai_lib/api/crud_safety.py` — `delete_with_existence_check` + `delete_or_404` shipped 2026-05-10.

---

## 1. Context & Purpose

Engineer J's `delete-precheck-seed-lift` Phase 0 grep across all products surfaced N=9 total callsites of the `delete().execute()` + `if not result.data: raise` anti-pattern. The project rightly stayed scoped to its named 3 (PF-9 + ERP×2); the other 6 are listed in §11 of that project as a backlog candidate. This project is the dedicated cleanup of those 6.

The 6 callsites:
- `products/erp-imobiliario/backend/app/services/metas_empresa_service.py:92`
- `products/erp-imobiliario/backend/app/services/metas_equipe_service.py:86`
- `products/core/backend/app/routers/settings.py:126`
- `products/core/backend/app/routers/settings.py:191`
- `products/daily-life/backend/app/routers/goals.py:169`
- `products/daily-life/backend/app/routers/schedule.py:171`
- `products/daily-life/backend/app/routers/notes.py:141`

(That's 7 listed; Engineer J's report said 6 in summary but listed 7. Phase 0 audit will reconcile the exact count.)

## 2. Confirmed constraints

- **Helper already shipped** at `seed/lib/backend/noctusai_lib/api/crud_safety.py` (commit `286df84` on main).
- **Two raise conventions coexist** (HTTPException for core/daily-life via routers, LookupError for ERP services). Helper supports both via `not_found_exc` injection.
- **Mechanical refactor** — no design decisions, no architecture changes. Single PR.

## 3. Design principles

1. **Use the helper, don't re-inline.** Every callsite imports `delete_with_existence_check` or `delete_or_404` from `noctusai_lib.api.crud_safety`.
2. **Convention-preserving.** Core/daily-life use `delete_or_404(message=...)`. ERP services use `delete_with_existence_check(..., not_found_exc=lambda: LookupError(...))`.
3. **Tests verify behavior preservation, not new behavior.** Each callsite already has a happy path test + a 404 test (or LookupError test).

## 4. Scope

- **In scope:** 6-7 callsite refactors (Phase 0 reconciles exact count) + test updates where assertions reference internal monkey-patches.
- **Out of scope:** Re-extracting the helper, changing the helper's signature, the 3 callsites Engineer J already refactored.

## 5. Architecture / Data Model

No architecture change. Same `delete_with_existence_check` / `delete_or_404` helper consumed at additional callsites.

## 6. Implementation phases

### Phase 0 — Reconcile callsite count + re-grep

- [ ] Re-grep across all products for `\.delete\(\)\.execute\(\)` + `if not result\.data` pattern.
- [ ] Confirm exact callsite count (6 vs 7 — Engineer J's summary said 6 but listed 7). If N≥4 NEW callsites since Engineer J's grep, **STOP** and escalate (recurrence rule MUST-formalize already fired).
- [ ] Decide raise-shape per callsite: HTTPException via `delete_or_404` (routers) vs LookupError via `delete_with_existence_check` (services).

### Phase 1 — Mechanical refactor

- [ ] AST-first edits (libcst) per callsite. NEVER sed/regex.
- [ ] Add `from noctusai_lib.api.crud_safety import delete_or_404` (or `delete_with_existence_check`) at each module top.
- [ ] Replace the 4-line pattern with the helper call.
- [ ] Preserve message strings + status codes.

### Phase 2 — Verify + close

- [ ] Run `pytest` for each affected product backend — all green (no regression).
- [ ] Run keeper review for each affected product — 0 issues.
- [ ] Run `grep` to confirm zero remaining instances of the anti-pattern across all products (the seed-lib helper is now the canonical shape).
- [ ] Tick all sub-tasks + Improvements blocks + §11 close entry.
- [ ] Archive via `noctus.dev.archive`.

## 7. Open questions

- None — mechanical refactor; Engineer J's Phase 0 surfaced everything needed.

## 8. Dependencies & blockers

- Helper landed on main (commit `286df84`). No blocker.

## 9. Success criteria

- [ ] 6-7 callsites consume the helper.
- [ ] Zero remaining `.delete().execute() + if not result.data:` shapes across products.
- [ ] Test suites green for all affected products.

## 10. How to use this plan

Single-engineer dispatch via `git worktree add`. Mechanical scope — should close in one session.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer J's `delete-precheck-seed-lift` Phase 0 grep surfaced 6-7 additional callsites of the same anti-pattern (core/settings ×2, daily-life/goals,schedule,notes, ERP metas_empresa, metas_equipe). Helper already shipped — this project is the mechanical consumer refactor. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
