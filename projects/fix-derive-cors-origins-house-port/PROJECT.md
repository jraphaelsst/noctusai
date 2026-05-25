# fix-derive-cors-origins-house-port — Project Document

- **Created:** 2026-05-25
- **Status:** 📋 Filed (follow-up) — deferred from the social-wiring dev-pilot SSO/CORS fix
- **Owner:** joaoraphaelsst · architect
- **Priority:** LOW — container + prod CORS are correct; this is the unsupported NATIVE-dev path only.

---

## 1. Context & Problem

`seed/lib/backend/noctusai_lib/config/cors_registry.py` `derive_cors_origins` emits each product's **`frontend_port`** for the localhost dev origins (line ~229: `_add(f"http://localhost:{entry['frontend_port']}")`). The single-container house model serves on the **`backend_port`** (the FIRST `start.sh slug:Name:HOUSE:OLD_FRONTEND` port — what the container publishes + what the browser sends as Origin). The frontend port is vestigial (pre-house 2-container era). So `@registry:all` / `@registry:own:<slug>` allow-list a **dead** localhost origin.

This is the same house-port-vs-vestigial-frontend-port family as the `url_base` fix (migration 037) and the dev-CORS-band fix (`.env.example`, 2026-05-25).

**Why it's LOW priority (not fixed in-flight):**
- **Dev container** (the real dev runtime) has NO `start.sh` → `@registry:all` derives empty regardless → dev CORS comes from the explicit `CORS_ORIGINS` house-port band in `.env`/`.env.example` (already fixed). So `derive`'s port is moot in the container.
- **Prod** uses the `PRODUCT_URL_*` origins (the localhost frontends are harmless noise). So `derive`'s port is moot in prod.
- Only the **unsupported NATIVE-dev** path (core run outside a container, `start.sh` readable, no `CORS_ORIGINS` set) is wrong.

The in-place fix (frontend→backend on line 229) was **reverted** during the 2026-05-25 session because it cascades into ~10 test updates (`tests/config/test_cors_registry.py` + `tests/config/test_per_product_cors_sentinel.py` both assert frontend ports), too much churn for a moot-in-practice path under time pressure.

## 3a. Seed-first analysis

Single seed function (`cors_registry.derive_cors_origins`) + its colocated tests. Not per-product. The fix is one line + test alignment.

## 4. Scope

1. `cors_registry.py`: emit `backend_port` (house) for the registry localhost origins (line ~229). Update the module docstring (s/frontend/house/ where it means the served port).
2. Update `tests/config/test_cors_registry.py` (~4 assertions: `8080→8001`, `8090→8002`, the `without_localhost_alts` sorted list, the `core_migration` `frontend_port→backend_port`).
3. Update `tests/config/test_per_product_cors_sentinel.py` (each product's `@registry:own` now resolves its house port — align the per-product assertions).
4. (Optional) a dev-only localhost HOUSE-port band fallback in `derive` for the container case (no `start.sh`) so `@registry:all` works without the explicit `.env` band — gated to non-deploy (no `PRODUCT_URL_*`). Decide vs. keeping the `.env`-band approach (simpler, already shipped). If added, it changes the "alts-only" baseline → ~4 more test updates.

## 6. Success criteria
- `derive_cors_origins(@registry:all)` with a readable `start.sh` yields each product's **house** localhost origin (8001/8011/...), not the frontend port.
- `pytest seed/lib/backend/tests/config/` green.
- No change to container dev (`.env` band) or prod (`PRODUCT_URL_*`) behavior.
