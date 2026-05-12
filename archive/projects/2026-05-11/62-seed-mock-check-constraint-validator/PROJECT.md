# seed-mock-check-constraint-validator — Project Document

> Living document. Adds opt-in CHECK-constraint validation to
> `MockSupabaseClient` so test-time writes that PostgreSQL would reject at
> runtime fail loudly instead of silently passing.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 1 staged (engineer reported; awaiting orchestrator merge)
- **Owner / stakeholders:** Architect · Engineer ADCO-MOCK-CHECK-VALIDATOR-2
- **Related docs:** `KB § PATTERNS/testing.md`,
  `projects/mock-supabase-schema-validation/` (prior column-validator work),
  `projects/adco-rewards-cross-tenant-fix/` (sibling ADCO context)
- **Project slug:** `seed-mock-check-constraint-validator` — lives at
  `projects/<slug>/` because the change extends the seed test framework
  consumed by every product.
- **Branch:** `seed-mock-check-constraint-validator-2026-05-11`

---

## 1. Context & Purpose

PostgreSQL CHECK constraints declared in migrations (`status IN
('acumulado', 'resgatado', 'expirado')`, `tipo IN ('cashback', 'pontos')`,
etc.) are enforced at INSERT/UPDATE time by the real database. The
in-process `MockSupabaseClient` used by every product's tests has had no
analog: a service that writes `status='success'` against a CHECK-constrained
column produces a green test, then a red deploy.

The ADCO-REWARDS-STATUS-CHECK incident (2026-05-11) is the archetypal slip
this validator closes: a rewards-service path inserted `status='success'`
into `recompensas_acumuladas`; tests passed; the real Supabase rejected
the write on the first production call.

This project ships an **opt-in** validator at the seed layer + a **narrow
adoption** in the AdConnect rewards-table mock-fixture path.

---

## 2. Confirmed constraints

Things shaping the design:

- **Opt-in, default OFF** — flipping default ON would break every product's
  existing test suite (many tests write CHECK-violating fixtures by
  accident, with no current consumer). Rollout follows the same path as
  the `validate_schema` column validator (default ON in Phase 4 after
  per-product cleanups).
- **Per-product manifest** — the manifest is declared in each product's
  `conftest.py`, mirroring the live migration. No auto-extraction from
  SQL: the migration parser already feeds `_schema_cache`, but parsing
  CHECK expressions correctly (`IN (...)`, `BETWEEN ...`, range
  expressions, function calls) is a substantially larger surface than
  column-name extraction. Out of scope for this project; tracked as a
  follow-up.
- **Parallel agent in flight** — `MOCK-SELECT-PREDICATE-FIX-3` is editing
  the SELECT path of the same file. This brief touches the INSERT/UPDATE
  path only. Coordination at commit time, architect resolves merge.

---

## 3. Design principles

1. Opt-in by default. No existing test changes behavior unless a manifest
   is supplied.
2. Symmetric INSERT + UPDATE coverage — both write paths fire the same
   validator. UPSERT inherits the same hook.
3. Error message names the offending `table.column`, value, and full
   allowed set — silent-error rule.
4. Test-time validator only — no production code path consults the
   manifest. The real DB enforces real constraints.
5. NULL is acceptable unless the manifest explicitly lists `None` in the
   allowed tuple — NOT-NULL enforcement is orthogonal and out of scope.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** YES — every product
   that uses `MockSupabaseClient` writes against tables with CHECK
   constraints declared in its migration. The validator IS cross-product.
2. **Is the data source product-specific?** YES — each product supplies
   its own manifest, but the validator container is uniform.
3. **Is the placement product-specific?** NO — the validator lives in
   `seed/lib/backend/noctusai_lib/testing/mocks.py` (the canonical mock
   client). Per-product wiring is one line in the product's `conftest.py`.
4. **Is the visibility / permission rule the same?** YES — uniform
   "raise on miss".
5. **Does the seam already exist in seed?** YES — `MockSupabaseClient.__init__`
   already accepts `validate_schema` + `strict_unknown_tables` kwargs as
   opt-in validation knobs. The new `validate_schema_constraints` +
   `manifest` kwargs mirror that exact shape.
6. **Default-on or opt-in?** OPT-IN this phase — see §2 above. Rollout
   pattern mirrors the column validator.

**Litmus — per-product code count:** ~1 line per product (the
`MockSupabaseClient(...)` call site in `conftest.py` adds two kwargs and
imports a manifest constant). Acceptable.

---

## 4. Out of scope

- Auto-parsing CHECK expressions from migration SQL — separate follow-up.
- NOT-NULL enforcement (handled by Postgres at insert-time; orthogonal).
- FK enforcement at the mock level — out of scope; tests use
  `MockRequestBuilder.inserted_payloads` to assert relationships.
- UPSERT conflict-target tracking — depends on the broader upsert
  propagation work in `projects/mock-supabase-write-propagation/`.

---

## 5. Files touched

- `seed/lib/backend/noctusai_lib/testing/schema_errors.py` —
  new `MockCheckViolation(AssertionError)` class with `schema / table /
  column / invalid_value / allowed_values / operation` attributes + a
  diagnostic message.
- `seed/lib/backend/noctusai_lib/testing/mocks.py` — new
  `_validate_check_constraints()` helper + `_resolve_constraint_entry()`
  manifest lookup; new `validate_constraints` + `constraint_manifest`
  kwargs threaded through `MockRequestBuilder`, `MockFilterBuilder`, and
  `MockSupabaseClient`; new `_builder_kwargs_with_constraints()` helper
  for downstream builder construction; INSERT / UPDATE / UPSERT paths
  invoke the validator when opted in.
- `seed/lib/backend/noctusai_lib/testing/__init__.py` — export
  `MockCheckViolation`.
- `seed/lib/backend/tests/testing/test_mocks_check_constraints.py` —
  7 unit tests covering green + 4 red shapes + default-off + qualified-key
  resolution.
- `products/adconnect/backend/tests/conftest.py` — narrow opt-in: declares
  `ADCONNECT_CHECK_MANIFEST` for `recompensas_acumuladas` +
  `resgates_recompensa`, wires `validate_schema_constraints=True` +
  `manifest=ADCONNECT_CHECK_MANIFEST` on the `client` fixture's
  `MockSupabaseClient(...)` call site.

---

## 6. Phase plan

### Phase 1 — seed validator + adconnect adoption (this brief)

- Add `MockCheckViolation` to `schema_errors.py` and re-export.
- Plumb the validator through `mocks.py`.
- Write 7 unit tests.
- Opt in adconnect's `conftest.py` with the rewards-tables manifest.
- Verify the ADCO-REWARDS-STATUS-CHECK shape is caught by an explicit test
  (`test_insert_with_invalid_status_would_have_caught_adco_rewards_bug`).
- Verify no regression in `tests/test_mock_*` suite.

### Phase 2 — follow-up (deferred)

- Extend manifest coverage to remaining adconnect tables (distributors,
  pedidos, sellout, regras_recompensa).
- Roll out manifests to other products (therapy, daily-life, mailing, …)
  that have CHECK-constrained columns.
- Migration-SQL auto-parser to derive manifests from `CHECK (col IN
  (...))` clauses.
- Per-product Phase: flip default to ON (mirrors `validate_schema` phases).

---

## 7. Open questions

- **Should UPSERT validate?** Decided YES — same shape as INSERT/UPDATE.
  Filed at §6 above.
- **NULL handling?** Decided: skip NULL unless `None` in the allowed
  tuple. Documented in §3 principle 5.

---

## 10. Verification commands

```bash
# Run the new validator tests
cd seed/lib/backend
PYTHONPATH=. pytest tests/testing/test_mocks_check_constraints.py -v

# Regression — existing mock tests
PYTHONPATH=. pytest tests/test_mock_schema_validation.py \
                   tests/test_mock_payload_tracking.py \
                   tests/test_mock_write_propagation.py -v

# Adconnect rewards engine tests (opted-in path)
cd ../../../products/adconnect/backend
PYTHONPATH=../../../seed/lib/backend:. pytest tests/services/test_rewards_engine.py -v
```

---

## 11. Change log

- **2026-05-11 — Phase 1 staged.** Engineer ADCO-MOCK-CHECK-VALIDATOR-2
  added `MockCheckViolation` + opt-in validator + 7 tests +
  adconnect opt-in. All 7 new tests green; 78 existing mock-related
  tests still green; 1174 seed-lib tests green except 11 pre-existing
  unrelated `test_per_product_cors_sentinel` failures. AdConnect rewards
  engine tests (15) green; rewards router tests error on pre-existing
  baseline collection issue unrelated to this change.
