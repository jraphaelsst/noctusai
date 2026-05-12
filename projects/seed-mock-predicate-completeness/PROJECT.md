# Seed Mock Predicate Completeness — Project Document

> **Living document.** Revise phases as we learn.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Design locked → Phase 1 ready
- **Owner / stakeholders:** joaoraphaelsst · architect
- **Related docs:** `seed/lib/backend/noctusai_lib/testing/mocks.py` (target), `noctusai_lib.testing.pytest_plugin` (optional Phase 2 target), `KB § PATTERNS/testing.md`. Filed as follow-up to Engineer T's THERAPY-OOS-10 work (commit `ef01f57`).
- **Project slug:** `seed-mock-predicate-completeness` at `projects/seed-mock-predicate-completeness/`

---

## 1. Context & Purpose

Engineer T (THERAPY-OOS-10, 2026-05-11) discovered two structural gaps in `MockSupabaseClient`'s predicate evaluator that forced test-side workarounds. These workarounds work, but they're ugly and propagate forward — every future test that wants IS-NULL semantics or filter-negation will need the same shim. Fixing the seed-side root cause eliminates the shims and prevents future tests from needing the same workaround pass.

**Two specific gaps:**

1. **`_eval_is(row, col, value)` uses literal Python `is`** — so `.is_("deleted_at", "null")` evaluates as `row.get("deleted_at") is "null"`. With `deleted_at=None`, this is False (None is not the string "null"), filtering out the row. Real PostgREST `.is_("col", "null")` means "WHERE col IS NULL" — should evaluate to `row.get(col) is None` when value=="null".
2. **`_FilterMixin.not_` is a no-op property** — currently `@property → return self`, which means `.not_.in_(...)` silently drops the negation, returning the same rows as `.in_(...)`. Real PostgREST negation flips the matched-set.

**Plus an optional Phase 2 lift:**

3. **JWT-regex `SUPABASE_*` env-var placeholders** — every product test conftest currently has to pre-populate placeholder env vars at module-load time (because `app.database.py:14` instantiates `get_admin_client()` at import). Lifting this into `noctusai_lib.testing.pytest_plugin` saves every product from authoring its own.

**The win:** the workaround comment block Engineer T added in 8 therapy test files (`"null"` literal-string shim) can come out once Gap 1 lands. Negation semantics become trustworthy. Future products inherit Supabase-env scaffolding without rebuilding it.

---

## 2. Confirmed constraints

- **Seed change ripples across all products.** Touching `mocks.py` affects every product's test suite. Phase 1 ships in one well-tested commit; any latent test that was relying on broken behavior surfaces immediately. *(Acceptable — that's exactly why we fix at the seed.)*
- **Backward-compat for the workaround shim.** Engineer T's `"null"` literal-string seed seeds will continue to PASS after the fix (because `row.get(col) is None when value=="null"` is the new semantics, but a row with `deleted_at="null"` also returns `row.get("deleted_at") == "null"` which doesn't match the IS-NULL case). The shims become unnecessary but not broken; they'll get cleaned up in a follow-up sweep. *(Why: avoid forcing a same-commit cleanup of 8+ test files.)*
- **Test-the-detector applies.** Mock changes ship with regression tests in `seed/lib/backend/tests/` (or wherever the seed test home lives).

---

## 3. Design principles

1. **Fix at the seed root, not in product test code.** The shim Engineer T applied is acceptable as a temporary measure (Stage 3 rule: "no workarounds — fix the root cause"). This project IS the root-cause fix.
2. **Match real PostgREST semantics.** `.is_("col", "null")` → SQL `WHERE col IS NULL` → Python `row.get(col) is None`. `.is_("col", "true")` / `.is_("col", "false")` analogous. `.not_.eq(...)` → negation.
3. **Don't over-implement.** Stick to what real PostgREST supports + what products actually use. Don't add features the keeper would flag as unused.

---

## 3a. Seed-first analysis

1. Identical-for-every-product? Yes — this is THE seed mock; all products inherit.
2. Data source product-specific? No — seed code.
3. Placement product-specific? No — `seed/lib/backend/noctusai_lib/testing/mocks.py`.
4. Visibility/permission uniform? Yes.
5. Seam exists in seed? This IS the seed seam.
6. Default-on or opt-in? Default-on — semantic correctness, not opt-in.

**Litmus — per-product code count: 0 lines.** ✅

---

## 4. Scope

**In scope:**

- Fix `_eval_is` to match PostgREST IS-NULL / IS-TRUE / IS-FALSE semantics.
- Fix `_FilterMixin.not_` to actually negate the next filter (instead of returning self unchanged).
- Add regression tests in the seed mock test home that prove both fixes catch the broken-old vs working-new behavior.
- Optional Phase 2: lift JWT-regex SUPABASE_* placeholder pre-population into `noctusai_lib.testing.pytest_plugin`.

**Out of scope:**

- Cleaning up the 8 therapy test files' `"null"` shim. Filed as `THE-MOCK-SHIM-CLEANUP` follow-up.
- Adding new mock features beyond PostgREST parity (e.g. operators products don't use).
- Refactoring the broader `MockSupabaseClient` architecture.

---

## 5. Files to touch

- `seed/lib/backend/noctusai_lib/testing/mocks.py` — `_eval_is` + `_FilterMixin.not_` rewrites.
- `seed/lib/backend/tests/test_mocks.py` (or equivalent — engineer locates) — regression tests.
- Phase 2 (optional): `seed/lib/backend/noctusai_lib/testing/pytest_plugin.py` — env-var pre-population.

---

## 6. Phase plan

### Phase 1 — Seed mock predicate fixes (single engineer Q)

**1.1** Read `seed/lib/backend/noctusai_lib/testing/mocks.py` end-to-end. Find `_eval_is` and `_FilterMixin.not_`.

**1.2** Implement `_eval_is(row, col, value)`:
- `value == "null"` → return `row.get(col) is None`
- `value == "true"` → return `row.get(col) is True`
- `value == "false"` → return `row.get(col) is False`
- otherwise → fall back to literal equality (or raise — match real PostgREST: only those three values are valid for `.is_()`)

**1.3** Implement `_FilterMixin.not_` as an actual negation:
- Convert from `@property → return self` to a flag/state that the NEXT filter call inverts. Possibly: `def not_(self) -> Self: self._next_filter_negated = True; return self`.
- The next `.eq(...)` / `.in_(...)` / `.is_(...)` / etc. checks the flag and inverts the predicate evaluation.
- Reset the flag after the predicate is consumed (so chained `.not_.eq(...).eq(...)` doesn't negate the second eq).

**1.4** Regression tests:
- `TestEvalIsNull` — seed with `deleted_at=None`, query `.is_("deleted_at", "null")`, assert row returned.
- `TestEvalIsNotNull` — seed with `deleted_at="2026-05-11"`, query `.is_("deleted_at", "null")`, assert row filtered out.
- `TestEvalIsTrue` / `TestEvalIsFalse` — analogous.
- `TestNotEq` — seed two rows, query `.not_.eq("col", "x")`, assert only the non-matching row returns.
- `TestNotIn` — analogous for `.in_`.
- `TestNotChainReset` — `.not_.eq(...).eq(...)` — first eq negated, second eq not.
- `TestBackcompatNullLiteral` — seed with `deleted_at="null"` (the workaround shim), `.is_("deleted_at", "null")` — should NOT match (because the column value is the string "null" not None). Confirms Engineer T's shim becomes obsolete-but-harmless.

**1.5** Run `pytest seed/lib/backend/tests/` — full seed test suite green.

**1.6** Run a sample of product test suites (`pytest products/therapy-platform/backend products/pf/backend products/erp/backend`) — confirm no regressions from the seed change. Engineer T's `"null"` shims are *expected* to continue passing (the shim seeded literal `"null"` strings, not None; the new `_eval_is` doesn't match them via the IS-NULL path, so those tests still rely on the shim's literal-string seed equality — which still works). Confirm.

**1.7** Append §11 change log to this PROJECT.md.

### Phase 2 — Optional JWT-regex env-var placeholder lift (separate dispatch decision)

**2.1** Lift the JWT-regex SUPABASE_* placeholder pre-population pattern from Engineer T's `products/therapy-platform/backend/tests/conftest.py` into `noctusai_lib.testing.pytest_plugin`. Every product test suite that imports the plugin then inherits the placeholders.

**2.2** Remove the pre-populated env vars from each product conftest that has them (sweep).

**2.3** Regression test: a fresh product scaffold's tests run green without authoring its own env-var pre-population.

(Phase 2 is independent of Phase 1 and may be deferred.)

### Phase 3 — Shim cleanup follow-up (separate project)

After Phase 1 lands, file `THE-MOCK-SHIM-CLEANUP` for the 8 therapy test files. Replace `"deleted_at": "null"` seeds with `"deleted_at": None` (the natural shape). The `is_` predicate now correctly matches None to "null".

(Phase 3 is a follow-up; engineer doesn't do it in this project.)

---

## 7. Open questions

(none active — design locked with user via filed-as-followup)

---

## 8. Risks & mitigations

- **Seed change unmasks latent product test failures.** If any product test was passing because of the broken `not_` semantics (e.g. asserting "rows returned" when the real semantics would return zero), Phase 1 surfaces it. *Mitigation:* Phase 1.6 sample-runs three products; failures get filed as per-product fix projects. Acceptable cost — these are real correctness bugs.
- **`.not_` semantic ambiguity.** Real PostgREST `.not_.in_("col", [...])` returns rows whose col NOT IN the list, AND also excludes rows where col IS NULL. The seed mock might want to match that or use Python's natural negation (`not in` returns True for None). *Mitigation:* match real PostgREST; document the choice in the new code comment.

---

## 9. Success criteria

- `_eval_is` matches PostgREST IS-NULL / IS-TRUE / IS-FALSE semantics.
- `_FilterMixin.not_` actually negates the next filter.
- Regression tests pass for both, including the not-chain-reset edge case.
- A sample product test run (≥3 products) confirms no regressions.

---

## 10. Copy-paste commands

```bash
cd /Users/rapha/Documents/repository/NoctusAI/noctusai
pytest seed/lib/backend/tests/ -v -k "test_mocks or test_predicate"
pytest products/therapy-platform/backend products/pf/backend products/erp/backend --tb=short 2>&1 | tail -100
```

---

## 11. Change log

- **2026-05-11** — Project filed from Engineer T's THERAPY-OOS-10 findings (`feedback_findings_md`). Engineer Q dispatch authorized when current wave settles.
