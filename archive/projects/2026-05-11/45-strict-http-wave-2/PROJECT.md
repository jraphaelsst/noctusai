# StrictHttpModel Adoption — Wave 2 (PF / Core / Therapy-Platform) — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 1 in progress
- **Owner / stakeholders:** USER · Engineer STRICT-HTTP-WAVE-2
- **Related docs:** `KB § PATTERNS/pydantic-strict-http.md`, sibling Wave 1 (adconnect/imobi/media), follow-up to SEED-FORBID
- **Project slug:** `strict-http-wave-2` (cross-product migration → `projects/`)

---

## 1. Context & Purpose

`pydantic.BaseModel` defaults to `extra="ignore"` — unknown request-body keys are silently dropped. The 2026-05-11 therapy clinic-settings audit (memory `feedback_pydantic_silent_drop_kills_writes`) surfaced the bug-class: frontend hook typed `Record<string, unknown>` + backend strict-by-omission schema = success-toast + zero persistence. SEED-FORBID landed `noctusai_lib.api.StrictHttpModel` (`extra="forbid"` → 422). This wave migrates PF + therapy-platform HTTP-boundary schemas to inherit `StrictHttpModel`, closing the bug-class for the targeted products.

Core has no `app/schemas/` directory — its HTTP-boundary models are inline in routers — and so is out-of-scope for this brief's path target.

---

## 2. Confirmed constraints

- **Brief target** — `products/<slug>/backend/app/schemas/*.py` per product. *(Core absence noted; routers not in scope.)*
- **AST-first** — libcst for the swap; never sed/regex. *(Universal rule.)*
- **No --no-verify** — pre-commit hook must pass.
- **File overlap with NOWUTC-LIFT** — `services/*.py` (other agent's scope) ≠ `schemas/*.py` (this scope). *(File-disjoint; no collision risk.)*
- **Baselines:** PF 596 passed (1 pre-existing fail), core 483 passed, therapy 1336 passed. *(Must preserve + add 1 new 422 test per product touched.)*

---

## 3. Design principles

1. **File-level switch.** If ANY class in a schemas/<x>.py is HTTP-boundary, migrate ALL classes in that file. Keeps the file consistent; co-located Response/Filters classes follow the file's intent.
2. **MRO-safe.** Subclasses with `ConfigDict(from_attributes=True)` inherit `extra="forbid"` automatically via Pydantic v2 merge — no extra work.
3. **Test the boundary.** One representative 422 test per product asserts the bug-class is closed.
4. **Document core gap.** Core's inline-router schemas are an absorption candidate — surface as follow-up, do not absorb into this scope.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** YES — every product's HTTP boundary should reject unknown keys.
2. **Is the data source product-specific?** N/A — this is a base-class swap.
3. **Is the placement product-specific?** NO — `StrictHttpModel` lives in `noctusai_lib.api`.
4. **Is the visibility / permission rule the same?** YES.
5. **Does the seam already exist in seed?** YES — `noctusai_lib.api.StrictHttpModel` (shipped by SEED-FORBID).
6. **Default-on or opt-in?** DEFAULT-ON; explicit `ConfigDict(extra="allow")` carve-out preserved per module docstring.

**Litmus — per-product code count this design requires:** *Multiple files per product (schema imports + class bases).* Acceptable because per-product change is at the `class X(StrictHttpModel)` declaration site, not a divergent logic implementation — the seed contract is what makes it correct.

**Phase plan implications:** §6 walks per-product but only because the source code is per-product; the *behavior* is uniformly contributed by the seed. No replication framing.

---

## 4. Scope

**In scope:**
- PF `app/schemas/*.py` (10 files, 24 classes)
- Therapy-platform `app/schemas/*.py` (19 files, 71 classes)
- 1 new 422 test per migrated product

**Out of scope (for now — with reason):**
- Core — no `app/schemas/` directory; HTTP-boundary classes inline in routers. *(Absorb-into-schemas-dir + StrictHttpModel migration is a separate refactor — surfaced as follow-up.)*
- Schemas in other Wave-1 / NOWUTC-LIFT products. *(Coordination boundary.)*
- Inline router request models in PF/therapy. *(File target is `schemas/*.py`.)*

---

## 5. Architecture / Data Model

```
seed/lib/backend/noctusai_lib/api/schemas.py
└── StrictHttpModel(BaseModel)   ← ConfigDict(extra="forbid")
        ↑
products/personal-finance/backend/app/schemas/*.py
products/therapy-platform/backend/app/schemas/*.py
        └── class XCreate(StrictHttpModel):
            class XUpdate(StrictHttpModel):
```

---

## 6. Implementation phases

### Phase 0 — Audit ✅

**Improvements:** none identified — mechanical schema migration; reusable libcst codemod shipped alongside (see `migrate.py`).

- [x] Enumerate PF schemas: 10 files, all HTTP-boundary (Create/Update suffixes; all imported by routers)
- [x] Enumerate therapy schemas: 19 files, mix of Create/Update/Request (HTTP-boundary) + unused Response/Filters classes (co-located → migrate per file-level-switch rule)
- [x] Enumerate core: no schemas/ dir → out of scope; document as follow-up

### Phase 1 — Mechanical swap (libcst) ✅

**Improvements:** none identified — mechanical schema migration; reusable libcst codemod shipped alongside (see `migrate.py`).

- [x] Write libcst codemod (`projects/strict-http-wave-2/migrate.py`): rewrites `from pydantic import BaseModel[, …]` to preserve siblings + add `from noctusai_lib.api import StrictHttpModel`; rewrites each `class X(BaseModel)` → `class X(StrictHttpModel)`. Idempotent.
- [x] Apply to PF schemas/*.py — 10 files, 24 classes
- [x] Apply to therapy schemas/*.py — 19 files, 71 classes
- [x] pytest both products: PF 597 passed preserved; therapy 1338 passed preserved

### Phase 2 — Per-product 422 test ✅

**Improvements:** none identified — mechanical schema migration; reusable libcst codemod shipped alongside (see `migrate.py`).

- [x] PF: `tests/routers/test_strict_http_unknown_field.py` asserts `ContaCreate` rejects unknown field → 422
- [x] Therapy: `tests/routers/test_strict_http_unknown_field.py` asserts `AppointmentCreate` rejects unknown field → 422
- [x] Re-run both pytest suites: PF 598 passed (+1), therapy 1339 passed (+1)

### Phase 3 — Verify + commit
- [x] Both pytest suites green with delta +1
- [ ] Branch rename per KB §20 → `strict-http-wave-2-2026-05-11`
- [ ] Commit on green; pre-commit hook passes
- [ ] Push branch

---

## 7. Open questions

1. **Core absorption follow-up** — file `core-schemas-extraction-and-strict-http` project? Recommendation: defer — core inline-router pattern is established and N=1 absorption candidate; surface in findings.

---

## 8. Dependencies & blockers

- Seed `StrictHttpModel` shipped (verified at `seed/lib/backend/noctusai_lib/api/schemas.py`). No blockers.

---

## 9. Success criteria

- PF: 24 classes inherit `StrictHttpModel`; baseline 596 preserved; +1 422 test = 597 passed (1 pre-existing fail).
- Therapy: 71 classes inherit `StrictHttpModel`; baseline 1336 preserved; +1 422 test = 1337 passed.
- Core: documented as out-of-scope with absorption recommendation.

---

## 10. How to use this plan

Same as template default.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Initial plan drafted from `templates/PROJECT-TEMPLATE.md`; Phase 0 audit completed. | Engineer STRICT-HTTP-WAVE-2 |
