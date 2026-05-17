# conftest-workaround-cleanup — Project Document

> Living document. Filed 2026-05-16 as the **named destination** for the mechanical removal of the now-redundant conftest call-site workarounds rendered no-ops by DEP-A during the social-wiring absorption. Self-contained — no dependency on the originating project folder surviving.

- **Created:** 2026-05-16
- **Status:** Filed / not started — **gated** on DEP-A being FF-merged to main (prerequisite below)
- **Owner:** Raphael · architect: Claude Opus 4.7
- **Slug:** `conftest-workaround-cleanup` (cross-product / test-infra hygiene → `projects/conftest-workaround-cleanup/`)

## 1. Context & Purpose

DEP-A (commit `4b6c6c2`, 2026-05-16) made `purge_shadowing_editable_finders` per-package-root aware — the **structural root fix** for the `noctusai_seed` import-shadow class. As a side effect, three product-side conftest call-site workarounds (applied during Wave 3 so the pilots could be independently green) are now **harmless no-ops**:

- `products/erp-imobiliario/backend/.../conftest.py` framework-fallback (applied `c16bfae`).
- `products/core/backend/.../conftest.py` config re-register (applied `c9e1abb`, W3.5).
- The therapy-platform PYTHONPATH crutch (therapy now collects natively post-DEP-A).

They were kept this wave per the parallel-collision discipline (other engineers held adjacent files) and catalogued accept-with-rationale meanwhile. This project is the **mechanical post-FF cleanup**: remove the dead workarounds, file-disjoint.

## 2. Prerequisites / gate

- **DEP-A FF-merged to main.** A branch-pushed DEP-A is not enough — the cleanup must run against a tree where the structural fix is the base, so the removal provably regresses nothing (pytest collect-clean is the oracle, per product). Verify DEP-A is on `origin/main` before dispatching.

## 3. Scope

- Remove the 3 now-no-op conftest workarounds (one file-disjoint chunk per product); flip the corresponding accept-with-rationale entries `accept`→`formalized` (DEP-A is the formalization).
- Oracle: each touched product's `pytest --collect-only` is clean with ZERO workaround (the DEP-A acceptance signal: daily-life/PF/ERP/core 0-err).

## 4. Success criteria

The 3 workarounds are gone; every touched product collects clean natively; accept-with-rationale entries flipped to formalized; no behavior change.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-16 | Filed as the mechanical post-FF cleanup for the conftest workarounds DEP-A made no-ops (kept this wave per parallel-collision discipline; accept-with-rationale meanwhile). | Claude Opus 4.7 |
