# test-isolation-pollution-audit — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-11
- **Status:** ✅ **COMPLETE.** All 4 therapy isolation-pollution failures fixed at the polluter source (seed-lib `MockRequestBuilder.__init__` deep-copy guard). ERP (4F) + PF (2F — baseline-drifted from "3F") classified as **genuine logic/test bugs**, filed as `products/erp-imobiliario/projects/financeiro-overdue-test-genuine-bug/` + `products/personal-finance/projects/orcamento-progresso-test-genuine-bug/`. KB amended with "Test-isolation pollution detection" subsection.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `test-isolation-pollution-audit`

---

## 1. Context & Purpose

Throughout the 2026-05-10 mass-dispatch session, multiple engineers observed pytest baseline-failure shape:

- **therapy-platform**: 4 pre-existing failures (`test_review_alert_admin_allowed`, `test_deny_refund_with_reason`, `test_review_as_false_positive`, `test_review_pending_homework_fails`) — all 4 PASS when run in isolation; FAIL in full-suite. (Engineers C, R, V observed.)
- **ERP**: 4 pre-existing failures (mark_overdue + inadimplência) — Engineer D + J observed; status unclear if isolation-bug or genuine logic bug.
- **PF**: 3 pre-existing failures (mock UPDATE propagation) — Engineer B + Q observed; appear genuine (mock-side gap).

The therapy 4F set is the clearest test-isolation pollution case — pass-in-isolation + fail-in-full-suite is the hallmark of mutable-module-state / fixture-bleed.

## 2. Confirmed constraints

- **Pass-in-isolation + fail-in-full-suite ≡ test pollution** (module-level state, fixture-bleed, or test-ordering-dependent assertion).
- **The polluter is upstream of the failing tests** in the test-ordering — identifying it requires bisection.
- **pytest-randomly** would help amplify the bug + nail the polluter — install + run repeatedly.

## 3. Design principles

1. **Diagnose before patch.** Don't add `@pytest.fixture(autouse=True)` cleanups blindly — find the polluter first.
2. **pytest-randomly + bisect** is the canonical detection recipe.
3. **Fix at the polluter, not the polluted.** The fix lives where the mutable state leaks, not where it manifests.

## 3a. Seed-first analysis

- **Cross-product?** YES — three products affected.
- **Seed home?** N/A — this is a debug/audit project. The methodology lesson (if any) lands in `KB § PATTERNS/testing.md`.
- **Per-product code count for fix?** Per-test or per-fixture; the polluter may be a single mutable-default-arg or module-level state.

## 4. Scope

- **In scope:**
  - therapy-platform: identify the 4 isolation-pollution polluter(s) + fix.
  - ERP: classify the 4 failures (isolation-bug vs genuine).
  - PF: classify the 3 failures (isolation-bug vs genuine).
  - KB doc amend: testing patterns gain a "pollution detection" subsection.
- **Out of scope:**
  - Fixing genuine logic bugs (file as separate follow-ups if surfaced).

## 5. Architecture / Data Model

Detection recipe per product:

```bash
# 1. Reproduce full-suite failure
pytest products/<product>/backend/ -q
# 2. Confirm isolation passes
pytest products/<product>/backend/tests/path/to/test::ClassName::test_method -q
# 3. pytest-randomly + bisect to find polluter
pytest products/<product>/backend/ -p randomly --randomly-seed=<seed>
pytest products/<product>/backend/ --co -q  # list test order
# Bisect: run subsets to narrow the polluter cluster
```

## 6. Implementation phases

### Phase 0 — therapy-platform isolation-pollution diagnosis ✅

- [x] Install `pytest-randomly` in therapy-platform's test env.
- [x] Reproduce the 4 failures in full suite; confirm pass in isolation.
- [x] Bisect to find the polluter (or polluter cluster).
- [x] Document polluter + leak shape (module-level state? fixture autouse=True without teardown? mutable-default-arg?).

**Polluter identified:** `seed/lib/backend/noctusai_lib/testing/mocks.py::MockRequestBuilder` — the write-to-read propagation feature (added 2026-05-10) calls `dict.update(row, payload)` *in place* on rows stored in `self._data`. Since `_data` is materialized via shallow `list(data)`, callers that pass a module-level `SAMPLE_X` dict have that dict mutated by any UPDATE in any test. **Leak shape:** module-level mutable fixture dict shared by reference into the mock's mutation primitive. Reproduced minimally: running `test_submit_homework` (mutates status → "concluido") then `test_review_pending_homework_fails` (expects status=="pendente") = 1F. Same shape applies to all 4 (crisis-router, refunds-router, crisis-service, homework-service).

**Improvements:**
- Caught a hidden cost of the 2026-05-10 write-propagation feature: cross-test fixture pollution when callers pass module-level dicts. Fix preserves the feature (within-builder mutation still propagates) while isolating callers.

### Phase 1 — Fix therapy-platform polluter ✅

- [x] Patch polluter (add teardown, scope fixture correctly, remove module-state).
- [x] Verify 4 failures gone in full suite.
- [x] Verify they STILL pass in isolation (no regression).

**Fix shape:** deep-copy at storage time in `MockRequestBuilder.__init__`. Three lines changed (dict / list / iterable branches) wrapped in `copy.deepcopy(...)`. AST-driven via libcst (per the AST-first rule). `import copy` added to top of module.

**Verification (with `PYTHONPATH=$WORKTREE/seed/lib/backend`):**
- Therapy full-suite, deterministic order: **1284 passed, 14 skipped, 0 failed** (was 4F).
- Therapy full-suite, `pytest-randomly` seeds {1, 42, 999}: all **1284 passed, 14 skipped, 0 failed**.
- Each of the 4 named tests, in isolation: still passing (no regression).
- Seed-lib own tests (`test_mock_write_propagation.py` + `test_mock_payload_tracking.py`): 30 passed (no regression on the propagation feature).

**Improvements:**
- AST patch via libcst — kept structural-edit discipline. Comment expanded to call out the deep-copy intent for future readers.

### Phase 2 — ERP + PF classification ✅

- [x] Run same audit recipe on ERP (4F) + PF (3F).
- [x] Classify each: isolation-pollution / genuine logic bug.
- [x] For isolation: same fix shape as Phase 1.
- [x] For genuine: file as separate follow-up project; don't fix in scope here.

**ERP (4F) — ALL GENUINE.** Each fails in isolation:
- `test_financeiro_service.py::TestMarkOverdue::test_marks_overdue_records` — seeded `status="atrasado"` rows but service filters `eq("status", "pendente")` → count=0, expected 2.
- `test_recorrencia_service.py::TestVerificarInadimplencia::test_marks_overdue_lancamentos` / `test_marks_overdue_parcelas` / `test_combined_lancamentos_and_parcelas` — same fixture-vs-contract drift around `pendente → atrasado` transition.

**Filed:** `products/erp-imobiliario/projects/financeiro-overdue-test-genuine-bug/`.

**PF (2F — baseline-drifted from "3F" in the original project doc) — ALL GENUINE.** Each fails in isolation:
- `test_orcamentos_service.py::TestObterProgressoWithSync::test_progress_percentage_calculation` — `percentual_usado = 0.0` not 50.0; suspected mock-aggregation gap.
- `test_transacoes_service.py::TestBalanceReversalOnUpdate::test_reverses_old_and_applies_new` — `result = None`; suspected mock-update-return-shape gap.

**Filed:** `products/personal-finance/projects/orcamento-progresso-test-genuine-bug/`.

**Improvements:**
- PROJECT.md said "PF 3F"; baseline at audit time = 2F. Counts drift between filing and execution; always re-verify at project-pickup.

### Phase 3 — KB amend + close ✅

- [x] `KB § PATTERNS/testing.md` gains a "Test-isolation pollution detection" subsection: pytest-randomly recipe + bisect + common polluter shapes.
- [x] Memory entry if a durable methodology lesson surfaces — **routed to orchestrator as text** (engineer does not edit MEMORY.md per §17.6 protocol; orchestrator transcribes the methodology lesson at merge time).
- [x] Archive (orchestrator at project close).

**Improvements:**
- Memory entry candidate (routed to orchestrator): "Mock-Supabase write-propagation must deep-copy input rows — in-place mutation of caller-shared dicts is a pollution vector. Deep-copy at storage time in `MockRequestBuilder.__init__` preserves the within-builder propagation feature while isolating module-level fixture dicts. N=4 polluted tests in therapy-platform surfaced this; fixed at the seed."

## 7. Open questions

- None — methodology is well-known; this is execution-only.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [ ] therapy-platform: 0 isolation-pollution failures.
- [ ] ERP + PF: classified + fixed-or-filed.
- [ ] KB testing pattern updated.

## 10. How to use this plan

Single-engineer dispatch. Iterative bisection work; might require multi-hour focused session.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineers J, V, R observed pass-in-isolation + fail-in-full-suite pattern across therapy-platform (4F), ERP (4F), PF (3F). pytest-randomly + bisect is the canonical recipe. | claude-opus-4-7 |
| 2026-05-11 | **All phases complete.** Phase 0: polluter identified — `MockRequestBuilder.__init__` shallow-copies `_data` list, allowing UPDATE/DELETE in-place mutation to reach caller's module-level `SAMPLE_X` dicts. Phase 1: deep-copy guard at storage time (AST patch via libcst); therapy 4F → 0F (verified deterministic + pytest-randomly seeds 1/42/999); seed-lib own propagation tests still 30/30 pass. Phase 2: ERP 4F + PF 2F (was 3F per project doc; baseline drift) all reproduce in isolation → genuine bugs; filed as `products/erp-imobiliario/projects/financeiro-overdue-test-genuine-bug/` + `products/personal-finance/projects/orcamento-progresso-test-genuine-bug/`. Phase 3: KB testing.md amended with "Test-isolation pollution detection" subsection. | engineer (worktree-ab7998dd) |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
