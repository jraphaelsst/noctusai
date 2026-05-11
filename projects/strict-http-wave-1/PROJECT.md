# StrictHttpModel Wave 1 — adconnect / imobi-scheduling / media-scheduling

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 0-3 complete (mechanical migration + 422 tests + keeper green) — ready for orchestrator FF-to-main
- **Owner / stakeholders:** orchestrator (architect) + Engineer STRICT-HTTP-WAVE-1
- **Related docs:** `KB § PATTERNS/pydantic-strict-http.md`, `seed/lib/backend/noctusai_lib/api/schemas.py`, `MEMORY.md → feedback_pydantic_silent_drop_kills_writes`
- **Project slug:** `strict-http-wave-1` (lives at `projects/strict-http-wave-1/` — cross-product migration)

---

## 1. Context & Purpose

Pydantic v2's `BaseModel` defaults to `extra="ignore"` — unknown fields are silently dropped during validation. Combined with frontend hooks typed `Record<string, unknown>`, this produces the silent-drop bug class: a misrouted POST returns 200 with zero persistence, the user sees a success toast, and the server logs show nothing. Captured 2026-05-11 from the therapy clinic-portal Settings.tsx audit (NNN/VVV).

Seed earlier shipped `noctusai_lib.api.StrictHttpModel` (`extra="forbid"`) as the HTTP-boundary base — schemas that inherit it 422 on unknown keys, naming the offending `loc`. Wave 1 migrates the three lowest-risk products: adconnect, imobi-scheduling, media-scheduling.

---

## 2. Confirmed constraints

- **Heuristic for "HTTP-boundary"** — schema used as a FastAPI route param annotation OR `response_model` (or destined for one — Create/Update/Out shapes that exist as scaffold-validated by `test_schemas.py`). *(Internal-only DTOs in `app/models/` skip migration.)*
- **AST-first** — libcst codemod (`/tmp/strict_http_migrate.py`); no sed/regex on Python source.
- **Carve-out preserved** — `adconnect.schemas.admin.DistributorWithMetricsOut` keeps `extra="allow"` (deliberate: accepts unknown DB columns until admin V2 locks the shape). The carve-out is now EXPLICIT — it inherits `StrictHttpModel` AND declares `model_config = ConfigDict(extra="allow")` rather than relying on `BaseModel`'s default. The seed schemas docstring already names this class as the canonical carve-out example.
- **Branch naming** — `strict-http-wave-1-2026-05-11` (KB §20 engineer-letter naming convention).
- **Coordination** — file-disjoint with NOWUTC-LIFT (touches `services/*.py`, not `schemas/*.py`).

---

## 3. Design principles

1. **Mechanical at the seam, intentional at the carve-out** — the codemod replaces base class + import; explicit re-declaration only for documented carve-outs.
2. **Bug class on the request side** — primary defense is request-body strictness. Response-side strictness can surface incomplete schemas (see §11 — `RedemptionOut` was missing `org_id`); the fix is to make the schema accurate, not to disable strictness.
3. **One 422 test per product** — minimum coverage to lock the new behavior; uses an unrelated unknown field (`bogus_field`) so the test stays independent of legitimate schema evolution.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** YES — every HTTP-boundary schema inherits the same `StrictHttpModel` base. The contract is the `extra="forbid"` ConfigDict.
2. **Is the data source product-specific?** N/A — this is a typing contract, not a data flow.
3. **Is the placement product-specific?** YES — each product's schema files. The base class is seed-shaped (`noctusai_lib.api.StrictHttpModel`); products just inherit.
4. **Is the visibility / permission rule the same?** YES — strictness is uniform.
5. **Does the seam already exist in seed?** YES — `StrictHttpModel` at `seed/lib/backend/noctusai_lib/api/schemas.py`, exported via `noctusai_lib.api.StrictHttpModel`.
6. **Default-on or opt-in?** DEFAULT-ON — products migrate to inherit; carve-out via explicit `ConfigDict(extra="allow")`.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — per-product schema files update inheritance (`BaseModel` → `StrictHttpModel`). The contract lives in seed; products inherit. This is base-class adoption, not pattern replication. ~40-50 LoC delta per product (inheritance + import lines).

**Phase plan implications:** §6 phases work in seed-base-adoption terms, not "per-product re-implement". The seed already ships the contract; this project's work is mechanical inheritance swap + per-product carve-out review + per-product test fan-out.

---

## 4. Scope

**In scope:**
- adconnect schema migration (`products/adconnect/backend/app/schemas/*.py`)
- imobi-scheduling schema migration (`products/imobi-scheduling/backend/app/schemas/*.py`)
- media-scheduling inline router schemas (`products/media-scheduling/backend/app/routers/authorized_users.py`)
- Per-product 422-unknown-field test (1 new test per product)
- `DistributorWithMetricsOut` carve-out → explicit `extra="allow"` on `StrictHttpModel` subclass
- Schema-correctness fix exposed by strict mode: `RedemptionOut.org_id` added as Optional (was silently dropped pre-migration)

**Out of scope (for now — with reason):**
- Wave 2 products (core, erp, pf, therapy, daily-life, mailing, dev-team) — separate engineers, separate branches.
- Frontend hook tightening (`Record<string, unknown>` → typed payloads) — closes the bug class at the source; tracked in `MEMORY.md → feedback_pydantic_silent_drop_kills_writes` follow-up.
- Response-side schema completeness audit beyond what tests surface — exhaustive review deferred.

---

## 5. Architecture / Data Model

**Seed contract** (already shipped — verified):
```python
# seed/lib/backend/noctusai_lib/api/schemas.py
class StrictHttpModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

**Per-product migration shape**:
```python
# BEFORE
from pydantic import BaseModel
class XCreate(BaseModel):
    field: str

# AFTER
from noctusai_lib.api import StrictHttpModel
class XCreate(StrictHttpModel):
    field: str
```

**Explicit carve-out shape** (adconnect.admin.DistributorWithMetricsOut):
```python
class DistributorWithMetricsOut(StrictHttpModel):
    model_config = ConfigDict(extra="allow")   # explicit opt-out
    ...
```

**File touch list**:
- adconnect: `schemas/{admin,catalog,financial,identity,orders,rewards,sellout}.py` (7 files, 40 classes migrated, 1 carve-out, 1 schema-correctness fix in `rewards.py`)
- imobi-scheduling: `schemas/{appointment,condominium,conversation,example,oauth_credential,pending_chat_identity,property,route,service,tool_call_audit,user}.py` (11 files, 39 classes)
- media-scheduling: `routers/authorized_users.py` (1 file, 2 classes — schemas inline; no `schemas/` dir consumers yet)

---

## 6. Implementation phases

### Phase 0 — Audit ✅
- [x] Enumerate HTTP-boundary schemas per product
- [x] Count classes by file
- [x] Identify carve-outs (`DistributorWithMetricsOut`)
- [x] Confirm media-scheduling has only inline router schemas (no `schemas/` dir consumers)

**Improvements:**
- Brief baselines were stale (adconnect 204→229, imobi 368→393, media 87→112). Document in Phase 1 retrospective so future Wave dispatchers refresh baselines.
- imobi-scheduling has 11 schema files but only `example.py` is wired by a router today; the rest are scaffolded-and-test-validated. We migrate them anyway since the test contracts will exercise strictness when they get wired — closing the bug class at scaffold time, not after consumption.

### Phase 1 — Mechanical inheritance swap ✅
- [x] libcst codemod (`/tmp/strict_http_migrate.py`) — replaces `class X(BaseModel):` → `class X(StrictHttpModel):`, drops `BaseModel` from `from pydantic import ...` iff unused, inserts `from noctusai_lib.api import StrictHttpModel`
- [x] Apply to adconnect 7 schema files (40 classes, 1 carve-out preserved)
- [x] Apply to imobi-scheduling 11 schema files (39 classes)
- [x] Apply to media-scheduling 1 router file (2 classes)
- [x] Make `DistributorWithMetricsOut` carve-out explicit (`StrictHttpModel` + `ConfigDict(extra="allow")`)
- [x] AST-parse validation per file

**Improvements:**
- libcst codemod produced clean diff in one shot — single-pass migration works because `BaseModel` usage pattern is uniform across the codebase.
- Schema-correctness gap caught by strict mode: `RedemptionOut` was missing `org_id` (DB returns it). Pre-migration: silently dropped from response. Post-migration: 422 ResponseValidationError. Fixed by adding `org_id: Optional[str] = None` to the schema — this is exactly the bug class StrictHttpModel reveals, on the response side. Worth a one-time audit pass on other response_models that wrap raw DB rows (followup, not in scope).

### Phase 2 — Test fan-out ✅
- [x] adconnect: full suite preserved at 229 passed + new `test_redeem_rejects_unknown_field_with_422` (total 230)
- [x] imobi-scheduling: full suite preserved at 393 passed + new `test_create_with_unknown_field_returns_422` (total 394)
- [x] media-scheduling: full suite preserved at 112 passed + new `test_create_authorized_user_rejects_unknown_field_with_422` (total 113)

**Improvements:**
- Test pattern is byte-identical across products (POST with unknown field → assert 422 + assert `bogus_field` in error `loc`). Recurrence rule N=3 — worth a seed `framework_test_suites.TestStrictHttpBoundary` mixin for future products to inherit. File as Wave 2 follow-up.

### Phase 3 — Keeper review ✅
- [x] `noctus.dev.review --product adconnect` → 0 issues
- [x] `noctus.dev.review --product imobi-scheduling` → 0 issues
- [x] `noctus.dev.review --product media-scheduling` → 0 issues

**Improvements:** none identified. Keeper green across all 3 products on first run — the migration is mechanical enough that no compliance regression surfaced.

---

## 11. Change Log

- 2026-05-11 — Phase 0 audit (3 products, 81 candidate classes across 19 files)
- 2026-05-11 — Phase 1 mechanical migration via libcst codemod (81 classes migrated, 1 explicit carve-out, 1 schema-correctness fix on RedemptionOut)
- 2026-05-11 — Phase 2 test fan-out (+3 422-tests, baselines preserved across all 3 products)
- 2026-05-11 — Phase 3 keeper review green (`noctus.dev.review` → 0 issues for all 3 products)
