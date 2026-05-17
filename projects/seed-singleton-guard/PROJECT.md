# seed-singleton-guard — Project Document

> Living document. Filed 2026-05-16 as the **named destination** for the `noctusai_lib.testing.seed_singleton_guard` N≥3 test-isolation helper surfaced across the social-wiring absorption (TEST-ISO / DEP-A). Self-contained — no dependency on the originating project folder surviving.

- **Created:** 2026-05-16
- **Status:** Filed / not started — **gated** on the prerequisite below (DEP-A landed; this is the formalize step)
- **Owner:** Raphael · architect: Claude Opus 4.7
- **Slug:** `seed-singleton-guard` (cross-product / seed-testing-infra → `projects/seed-singleton-guard/`)

## 1. Context & Purpose

The social-wiring absorption hit the **same test-infra global-state-leak class three times** (N≥3 → MUST formalize per the recurrence rule):

1. `noctusai_seed` `exec_module` shadow under cached `app.*` → fixed by the `purge_shadowing_editable_finders` per-package-root structural fix (DEP-A, commit `4b6c6c2`).
2. Module conftests re-running the purge after the canonical purge + seed-singleton population → swapped `sys.modules` (TEST-ISO, commit `09b7165`).
3. Module `client` fixtures mutating process-globals (consent registry, `DatabaseModule` patch, `ai_consent_features` cache, seed APScheduler) with no per-test restoration → ~55 cascade only under `pytest-randomly`.

Each was re-discovered product-side and bandaged locally. The root primitive — a seed `noctusai_lib.testing.seed_singleton_guard` (an autouse snapshot/restore guard for the seed-singleton + editable-finder + process-global surface) — should be **inherited** by every product test suite so the leak class cannot recur, rather than each product re-finding it (cf. the existing `bind_consent_module_to_mock` helper, the 2nd reinvention).

## 2. Prerequisites / gate

- DEP-A (`purge_shadowing_editable_finders` per-package-root awareness) has landed — that is the *structural* root fix. This project is the **formalize-into-seed step**: extract the autouse snapshot/restore pattern (currently in `tests/modules/conftest.py`) into a reusable `noctusai_lib.testing` helper + the recipe for products to adopt it.

## 3. Scope

- `noctusai_lib.testing.seed_singleton_guard` — autouse fixture/context that snapshots + restores the seed-singleton + editable-finder + the known process-global surface; documented adoption recipe; colocated tests.
- Migrate the social-wiring `tests/modules/conftest.py` ad-hoc guard to the seed helper (proves the extraction).
- KB § PATTERNS/testing.md section + memory entry (three-way sync).

## 4. Success criteria

Product test suites inherit isolation from the seed helper (no per-product re-implementation); the 3 leak instances above stay fixed; a new product gets the guard for free.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-16 | Filed as the N≥3-formalize destination for the test-infra global-leak class (exec_module shadow / conftest re-purge / fixture global mutation). DEP-A is the structural root fix; this is the seed-helper formalize step. | Claude Opus 4.7 |
