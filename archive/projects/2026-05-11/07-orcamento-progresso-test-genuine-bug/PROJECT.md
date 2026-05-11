# orcamento-progresso-test-genuine-bug — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Filed by `projects/test-isolation-pollution-audit/` Phase 2. PF baseline = **2 failures** (project doc said 3, but a 3rd may have been resolved upstream between filing and audit). Both remaining failures fail in isolation → **genuine logic / mock-coverage bugs**, NOT isolation pollution.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `orcamento-progresso-test-genuine-bug`

---

## 1. Context & Purpose

During execution of `projects/test-isolation-pollution-audit/` (2026-05-11), Phase 2 classification confirmed both PF failures reproduce in single-test invocation, proving NOT isolation pollution.

**Failing tests (both fail in isolation):**

1. `products/personal-finance/backend/tests/services/test_orcamentos_service.py::TestObterProgressoWithSync::test_progress_percentage_calculation`
   - `result["percentual_usado"]` asserted to be `50.0` but came back as `0.0`.
   - Probable cause: mock-Supabase aggregation/sum path returning 0 instead of summing seeded transactions, OR the service queries a path the mock doesn't simulate (e.g. RPC, JOIN, or schema-bound view).

2. `products/personal-finance/backend/tests/services/test_transacoes_service.py::TestBalanceReversalOnUpdate::test_reverses_old_and_applies_new`
   - `svc.atualizar("tx-001", {"valor": 500})` returned `None`.
   - Probable cause: the service's UPDATE chain in the mock returns no row because the predicate doesn't match seeded data, OR the mock-update-return-shape doesn't preserve `result.data[0]`.

Both look like **mock-coverage gaps in the service code paths** (e.g. an RPC sum, or a different filter shape), not isolation pollution — even after the 2026-05-11 deep-copy guard, both still fail.

---

## 2. Confirmed constraints

- These are **genuine bugs**, classified by `projects/test-isolation-pollution-audit/` Phase 2.
- No isolation-pollution fix will resolve them.
- PROJECT.md for `test-isolation-pollution-audit` said "PF 3F"; current baseline shows 2F — third may have been resolved between filing and audit; not investigated here.

## 3. Design principles

- Read the service implementation first; understand which mock primitive (`select`, `update`, RPC, view) it uses.
- Decide: extend the mock primitive (if recurring shape) OR patch the test seed (if one-off).

## 3a. Seed-first analysis

- **Cross-product?** Possibly — `orcamento progresso` uses sum/aggregation. If the mock-Supabase gap is generic, fix lives in seed (`noctusai_lib.testing`). If specific to PF service shape, lives in PF.
- **Seed home?** Decide after Phase 0 diagnosis.

## 4. Scope

- **In scope:**
  - Diagnose both failures (mock-gap vs. service-bug).
  - Fix at correct layer.
  - Verify both pass in isolation AND in full-suite.
- **Out of scope:**
  - The "3rd PF failure" mentioned in the parent project (already gone at audit time).

## 5. Architecture / Data Model

Failures cluster around:
- Budget progress percentage calculation (transactional sum into orçamento context).
- Transaction-update balance reversal flow.

## 6. Implementation phases

### Phase 0 — Diagnose both

- [ ] Read `app/services/orcamentos_service.py::obter_progresso` + test fixture.
- [ ] Read `app/services/transacoes_service.py::atualizar` + test fixture.
- [ ] Document each mismatch.

### Phase 1 — Fix both

- [ ] Patch at correct layer (seed mock vs. PF code).
- [ ] Verify both pass in isolation.
- [ ] Verify the full PF suite is green (0F).

## 7. Open questions

- Does `obter_progresso` call an RPC or use a sum-aggregation query that the mock doesn't simulate? Inspecting the service file will resolve.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [ ] Both named tests pass in isolation.
- [ ] Full PF suite green.

## 10. How to use this plan

Single-engineer dispatch. Likely 1-hour focused session.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | **Filed** by `projects/test-isolation-pollution-audit/` Phase 2 after classifying these as genuine bugs (both reproduce in isolation). | engineer |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
