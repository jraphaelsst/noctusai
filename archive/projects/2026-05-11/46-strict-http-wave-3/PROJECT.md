# StrictHttpModel Wave 3 — mailing / daily-life / dev-team / erp-imobiliario

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 0-3 complete (mechanical migration + 422 tests + keeper green) — ready for orchestrator FF-to-main
- **Owner / stakeholders:** orchestrator (architect) + Engineer STRICT-HTTP-WAVE-3
- **Related docs:** `KB § PATTERNS/pydantic-strict-http.md`, `seed/lib/backend/noctusai_lib/api/schemas.py`, `projects/strict-http-wave-1/PROJECT.md` (precedent), `MEMORY.md → feedback_pydantic_silent_drop_kills_writes`
- **Project slug:** `strict-http-wave-3` (lives at `projects/strict-http-wave-3/` — cross-product migration)

---

## 1. Context & Purpose

Pydantic v2's `BaseModel` defaults to `extra="ignore"` — unknown fields are silently dropped during validation. Combined with frontend hooks typed `Record<string, unknown>`, this produces the silent-drop bug class: a misrouted POST returns 200 with zero persistence, the user sees a success toast, and the server logs show nothing. Captured 2026-05-11 from the therapy clinic-portal Settings.tsx audit (NNN/VVV).

Seed earlier shipped `noctusai_lib.api.StrictHttpModel` (`extra="forbid"`) as the HTTP-boundary base — schemas that inherit it 422 on unknown keys, naming the offending `loc`. Wave 1 (adconnect / imobi-scheduling / media-scheduling) merged at `dfa6e3b`. Wave 2 (PF / core / therapy) in flight in parallel. Wave 3 closes the remaining four products: mailing, daily-life, dev-team, erp-imobiliario.

---

## 2. Confirmed constraints

- **Heuristic for "HTTP-boundary"** — schema used as a FastAPI route param annotation OR `response_model` (or destined for one — Create/Update/Out shapes that exist as scaffold-validated by `test_schemas.py`). *(Internal-only DTOs in `app/models/` skip migration — daily-life and dev-team have no `schemas/` directory; ERP has a single schemas file plus heavy inline router schemas; mailing has 5 schemas files + 2 inline-router files.)*
- **AST-first** — libcst codemod at `/tmp/strict_http_migrate_w3.py`; no sed/regex on Python source. Same shape as Wave 1's `/tmp/strict_http_migrate.py` (mechanical inheritance swap + import rewire + `BaseModel` drop if unused).
- **Carve-out preserved** — `erp-imobiliario.routers.whatsapp_webhook.WAHAMessageEvent` keeps `extra="allow"` (deliberate: WAHA emits richer event shapes — id, timestamp, me, engine, environment — that the handler ignores by name; strict mode would 422 every webhook). The carve-out is EXPLICIT: inherits `StrictHttpModel` AND declares `model_config = ConfigDict(extra="allow")`, with an inline comment naming the pattern and pointing at Wave 1's `DistributorWithMetricsOut` precedent.
- **Branch naming** — `strict-http-wave-3-2026-05-11` (KB §20 engineer-letter naming convention).
- **Coordination** — file-disjoint with Wave 2 (PF/core/therapy schemas) and SLOWAPI-PEP563-DETECTOR / HOUND-ABC-FILTER (`mcp/noctusai/`) and THERAPY-MP-KB-REFRESH (therapy docs). Cherry-picked baseline confirmed (NOWUTC-LIFT touches ERP services; this work touches schemas + routers — no overlap).
- **Wave 1 codemod reused** — same `libcst` transform shape (`BaseModel` base → `StrictHttpModel` base; drop `BaseModel` from `pydantic` import when unused; insert `from noctusai_lib.api import StrictHttpModel`). Idempotent on re-run.

---

## 3. Design principles

1. **Mechanical at the seam, intentional at the carve-out** — the codemod replaces base class + import; explicit re-declaration only for documented carve-outs (here: `WAHAMessageEvent` for 3rd-party webhook payload shape drift).
2. **Bug class on the request side** — primary defense is request-body strictness. Response-side strictness can surface incomplete schemas (Wave 1's `RedemptionOut` was missing `org_id`); the fix is to make the schema accurate, not to disable strictness. Wave 3 surfaced no response-shape gaps under test (baselines preserved exactly).
3. **One 422 test per product** — minimum coverage to lock the new behavior; uses an unrelated unknown field (`bogus_field`) so the test stays independent of legitimate schema evolution.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** YES — every HTTP-boundary schema inherits the same `StrictHttpModel` base. The contract is the `extra="forbid"` ConfigDict.
2. **Is the data source product-specific?** N/A — this is a typing contract, not a data flow.
3. **Is the placement product-specific?** YES — each product's schema files / inline-router declarations. The base class is seed-shaped (`noctusai_lib.api.StrictHttpModel`); products just inherit.
4. **Is the visibility / permission rule the same?** YES — strictness is uniform.
5. **Does the seam already exist in seed?** YES — `StrictHttpModel` at `seed/lib/backend/noctusai_lib/api/schemas.py`, exported via `noctusai_lib.api.StrictHttpModel`.
6. **Default-on or opt-in?** DEFAULT-ON — products migrate to inherit; carve-out via explicit `ConfigDict(extra="allow")`.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — per-product schema files update inheritance (`BaseModel` → `StrictHttpModel`). The contract lives in seed; products inherit. This is base-class adoption, not pattern replication. ~5-80 LoC delta per product (inheritance + import lines; ERP largest due to inline-router density).

**Phase plan implications:** §6 phases work in seed-base-adoption terms, not "per-product re-implement". The seed already ships the contract; this project's work is mechanical inheritance swap + per-product carve-out review + per-product test fan-out.

---

## 4. Scope

**In scope:**
- mailing schema migration (`products/mailing/backend/app/schemas/*.py` — 5 files; `routers/ai.py`, `routers/settings.py` — inline)
- daily-life inline router schema migration (`products/daily-life/backend/app/routers/*.py` — 5 files: metrics/tasks/goals/notes/schedule; no `schemas/` directory in daily-life)
- dev-team inline API schema migration (`products/dev-team/backend/app/api/*.py` — 2 files: run/configs; no `schemas/` directory)
- erp-imobiliario schema + inline router migration (`schemas/matching.py` + 45 router files with inline `BaseModel` declarations)
- Per-product 422-unknown-field test (1 new test per product, 4 total)
- `WAHAMessageEvent` carve-out → explicit `extra="allow"` on `StrictHttpModel` subclass (3rd-party webhook payload-shape resilience)

**Out of scope (for now — with reason):**
- Wave 1 products (adconnect/imobi/media) — already merged at `dfa6e3b`.
- Wave 2 products (PF/core/therapy) — separate engineer/branch in flight.
- Frontend hook tightening (`Record<string, unknown>` → typed payloads) — closes the bug class at the source; tracked in `MEMORY.md → feedback_pydantic_silent_drop_kills_writes` follow-up.
- Response-side schema completeness audit beyond what tests surface — exhaustive review deferred. Wave 3 surfaced no new gaps under test (in contrast to Wave 1's `RedemptionOut.org_id` discovery).

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

**Explicit carve-out shape** (erp-imobiliario.routers.whatsapp_webhook.WAHAMessageEvent):
```python
class WAHAMessageEvent(StrictHttpModel):
    # Carve-out: inbound 3rd-party webhook payload — WAHA emits richer event
    # shapes (id, timestamp, me, engine, environment, …) that we ignore by
    # name. Strict-mode would 422 every event.
    model_config = ConfigDict(extra="allow")
    event: str
    session: str
    payload: dict
```

**File touch list**:
- mailing: `schemas/{automations,campaigns,contacts,lists,templates}.py` (5 files, 20 classes) + `routers/{ai,settings}.py` (2 files, 9 classes) — 7 files, 29 classes total
- daily-life: `routers/{metrics,tasks,goals,notes,schedule}.py` (5 files, 10 classes)
- dev-team: `api/{run,configs}.py` (2 files, 2 classes)
- erp-imobiliario: `schemas/matching.py` (1 file, 9 classes) + 45 router files with inline schemas (115 classes; 1 carve-out — `WAHAMessageEvent`) — 46 files, 124 classes

**Cumulative: 60 files, 165 classes migrated; 1 explicit carve-out.**

---

## 6. Implementation phases

### Phase 0 — Audit ✅
- [x] Enumerate HTTP-boundary schemas per product (mailing: 7 files; daily-life: 5 files; dev-team: 2 files; ERP: 46 files)
- [x] Count classes by file (29 / 10 / 2 / 124 = 165 total)
- [x] Identify carve-outs (`WAHAMessageEvent` — WAHA 3rd-party webhook)
- [x] Confirm daily-life + dev-team have no `schemas/` directory (inline-only)
- [x] Capture pre-migration baselines: mailing 213+1pre-existing-fail, daily-life 209, dev-team 42+4pre-existing-fail (drift from brief's 19+4), ERP 1861+12pre-existing-fail (drift from brief's 1862)

**Improvements:**
- Brief baselines were slightly stale (dev-team 19→42, ERP 1862→1861). Same shape as Wave 1's drift. Future Wave dispatchers should refresh baselines or note "approximate" in brief.
- daily-life has no `schemas/` directory at all — every Create/Update DTO is declared inline in the router. Same for dev-team. ERP mixes both: a single `schemas/matching.py` plus 115 inline-router schemas across 45 files.
- ERP's inline-router density (45 files, average 2.5 classes per file) makes it the highest-LoC migration of any Wave to date; per-file changes are tiny so the codemod handled all 124 classes in a single pass.

### Phase 1 — Mechanical inheritance swap ✅
- [x] libcst codemod (`/tmp/strict_http_migrate_w3.py`) — replaces `class X(BaseModel):` → `class X(StrictHttpModel):`, drops `BaseModel` from `from pydantic import ...` iff unused, inserts `from noctusai_lib.api import StrictHttpModel`. Idempotent. AST-parse validates after every write.
- [x] Apply to mailing 7 files (29 classes)
- [x] Apply to daily-life 5 files (10 classes)
- [x] Apply to dev-team 2 files (2 classes)
- [x] Apply to ERP 46 files (124 classes)
- [x] Make `WAHAMessageEvent` carve-out explicit (`StrictHttpModel` + `ConfigDict(extra="allow")` + inline comment pointing at Wave 1's precedent)
- [x] AST-parse validation per file

**Improvements:**
- Single-pass codemod ran clean across all 4 products. 165 classes, 0 syntax errors, 0 false positives in import detection (no spurious `BaseModel` drops where it was still referenced elsewhere).
- The `model_config = ConfigDict(extra="allow")` carve-out detection lives in the codemod (skips re-base if already opted out). Wave 3 hit zero existing carve-outs — they all happen at orchestrator-curated boundaries, not inside individual product code.
- The 3rd-party webhook carve-out class is now N=1; if Stripe/Resend/WhatsApp adapters multiply, this becomes a recurrence candidate — file a follow-up to look at sibling webhooks (resend in mailing, stripe in core/billing) and decide whether to bake the "external webhook payload" carve-out into a shared subclass.

### Phase 2 — Test fan-out ✅
- [x] mailing: full suite preserved at 213+1pre-existing → 214+1 (new `test_create_rejects_unknown_field_with_422` on `/api/campaigns`)
- [x] daily-life: full suite preserved at 209 → 210 (new `test_create_task_rejects_unknown_field_with_422` on `/api/tasks`)
- [x] dev-team: full suite preserved at 42+4pre-existing → 43+4 (new `test_run_team_rejects_unknown_field_with_422` on `/api/run`)
- [x] erp-imobiliario: full suite preserved at 1861+12pre-existing → 1862+12 (new `test_create_atividade_rejects_unknown_field_with_422` on `/api/atividades`)

**Improvements:**
- The test pattern is now N=7 byte-identical across Wave 1 (3) + Wave 3 (4). Wave 1 already flagged this as a seed `framework_test_suites.TestStrictHttpBoundary` mixin candidate. With Wave 3 done, the next adopter (Wave 2 once it lands, or any new product) should consume the mixin, not re-author the test by hand. File for post-Wave-2 absorption.
- The 422 test pattern relies on knowing one POST endpoint that takes a request body — for products with N inline-router schemas, picking the endpoint is judgment. Pattern: pick the most representative Create endpoint (mailing→campaigns, daily-life→tasks, dev-team→run, ERP→atividades). The endpoint itself is incidental; the test exercises StrictHttpModel uniformly.

### Phase 3 — Keeper review ✅
- [x] `noctus.dev.review --product mailing` → 0 issues
- [x] `noctus.dev.review --product daily-life` → 0 issues
- [x] `noctus.dev.review --product dev-team` → 0 issues
- [x] `noctus.dev.review --product erp-imobiliario` → 0 issues

**Improvements:** none identified. Keeper green across all 4 products. Same as Wave 1 — the mechanical migration introduces no new compliance regression because the change is uniform base-class adoption.

---

## 11. Change Log

- 2026-05-11 — Phase 0 audit (4 products, 165 candidate classes across 60 files; 1 carve-out identified — `WAHAMessageEvent`)
- 2026-05-11 — Phase 1 mechanical migration via libcst codemod (165 classes migrated, 1 explicit carve-out: `WAHAMessageEvent` extra="allow" for 3rd-party WAHA webhook payload shape drift)
- 2026-05-11 — Phase 2 test fan-out (+4 422-tests, baselines preserved across all 4 products)
- 2026-05-11 — Phase 3 keeper review green (`noctus.dev.review` → 0 issues for all 4 products)
