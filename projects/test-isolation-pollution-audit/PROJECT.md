# test-isolation-pollution-audit — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 📋 **READY FOR EXECUTION.** Filed under user signal "create projects for deferrals/parks that happen along the way." Multiple engineers this session (J, V, R) observed pytest baseline failures that PASS in isolation but FAIL in full-suite runs across multiple products. Indicates module-level / fixture-level state pollution.
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

### Phase 0 — therapy-platform isolation-pollution diagnosis

- [ ] Install `pytest-randomly` in therapy-platform's test env.
- [ ] Reproduce the 4 failures in full suite; confirm pass in isolation.
- [ ] Bisect to find the polluter (or polluter cluster).
- [ ] Document polluter + leak shape (module-level state? fixture autouse=True without teardown? mutable-default-arg?).

### Phase 1 — Fix therapy-platform polluter

- [ ] Patch polluter (add teardown, scope fixture correctly, remove module-state).
- [ ] Verify 4 failures gone in full suite.
- [ ] Verify they STILL pass in isolation (no regression).

### Phase 2 — ERP + PF classification

- [ ] Run same audit recipe on ERP (4F) + PF (3F).
- [ ] Classify each: isolation-pollution / genuine logic bug.
- [ ] For isolation: same fix shape as Phase 1.
- [ ] For genuine: file as separate follow-up project; don't fix in scope here.

### Phase 3 — KB amend + close

- [ ] `KB § PATTERNS/testing.md` gains a "Test-isolation pollution detection" subsection: pytest-randomly recipe + bisect + common polluter shapes.
- [ ] Memory entry if a durable methodology lesson surfaces (e.g. "module-level state across products always pollutes — extract to fixtures").
- [ ] Archive.

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

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
