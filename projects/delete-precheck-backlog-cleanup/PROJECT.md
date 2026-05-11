# delete-precheck-backlog-cleanup — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** ✅ **CLOSED — all 3 phases shipped.** 8 callsites refactored (Phase 0 reconciled — Engineer J's grep missed `products/core/backend/app/routers/webhooks.py:143` due to a multi-line break in the chain; 1 newly-discovered ≪ N≥4 STOP threshold, scope expanded inline). Helper gap caught + fixed: hardcoded `select("id")` broke `platform_settings` (keyed on `key`); patched to use first-predicate column as projection. 14 helper unit tests green (was 12). Per-product baselines unchanged (core: −2 failures vs baseline, daily-life: 234/234 green, erp: 4/4 baseline failures match exactly). Keeper: 0 issues across core / daily-life / erp-imobiliario. Final grep: 0 remaining `.delete().execute() + if not result.data:` shapes in `products/*/backend/`.
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

### Phase 0 — Reconcile callsite count + re-grep ✅

- [x] Re-grep across all products for `\.delete\(\)\.execute\(\)` + `if not result\.data` pattern.
- [x] Confirm exact callsite count (8 — Engineer J's listed 7; reverse-grep `if not result.data` then look-back caught the 8th at `products/core/backend/app/routers/webhooks.py:143`, missed before due to multi-line chain break). 1 newly-surfaced ≪ N≥4 STOP threshold → expanded scope inline.
- [x] Decide raise-shape per callsite: HTTPException via `delete_or_404` (5 routers: core/settings ×2, core/webhooks, daily-life/goals + schedule + notes) vs LookupError via `delete_with_existence_check` (2 services: erp metas_empresa + metas_equipe).

**Improvements:**
- Surface vs Engineer J: Engineer J's `.delete().execute()` regex was too literal — broke on multi-line chains. Used reverse-grep (`if not result.data` then look-back for `.delete()` within 6 lines of an assignment) as more-robust shape detection. Recommendation: add this pattern to `noctus.dev.scan_block_patterns` / `noctus.hound.scan` so future audits don't depend on agent care.

### Phase 1 — Mechanical refactor ✅

- [x] AST-first edits (libcst) per callsite. NEVER sed/regex. Single libcst transformer at `/tmp/precheck-refactor/refactor.py`:
  - Matches `result = db.table("T").delete().eq(...)*.execute()` via CST walk (any `.eq()` chain length)
  - Matches the following `if not result.data: raise ...` block (single-statement body)
  - Replaces BOTH statements with one helper call (positional db + table + variadic predicate tuples + kwarg message/not_found_exc)
  - Auto-inserts `from noctusai_lib.api.crud_safety import <helper>` at the right slot in module top (after last existing import; handles modules with __future__ + docstring correctly)
- [x] Add helper import at each of 7 module tops (8 callsites, but settings.py has 2 callsites sharing the same import). 
- [x] Replace each 3-line anti-pattern block with the 1-line helper call.
- [x] Preserve message strings + status codes (no diff in 404 detail strings; no change to LookupError messages).

**Improvements:**
- Discovered + patched seed-lib helper gap during Phase 2 verification: `delete_with_existence_check` hardcoded `select("id")` for the existence pre-check, which fails the mock-schema validator (and would fail in prod) on tables keyed on non-`id` columns (e.g. `platform_settings.key`). Patched the helper to use `predicates[0][0]` as the projection column + added `ValueError` for zero-predicates case. Added 2 regression tests (`test_select_projection_uses_first_predicate_column` + `test_no_predicates_raises_value_error`). Helper test count: 12 → 14.

### Phase 2 — Verify + close ✅

- [x] Run `pytest` for each affected product backend — all green (no regression):
  - **core**: 6 failed / 451 passed / 9 skipped. **Baseline was 8 failed**; all 6 remaining are pre-existing (api_keys ×2, onboarding ×2, test_accounts, webhooks-PATCH). The 2 fixes: org-settings-DELETE and webhook-DELETE happy paths that were baseline-broken pass now because the helper does the right thing.
  - **daily-life**: 234 passed / 0 failed.
  - **erp-imobiliario**: 4 failed / 1856 passed (matches baseline exactly: same 4 pre-existing failures in test_financeiro / test_recorrencia services).
  - **seed-lib (crud_safety)**: 14/14 helper tests green.
  - **seed-lib (all)**: 1067/1067 green (no regression).
- [x] Run keeper review for each affected product — 0 issues (core / daily-life / erp-imobiliario).
- [x] Run `grep` to confirm zero remaining instances of the anti-pattern across all products. Confirmed: `TOTAL: 0`.
- [x] Tick all sub-tasks + Improvements blocks + §11 close entry.
- [ ] Archive via `noctus.dev.archive` — **orchestrator handles archive after fresh-eyes merge per brief; engineer does NOT delete the project folder.**

## 7. Open questions

- None — mechanical refactor; Engineer J's Phase 0 surfaced everything needed.

## 8. Dependencies & blockers

- Helper landed on main (commit `286df84`). No blocker.

## 9. Success criteria

- [x] **8** callsites consume the helper (1 more than Engineer J's listed 7; surfaced via reverse-grep that caught multi-line chains).
- [x] Zero remaining `.delete().execute() + if not result.data:` shapes across products (final grep: `TOTAL: 0`).
- [x] Test suites green for all affected products (no new failures; core: −2 vs baseline; daily-life + erp + seed-lib: exact baseline match).

## 10. How to use this plan

Single-engineer dispatch via `git worktree add`. Mechanical scope — should close in one session.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer J's `delete-precheck-seed-lift` Phase 0 grep surfaced 6-7 additional callsites of the same anti-pattern (core/settings ×2, daily-life/goals,schedule,notes, ERP metas_empresa, metas_equipe). Helper already shipped — this project is the mechanical consumer refactor. | claude-opus-4-7 |
| 2026-05-10 | **Phase 0 reconciled — actual count = 8** (not 6 or 7). Engineer J's grep missed `products/core/backend/app/routers/webhooks.py:143` because the `.delete().eq(...)` chain was broken across multiple lines, defeating their literal `\.delete\(\)\.execute\(\)` regex. Reverse-grep (find `if not result.data:`, look back ≤6 lines for `.delete()` + assignment + chained `.execute()`) caught all 8. 1 newly-surfaced ≪ N≥4 STOP threshold → expanded scope inline. | claude-opus-4-7 (engineer dispatch) |
| 2026-05-10 | **Phase 1 complete.** AST-first refactor via libcst across 8 callsites in 7 files. Single transformer handles both helper variants (`delete_or_404` for routers raising `HTTPException`, `delete_with_existence_check` for services raising `LookupError`) + variadic predicate counts (1-2 `.eq()` pairs observed) + auto-injects the import at the right module-top slot. Zero whitespace damage. | claude-opus-4-7 (engineer dispatch) |
| 2026-05-10 | **Phase 2 surfaced + fixed a seed-lib helper gap.** First pytest run on core caught `MockSchemaError: public.platform_settings has no column 'id' (called via select)` — the helper hardcoded `select("id")` for the existence pre-check. Patched `delete_with_existence_check` to use the first predicate's column name as the projection (`predicates[0][0]`) + added `ValueError` for zero-predicates case. Added 2 regression tests. 14 helper tests now green (was 12). All 8 callsite refactors land green. | claude-opus-4-7 (engineer dispatch) |
| 2026-05-10 | **Phase 2 verification complete.** Per-product test results: core 6F/451P (baseline was 8F → net −2 because helper fixes 2 baseline-broken DELETE tests); daily-life 234P/0F; erp-imobiliario 4F/1856P (exact baseline match — 4 pre-existing failures in test_financeiro / test_recorrencia services unrelated to delete-precheck). Keeper 0 issues for all 3 products. Final grep: 0 remaining `.delete().execute() + if not result.data:` shapes in `products/*/backend/`. | claude-opus-4-7 (engineer dispatch) |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
