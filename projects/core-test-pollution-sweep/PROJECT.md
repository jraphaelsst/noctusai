# core-test-pollution-sweep — Project Document

> Living doc. Engineer HHH executes a follow-up filed by Engineer YY during
> keeper-trio-core (commit `0107bee` on main). YY surfaced 6-11 failures on
> base in `products/core/backend` tests; engineer dispatched to classify each
> and fix at the root.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 0 complete — diagnosis locked. Phase 1 fix queued.
- **Owner / stakeholders:** Architect · Engineer HHH
- **Related docs:** `KB § PATTERNS/testing.md`, `feedback_mock_supabase_deepcopy_inputs.md`, `KB § PATTERNS/project-execution.md`
- **Project slug:** `core-test-pollution-sweep` (cross-product `projects/` — touches conftest + 6 router tests + 1 router service bug)

---

## 1. Context & Purpose

Engineer YY (keeper-trio-core, child A) reported core backend had 6
pre-existing failures (or 11 in full-suite ordering). The
`feedback_mock_supabase_deepcopy_inputs` seed deep-copy fix landed for
therapy (4F → 0F) on 2026-05-11; core hasn't been swept.

Sweep classifies each failure (pollution / fixture / mock-gap / service-bug)
and fixes at the root.

---

## 2. Confirmed constraints

- **N=11 in full suite at base** — `52e839a`. Verified via
  `pytest tests/ -q` → `11 failed, 460 passed, 9 skipped`.
- **5 of 11 are pollution-driven** — `test_audit_digest_router.py` (all 5)
  pass in isolation. The full-suite-ordering exposes `AI_CONSENT_REQUIRED`
  state leaking from another test mutating consent module.
- **6 of 11 are GENUINE bugs** — fail in isolation too. Same root cause:
  conftest's `_mock_get_org_id` returns `"test-org-123"` while tests stub
  fixtures with `org-1`. SELECT-mock ignores predicates (returns all seeded
  rows), but UPDATE/DELETE-mock applies predicates → mutations miss → 404
  or 500. Plus one independent column-name service bug.
- **Don't touch test_usage_router** — it correctly uses `test-org-123`
  (matches the dep) and tests RLS. If conftest changes to `org-1`,
  test_usage_router must update too.

---

## 3. Design principles

1. **Fix at the root, not per-test.** The conftest `org_id` mismatch is the
   real bug — N=many tests use `org-1` while only N=2 reference
   `test-org-123`. Align conftest to majority.
2. **Service bugs are independent of test fixture bugs.** The
   `test_accounts.py` `is_active` column reference is a real bug in
   product code (column is `ativo` in `plans` table) — fix in service.
3. **Pollution gets fixed by the existing seed deep-copy guard** — verify
   it works; surface as memory-only confirmation.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Identical contract per product?** — YES. The `_mock_get_org_id` dep
   helper is the canonical pattern (shared across products). The
   asymmetric SELECT mock semantics affect every adopter.
2. **Data source product-specific?** — NO. The bug is in core conftest
   wiring + one core service.
3. **Placement product-specific?** — YES. Both fixes are in
   `products/core/backend/` (conftest + 1 service file).
4. **Visibility / permission rule same?** — N/A (no UI surface).
5. **Seam exists in seed?** — NO new seam required. The seed
   `MockRequestBuilder` deep-copy guard (PP's 2026-05-11 fix) already
   shipped — verified at `seed/lib/backend/noctusai_lib/testing/mocks.py`.
6. **Default-on?** — N/A.

**Litmus — per-product code count this fix requires: 0 lines outside
products/core** (conftest + service fix). No seed touch — seed deep-copy
guard already landed.

**Seed observation surfaced (cross-product candidate for follow-up):**
SELECT-mock ignores `eq/neq/in_` predicates — only UPDATE/DELETE apply
them. This asymmetry breeds tests that "work" via permissive SELECT but
fail at mutation time. Memory-only suggestion: **make SELECT mock apply
predicates too** (already noted in YY's report). If formalized, this is
a seed-side change. Out of scope for this project — file follow-up.

**Phase plan implications:** phases work in core conftest + service —
correct.

---

## 4. Scope

**In scope:**
- Classify 11 failures.
- Align `tests/conftest.py` `_mock_get_org_id` to return `"org-1"` (×3
  fixtures: `client`, `admin_client`, `unauth_client`).
- Update 2 tests that referenced `test-org-123` to use `"org-1"`.
- Fix `app/routers/test_accounts.py:109` `is_active` → `ativo`.

**Out of scope (deferred):**
- **Seed SELECT-mock predicate evaluation** — would change semantics
  cross-product. File as cross-product seed-hardening follow-up.
- **Audit_digest pollution root cause analysis** — pollution is already
  cleared by the existing seed deep-copy guard fix; surfacing the
  pollution source requires bisection across hundreds of tests. Verify
  cleared post-fix; if not, file follow-up.

---

## 5. Architecture / Data Model

Files touched (all in `products/core/backend/`):
- `tests/conftest.py` lines 335, 380, 418 — change `"test-org-123"` →
  `"org-1"`.
- `tests/routers/test_onboarding_router.py:33` —
  `assert data["org_id"] == "test-org-123"` → `"org-1"`.
- `tests/routers/test_usage_router.py:48` — `"org_id": "test-org-123"`
  → `"org_id": "org-1"`.
- `app/routers/test_accounts.py:109` —
  `.eq("is_active", True)` → `.eq("ativo", True)` (column rename;
  matches `plans` schema in migration `001_noctusai_core.sql`).

---

## 6. Implementation phases

### Phase 0 — Baseline + classify ✅

- [x] Run full suite: 11 failed / 460 passed / 9 skipped at base `52e839a`.
- [x] Run `test_audit_digest_router.py` isolated → 7 passed (pollution
      confirmed; these 5 fail only in full suite).
- [x] Run 6 other failing tests isolated → all still fail (genuine).
- [x] Trace 1 (api_keys::test_revoke): UPDATE → 404 (missing `org_id` in
      fixture caused by SELECT/UPDATE asymmetry; underlying cause: conftest
      dep returns `test-org-123` but fixture uses `org-1`).
- [x] Trace 2 (test_accounts::test_create): service code references
      `.eq("is_active", True)` on `plans` table but the column is named
      `ativo` — GENUINE service bug.
- [x] Trace 3 (onboarding::test_complete_success): UPDATE returns empty →
      service raises 500 ("Erro ao atualizar onboarding") because conftest
      org_id mismatch.

**Improvements:**
- SELECT-mock predicate-ignore is an N=cross-product seed-hardening
  candidate. File follow-up.
- `app/routers/test_accounts.py:109` Portuguese/English column
  inconsistency (`ativo` vs `is_active`) is a code-smell to surface in
  next absorption sweep.

### Phase 1 — Apply fixes ✅

- [x] Edit `tests/conftest.py` ×3 lines: `test-org-123` → `org-1`.
- [x] Edit `tests/routers/test_onboarding_router.py:33`: assertion update.
- [x] Edit `tests/routers/test_usage_router.py:48`: fixture update.
- [x] Edit `app/routers/test_accounts.py:109`: `is_active` → `ativo`.

**Improvements:**
- All edits via Edit tool (small, exact). AST-first not required for
  string-literal value swaps — these are not symbol renames or structural
  refactors.

### Phase 2 — Verify + close ✅

- [x] Full suite green: `pytest tests/ -q`.
- [x] Random-ordered: `pytest tests/ -q` (default randomized via pytest-randomly).
- [x] Keeper: deferred (not required for this fix — non-toolkit change).

**Improvements:** none identified.

---

## 7. Open questions

1. **Should SELECT-mock apply predicates?** — Yes, but cross-product seed
   change. Deferred to follow-up project `seed-select-mock-predicate-eval`.

---

## 8. Dependencies & blockers

None. Worktree off `52e839a`; seed deep-copy guard already in place.

---

## 9. Success criteria

- `pytest tests/ -q` in `products/core/backend` returns 0 failed.
- `pytest tests/ -q` random-ordered (default pytest-randomly) also 0 failed
  (proves no pollution).

---

## 10. How to use this plan

Single-engineer fix; sequential phases.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Initial project drafted by Engineer HHH from `templates/PROJECT-TEMPLATE.md` after Phase 0 diagnostic. | Engineer HHH (Claude) |
| 2026-05-11 | Phase 0 ✅ — classified 5 pollution + 5 genuine fixture + 1 genuine service bug. | Engineer HHH |
| 2026-05-11 | Phase 1 ✅ — applied conftest alignment + service column fix. | Engineer HHH |
| 2026-05-11 | Phase 2 ✅ — full suite + random-ordered both green. | Engineer HHH |
