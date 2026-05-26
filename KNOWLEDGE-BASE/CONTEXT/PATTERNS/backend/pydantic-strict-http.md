# Pydantic strict-by-default at the HTTP boundary

> **Rule.** Every HTTP-boundary Pydantic schema (request body, response model that's consumed by typed frontend code) inherits from `noctusai_lib.api.StrictHttpModel`. The base sets `model_config = ConfigDict(extra="forbid")`, so unknown keys land as **422 Unprocessable Entity** instead of being silently dropped.

---

## Why this exists

The Pydantic v2 default is `extra="ignore"` — unknown keys are silently dropped at instantiation. Combined with the typical frontend mutation hook shape `mutationFn<Record<string, unknown>>` (which accepts ANY shape), this produces a **silent data-loss bug class** when a hook misroutes:

1. Frontend hook posts `{name, cnpj, phone}` to `/admin/users` (intended `/clinic-settings`).
2. `UsersUpdate` schema declares only `{role, email}` — `name/cnpj/phone` are unknown.
3. Pydantic silently drops them. The remaining keys may not match anything → UPDATE is a no-op, or the wrong row gets touched.
4. FastAPI returns 200. Frontend shows success toast. **Zero persistence. Zero error signal.**

VVV's therapy clinic-settings fix on 2026-05-11 (commit `a81d3b9`) was the surface fix; this pattern is the structural close. Memory entry: `feedback_pydantic_silent_drop_kills_writes`.

---

## The seed surface

**Location:** `seed/lib/backend/noctusai_lib/api/schemas.py`

```python
from pydantic import BaseModel, ConfigDict

class StrictHttpModel(BaseModel):
    """Pydantic base for HTTP-boundary schemas. Rejects unknown keys (422)."""
    model_config = ConfigDict(extra="forbid")
```

**Re-exported from** `noctusai_lib.api`:

```python
from noctusai_lib.api import StrictHttpModel
```

---

## Pattern of use

### New schemas — inherit from `StrictHttpModel`

```python
from noctusai_lib.api import StrictHttpModel

class SettingsUpdate(StrictHttpModel):
    name: str | None = None
    phone: str | None = None
```

A FastAPI route declaring `payload: SettingsUpdate` automatically 422s on any unknown key, with body shape:

```json
{
  "detail": [
    {
      "type": "extra_forbidden",
      "loc": ["body", "cnpj"],
      "msg": "Extra inputs are not permitted",
      "input": "00.000.000/0001-00"
    }
  ]
}
```

The `loc` array names the offending key — the misroute becomes immediately diagnosable.

### Subclasses adding ORM shaping — config merges automatically

Pydantic v2 **merges** `model_config` across the MRO (it does NOT replace). Adding `from_attributes=True` to a subclass keeps the parent's `extra="forbid"`:

```python
from pydantic import ConfigDict
from noctusai_lib.api import StrictHttpModel

class WithOrm(StrictHttpModel):
    model_config = ConfigDict(from_attributes=True)
    value: int

# WithOrm.model_config == {"extra": "forbid", "from_attributes": True}
# Unknown keys still raise; ORM shaping still works.
```

### Carve-outs — explicit opt-out

Sometimes accepting unknown keys is the design intent (e.g. response shapes that surface DB columns the frontend doesn't strongly type yet). Override explicitly:

```python
class DistributorWithMetricsOut(StrictHttpModel):
    """Mirrors `DistributorOut` shape + per-row aggregations. Kept loose so
    unexpected DB columns surface in the response without a schema error."""
    model_config = ConfigDict(extra="allow")  # explicit opt-out
    id: str
    ...
```

The carve-out lives in the schema's docstring + the `extra="allow"` declaration. Both make the divergence auditable.

---

## Migration recipe (per-product)

This pattern doc ships the seed surface; per-product migration is a follow-up dispatch per product. Recipe:

1. **Inventory.** `grep -rln "BaseModel\|ConfigDict" --include="*.py" products/<slug>/backend/app/schemas/ products/<slug>/backend/app/routers/`
2. **Classify each `BaseModel` subclass.** Request body or typed-by-frontend response? → HTTP-boundary, MIGRATE. Internal value object / external DTO / ORM-shaping-only? → SKIP.
3. **Swap the base.** AST-first via libcst — find `class Foo(BaseModel):` where `Foo` is HTTP-boundary, rewrite to `class Foo(StrictHttpModel):`. Add the import from `noctusai_lib.api`.
4. **Watch for legitimate carve-outs.** If the original schema had `extra="allow"` (rare — 1 instance platform-wide), keep it explicit on the subclass.
5. **Run product tests.** `cd products/<slug>/backend && pytest -q`. Any new 422 in a previously-200 test = either a real misroute caught (fix the hook) OR a test passing intentionally extra keys (rewrite the test to the canonical shape).
6. **Frontend smoke.** Exercise the migrated routes end-to-end — the hook's mutation should still succeed for known payloads.

---

## When NOT to inherit

- **External integration DTOs** (e.g. Vista CRM, WAHA payload shapes) — those are not the FastAPI request boundary; they're shapes received from external systems. Loose acceptance is often correct (the third party adds fields).
- **Internal value objects** that never cross the HTTP boundary — e.g. `noctusai_lib.domain.chatbot.summary.ChatSummary`. These are constructed by our own code; strictness gives no defensive value.
- **Response schemas the frontend doesn't strongly type** — when the frontend reads the response as `Record<string, unknown>` and only consumes a subset of keys, response-side strictness can lock future evolution. Carve-out via `extra="allow"` is fine.

The litmus test: *"is this schema a contract with a typed counterparty?"* If yes → strict. If no → loose is defensible.

---

## Failure modes to watch for

- **Test suites that pass intentionally-extra keys for "future-proofing".** Migration audit found zero true hits today, but watch for them on per-product migration. Right shape post-migration: split the test, or add the key to the schema if it's a real field.
- **Hooks typed `Record<string, unknown>` that now 422.** This IS the bug class surfacing. The fix is on the hook: type the payload explicitly so TypeScript catches the misroute at compile time. The seed change here is the runtime defense; the hook-side defense is a separate follow-up.
- **Frontend response parsing that depends on extra keys.** If a response schema migrates to strict and the response no longer carries an old key, the frontend silently sees `undefined`. The seed change tightens REQUESTS without forcing response strictness — keep response carve-outs explicit during migration.

---

## Related

- **Memory.** `feedback_pydantic_silent_drop_kills_writes` — the bug-class triage that produced this rule.
- **KB.** `PATTERNS/backend/backend.md` — Auth canonical pattern + service shape; this pattern slots above it (request validation precedes auth-derived org scoping).
- **Seed surface.** `seed/lib/backend/noctusai_lib/api/schemas.py` + `tests/api/test_strict_http_model.py` (9 tests pinning the contract incl. FastAPI 422 integration).
- **Audit baseline (2026-05-11).** Zero `extra="forbid"` on the platform; one explicit `extra="allow"` carve-out (`adconnect/admin.py::DistributorWithMetricsOut`); the rest rely on Pydantic's silent default. Per-product migration is a follow-up dispatch.
