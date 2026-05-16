# Improvements — Containerization → single-container-per-product — Project Document

> **Auto-generated** from `PROJECT.md` by `python mcp/noctusai/cli.py --improvements <plan.md>`. Regenerated every time a phase is ticked complete. Do not edit by hand.

> This file captures **improvement opportunities discovered while implementing each phase** — things future iterations of *this* phase should consider. It is NOT a preview of upcoming phase tasks (those live in the plan itself). When a phase is refactored or revisited, open this file first.

**Plan:** `PROJECT.md`
**Plan status:** Design locked → Phase 0 ready
**Completed phases:** 2 of 7.
**Phases with recorded improvements:** 2 of 2 completed.

## Improvements by phase

### Phase 0 — Audit (read actual files, confirm assumptions)

none — read-only audit phase; discoveries logged in §11 + `findings.md`.

### Phase 1 — Seed factory `serve_spa` seam

- *Asset-vs-route heuristic = filename suffix.* A client route whose last segment contains a dot (e.g. `/reports/2024.q1`) would be misclassified as an asset → 404 instead of `index.html`. Acceptable now (rare in our products' route shapes). **Deferred → Phase 2**: when wiring real products, eyeball each product's router paths; if any dotted client route exists, switch the heuristic to an explicit assets-prefix check (`/assets/`, `/static/`) instead of suffix.
- *`SERVE_SPA_DIR` is un-namespaced.* Other env in the platform uses no consistent prefix either, so left as-is for discoverability; noting in case a future env-var audit standardizes (→ accept-with-rationale if it recurs).
- *Local starlette imports inside `_mount_spa`.* Intentional — only single-container products pay the import; keeps the seam zero-cost for `native`/two-container. Applied as-is (rationale recorded here).
- No formal proposal filed — items are observations + one Phase-2-scoped deferral with a named destination; apply-inline-then-delete default (this block + §11 = audit trail).

## Deferred items (from §4 Out of scope)

_Work deliberately scoped out of this plan. Track as candidates for future plans, not as improvements to existing phases._

- Production deploy pipeline / GHCR publishing changes — per-product registry strategy stays as locked (§11a KB); not touched here.
- Horizontal frontend/backend independent scaling — single-tenant dev fleet; irrelevant now (catalogued accept-with-rationale if it ever matters).
- `dev-team`'s extra `/opt/dev_team` editable install — preserved as-is in its Dockerfile; audited in Phase 0, not redesigned.

## Open questions still blocking

- **Same-origin VITE rewiring depth** — does dropping cross-origin break any product whose frontend hardcodes an absolute API URL? — answer in Phase 0 (audit `vite.config.factory.ts` + per-product `VITE_*`).
- **Two root files vs compose `profiles`/`-p` for the project split** — settle in Phase 3 (lean: separate `-p noctusai-products` / `-p noctusai-infra` invocations from `start.sh`; `include:` stays within products).
- **`imobi-scheduling` override absence** — fold into the standardized pattern (Phase 3/4) or accept-with-rationale? Lean: fold (standardization is the project's point).
