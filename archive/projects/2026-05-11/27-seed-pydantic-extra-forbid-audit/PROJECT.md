# seed-pydantic-extra-forbid-audit — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 0 + Phase 1 + Phase 2 complete (single-session ship)
- **Owner / stakeholders:** USER · Engineer SEED-FORBID
- **Related docs:** memory `feedback_pydantic_silent_drop_kills_writes`, predecessor archives `VVV therapy-clinic-settings-misrouting`, KB `§ PATTERNS/backend.md`, KB `§ PATTERNS/pydantic-strict-http.md` (new)
- **Project slug:** `seed-pydantic-extra-forbid-audit` — lives at `projects/seed-pydantic-extra-forbid-audit/` (cross-product seed-side change, not product-scoped). Intent: **wiring** (seed surface ships; per-product migration is downstream).

---

## 1. Context & Purpose

VVV's therapy-clinic-settings fix on 2026-05-11 exposed a bug class that crosses the entire HTTP boundary of the platform: **silent data-loss when a frontend hook posts a key the backend Pydantic schema doesn't declare.** The chain looked like this:

1. Frontend hook typed `mutationFn<Record<string, unknown>>` — accepts ANY shape.
2. Backend Pydantic schema (`SettingsUpdate` or similar) defaults to `extra="ignore"` — silently drops unknown keys.
3. Hook hits the wrong endpoint (`/admin/users` instead of `/clinic-settings`); fields like `name`, `cnpj`, `phone` are not in the destination schema; Pydantic drops them; INSERT/UPDATE writes only the keys that happened to match.
4. User sees success toast; zero persistence.
5. Type system gives zero signal because the hook generic accepts anything.

The bug shows up as "settings won't save", and it can recur **anywhere the same hook + schema shape exists**. The fix lives at the seed: when an HTTP-boundary schema rejects unknown keys with **422 Unprocessable Entity**, the misroute becomes a loud test failure / runtime error instead of a silent drop.

**Win:** a canonical `StrictHttpModel` base in seed-lib so future schemas default to strict; existing schemas opt in via inheritance change; the bug class shrinks to "did the author forget to inherit?" — answerable by a single grep.

---

## 2. Confirmed constraints

Things the brief / memory established:
- **Per-product migration is OUT of scope this dispatch.** Only the seed surface ships here; per-product wiring is a follow-up. *(Rules out touching 82+ product router files + 54 product schema files in one PR.)*
- **AST-first.** Python edits go through `libcst`; no regex/sed on source. *(CLAUDE.md universal rule.)*
- **No --no-verify.** Pre-commit hook is the safety net. *(CLAUDE.md universal rule.)*
- **Tests + KB amend mandatory.** Phase 2 covers both. *(Brief §Verification.)*
- **Memory amend mandatory.** Reference the new seed surface from `feedback_pydantic_silent_drop_kills_writes`. *(Brief §Verification.)*

---

## 3. Design principles

1. **Seed ships the base, products opt in.** Every HTTP-boundary schema's job is to inherit from `StrictHttpModel` — one diff per class, mechanical migration. We do NOT mass-edit product schemas in this dispatch.
2. **Strict at the HTTP boundary; loose elsewhere.** `from_attributes=True` ORM-shaping schemas and internal value objects are NOT the target — only request/response shapes the FastAPI router declares.
3. **The error case is loud.** Pydantic's `ValidationError` on `extra="forbid"` returns 422 with a body that names the offending key. The frontend hook + tests see it immediately.
4. **No silent fallback.** If a product wants the old loose behavior for one schema, it overrides `model_config` explicitly — the override is the audit trail.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** **YES.** Every HTTP-boundary schema in every product wants the same "reject unknown keys" semantic. *Per-product variation = a separate vulnerability, not a feature.*
2. **Is the data source product-specific?** **NO.** The base class itself is uniform; products override only if they have a legitimate reason (e.g. passthrough for unknown DB columns — `adconnect/admin.py::DistributorWithMetricsOut` documents this case).
3. **Is the placement product-specific?** **NO.** `noctusai_lib.api.schemas` is the canonical home. The `api/` layer's contract (per its `__init__.py` docstring) is "above the FastAPI request boundary — request/response shapes" — exactly where `StrictHttpModel` belongs.
4. **Is the visibility / permission rule the same?** **YES.** Public to every product backend; no permission gate.
5. **Does the seam already exist in seed?** **NO.** `noctusai_lib/primitives/responses.py` has `PaginationMeta(BaseModel)` and `PaginatedResponse(BaseModel, Generic[T])` but neither inherits from a strict base. The api/ layer has no schema base today — **new file `noctusai_lib/api/schemas.py`** is the right shape.
6. **Default-on or opt-in?** **OPT-IN at the schema level**, but **the seed-shipped class IS the strict default**. Every new schema inheriting from `StrictHttpModel` is default-strict; legacy schemas inheriting from `pydantic.BaseModel` stay loose until migrated.

**Litmus — per-product code count this design requires:**

- [x] **0 lines** — seed ships the base; per-product migration is a separate dispatch. *(This project ships exactly the seed surface. Zero per-product LoC change in THIS dispatch.)*

**Phase plan implications:** §6 works entirely in seed (`seed/lib/backend/noctusai_lib/api/`) + seed tests + KB. No `products/*/` paths in this project's diff.

---

## 4. Scope

**In scope:**
- New `seed/lib/backend/noctusai_lib/api/schemas.py` shipping `StrictHttpModel` base class.
- Tests verifying the contract (rejects unknown, accepts known, raises 422 via FastAPI integration).
- KB pattern doc.
- Memory amend pointing to the new seed surface.
- Audit counts in PROJECT.md §11.

**Out of scope (for now):**
- **Migration of any product schema** — separate per-product wiring dispatch. *(Brief §Constraints explicit.)*
- **Migration of seed's own legacy schemas** (`primitives/responses.py::PaginationMeta`, etc.) — those are response-side, not the silent-drop attack surface; deferred to follow-up.
- **Frontend hook-side defense** (typing `mutationFn<TPayload extends StrictPayload>`) — the seed change closes the backend half; frontend half is a follow-up.

---

## 5. Architecture / Data Model

**New file:** `seed/lib/backend/noctusai_lib/api/schemas.py`

```python
"""HTTP-boundary base schemas — strict-by-default request/response shapes.

The platform default of `extra="ignore"` silently drops unknown keys.
Frontend mutations typed `Record<string, unknown>` + backend schemas using
that default = silent data-loss when a hook misroutes (2026-05-11 therapy
clinic-settings bug — memory `feedback_pydantic_silent_drop_kills_writes`).

`StrictHttpModel` rejects unknown keys with `ValidationError` → 422 at the
FastAPI boundary. Every new HTTP-boundary schema inherits from this.
"""
from pydantic import BaseModel, ConfigDict

class StrictHttpModel(BaseModel):
    """BaseModel with `extra="forbid"` for the HTTP request/response boundary."""
    model_config = ConfigDict(extra="forbid")
```

**Re-export:** `noctusai_lib/api/__init__.py` exposes `StrictHttpModel` as the public API.

**Tests:** `seed/lib/backend/tests/api/test_strict_http_model.py` — unit (instantiation rejects/accepts) + FastAPI integration (router + payload + 422 assertion).

**KB doc:** `KNOWLEDGE-BASE/CONTEXT/PATTERNS/pydantic-strict-http.md` — when to inherit, when to override, migration guidance.

---

## 6. Implementation phases

### Phase 0 — Audit current state ✅

- [x] Search seed + all products for Pydantic `extra=` declarations.
- [x] Count current distribution.
- [x] Identify seed-side knob (BaseAppSettings? Shared base?).
- [x] Test-risk audit — find tests that intentionally pass unknown fields.

**Findings (audit):**
- `extra="forbid"` declared: **0** files across seed + 8 products.
- `extra="ignore"` declared: **0** files (everyone relies on the silent Pydantic default).
- `extra="allow"` declared: **1** file (`products/adconnect/backend/app/schemas/admin.py::DistributorWithMetricsOut` — documented in its docstring as a deliberate carve-out for unknown DB columns).
- HTTP-boundary `BaseModel` files in products: **54** in `schemas/`, **82** referencing `BaseModel/model_config/ConfigDict` in `routers/`.
- HTTP-boundary `BaseModel` files in seed: **4** (`primitives/responses.py`, `integrations/vista/types.py`, `integrations/whatsapp/settings.py`, `domain/chatbot/summary.py`).
- Existing `model_config` usages (40+ files): all `from_attributes=True` (ORM-shaping) or `protected_namespaces=()` (model_-prefix conflict). None block adding `extra="forbid"` — `ConfigDict` accepts multiple keys.
- No seed-wide `BaseAppSchema` exists today — every schema inherits from `pydantic.BaseModel` directly.
- Test-risk: `grep` for `extra.*forbid\|extra.*ignore\|model_extra` in tests returned 2 files, both unrelated to schema validation (false positives — `extra` parameter on different objects).

**Decision (Path A vs B):** **Path A — ship `StrictHttpModel` at seed boundary base.** Rationale: zero per-product LoC change in this dispatch (matches brief §Constraints); single class to import; product migration becomes a mechanical inheritance swap (`class Foo(BaseModel)` → `class Foo(StrictHttpModel)`); the override path (`model_config = ConfigDict(extra="allow")` to opt out) keeps the loose-by-design case (adconnect's `DistributorWithMetricsOut`) explicit.

**Improvements (Phase 0):** zero true `extra="ignore"` declarations means the silent-drop bug class affects EVERY HTTP-boundary schema (54 + 82 = 136 sites) — wider than the original symptom. Migration via inheritance swap is mechanical 1-line-per-class; Pydantic v2.9 `ConfigDict` MRO-merge preserves existing `from_attributes=True` declarations through inheritance.

### Phase 1 — Ship seed change ✅

- [x] Create `seed/lib/backend/noctusai_lib/api/schemas.py` with `StrictHttpModel`.
- [x] Update `seed/lib/backend/noctusai_lib/api/__init__.py` to export `StrictHttpModel`.
- [x] Verify no existing seed schema gets accidentally tightened (we DON'T migrate `PaginationMeta` etc. in this dispatch — that's response-side, separate follow-up).

**Improvements:**
- The `__init__.py` docstring mentions occupants — `schemas.py` is now in that list. Added.
- `noctusai_lib/primitives/responses.py::PaginationMeta` and `::PaginatedResponse` are response-side seed schemas — they don't suffer the silent-drop bug because they're never the destination of a frontend POST. Deferred to a follow-up cleanup that audits whether response schemas benefit from strict (probably not — response shapes are emitted by us, never received).
- `noctusai_lib/integrations/vista/types.py` + `whatsapp/settings.py` are external-integration types, not HTTP-boundary; out of scope.

### Phase 2 — Tests + KB ✅

- [x] `seed/lib/backend/tests/api/test_strict_http_model.py` — unit + FastAPI integration tests.
- [x] `KB § PATTERNS/pydantic-strict-http.md` — new pattern doc.
- [x] KB INDEX update.
- [x] CLAUDE/backend.md pointer (canonical HTTP-boundary pattern reference).
- [x] Memory amend `feedback_pydantic_silent_drop_kills_writes` to reference the new seed surface.
- [x] `pytest seed/lib/backend/tests/api/ -q` green.
- [x] `bash scripts/verify-kb-sync.sh` green.

**Improvements:**
- The FastAPI integration test demonstrates the exact 422 shape — when product migration starts, that test is the copy-paste template for product test suites.
- KB doc includes a "migration recipe" subsection — what to grep for, what to swap, how to handle `from_attributes=True` co-existence.

---

## 7. Open questions

1. **Should `StrictHttpModel` also lock `model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)`?** — Deferred. Whitespace stripping is a separate concern and could break legitimate payloads (e.g. user-edited prose). Ship the minimal strict-by-default; add `str_strip_whitespace` only if N≥2 products want it.
2. **Frontend hook-side defense — when?** — Deferred to a separate dispatch. The seed change closes the backend half (422 surfaces the misroute); the frontend half adds compile-time generics (`mutationFn<TPayload extends StrictPayload>`).
3. **Migration sequencing — single mega-dispatch or per-product?** — Recommend per-product (smaller diff, easier review, per-product test green gate). Filed as follow-up scope.

---

## 8. Dependencies & blockers

None for the seed surface — Pydantic v2 ships `extra="forbid"` natively. The pattern is canonical.

---

## 9. Success criteria

- [x] `noctusai_lib.api.StrictHttpModel` importable from any product backend.
- [x] Unit test: instantiating `StrictHttpModel(known_field=..., unknown_field=...)` raises `ValidationError`.
- [x] FastAPI integration test: POSTing `{unknown_key: ...}` to a route declaring `StrictHttpModel`-subclassed body returns 422 with body naming the offending key.
- [x] `pytest seed/lib/backend/tests/ -q` green.
- [x] KB pattern doc + INDEX entry + CLAUDE/backend.md pointer.
- [x] Memory `feedback_pydantic_silent_drop_kills_writes` references the new seed surface.

---

## 10. How to use this plan

Single-session ship. The seed surface is small, the audit is mechanical, and per-product migration is explicitly out of scope. Engineer SEED-FORBID's report at session-close is the artifact the architect uses to decide migration sequencing.

---

## 11. Change Log

- **2026-05-11** — Project filed + Phases 0+1+2 completed in single session by Engineer SEED-FORBID. Audit confirmed zero `extra="forbid"` across seed + 8 products (the entire HTTP boundary is silently `extra="ignore"`). Path A chosen: `StrictHttpModel` base in `seed/lib/backend/noctusai_lib/api/schemas.py`; products opt in via inheritance. Tests + KB doc + memory amend shipped. Per-product migration filed as follow-up.
