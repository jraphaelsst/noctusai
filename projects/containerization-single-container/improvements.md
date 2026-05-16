# Improvements — Containerization → single-container-per-product — Project Document

> **Auto-generated** from `PROJECT.md` by `python mcp/noctusai/cli.py --improvements <plan.md>`. Regenerated every time a phase is ticked complete. Do not edit by hand.

> This file captures **improvement opportunities discovered while implementing each phase** — things future iterations of *this* phase should consider. It is NOT a preview of upcoming phase tasks (those live in the plan itself). When a phase is refactored or revisited, open this file first.

**Plan:** `PROJECT.md`
**Plan status:** Design locked → Phase 0 ready
**Completed phases:** 3 of 7.
**Phases with recorded improvements:** 3 of 3 completed.

## Improvements by phase

### Phase 0 — Audit (read actual files, confirm assumptions)

none — read-only audit phase; discoveries logged in §11 + `findings.md`.

### Phase 1 — Seed factory `serve_spa` seam

- *Asset-vs-route heuristic = filename suffix.* A client route whose last segment contains a dot (e.g. `/reports/2024.q1`) would be misclassified as an asset → 404 instead of `index.html`. Acceptable now (rare in our products' route shapes). **Deferred → Phase 2**: when wiring real products, eyeball each product's router paths; if any dotted client route exists, switch the heuristic to an explicit assets-prefix check (`/assets/`, `/static/`) instead of suffix.
- *`SERVE_SPA_DIR` is un-namespaced.* Other env in the platform uses no consistent prefix either, so left as-is for discoverability; noting in case a future env-var audit standardizes (→ accept-with-rationale if it recurs).
- *Local starlette imports inside `_mount_spa`.* Intentional — only single-container products pay the import; keeps the seam zero-cost for `native`/two-container. Applied as-is (rationale recorded here).
- No formal proposal filed — items are observations + one Phase-2-scoped deferral with a named destination; apply-inline-then-delete default (this block + §11 = audit trail).

### Phase 2 — Seed-level single-container images (base + thin inheritors)

- *Inert `||"http://localhost:80XX"` fallback strings still in bundles* (dead — truthy `window.location.origin` LHS). Root: scattered `import.meta.env.VITE_BACKEND_API_URL || '...'` idiom (N≫3). **Deferred → follow-up project candidate `frontend-api-base-dry`** (route consumers through the single `env.BACKEND_API_URL`).
- *`propagate-dockerfiles.sh --check` not yet pre-commit-wired* — thin files can drift from the canonical. **Deferred → Phase 6** (beside `verify-kb-sync.sh`).
- *Base image tag is hardcoded `:dev`* in thin Dockerfiles + build script. Fine for local/dev; a real registry tag strategy (per-product GHCR §11a KB) for the BASE image is a **Phase 6 / deploy concern** — noted, named.
- *`scripts/build-base-images.sh` not yet called by start.sh* — wired in **Phase 5** (explicit dependency, not silent).
- [x] **Same-origin contract:** `vite.config.factory.ts` — `process.env.VITE_SAME_ORIGIN==='1'` ⇒ inject `VITE_BACKEND_API_URL` `define` as the **raw expression `window.location.origin`** (not JSON-stringified). `seed/lib/frontend/src/env.ts` — `BACKEND_API_URL` getter reads the define-rewritten **literal** `import.meta.env.VITE_BACKEND_API_URL` (+ `/// <reference types="vite/client" />`). **Zero product-file changes**; `tsc --noEmit` green. Simpler than the planned dual-flag (no `VITE_SAME_ORIGIN` define needed).
- [x] Rewrote `products/seed/backend/Dockerfile` → 4-stage (`frontend-build` w/ `VITE_SAME_ORIGIN=1` · `frontend-dev` · `builder` · `runtime` copies dist + `ENV SERVE_SPA_DIR` + uvicorn serves API+SPA on one port).
- [x] **0 per-product backend code** — seed `app.main` unchanged; `create_product_app` reads `SERVE_SPA_DIR` env (Phase 1 seam) set by the Dockerfile.
- [x] `scripts/propagate-dockerfiles.sh` (targeted subst, bash-3 safe, `--check` mode) → regenerated 10 product backend Dockerfiles. `imobi-scheduling` stale shape **fixed** (now port 8011 / own paths); `dev-team` `/opt/dev_team` extras preserved; core/erp VITE args spliced.
- [x] **Verified:** real `VITE_SAME_ORIGIN=1 npm run build` of seed SPA → bundle contains `window.location.origin||"http://localhost:8004"` (truthy LHS ⇒ localhost fallback is dead/inert; API base = runtime origin, tunnel-correct). No live `http://localhost` API base leaks.
- [x] **Re-sequenced:** frontend `Dockerfile` + `nginx.conf.template` deletion moved to **Phase 3** (atomic with the compose rewrite that removes the `dockerfile:` refs — deleting now = broken intermediate, violates no-incomplete-commits). Logged §11.

**Improvements:**
- *Inert `||"http://localhost:80XX"` fallback strings remain in bundles* (dead bytes — truthy `window.location.origin` LHS). Root cause: scattered `import.meta.env.VITE_BACKEND_API_URL || '...'` idiom across products instead of consuming `env.BACKEND_API_URL`. Harmless now. **Deferred → follow-up project candidate `frontend-api-base-dry`** (route all consumers through the single seed accessor; N≫3 recurrence — formalize). Named destination, not silent.
- *`scripts/propagate-dockerfiles.sh --check` not yet in pre-commit* — per-product backend Dockerfiles can silently drift from canonical. **Deferred → Phase 6** (wire into pre-commit beside `verify-kb-sync.sh`).
- *seed canonical keeps `{{BACKEND_*_EXTRA}}` marker comments* — harmless `#` lines when seed builds standalone; they're the template seams. Accept-with-rationale (spine-file template markers; cheap; documented here).
- *`frontend-dev` `EXPOSE 5273` is a placeholder port* — real dev-sidecar ports defined in **Phase 4**.

## Deferred items (from §4 Out of scope)

_Work deliberately scoped out of this plan. Track as candidates for future plans, not as improvements to existing phases._

- Production deploy pipeline / GHCR publishing changes — per-product registry strategy stays as locked (§11a KB); not touched here.
- Horizontal frontend/backend independent scaling — single-tenant dev fleet; irrelevant now (catalogued accept-with-rationale if it ever matters).
- `dev-team`'s extra `/opt/dev_team` editable install — preserved as-is in its Dockerfile; audited in Phase 0, not redesigned.

## Open questions still blocking

- **Same-origin VITE rewiring depth** — does dropping cross-origin break any product whose frontend hardcodes an absolute API URL? — answer in Phase 0 (audit `vite.config.factory.ts` + per-product `VITE_*`).
- **Two root files vs compose `profiles`/`-p` for the project split** — settle in Phase 3 (lean: separate `-p noctusai-products` / `-p noctusai-infra` invocations from `start.sh`; `include:` stays within products).
- **`imobi-scheduling` override absence** — fold into the standardized pattern (Phase 3/4) or accept-with-rationale? Lean: fold (standardization is the project's point).
