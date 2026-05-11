# CORS Hardening Audit — Project Document

> Phase 0 read-only cross-product CORS audit. Inventory + severity classification + Phase 1 dispatch shape.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 0 (audit) complete — Phase 1 dispatch shape recommended
- **Owner / stakeholders:** USER (architect)
- **Related docs:**
  - `seed/lib/backend/noctusai_lib/api/app_factory.py` (canonical CORS seam)
  - `seed/lib/backend/noctusai_lib/config/settings.py` (BaseAppSettings.cors_origins + cors_origins_list)
  - `seed/framework/backend/noctusai_seed/config.py` (ProductSettings — products extend)
  - `seed/framework/backend/noctusai_seed/app.py` (create_product_app → configure_app)
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/environment.md § CORS_ORIGINS cascade`
- **Project slug:** `cors-hardening-audit-2026-05-11` (cross-product → `projects/<slug>/`)

---

## 1. Context & Purpose

Every product backend ships a `cors_origins` config field on its product settings. The audit's purpose was to find: (a) wildcard-origin + credentials=True combinations (CRITICAL — Starlette refuses the combo but the field+seed combination still allows it to be requested), (b) dev-origin leakage in defaults that would be active in prod when root `.env` does not override, (c) wildcard methods/headers (defense-in-depth gaps), and (d) seed-seam adoption.

**Headline:** the seed seam (`configure_app(...)`) is fully adopted (11/11 products). All 11 backends route CORS through `create_product_app() → configure_app()` — there are **zero per-product CORSMiddleware mounts**. Methods and headers are enumerated at the seed and never overridden at the products. The risk is concentrated in **`core`'s `cors_origins = "*"` default + the seed's hardcoded `allow_credentials=True`**, plus a **missing `CORS_ORIGINS` line in the root `.env.example`** (KB documents the cascade but the template does not carry the slot).

---

## 2. Confirmed constraints

- **Audit-only** — Phase 0 read-only. No source edits. (Brief instruction.)
- **11 products in scope** — adconnect, core, daily-life, dev-team, erp-imobiliario, imobi-scheduling, mailing, media-scheduling, personal-finance, therapy-platform, youtube-crawler. (Matches `products/` listing.)
- **Findings-as-text fallback** — engineer return-shape if Write fails. (Did not fire — Write authorized in §17.6.)

---

## 3. Design principles

1. **Seed seam owns CORS.** Per-product CORS middleware mounts = structural fork, refactor at the seed level.
2. **Wildcard origins with credentials = CRITICAL.** Per Starlette/FastAPI docs: `allow_origins=["*"]` with `allow_credentials=True` is silently coerced (Starlette emits an effectively useless `Access-Control-Allow-Origin: *` without echoing the request origin — auth replay surface depending on framework version + browser). Either origins must be enumerated or credentials must be False.
3. **Localhost defaults are fine IF prod `.env` overrides them.** The risk is when prod deploys forget to set `CORS_ORIGINS`.
4. **Methods + headers enumeration is defense-in-depth.** The seed already enumerates both — preserve this property.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** YES. CORS middleware shape is a single platform-wide contract.
2. **Is the data source product-specific?** NO. Origins come from a single field per product, layered over by root `.env CORS_ORIGINS`.
3. **Is the placement product-specific?** NO. The seam is `seed/lib/backend/noctusai_lib/api/app_factory.py § configure_app()`, mounted from `seed/framework/backend/noctusai_seed/app.py § create_product_app()`.
4. **Is the visibility / permission rule the same?** YES. Universal.
5. **Does the seam already exist in seed?** YES — `configure_app(...)` ships canonical CORS with enumerated methods/headers; products only choose their `cors_origins` value.
6. **Default-on or opt-in?** DEFAULT-ON — every product inherits via `create_product_app()`.

**Litmus — per-product code count this design requires:**
- [x] **0 lines** of per-product CORS middleware. The only per-product surface is the `cors_origins` field default — and even that is subject to root `.env` override.

**Phase plan implications:** any Phase 1 fix lives at the seed (app_factory + BaseAppSettings) + `.env.example` + KB doc. Product files touch only `cors_origins` defaults (text-tighten). Phase 1 is NOT a per-product walk-through.

---

## 4. Scope

**In scope (Phase 0 — this audit):**
- Per-product CORS classification (origins / credentials / methods / headers / severity).
- Seed seam audit.
- Top-3 highest-priority gaps.
- Phase 1 dispatch shape (recommendation only — no execution).

**Out of scope (deferred to Phase 1+):**
- Any source code edit.
- Root `.env.example` CORS_ORIGINS slot addition.
- Seed-level wildcard guard (refuse `cors_origins="*"` when `allow_credentials=True`).
- KB doc refresh of `environment.md` port list (ports listed there are stale vs current product set).

---

## 5. Architecture / Data Model

### 5.1 The seed CORS seam

**File:** `seed/lib/backend/noctusai_lib/api/app_factory.py`

```python
# Lines 125–132
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,                                    # HARDCODED True
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=_allow_headers,        # enumerated default; per-product override allowed
    expose_headers=_expose_headers,      # enumerated default; per-product override allowed
)
```

Default `_allow_headers`: `["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "X-Correlation-ID", "X-Request-ID"]`.
Default `_expose_headers`: `["X-Correlation-ID", "X-Response-Time-Ms", "Content-Disposition"]`.

### 5.2 The `cors_origins_list` property

**File:** `seed/lib/backend/noctusai_lib/config/settings.py` (lines 51–55)

```python
@property
def cors_origins_list(self) -> list[str]:
    if self.cors_origins == "*":
        return ["*"]                                           # WILDCARD ALLOWED
    return [origin.strip() for origin in self.cors_origins.split(",")]
```

This explicitly enables the wildcard path when `cors_origins == "*"` — and the seed combines that with `allow_credentials=True` unconditionally.

### 5.3 The `ProductSettings` base default

**File:** `seed/framework/backend/noctusai_seed/config.py` (line 38)
`cors_origins: str = "http://localhost:5173,http://localhost:3000"` — every product can override.

### 5.4 Per-product CORS table

All 11 products mount CORS exclusively via `create_product_app() → configure_app()`. There are **zero per-product `CORSMiddleware` / `add_middleware(CORSMiddleware, ...)` mounts**. The only per-product CORS surface is the `cors_origins` field on the product `Settings` class.

Confirmed by:
- `grep -rn 'CORSMiddleware\|allow_origins\|allow_credentials\|allow_methods\|allow_headers' products/<p>/backend/` returns ONE hit per product — the `cors_origins` field on `app/config.py`.
- `grep -rn 'cors_allow_headers\|cors_expose_headers\|CORSMiddleware' products/` (excluding caches) returns zero hits — no product overrides the seed header / method defaults.

| Product | `cors_origins` default | Credentials | Methods | Headers | Severity |
|---|---|---|---|---|---|
| adconnect | `http://localhost:8007,http://localhost:8130,http://localhost:5173,http://localhost:3000` | True (seed) | enumerated (seed) | enumerated (seed) | OK |
| core | `*` | True (seed) | enumerated (seed) | enumerated (seed) | CRITICAL — wildcard + credentials |
| daily-life | `http://localhost:8005,http://localhost:8110,http://localhost:5173,http://localhost:3000` | True (seed) | enumerated (seed) | enumerated (seed) | OK |
| dev-team | `http://localhost:8009,http://localhost:8123,http://localhost:5173,http://localhost:3000` | True (seed) | enumerated (seed) | enumerated (seed) | OK |
| erp-imobiliario | `http://localhost:8080,http://localhost:5173,http://localhost:3000` | True (seed) | enumerated (seed) | enumerated (seed) | OK |
| imobi-scheduling | `http://localhost:8011,http://localhost:8160,http://localhost:5173,http://localhost:3000` | True (seed) | enumerated (seed) | enumerated (seed) | OK |
| mailing | `http://localhost:8006,http://localhost:8120,http://localhost:5173,http://localhost:3000` | True (seed) | enumerated (seed) | enumerated (seed) | OK |
| media-scheduling | `http://localhost:8096,http://localhost:8130,http://localhost:5173,http://localhost:3000` | True (seed) | enumerated (seed) | enumerated (seed) | OK |
| personal-finance | `http://localhost:8090,http://localhost:5173,http://localhost:3000` | True (seed) | enumerated (seed) | enumerated (seed) | OK |
| therapy-platform | `http://localhost:8095,http://localhost:5173,http://localhost:3000` | True (seed) | enumerated (seed) | enumerated (seed) | OK |
| youtube-crawler | `http://localhost:8010,http://localhost:8150,http://localhost:5173,http://localhost:3000` | True (seed) | enumerated (seed) | enumerated (seed) | OK |

**Severity counts:**
- CRITICAL (wildcard + credentials): **1** — core
- WARNING (wildcard methods/headers): **0**
- OK (enumerated everything): **10**

**Cross-cutting risks (apply to all 11 because the seed/seam carries them):**

| Risk | Evidence | Severity |
|---|---|---|
| CRITICAL — `core` ships `cors_origins="*"` while seed hardcodes `allow_credentials=True`. Wildcard origin + credentials is the documented auth-replay anti-pattern (Starlette + FastAPI docs warn explicitly; some versions silently neutralize, depending on browser the surface remains exploitable for non-credentialed reads). | `products/core/backend/app/config.py:21` + `seed/lib/backend/noctusai_lib/api/app_factory.py:127-128` | CRITICAL |
| HIGH — Root `.env.example` has NO `CORS_ORIGINS` slot. KB doc (`PATTERNS/environment.md § CORS_ORIGINS cascade`) says root `.env` overrides per-product defaults; absent from template means prod deploys silently fall back to localhost (or `*` for core). | `grep CORS .env.example` returns no matches; `.env.example` is 92 lines, no CORS slot. | HIGH |
| MEDIUM — The seed `allow_credentials=True` is unconditional, even when wildcard origins are configured. No guard / refusal at app boot. | `seed/lib/backend/noctusai_lib/api/app_factory.py:127-128` | MEDIUM |
| LOW — `environment.md § CORS_ORIGINS cascade` port list is stale (lists 5173/8080/8090/8095/8100/8110/8120 only — missing adconnect 8130, dev-team 8123, imobi-scheduling 8160, media-scheduling 8130, youtube-crawler 8150). KB doc decay. | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/environment.md:50` | LOW |

---

## 6. Implementation phases

### Phase 0 — Audit ✅ (this document)
- [x] Inventory each of 11 products' CORS shape.
- [x] Read the seed seam (`configure_app` + `cors_origins_list`).
- [x] Classify severity.
- [x] Identify top-3 gaps.
- [x] Recommend Phase 1 dispatch shape.

**Improvements:** none identified beyond what's in §5.4 risk table — those ARE the Phase 1 work items.

### Phase 1 — Recommended dispatch shape (NOT executed in this audit)

**Three parallel chunks, dispatched in a single Task tool-use turn (architect runs this in a separate session).** All chunks edit either seed or root-level config — none walks through products. Per the §3a litmus, per-product LoC = 0.

#### Engineer SEED-GUARD (file: `seed/lib/backend/noctusai_lib/api/app_factory.py` + tests)
- Refuse wildcard origins + credentials at boot. Either:
  - **(a) hard refuse** — `if "*" in settings.cors_origins_list and allow_credentials: raise ValueError(...)` early in `configure_app`, OR
  - **(b) soft-coerce** — when `*` detected, force `allow_credentials=False` and log WARNING.
- **Recommendation:** (a) hard refuse, because core hits it today and the refusal forces the right fix instead of silently degrading auth. Add a guard test.
- Status-pinned test colocated.

#### Engineer CORE-ORIGINS (file: `products/core/backend/app/config.py`)
- Replace `cors_origins = "*"` with an enumerated list of the union of every product's frontend origin + the core SSO origin.
- Document via comment that root `.env CORS_ORIGINS` overrides for prod.
- Verify SSO callback flow still works (cross-product redirect — core IS the SSO authority, so its CORS must accept every product frontend).

#### Engineer ENV-EXAMPLE-AND-KB (files: `.env.example` + `KNOWLEDGE-BASE/CONTEXT/PATTERNS/environment.md`)
- Add `CORS_ORIGINS` slot to root `.env.example` with the canonical comma-separated list of every product's frontend port.
- Refresh the stale port list in `environment.md § CORS_ORIGINS cascade` — currently missing 5 ports.
- Optionally: add a `CORS_ORIGINS=` block to other product `.env.example`s once that template lift happens (memory note: only imobi-scheduling has a per-product backend `.env.example` today).

**Wave-2 follow-ups (filed after Wave-1 FF-merges):**
- Document the wildcard-origin / credentials guard in `KB § PATTERNS/backend.md` or a new `KB § PATTERNS/cors.md`.
- Re-run audit after Phase 1 to confirm severity counts drop to 0 CRITICAL / 0 HIGH.

### Phase 2 — Future (deferred)
- Consider deriving `cors_origins` from the platform-level port registry (`KB § 05-INFRASTRUCTURE.md`) so adding a product auto-extends the allowlist.

---

## 7. Open questions

1. **Core's `cors_origins = "*"` — historical or required?** Core is the SSO control-plane (it serves auth redirects across every product). Does it need a wildcard, or can it enumerate the known frontend origins union? *Recommendation:* enumerate — the union is known at any given moment (it IS the port registry). Wildcard was almost certainly an early-dev shortcut.
2. **Guard shape — hard refuse vs soft coerce?** Hard refuse forces the explicit fix; soft coerce keeps the app booting in degraded mode. *Recommendation:* hard refuse, with the seed-philosophy "no silent errors" rule.
3. **Root `.env.example` CORS_ORIGINS — single line or per-port-comments?** *Recommendation:* per-port-comments (one line per known product origin) so adding a new product is a single-line append.

---

## 8. Dependencies & blockers

- None for Phase 0 (audit). Phase 1 dispatch depends on user confirming Q1+Q2 recommendations.

---

## 9. Success criteria

- [x] Phase 0: every product classified; severity table complete; gaps identified; Phase 1 shape recommended.
- [ ] Phase 1 (deferred): `core/app/config.py` cors_origins enumerated; seed guards wildcard+credentials; root `.env.example` carries `CORS_ORIGINS` slot.
- [ ] Phase 1 verification: re-run audit → 0 CRITICAL / 0 HIGH.

---

## 10. How to use this plan

- Phase 0 is single-pass. The deliverable is this document + findings.md.
- Phase 1 SHOULD dispatch as 3 parallel chunks per §6 (single Task tool-use turn).
- After Phase 1 FF-merge: re-run the audit (`grep -rn 'cors_origins\|CORSMiddleware\|allow_origins' products/*/backend/ + seed/`).

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Phase 0 audit + recommendation drafted | Engineer CORS-AUDIT (claude-opus-4-7) |
