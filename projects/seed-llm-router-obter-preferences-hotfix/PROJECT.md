# seed-llm-router-obter-preferences-hotfix — Project Document

> **Filed 2026-05-20** as the seed-side runtime-bug hotfix surfaced by ERP-P7's LLM mount-smoke test. Self-contained (durable-docs rule).
>
> **Symbol-first authoring** per `KB § PATTERNS/doc-symbology.md`.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** 📋 **FILED** — runtime-crash bug; tight scope; lightweight feature/hotfix candidate.
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

- **P0 ⏳** — Read the source + design call: add method OR fix call site.
- **P1 ⏳** — Apply the fix in seed.
- **P2 ⏳** — Add the regression test (a seed-side mount-smoke on `/api/llm/preferences` that touches the DB module).
- **P3 ⏳** — Verify: pytest the full seed framework suite + pilot products.

---

## 7. Open questions

1. **Add `get_user_client()` or change the call site?** Read the source to decide.

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
