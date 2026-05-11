# financeiro-overdue-test-genuine-bug — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Filed by `projects/test-isolation-pollution-audit/` Phase 2. 4 ERP pre-existing failures classified as **genuine logic / test-fixture bugs**, NOT isolation pollution — they fail both in full-suite AND in isolation.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `financeiro-overdue-test-genuine-bug`

---

## 1. Context & Purpose

During execution of `projects/test-isolation-pollution-audit/` (2026-05-11), Phase 2 classification confirmed that ERP's 4 pre-existing failures all reproduce in **isolation** (single-test invocation), proving they are NOT test-isolation pollution. They are genuine mismatches between test fixtures and service contracts — likely the test seeds rows in a state that the service-under-test does not match against, so the service correctly returns "0 matched" and the test wrongly asserts "2 matched".

**Failing tests (all 4 fail in isolation):**

1. `products/erp-imobiliario/backend/tests/services/test_financeiro_service.py::TestMarkOverdue::test_marks_overdue_records`
2. `products/erp-imobiliario/backend/tests/services/test_recorrencia_service.py::TestVerificarInadimplencia::test_marks_overdue_lancamentos`
3. `products/erp-imobiliario/backend/tests/services/test_recorrencia_service.py::TestVerificarInadimplencia::test_marks_overdue_parcelas`
4. `products/erp-imobiliario/backend/tests/services/test_recorrencia_service.py::TestVerificarInadimplencia::test_combined_lancamentos_and_parcelas`

**Sample evidence (`test_marks_overdue_records`):**
- Test seeds rows with `status="atrasado"` (already overdue).
- `FinanceiroService.mark_overdue()` filters `eq("status", "pendente").lt("data_vencimento", today)` — no `pendente` rows → 0 returned.
- Test asserts `count == 2`. AssertionError: `0 == 2`.

The fixture should seed `status="pendente"` and `data_vencimento` past today; OR the test should assert the no-op result. Same pattern likely applies to the recorrencia trio.

---

## 2. Confirmed constraints

- These are **genuine bugs**, classified by `projects/test-isolation-pollution-audit/` Phase 2 (`pytest -p no:randomly <single-test> -q` reproduces).
- No isolation-pollution fix will resolve them (the deep-copy guard added in `seed/lib/backend/noctusai_lib/testing/mocks.py` doesn't change their outcome).
- ERP is not currently on the critical-path; deferred to its own ownership.

## 3. Design principles

- Diagnose per-test: read the service contract, read the test fixture, identify the mismatch.
- Fix the fixture (preferred) unless the service contract itself is the bug.

## 3a. Seed-first analysis

- **Cross-product?** NO — ERP-specific service-layer tests.
- **Seed home?** N/A — bug-fix scope.

## 4. Scope

- **In scope:**
  - Diagnose each of the 4 failing tests (fixture vs. service-contract mismatch).
  - Patch fixtures (or service, if contract is the bug).
  - Verify all 4 pass both in isolation AND in full-suite.
- **Out of scope:**
  - Refactoring the financeiro/recorrencia services.

## 5. Architecture / Data Model

Failures cluster around the `pendente → atrasado` (overdue) transition. Likely a fixture-vocabulary drift: tests written when the service used different status names, or before the `data_vencimento < today` predicate was tightened.

## 6. Implementation phases

### Phase 0 — Diagnose all 4

- [ ] Read each test fixture + the corresponding service method.
- [ ] Document the exact mismatch per test (fixture-state vs. service-filter).

### Phase 1 — Fix all 4

- [ ] Patch each fixture (or service, if the contract is the bug).
- [ ] Verify each passes in isolation.
- [ ] Verify the full ERP suite is green (0F).

## 7. Open questions

- For `test_marks_overdue_records`: should the test seed `pendente` rows (more useful — exercises the real path) or assert `count == 0` (tests current behavior)? **Recommendation:** seed `pendente` rows so the test exercises the actual contract.

## 8. Dependencies & blockers

- None. Self-contained ERP-only fix.

## 9. Success criteria

- [ ] All 4 named tests pass in isolation.
- [ ] Full ERP suite green (`pytest products/erp-imobiliario/backend/` → `0 failed`).

## 10. How to use this plan

Single-engineer dispatch. Likely 1-2 hour focused session.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | **Filed** by `projects/test-isolation-pollution-audit/` Phase 2 after classifying these 4 as genuine logic/test bugs (all reproduce in isolation). | engineer |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
