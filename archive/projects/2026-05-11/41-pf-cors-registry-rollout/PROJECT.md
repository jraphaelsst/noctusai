# PF CORS Registry Rollout — Project Document

> PF-only follow-up to CORS-REGISTRY-ROLLOUT (2026-05-11). PF was excluded
> from the original 10-product wave to avoid colliding with PF-AUTH-MIG; both
> now merged, so PF migrates to `@registry:own:personal-finance` cleanly.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Done — PF migrated, 22/22 sentinel tests green (+2 for PF: class-default + resolved-set parity), keeper 0 NEW.
- **Owner / stakeholders:** USER · Engineer PF-CORS-REGISTRY (this branch)
- **Related docs:**
  - `projects/cors-registry-rollout-2026-05-11/PROJECT.md` — predecessor (10 products).
  - `seed/lib/backend/noctusai_lib/config/cors_registry.py` — registry helper (unchanged).
  - `seed/lib/backend/noctusai_lib/config/settings.py` lines 51-90 — sentinel resolution (unchanged).
  - `KB § PATTERNS/environment.md § CORS_ORIGINS cascade`.
- **Project slug:** `pf-cors-registry-rollout` (root-level — cross-cutting, even though only 1 product).

---

## 1. Context & Purpose

CORS-REGISTRY-ROLLOUT (2026-05-11) migrated 10 of 11 hand-enumerated
`cors_origins` defaults to `"@registry:own:<slug>"`. PF was excluded because
PF-AUTH-MIG (in flight at the time) owned `products/personal-finance/backend/app/config.py`.

Both predecessors have now merged. PF is the last hand-enumerated holdout
(`"http://localhost:8090,http://localhost:5173,http://localhost:3000"`).
Per replication-to-seed symmetry (CLAUDE.md §1), the right per-product
code count for a cross-product concern is zero — the PF enumeration goes.

Win shape: every product reads its frontend-port + localhost-alts from
`start.sh PRODUCTS`. No drift possible.

---

## 2. User interrogation (Q→A)

Architect-dispatched follow-up; no live interrogation. Constraints set by
the brief inherit from CORS-REGISTRY-ROLLOUT.

---

## 3. Confirmed constraints

- **Sentinel form** — `"@registry:own:personal-finance"`.
- **AST-first** — libcst rewrite (single-line, but the rule fires regardless).
- **No `--no-verify`** — pre-commit hook must pass.
- **Branch-only push** — orchestrator owns FF-to-main.
- **Pre/post set equality** — the new resolution must match the old enumeration.

## 3a. Seed-first analysis

- **Concern type:** cross-product (CORS allow-list).
- **Seed location:** `noctusai_lib.config.cors_registry` + `BaseAppSettings.cors_origins_list`.
- **Per-product code count after this change:** 1 line per product (the sentinel string).
  CORE uses `@registry:all`; the other 10 + PF use `@registry:own:<slug>`. Zero
  product-side logic — just data declaration.
- **Replication test:** if a new product joins `start.sh PRODUCTS`, its CORS
  list flips automatically. PASS.

---

## 4. Pre/post evidence

**Pre-migration** (`PFSettings.cors_origins = "http://localhost:8090,http://localhost:5173,http://localhost:3000"`):
```
{http://localhost:3000, http://localhost:5173, http://localhost:8090}
```

**Post-migration** (`PFSettings.cors_origins = "@registry:own:personal-finance"`):
```
{http://localhost:3000, http://localhost:5173, http://localhost:8090}
```

Set-equal. Cardinality identical (3 elements). `start.sh PRODUCTS` row
`personal-finance:Personal Finance:8002:8090` supplies the `8090`.

---

## 5. Files touched

- `products/personal-finance/backend/app/config.py` — single-line default swap (libcst).
- `seed/lib/backend/tests/config/test_per_product_cors_sentinel.py` — add `"personal-finance"`
  to `PRODUCT_SLUGS` (now 11 entries); docstring updated.
- `seed/lib/backend/noctusai_lib/config/cors_registry.py` — **no change**. The brief
  asked to add PF to a `PRODUCT_SLUGS` tuple in this module and to update
  `derive_cors_origins`, but neither exists/needs touching: `derive_cors_origins`
  is data-driven from `start.sh PRODUCTS`, and the only `PRODUCT_SLUGS` symbol
  in the codebase is the test parametrization. See findings §1.

---

## 6. Phases

- **Phase 0 — Audit** (DONE): read PF config.py; confirmed hardcoded
  3-origin enumeration. Verified `start.sh` registry row + sentinel resolution
  yields the same set.
- **Phase 1 — Tuple update** (DONE): added `"personal-finance"` to
  `PRODUCT_SLUGS` in the sentinel test file (alphabetic position).
- **Phase 2 — Config migration** (DONE): libcst transformer swapped
  default to `"@registry:own:personal-finance"`.
- **Phase 3 — Tests** (DONE):
  - Sentinel suite: 22/22 (was 20 baseline; +2 for PF).
  - PF backend: 596 passed, 10 skipped, 1 pre-existing unrelated failure
    (`test_cotacoes_service.py::test_falls_back_to_mock_on_error` — `yf`
    attribute missing on `cotacoes_service` module; verified failing on
    pre-edit stash). Cardinality preserved relative to baseline.
- **Phase 4 — Keeper** (DONE): `noctus.dev.review --product personal-finance`
  → `issues_found: 0`. 0 NEW.

---

## 7. Improvements (live)

- (none surfaced)

---

## 11. Change log

- 2026-05-11 — Project filed + executed in one pass; engineer PF-CORS-REGISTRY.
