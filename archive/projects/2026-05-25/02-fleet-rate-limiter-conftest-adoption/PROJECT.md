# fleet-rate-limiter-conftest-adoption — Project Document

> Filed 2026-05-23 from the CI-rehab session. Self-contained (durable-docs rule).

- **Status:** ✅ SHIPPED 2026-05-25 — grounded against the tree (doc was stale): all 9 limiter-bearing products already import `reset_rate_limiter` EXCEPT `knowledge-extractor`, fixed this commit (P1 complete). P2 keeper `check_limiter_conftest_import` already exists + is wired into `check_all_products` (compliance.py). Success criteria met → ready to archive. *(Original filing said adconnect/dev-team/erp/seed/social-wiring were missing — all since adopted; only KE remained.)*
- **Owner:** architect

## 1. Context & Purpose

The seed ships `noctusai_lib.testing.fixtures.reset_rate_limiter` — an autouse fixture that clears the slowapi in-memory limiter between tests (absorbed from N=5 byte-identical per-product fixtures). With Redis down in tests, slowapi falls back to an **in-process in-memory** limiter whose state leaks across tests: a rate-limit "over limit" test exhausts an endpoint bucket, so any later test hitting that endpoint gets a **429** under `pytest-randomly` ordering — a latent order-dependent flake (passes in CI's seed, fails in others). This bit PF (`test_ai_router::test_persists_classification`) in the 2026-05-23 CI rehab; fixed by adding the import to PF's conftest.

**The gap is fleet-wide.** Scan 2026-05-23 — products with `app/rate_limit.py` whose `tests/conftest.py` does NOT import `reset_rate_limiter`:

| Product | conftest imports it? |
|---|---|
| core, daily-life, therapy-platform | ✅ |
| **adconnect, dev-team, erp-imobiliario, seed, social-wiring** | ❌ MISSING (latent flake) |
| personal-finance | ✅ fixed 2026-05-23 (commit `2ff7b934`) |

N=6 missing (1 fixed) ⇒ recurrence rule fires: formalize.

## 3a. Seed-first analysis

The fix already lives in the seed (`reset_rate_limiter`). This is an **adoption + enforcement** gap, not a missing primitive. Per-product code = 1 import line each (unavoidable — conftest is product-local), but the ENFORCEMENT is a single cross-product keeper. Zero new seed logic.

## 4. Scope

- **P1** — Add `from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401` to the 5 missing product conftests (adconnect, dev-team, erp-imobiliario, seed, social-wiring). Pilots first (erp + social-wiring), then non-pilots. ⚠ erp's conftest is being touched by the concurrent `feat/erp-portal-documentos-gate-fe` engineer — sequence erp AFTER that branch merges (collision avoidance).
- **P2** — Stage-4 keeper `check_limiter_conftest_import`: any product with `app/rate_limit.py` whose `tests/conftest.py` lacks the `reset_rate_limiter` import → warn. Colocated test (regression-test-the-detector). Wire into `check_seed_compliance`.
- **P3** — Verify each touched product's suite green under a couple of random seeds; three-way sync (KB testing.md note + memory).

## 9. Success criteria

- All products with a limiter import `reset_rate_limiter`; suites green under random ordering.
- `check_limiter_conftest_import` keeper ships green (0 baseline after P1).

## 11. Change log

| Date | Entry | By |
|---|---|---|
| 2026-05-23 | Filed from PF CI-rehab. PF fixed inline (`2ff7b934`); N=6 fleet gap scanned; keeper specced. | Architect |
