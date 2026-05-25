# social-wiring-vista-seed-lift — Project Document

> Living doc. Scope: lift `CRMService` / `PropertyData` / `build_youtube_metadata` / `validate_product_code` from `products/social-wiring/backend/app/services/crm_service.py` into seed-lib so future products (ERP-imobiliário, etc.) consume from one source. Social-wiring becomes the first consumer.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** ✅ Wave 1-2 shipped. Seed `noctusai_lib.integrations.vista` adapter layer + `noctusai_lib.domain.real_estate` modules in place. Product-local `crm_service.py` deleted; all callers (chat_router, settings_router, whatsapp_router, whatsapp_intake_service, modules/youtube/routers/upload.py) consume from seed. Vista live-validated against ONE10010. Engineer surfaced pre-existing low-level `VistaClient` — deviation ratified (composes alongside, not replaces; the high-level adapter is the consumer-facing surface). Follow-up: refactor `VistaRESTAdapter` to compose `VistaClient` (DRY at N=2).
- **Owner / stakeholders:** rapha · seed maintainers
- **Related projects:** `projects/platform-auth-modernization/` (file-disjoint sibling — both land before youtube-drive-folder-fanout live test); `products/social-wiring/projects/youtube-drive-folder-fanout/`
- **Project slug:** `social-wiring-vista-seed-lift`
- **Location:** `products/social-wiring/projects/social-wiring-vista-seed-lift/` (consumer-side migration scoped to social-wiring; seed-side lift is platform-wide but originates here)

---

## 1. Context & Purpose

Today `products/social-wiring/backend/app/services/crm_service.py` ships four things — `CRMService` (Vista REST client), `PropertyData` (value object), `build_youtube_metadata` (real-estate-aware metadata shaping), `validate_product_code` (`ONE\d+` pattern check). The yt-crawler predecessor had the same shape, byte-for-byte (this code was lifted into social-wiring during the absorption). The seed already promises Vista as a "showcase adapter, future MCP server" (`KB § INTEGRATIONS/vista.md`), so the destination has been understood for a while.

The youtube-drive-folder-fanout project surfaced the gap — its new endpoint had to import `crm_service` from the product, not from seed. User asked: should this be in seed? Answer: yes. This project does the lift.

**Two seed targets:**
- `noctusai_lib.integrations.vista` — Protocol + Fake + Real(Vista REST) + factory. Same shape as `noctusai_lib.integrations.google_calendar`. CRM transport concern.
- `noctusai_lib.domain.real_estate` — `PropertyData` value object + `build_youtube_metadata` + `validate_product_code`. Pure functions, no IO. Domain concern (the YT metadata shape is real-estate-specific, not Vista-specific — could come from any CRM).

Split rationale: integrations modules ship IO; domain modules ship pure logic. Mirrors the seed layout (`KB § PATTERNS/seed-lib-layout.md`).

---

## 2. Confirmed constraints

- **Same push as platform-auth-modernization** — file-disjoint, parallel-dispatchable.
- **Social-wiring is the canonical consumer** — first to migrate; future products consume the same seed surface.
- **No degradation of the consumer** — the social-wiring `crm_service.py` deletion happens AFTER the migration; intermediate state is a thin re-export shim to avoid breaking imports mid-flight.
- **Fake+Real adapter shape** — Vista is an external HTTP API, so Protocol+Fake+Real+factory mandatory per [[feedback_seed_fake_real_pattern]].
- **`build_youtube_metadata` stays in domain** — it's pure logic, no IO; would fail the "would a Fake here exercise different code than the Real?" exemption test → exempt → domain layer.
- **Test fan-out** — every existing product test that imports `crm_service` continues passing via the re-export shim until the final deletion.

---

## 3. Design principles

1. **Split transport from domain.** Vista REST adapter ⊂ integrations; PropertyData + metadata builder ⊂ domain.
2. **Mirror existing seed integration shape.** `google_calendar` is the canonical reference — same `Protocol + Fake + Real + factory + types + mappers + (optional) router` structure.
3. **Migrate, don't fork.** After seed exports `PropertyData`, the social-wiring class becomes a thin re-export, then disappears entirely.
4. **No new abstractions.** Don't introduce a "RealEstateCRMAdapter" superclass that abstracts over Vista + future CRMs — Vista is the only one today; YAGNI per `KB § PATTERNS/project-execution.md`.

---

## 3a. Seed-first analysis

1. **Contract identical for every product?** YES — `CRMService.get_property(code) -> PropertyData | None` is a clean contract.
2. **Data source product-specific?** NO — Vista is one external service; any product can consume.
3. **Placement product-specific?** NO — seed-level `noctusai_lib.integrations.vista`.
4. **Visibility / permission rule?** YES — auth config is per-tenant via env (already today).
5. **Seam in seed?** NO — Vista is referenced in `KB § INTEGRATIONS/vista.md` as a "future MCP server" but doesn't exist in `noctusai_lib.integrations` yet.
6. **Default-on or opt-in?** OPT-IN — products consume by importing + wiring; no factory injection by default.

**Litmus:** seed-level lift is pure cross-product (correct). Per-product code count post-migration = `from noctusai_lib.integrations.vista import get_vista_adapter; from noctusai_lib.domain.real_estate import build_youtube_metadata, PropertyData` (3 lines).

---

## 4. Scope

**In scope:**
- New `noctusai_lib.integrations.vista` module: `VistaCRMAdapter` Protocol, `FakeVistaAdapter`, `VistaRESTAdapter`, `get_vista_adapter(...)` factory.
- New `noctusai_lib.domain.real_estate` module: `PropertyData` dataclass, `build_youtube_metadata(prop, code)`, `validate_product_code(code)`.
- Re-export shim at `products/social-wiring/backend/app/services/crm_service.py` (transition period only — deleted at project close).
- Social-wiring consumers (`whatsapp_intake_service.py` + the new `routers/upload.py` helper) switch their imports to seed.
- `KB § INTEGRATIONS/vista.md` updated with consume-side documentation per [[feedback_absorption_ships_consume_docs]].
- Tests: full coverage of both new seed modules; existing social-wiring tests continue passing.

**Out of scope:**
- Vista MCP tool exposure — already pointed at in `KB § INTEGRATIONS/vista.md` as a separate future project; not in this push.
- Per-tenant calibration (the documented gap) — open question elsewhere; not in this push.
- Migrating to other CRMs / abstracting a "RealEstateCRM" superclass — N=1 today.

---

## 5. Architecture / Data Model

### `noctusai_lib.integrations.vista`

```
vista/
  __init__.py        → Protocol, Fake, get_vista_adapter, errors, types re-exports
  types.py           → VistaConnectionStatus + value objects specific to transport
  protocol.py        → VistaCRMAdapter Protocol (async get_property(code))
  fake_adapter.py    → FakeVistaAdapter (in-memory; dev/test default)
  real.py            → VistaRESTAdapter (the existing CRMService code, renamed)
  factory.py         → get_vista_adapter(base_url, api_key, *, fake=False)
  errors.py          → VistaError, VistaNotConfigured, etc.
```

### `noctusai_lib.domain.real_estate`

```
real_estate/
  __init__.py        → PropertyData, build_youtube_metadata, validate_product_code re-exports
  types.py           → PropertyData @dataclass
  metadata.py        → build_youtube_metadata(prop: PropertyData, product_code: str) -> dict
  validators.py      → validate_product_code(code: str) -> bool
```

### Consume-side (social-wiring after migration)

```python
# whatsapp_intake_service.py
from noctusai_lib.integrations.vista import get_vista_adapter, VistaError
from noctusai_lib.domain.real_estate import build_youtube_metadata, validate_product_code

# routers/upload.py (the youtube-drive-folder-fanout helper)
from noctusai_lib.domain.real_estate import build_youtube_metadata, validate_product_code
from noctusai_lib.integrations.vista import get_vista_adapter, VistaError, VistaNotConfigured
```

The product's local `crm_service.py` becomes (transition):

```python
# Deprecated re-export shim — kept until every consumer migrates;
# then deleted.
from noctusai_lib.domain.real_estate import (
    PropertyData,
    build_youtube_metadata,
    validate_product_code,
)
from noctusai_lib.integrations.vista import (
    VistaError as CRMServiceError,
    VistaNotConfigured as CRMNotConfigured,
    VistaRESTAdapter as CRMService,
)
```

---

## 6. Implementation phases

### Phase 1 — Wave 1 dispatch (file-disjoint parallel engineer; sibling to platform-auth Wave 1)
- [ ] **E-VISTA**: scaffold both new seed modules (`integrations/vista` + `domain/real_estate`) with Fake + Real + factory + tests. NO consumer changes yet.
- [ ] Patch file at `/tmp/E-VISTA.patch`.

### Phase 2 — Wave 1 architect (salvage + integrate)
- [ ] Salvage patch, apply, run seed tests.
- [ ] Commit-on-ship.

### Phase 3 — Wave 2 dispatch (consumer migration)
- [ ] **E-SW-VISTA**: replace `products/social-wiring/backend/app/services/crm_service.py` with the re-export shim. Update direct callers to import from seed. Update existing tests' imports.

### Phase 4 — Wave 2 architect (validate + delete shim)
- [ ] Run full social-wiring backend test suite.
- [ ] If green, delete the shim entirely; update any remaining imports.
- [ ] Run again; commit.

### Phase 5 — Documentation
- [ ] Update `KB § INTEGRATIONS/vista.md` with consume-side recipe (`get_vista_adapter` factory, what `__all__` ships).
- [ ] Update `KB § PATTERNS/seed-lib-layout.md` § integrations roster (auto-derived; ensure listing).
- [ ] Update `social-wiring/MASTER-PROMPT.md` reference list.

### Phase 6 — Close
- [ ] Findings.md.

---

## 7. Open questions

1. **Should the Vista adapter ship sync or async `get_property`?** — current code is async (uses httpx.AsyncClient). Keep async for consistency with `google_calendar`. Decided.

---

## 8. Dependencies & blockers

- **Vista credentials must be in `.env`** (already today via `VISTA_BASE_URL` / `VISTA_API_KEY`).
- **No dependency on platform-auth-modernization** — file-disjoint, can run in parallel.

---

## 9. Success criteria

- `from noctusai_lib.integrations.vista import get_vista_adapter` works in social-wiring.
- `from noctusai_lib.domain.real_estate import build_youtube_metadata, PropertyData, validate_product_code` works.
- `products/social-wiring/backend/app/services/crm_service.py` deleted (zero local copy).
- Full social-wiring backend tests green.
- `KB § INTEGRATIONS/vista.md` consume-side recipe added.

---

## 11. Change Log

- **2026-05-20** — Project filed. Two-module split designed (integrations/vista + domain/real_estate). Wave 1 dispatch ready.
- **2026-05-20** — Wave 1 ✅ E-VISTA created the adapter layer (`VistaCRMAdapter` Protocol + `FakeVistaAdapter` + `VistaRESTAdapter` + `get_vista_adapter` factory + `noctusai_lib.domain.real_estate` w/ `PropertyData` + `build_youtube_metadata` + `validate_product_code`). 23 new tests; full seed-lib suite 1761/1761. Engineer surfaced the pre-existing `VistaClient` lower-level module — adapter composes alongside (preserves existing low-level surface).
- **2026-05-20** — Wave 2 ✅ E-SW-VISTA migrated 4 caller files to seed imports (chat_router, settings_router, whatsapp_router, whatsapp_intake_service). Architect inline-handled the 5th caller (`modules/youtube/routers/upload.py`, file-disjoint hard rule) + deleted `products/social-wiring/backend/app/services/crm_service.py` (zero local copy now). 465/465 social-wiring backend green.
- **2026-05-20** — Live validation: `await crm.get_property("ONE10010")` returns the real property (Casa em Alphaville, 6 quartos, 835m², R$ 7.200.000,00). `build_youtube_metadata` produces a 99-char YT title, emoji-rich description, and tag set including the product_code. Vista consume-from-seed proven end-to-end via Python REPL against the live Vista REST API.
