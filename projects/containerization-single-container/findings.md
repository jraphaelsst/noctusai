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

## Interesting findings (cont.)

- **Vite `define` raw-expression injection = tunnel-correct same-origin with zero consumer changes.** Setting the `import.meta.env.VITE_BACKEND_API_URL` define to the *un-stringified* text `window.location.origin` makes every literal reference resolve to the runtime origin — correct under localhost, *.trycloudflare.com tunnels and any deploy host. The scattered `|| 'http://localhost:80XX'` fallbacks become inert (truthy LHS). Bracket access (`env['X']`) is NOT define-rewritten — only the literal member expression is; that's why `env.ts` needed the one-line switch to the literal. (Phase 2)
- **The seed-faithful Docker pattern is base-image + thin inheritors, not copies and not a god-file.** `FROM noctus-seed-*-base` is the exact Docker analog of `create_product_app()`'s inherit-and-extend: common heavy layers in one base, product specificities in a ~70-line product file via a named seam (`{{BACKEND_EXTRA}}` splice for dev-team). Eliminates the propagated-copy drift class AND avoids per-product `if` conditionals in a shared file. Also caches the heavy layer once instead of 10×. (Phase 2 pivot — user-driven)

## Slips / errors / mistakes

- **Branch switch blocked by parallel-agent uncommitted work** (`LGPD-WARNINGS.md` et al). Did NOT stash/sweep others' work (authorship + collision discipline). Resolution path: split `containerization-single-container` off `origin/main` and cherry-pick own commits at phase-commit time. Not a methodology gap — the safety net (refusing to disturb parallel work) worked as intended.
