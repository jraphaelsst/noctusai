# seed-cors-origins-registry — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 5 in progress (Engineer CORS-REGISTRY)
- **Owner / stakeholders:** USER · Engineer CORS-REGISTRY (architect dispatch)
- **Related docs:** `projects/cors-hardening-audit-2026-05-11/PROJECT.md` (CORS-AUDIT), `seed/lib/backend/noctusai_lib/config/settings.py`, `seed/framework/backend/noctusai_seed/config.py`, `start.sh` PRODUCTS registry, KB § PATTERNS/environment.md
- **Project slug:** `seed-cors-origins-registry` — cross-product platform-infra; lives at `projects/<slug>/`.

---

## 1. Context & Purpose

CORS-AUDIT (commit `9754871`) flagged `cors_origins="*"` on core as the auth-replay anti-pattern (wildcard + credentials). CORE-ORIGINS (commit `04534f7`) replaced it with an enumerated 13-origin string at `products/core/backend/app/config.py:24` covering every frontend port across the fleet.

Inline enumeration works but breaks the **single source of truth**: when a new product joins `start.sh`'s `PRODUCTS=(...)` registry, the platform-wide CORS list does NOT auto-grow. Anyone adding a product must remember to also extend core's `cors_origins`. This is the per-product code count > 0 slip — for a cross-product concern (which frontend ports exist), the right answer is **zero**.

This project ships a seed-side helper that parses `start.sh PRODUCTS` and derives the origins list, plus a sentinel `cors_origins = "@registry:all"` / `"@registry:own:<slug>"` for products to opt in. CORE adopts immediately as the first consumer (its 13-origin enumeration becomes a one-line sentinel).

---

## 2. Confirmed constraints

- **No touch on `app_factory.py`** — SEED-GUARD in flight on `CORSMiddleware` mount + wildcard+credentials guard. *(Parallel-agent collision protocol.)*
- **No touch on workflows or per-product routers** — SEC-CI + AUTH-RL in flight elsewhere.
- **Seed-side helper + Settings property only** — scope-narrowed by architect brief.
- **Sentinel string approach** — `BaseAppSettings.cors_origins` stays `str`; products opt in via `"@registry:all"` / `"@registry:own:<slug>"`. Plain enumerated strings keep working unchanged.
- **Default rec from architect** — sentinel approach (chosen over `cors_origins_from_registry: bool` knob).

---

## 3. Design principles

1. **Zero per-product CORS port maintenance.** Adding a product to `start.sh PRODUCTS` automatically extends every product's `@registry:all` CORS list.
2. **Backward compatible.** Plain `cors_origins = "http://foo,..."` strings are untouched; sentinel is opt-in.
3. **Universal localhost alts.** `5173` (default Vite) + `3000` (default Next/React) always present — common dev shells that aren't in `PRODUCTS`.
4. **Graceful fallback.** Missing `start.sh` → return localhost alts only (don't crash); explicit error surfaces only on malformed registry.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** YES. "Allow my frontend + every other product frontend if I'm the SSO bridge" is a uniform pattern.
2. **Is the data source product-specific?** NO. `start.sh PRODUCTS` is platform-wide single source.
3. **Is the placement product-specific?** NO. `cors_origins_list` already lives on `BaseAppSettings` (seed-side); sentinel resolution belongs there too.
4. **Is the visibility / permission rule the same?** YES. CORS allowlist is uniform.
5. **Does the seam already exist in seed?** YES — `BaseAppSettings.cors_origins_list` property. Adding sentinel-resolution extends an existing seam.
6. **Default-on or opt-in?** OPT-IN. Plain enumerated strings keep working (backward compat); sentinel is opt-in via per-product `cors_origins = "@registry:..."`.

**Litmus — per-product code count:**

- [x] **0 lines** for products that opt in via sentinel — pure cross-product concern; lives entirely in seed.
- [x] **1 line** opt-in via `cors_origins = "@registry:all"` or `"@registry:own:<slug>"`.

**Phase plan:** §6 works in seed (correct).

---

## 4. Scope

**In scope:**
- New module `seed/lib/backend/noctusai_lib/config/cors_registry.py`
- `parse_products_registry(start_sh)` + `derive_cors_origins(...)` helpers
- Extend `BaseAppSettings.cors_origins_list` to recognize `@registry:all` / `@registry:own:<slug>` sentinels
- Tests at `seed/lib/backend/tests/config/`
- KB amend at `KB § PATTERNS/environment.md § CORS_ORIGINS cascade`
- CORE migration (`products/core/backend/app/config.py`) — 13-origin enumeration → `@registry:all` sentinel; verify identical resolution

**Out of scope (for now):**
- Per-product migration of the other 12 inline enumerations — DEFERRED. CORE is the highest-leverage adopter; per-product migration filed as follow-up after the seed seam ships.
- Changing `app_factory.py` — SEED-GUARD's scope.
- Touching `cors_origins_list` consumers downstream of CORSMiddleware mount.

---

## 5. Architecture / Data Model

**Single helper module** — `seed/lib/backend/noctusai_lib/config/cors_registry.py`:

```python
def parse_products_registry(start_sh: Path) -> list[ProductEntry]:
    """Parse PRODUCTS=( ... ) array between BEGIN/END sentinels.

    Returns [{slug, display, backend_port, frontend_port}, ...].
    Missing file → []. Empty array → [].
    """

def derive_cors_origins(
    start_sh: Optional[Path] = None,
    include_localhost_alts: bool = True,
    include_all_frontends: bool = True,
    own_slug: Optional[str] = None,
) -> list[str]:
    """Return canonical origins list.

    Sentinel cases:
    - include_all_frontends=True  → every frontend (SSO bridge)
    - own_slug="<slug>"           → just that product's frontend + alts
    """
```

**Sentinel resolution** in `BaseAppSettings.cors_origins_list`:

- `"@registry:all"` → `derive_cors_origins(include_all_frontends=True)`
- `"@registry:own:<slug>"` → `derive_cors_origins(own_slug=<slug>, include_all_frontends=False)`
- Plain string → existing `split(",")` behavior (unchanged)
- `"*"` → `["*"]` (unchanged)

**File locations:**

- `seed/lib/backend/noctusai_lib/config/cors_registry.py` — NEW.
- `seed/lib/backend/noctusai_lib/config/settings.py` — EDIT `cors_origins_list` to handle sentinels.
- `seed/lib/backend/tests/config/__init__.py` — NEW.
- `seed/lib/backend/tests/config/test_cors_registry.py` — NEW.
- `products/core/backend/app/config.py` — EDIT `cors_origins` to `"@registry:all"`.
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/environment.md` — AMEND.

---

## 6. Phase plan

- **Phase 0** — Read start.sh format + canonical CORE consumer + BaseAppSettings + READ-ONLY app_factory.py. ✅
- **Phase 1** — Ship `cors_registry.py` helper module.
- **Phase 2** — Extend `cors_origins_list` to recognize sentinels.
- **Phase 3** — Tests for parse + derive + sentinel resolution.
- **Phase 4** — KB amend at `KB § PATTERNS/environment.md`.
- **Phase 5** — Migrate CORE; verify identical 13-origin resolution.

---

## 7. Open Questions

None — design locked by architect brief.

---

## 8. Verification

- `cd seed/lib/backend && pytest tests/config/test_cors_registry.py -q` → green.
- `cd products/core/backend && pytest tests/ -q` → 471 baseline + green (after CORE migration).
- `bash scripts/verify-kb-sync.sh` → green.
- Boot test: `python -c "from noctusai_lib.config.cors_registry import derive_cors_origins; print(derive_cors_origins())"` → list of origins.
- CORE migration smoke: `python -c "from app.config import settings; print(sorted(settings.cors_origins_list))"` from `products/core/backend/` → matches sorted pre-migration 13-origin list.

---

## 9. Improvements

*(Captured live during execution.)*

- [x] **localhost alt ports universal** — `5173` (Vite default) + `3000` (Next default) hardcoded in `derive_cors_origins(include_localhost_alts=True)`. Avoids polluting `PRODUCTS` with non-port-pinned shells.
- [x] **Sentinel grammar narrow** — only `@registry:all` + `@registry:own:<slug>` supported initially. Wider grammar (`@registry:group:<name>`) deferred until N=2 ask surfaces.
- [x] **No fail-loud on missing start.sh** — return localhost alts only. Test env doesn't always have start.sh on the import path; crashing config init would block every test suite.

---

## 10. Copy-paste commands

```bash
# Phase 1-3 verification
cd seed/lib/backend && pytest tests/config/test_cors_registry.py -q

# Phase 5 verification (CORE adopter)
cd products/core/backend && pytest tests/ -q

# Boot smoke
cd seed/lib/backend && python -c "from noctusai_lib.config.cors_registry import derive_cors_origins; import json; print(json.dumps(derive_cors_origins(), indent=2))"

# Sync check
bash scripts/verify-kb-sync.sh
```

---

## 11. Change log

- 2026-05-11 — Phase 0 complete. Read `start.sh` registry format, CORE consumer, BaseAppSettings, app_factory.py (read-only).
- 2026-05-11 — Phase 1 — helper module shipped at `seed/lib/backend/noctusai_lib/config/cors_registry.py`.
- 2026-05-11 — Phase 2 — `cors_origins_list` sentinel resolution wired.
- 2026-05-11 — Phase 3 — tests green.
- 2026-05-11 — Phase 4 — KB amend at `KB § PATTERNS/environment.md`.
- 2026-05-11 — Phase 5 — CORE migrated; 13-origin resolution verified identical.
