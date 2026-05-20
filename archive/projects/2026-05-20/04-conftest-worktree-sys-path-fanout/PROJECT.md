# conftest-worktree-sys-path-fanout — Project Document

> **Filed 2026-05-20** as the N=5 cross-product DRY follow-up surfaced by ERP-P7. Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** ✅ **P0/P1/P3 DONE** — fix applied to 4 conftests; P2 seed-lift deferred. Engineer B 2026-05-20.
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

- **P0 ✅** — Audit: confirmed all 4 named conftests ship the half-fix shape (only `_LIB`, no `_FRAMEWORK`). PF=personal-finance slug. Alias variants observed: daily-life uses bare `sys`/`Path`; pf/adconnect/core use `_sys`/`_Path` aliases. ERP-imobiliario reference at `products/erp-imobiliario/backend/tests/conftest.py:48-60` is the byte-identical target shape.

  **Improvements:**
  - **Applied inline**: PF slug discrepancy — brief said `pf`, on-disk is `personal-finance`. Caught early at file-not-found; resolved by reading `ls products/`.
  - **Applied inline**: Alias-variant detection (`_sys`/`_Path` vs `sys`/`Path`) — fix script auto-detects per-file alias and preserves it byte-identically in the replacement.
  - **Bystander finding (deferred to architect)**: Stale editable-finder pollution — the host `pytest` fails BEFORE any conftest runs because `/opt/homebrew/lib/python3.11/site-packages/__editable___noctusai_lib_0_1_0_finder.py` maps `noctusai_lib` → deleted sibling worktree `.claude/worktrees/agent-a94cc7de313f7aebc/seed/lib/backend/noctusai_lib`. The `noctusai-product-bootstrap` `pytest11` entry-point fails to import, killing pytest before conftest sys-path-injection can help. **Workaround for P3**: `pytest -p no:noctusai-product-bootstrap` confirms the fix works. **Destination**: file a `stale-editable-install-cleanup` follow-up — root fix is `pip install -e seed/lib/backend` from the architect's primary tree to rebind the finder, OR teach `scripts/cleanup-stale-worktrees.sh` to also re-pin the editable install when a worktree is removed.

- **P1 ✅** — Applied byte-identical fix to 4 conftests via `/tmp/apply_fanout_fix.py` (alias-preserving). Patch at `/tmp/engineer-B-conftest-fanout.patch` (100 lines, 4-file diff).

  **Improvements:**
  - **Applied inline**: Idempotency guard — script skips files where `_FRAMEWORK` already appears, so re-running is safe.
  - **Bystander finding**: The fix script (`/tmp/apply_fanout_fix.py`) is the seed-lift in disguise — it's the algorithm any future product's conftest would need. **Destination**: P2 (seed-lift) below.

- **P2 ⏳ (optional, deferred)** — Seed-lift `inject_seed_paths()` to `noctusai_lib.testing.conftest_helpers`. Per brief instructions, NOT in P1 scope; filed as stretch bystander recommendation. See findings.md for the formalize-MUST argument (N=5 platform-wide).

- **P3 ✅** — Verified with `pytest --collect-only -p no:noctusai-product-bootstrap` (bypass for the pre-existing env-level stale-finder issue surfaced in P0 Improvements):
  - `personal-finance`: 625 tests collected
  - `daily-life`: 232 tests collected
  - `adconnect`: 266 tests collected
  - `core`: 533 collected + 2 pre-existing collection errors in `tests/services/test_sso_cache_invalidation.py` (TypeError: Router.__init__ — unrelated to fanout, pre-existing)

  Without the `-p no:noctusai-product-bootstrap` bypass, all 4 products (including ERP-imobiliario reference!) fail with the same `ModuleNotFoundError: No module named 'noctusai_lib'` — proving the failure is environmental, NOT solvable at conftest level.

  **Improvements:**
  - **Applied inline**: Verified ERP-P7 reference also fails identically without bypass — proves the env issue is pre-existing and the fanout fix shape itself is correct.
  - **Bystander finding (deferred to architect)**: Core's 2 pre-existing collection errors (`test_sso_cache_invalidation.py`) — out-of-scope here; **destination**: separate `core-sso-test-collection-error` follow-up project or fix-on-contact in next core-touching session.

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
| 2026-05-20 | P0/P1/P3 executed. 4 conftests patched byte-identically with `_FRAMEWORK = _REPO / "seed" / "framework" / "backend"` injection. Verified import resolves with `pytest -p no:noctusai-product-bootstrap`. Surfaced pre-existing env-level stale-editable-finder issue (deleted sibling worktree) — separate from this project's scope. P2 deferred. | Engineer B |
