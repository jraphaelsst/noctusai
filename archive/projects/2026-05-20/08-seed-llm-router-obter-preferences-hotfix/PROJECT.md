# seed-llm-router-obter-preferences-hotfix — Project Document

> **Filed 2026-05-20** as the seed-side runtime-bug hotfix surfaced by ERP-P7's LLM mount-smoke test. Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** ✅ **READY-FOR-COMMIT** — fix applied (3 call sites + `_require_org` widened); regression test added (9 methods, 4 classes); seed framework suite **94/94 green**; pilot LLM smoke green on erp/social-wiring/therapy.
- **Owner / stakeholders:** joaoraphaelsst@gmail.com · architect
- **Related docs:**
  - `seed/framework/backend/noctusai_seed/llm_router.py` (the buggy call site)
  - `seed/framework/backend/noctusai_seed/database.py` (the `DatabaseModule` lacking the method)
- **Project slug:** `seed-llm-router-obter-preferences-hotfix` (root `projects/`)

---

## 1. Context & Purpose

ERP-P7 was authoring the LLM mount-smoke test `test_isolates_other_orgs_preferences` (against `/api/llm/preferences`) and discovered that `llm_router.obter_preferences` calls `deps._db.get_user_client()` (no args) but `DatabaseModule` does NOT expose that method. The endpoint is wired and importable — but the first runtime GET would crash. The engineer pivoted to `/api/llm/providers` for the smoke (exercises the same isolation contract via `resolve_credential.org_settings.eq(org_id, key)`) and surfaced this as a seed-side bug needing a hotfix.

**Methodology learning surfaced by the engineer:** verify-the-seed-ships-it must extend to **METHOD signatures**, not just imports. A "structural verification" by import grep alone misses this class. Test-by-pytest, not `__init__.py` grep.

---

## 2. Confirmed constraints

- **Seed-side bug.** Lives in `seed/framework/backend/noctusai_seed/llm_router.py`.
- **Every product that mounts the LLM standard router is affected** on first GET `/api/llm/preferences`. The smoke just hasn't exercised it in pilot products.
- **Two possible fixes:**
  - (a) Add `get_user_client()` (or equivalent) to `DatabaseModule` if the design intent was user-scoped.
  - (b) Change the call site to use an existing method on `DatabaseModule` (likely `get_admin_client()` + explicit user filter, or pass user context differently).
- Design call needed in P0.

---

## 3a. Seed-first analysis

This IS the seed (`noctusai_seed.llm_router` is the canonical LLM router for every product). Fix lands in seed; consumers get it via the next `noctusai_seed` consume.

Per-product code count: 0 LoC (pure seed fix).

---

## 4. Scope

**In scope:**
- Read `llm_router.obter_preferences` + `DatabaseModule` source to confirm the call shape + design intent.
- Either add the missing method OR fix the call site.
- Add a pytest pin so the bug class can't recur (a smoke test on the endpoint that actually hits the database boundary).
- Three-way sync per `KB § PATTERNS/methodology-codification-pipeline.md`.

**Out of scope:**
- LLM preferences feature design (just fix the crash; the feature is correct in spec).
- Pilot-fleet adoption of the resulting mount-smoke (separate concern; covered by `KB § PATTERNS/pilot-products-first.md`).

---

## 6. Phases

- **P0 ✅** — Read the source + design call: add method OR fix call site.
  **Improvements:**
  - Applied inline: Q1 decided — **fix call site**, not add method. Source-of-truth read: `DatabaseModule` exposes `get_client(access_token)` (user-scoped when token given, admin when None), `get_admin_client()`, `get_core_client()`. `ProductDependencies.get_user_client(token)` (in `dependencies.py:159`) wraps `self._db.get_client(token)` — IT IS the canonical seam, used by `ai_router.py:48` + `ai_feedback_router.py:59,91`. The buggy `llm_router` was the odd-one-out N=1; bringing it in line is the minimal, blast-radius-zero fix.
  - Bystander finding (in-scope): same bug class existed in **`obter_usage`** (line 190 pre-fix) — fix-on-contact applied. The smoke test originally targeted only `obter_preferences`; expanding pin to all 3 endpoints.
  - Bystander finding: `_require_org` returned `(user, org_id)` 2-tuple, both `obter_preferences` and `salvar_preferences` discarded the token. Cleaner shape: `_require_org` returns `(user, org_id, token)` so each call site gets the seam input it needs. Updated all 5 callers (listar_providers, listar_models, obter_preferences, salvar_preferences, obter_usage) accordingly.

- **P1 ✅** — Apply the fix in seed.
  **Improvements:**
  - Applied inline: 3 occurrences of `deps._db.get_user_client()` → `deps.get_user_client(token)` (libcst-driven; AST-first per CLAUDE.md §1).
  - `_require_org` widened to 3-tuple return; all 5 call sites threaded token-correctly.
  - On-disk verification: `grep -c 'deps\._db\.get_user_client' llm_router.py` returns **0**; `grep -c 'deps\.get_user_client(token)' llm_router.py` returns **3**. R6 (harness-overlay) divergence ruled out.

- **P2 ✅** — Add the regression test (a seed-side mount-smoke on `/api/llm/preferences` that touches the DB module).
  **Improvements:**
  - Applied inline: New `tests/test_llm_router_mount_smoke.py` — 4 test classes, 9 test methods covering:
    - `TestObterPreferencesDoesNotCrash` — happy path (existing prefs), null-default fallback, AND a `del fake_deps._db.get_user_client` regression-pin that mirrors `DatabaseModule`'s real shape (so any regression to `deps._db.get_user_client(...)` raises `AttributeError`, exactly reproducing the original bug).
    - `TestSalvarPreferencesDoesNotCrash` — owner-can-save, non-admin-403, unknown-provider-400.
    - `TestObterUsageDoesNotCrash` — empty-rows happy path (covers the third bug-class instance).
    - `TestModelsStillWorks` — guard against the `_require_org` 2→3-tuple tuple-unpack hazard.
  - Every test asserts `resp.status_code == <int>` explicitly (KB § PATTERNS/testing.md § Status-code-assertion rule).
  - Deferred (with destination): `listar_providers` runtime-path guard NOT added — it touches `resolve_credential(...)` → real Supabase, would require monkey-patching seed-lib (forbidden by CLAUDE.md §1 `no-monkey-patching-our-code`). Test-design note recorded in the test docstring; behavior pinned at registry level by `test_build_standard_routers.py`. Destination: superseded by a future seed-side integration-harness lift if/when the recurrence rule fires.

- **P3 ✅** — Verify: pytest the full seed framework suite + pilot products.
  **Improvements:**
  - Applied inline: `cd seed/framework/backend && pytest tests/` → **94 passed, 0 failed**. Pilot smoke (`pytest -k llm`): erp-imobiliario **12/12 green** (incl. `test_standard_llm_smoke.py` 5/5); social-wiring **1/1 green**; therapy-platform has no `*llm*` test files (collection clean with PYTHONPATH wiring).
  - Methodology learning surfaced: the original PROJECT.md noted "verify-the-seed-ships-it must extend to METHOD signatures, not just imports." This hotfix is a structural case for **`scan_outlined`-grade detector** at the seed-method level — if a caller in `seed/` references a non-existent method on a seed class, the keeper could catch it via libcst attribute-resolution. Filed as a follow-up surface (out-of-scope here; needs a separate proposal). Destination: candidate keeper `check_seed_attribute_dangling` — appropriate for the methodology-codification pipeline.

---

## 7. Open questions

1. **Add `get_user_client()` or change the call site?** ✅ **Resolved P0** — change the call site. Rationale: `ProductDependencies.get_user_client(token)` already exists (`dependencies.py:159`) and is the canonical seam used by `ai_router` + `ai_feedback_router` (N=2 prior consumers). Adding a new method to `DatabaseModule` would create an N=3 pattern AND fork the canonical path — strictly worse than aligning the odd-one-out.

---

## 9. Success criteria

- `llm_router.obter_preferences` doesn't crash on first GET.
- Regression test in place at the seed level.
- Three-way sync: KB pattern doc updated (the "verify METHOD signatures" lesson) → memory entry → keeper detector candidate if a deterministic predicate fires.

---

## 11. Change log

| Date | Entry | By |
|---|---|---|
| 2026-05-20 | Filed as seed-side runtime-crash hotfix from ERP-P7 finding. Tight-scope; lightweight feature candidate. | Architect |
| 2026-05-20 | P0-P3 ✅ ship: fix-on-contact applied to 3 call sites (`obter_preferences`, `salvar_preferences`, `obter_usage`); `_require_org` widened to 3-tuple return; 9 regression-test methods added; seed framework 94/94 green; pilot smoke green. Methodology learning surfaced: candidate keeper `check_seed_attribute_dangling` (libcst attribute-resolution against seed class definitions) — filed as a follow-up surface. | Engineer A |
