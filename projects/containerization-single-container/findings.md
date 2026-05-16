# findings.md — containerization-single-container

Curated knowledge from execution. Five categories: slips · errors · mistakes · lessons · interesting findings.

## Interesting findings

- **Factory router order is SPA-mount-friendly.** `create_product_app()` registers std routers (9) → product routers (10) → health `/_*` (11), no catch-all. A `serve_spa` StaticFiles + SPA fallback slots cleanly as step 12 after health; `/_*` prefix is already reserved so no path conflict. (Phase 0)
- **`VITE_BACKEND_API_URL` is the only same-origin pivot.** `vite.config.factory.ts` injects it as absolute `http://localhost:${backendPort}` via `define:`. Single-container is same-origin so the prod build must emit empty/relative. Per-product composes only pass `VITE_CORE_URL`/`VITE_CORE_API_URL` (cross-product SSO — unaffected). The blast radius of the same-origin switch is one `define` in the factory. (Phase 0)
- **Backend Dockerfiles are mechanically uniform; frontend ones are not — but it doesn't matter.** 9/10 backend Dockerfiles are Δ=15 slug+port copies; the single-container Dockerfile retires the frontend Dockerfile entirely, so frontend-Dockerfile drift (Δ=57–76) never needs reconciling. The consolidation *erases* the least-uniform surface.

## Lessons

- **`imobi-scheduling` is unpatterned debt.** Its compose still carries `seed-backend/frontend/tunnel` service names + `noctus-seed-*` container names with imobi ports, no override, backend Dockerfile Δ=77. It was scaffolded by copy and never slug-substituted. Standardization here is corrective, not just cosmetic.

## Lessons (cont.)

- **`caplog` can't see seed-logged WARNINGs.** `create_product_app()` calls `configure_logging()` which reconfigures handlers/propagation, so pytest's `caplog` never receives `noctusai_seed.app` records (they appear in captured stdout via the app's own handler). Don't assert fail-soft via log capture in seed-factory tests — assert the *observable* contract (no crash + API still 200 + nothing mounted). Asserting the log would require monkeypatching our logging config = forbidden. (Phase 1)

## Slips / errors / mistakes

- **Branch switch blocked by parallel-agent uncommitted work** (`LGPD-WARNINGS.md` et al). Did NOT stash/sweep others' work (authorship + collision discipline). Resolution path: split `containerization-single-container` off `origin/main` and cherry-pick own commits at phase-commit time. Not a methodology gap — the safety net (refusing to disturb parallel work) worked as intended.
