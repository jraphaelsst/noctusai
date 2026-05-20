# conftest-worktree-sys-path-fanout — Project Document

> **Filed 2026-05-20** as the N=5 cross-product DRY follow-up surfaced by ERP-P7. Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** 📋 **FILED** — N=5 cross-product byte-identical pattern; formalize-pass.
- **Owner / stakeholders:** joaoraphaelsst@gmail.com · architect
- **Related docs:**
  - `products/erp-imobiliario/backend/tests/conftest.py` (the reference fix shipped by ERP-P7)
  - `KB § PATTERNS/testing.md`
  - axis-swap event 2026-05-16 (`seed/lib/backend/noctusai_seed` → `seed/framework/backend/noctusai_seed`)
- **Project slug:** `conftest-worktree-sys-path-fanout` (root `projects/`)

---

## 1. Context & Purpose

ERP-P7 (erp-wiring Phase 7) discovered that the ERP backend test suite was fully broken in worktree-isolated runs — `ModuleNotFoundError: No module named 'noctusai_seed'` for every test. Root cause: the 2026-05-16 axis-swap moved `noctusai_seed` from `seed/lib/backend` to `seed/framework/backend`, and the shadow-purge helper was updated, but the per-product conftest `sys.path.insert(0, _LIB)` half of the fix was NOT mirrored — only `seed/lib/backend` was on the path. In a worktree, the main-tree editable finder for `noctusai_seed` is correctly dropped (it points outside the worktree's `seed/framework/backend`) and there's no fallback path.

ERP-P7 fixed it for ERP-imobiliário in-flight (`_FRAMEWORK = seed/framework/backend` injection alongside `_LIB`). N=5 sample showed the same half-fix exists in `PF`, `daily-life`, `adconnect`, `core`. Every parallel-worktree engineer hits this 60+s tax on cold-start.

**This project is the byte-identical fix fan-out.**

---

## 2. Confirmed constraints

- **Byte-identical fix per product.** The `_FRAMEWORK` injection lines are functionally the same; only the relative path resolution differs (each product's `tests/conftest.py` computes the repo root differently).
- **One engineer dispatch.** 4 file-disjoint edits; parallel-safe.
- **No seed change.** The fix is per-product because `conftest.py` is per-product.
- **Optional seed-side formalization** at end: extract `from noctusai_lib.testing.conftest_helpers import inject_seed_paths` so future products inherit the fix at scaffold. Currently N=5 → fits the seed-lift criterion.

---

## 3a. Seed-first analysis

The proximate fix is per-product (each conftest computes paths differently). The **durable** fix is seed-side: lift `inject_seed_paths()` (or similar) to `noctusai_lib.testing` and call it from each conftest. After scaffold absorbs the helper, the same line ships in every new product.

Per-product code count after seed-lift: 1 line per conftest (a single function call). Without seed-lift: ~6-8 lines per conftest (the path computation + insertion).

**Recommended:** ship the per-product fix first (P1), then file the seed-lift as a stretch P2.

---

## 4. Scope

**In scope:**
- 4 conftest.py edits: `PF` / `daily-life` / `adconnect` / `core` (mirror the ERP-P7 fix).
- 1 verification: run each product's `pytest` from a fresh worktree to confirm the import is resolved.
- Optional seed-lift to `noctusai_lib.testing.conftest_helpers`.

**Out of scope:**
- Other products not in the N=5 sample (therapy-platform, social-wiring, etc.) — extend in a later wave if they have the same conftest shape.
- The cross-cutting "every product should ship `pytest-timeout`" rule — separate concern.

---

## 6. Phases

- **P0 ⏳** — Audit: verify the 4 named products have the same half-fix shape (the assumption is N=5 from ERP-P7's sampling, but confirm).
- **P1 ⏳** — Apply byte-identical fix to 4 conftests (parallel-safe, single engineer).
- **P2 ⏳ (optional)** — Seed-lift `inject_seed_paths()` to `noctusai_lib.testing.conftest_helpers`; refactor each conftest to call it.
- **P3 ⏳** — Verify: `pytest` from worktree-isolated checkout of each product passes.

---

## 7. Open questions

1. **Seed-lift in this project or separate?** Recommendation: ship P1 first (closes the immediate friction), defer P2 unless N=6+ (a 6th product would trigger formalize-MUST). Currently N=5 → formalize-candidate but not MUST.

---

## 9. Success criteria

- 4 product conftests inject both `_LIB` and `_FRAMEWORK` paths.
- `pytest` from a fresh worktree of any of the 4 products resolves `noctusai_seed` cleanly.
- Optional: seed helper ships if P2 elected.

---

## 11. Change log

| Date | Entry | By |
|---|---|---|
| 2026-05-20 | Filed as N=5 cross-product DRY from ERP-P7 finding. Cure for the worktree-bootstrap pattern. | Architect |
