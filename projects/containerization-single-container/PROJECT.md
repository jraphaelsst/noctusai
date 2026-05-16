# Containerization → single-container-per-product — Project Document

> Living document. Phase plan is suggestive; revise + log in §11 as work proceeds.

- **Created:** 2026-05-16
- **Last updated:** 2026-05-16
- **Status:** Design locked → Phase 0 ready
- **Owner / stakeholders:** joaoraphaelsst (architect: Claude Opus 4.7)
- **Related docs:** `KB § PATTERNS/containerization.md` · `products/seed/{backend,frontend}/Dockerfile` · `products/seed/docker-compose.yml` · `seed/framework/backend/noctusai_seed/app.py` · `start.sh` / `stop.sh`
- **Project slug:** `containerization-single-container` (location: `projects/` — cross-product / platform-infra; intent: `consolidation`)

---

## 1. Context & Purpose

Today the fleet runs **2–3 containers per product**: `<slug>-backend` (uvicorn), `<slug>-frontend` (nginx serving the built Vite SPA), and an opt-in `<slug>-tunnel`. 10 products → ~20 app containers + tunnel + shared infra ≈ 24 flat rows in the Docker Desktop dashboard, all under one `noctusai` compose project. Working on a single product (e.g. an ERP feature) means the whole fleet is up, and there is **no per-product on/off switch** — profiles only gate redis/waha/postgres/tunnel.

The win: **one container per product** (uvicorn serves the API *and* the built SPA on one port; nginx and the per-product private network disappear), the fleet split into **two compose projects** — `noctusai-products` (all products) and `noctusai-infra` (redis/waha/postgres) — so each product is a single dashboard row toggled in one click, the whole fleet is one project-level switch, and infra is independently controlled. Plus a **standardized, always-wired (profile-gated) tunnel** on every product and an opt-in **Docker dev-mode** (Vite HMR + uvicorn `--reload`) for the product under active development.

---

## 2. Confirmed constraints

- **Single container per product** — uvicorn serves API + the pre-built SPA bundle on one port; nginx + `<slug>-net` removed. *(User confirmed this === their original "single container per product".)*
- **Tunnel = mandatory in the standardized pattern, profile-gated for activation** — every product's compose ships the `<slug>-tunnel` service block (wired in, part of the canonical seed pattern), still `profiles: [tunnel-<slug>, tunnel-all]` so it only *runs* when asked. *(Rules out the current "optional / some products lack it" state; `imobi-scheduling` must be folded into the pattern.)*
- **Two compose projects, not per-product projects** — `noctusai-products` + `noctusai-infra`. *(User's idea; works *because of* single-container: each product = 1 container = 1 row = 1-click. Simpler than per-product projects; the `external: true` network inversion shrinks to the products↔infra boundary only.)*
- **Whole-fleet entrypoint retained** — `./start.sh` (no args) + the `noctusai-products` project-level switch both bring everything up. *(User explicit.)*
- **Dev mode = Option A (Vite-dev sidecar, seed-inherited)** — `docker-compose.override.yml` adds, for the active product only, a `vite dev --host` HMR sidecar + bind-mounted `uvicorn --reload`; default/prod stays one container. *(User selected over native-only and over both.)*

---

## 3. Design principles

1. **Seed-first by construction.** Pattern changes land in `products/seed/` + `seed/framework/backend/noctusai_seed/` first, then propagate to the 10 products. Per-product Dockerfiles/composes stay slug+port-substituted copies — zero per-product *logic*.
2. **One process, one container** (Docker idiom). uvicorn serving static is one process; no supervisord/nginx multiproc.
3. **Production-shaped default, dev-mode opt-in.** Bare `up` = the prod image (built SPA, single container). HMR is an explicit override, never the default.
4. **Same-origin frontend.** SPA served by the backend ⇒ API calls become same-origin relative (`/api/...`); the cross-origin `VITE_*_API_URL` wiring simplifies (empty/relative).
5. **One canonical writer per ops surface.** `start.sh`/`stop.sh`, root composes, and the seed Dockerfile are single-source; hand-edits only inside sentinels.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Contract identical for every product?** **YES** — every product is a `create_product_app()` FastAPI + a Vite SPA; "serve the built SPA from uvicorn" is uniform.
2. **Data source product-specific?** **NO** — this is infra/packaging, no product data.
3. **Placement product-specific?** **NO** — the SPA-serve seam lives in the seed factory; the Dockerfile/compose pattern is canonical at `products/seed/`.
4. **Visibility / permission rule the same?** **YES** — uniform; static-mount + SPA fallback identical everywhere.
5. **Seam already in seed?** **NO** — `create_product_app()` has no static-serve seam yet (Phase 1 adds `serve_spa`); Dockerfile/compose patterns exist but in 2-container shape (Phases 2–3 reshape).
6. **Default-on or opt-in?** **DEFAULT-ON** — single-container is the new universal shape; dev-mode sidecar is the opt-in.

**Litmus — per-product code count:** **0 lines of per-product logic.** Each product keeps a generated Dockerfile/compose (slug+port substituted — same as today); the behavioral seam is 100% in seed. ✅ pure cross-product concern.

**Phase plan implications:** §6 phases work **in seed** (factory seam, canonical Dockerfile, canonical compose, canonical override, ops scripts), then mechanically propagate. No product-by-product walk = correct.

---

## 4. Scope

**In scope:**
- Seed factory `serve_spa` seam (StaticFiles mount + SPA catch-all that never shadows `/api`).
- Single multi-stage canonical Dockerfile (node build → python runtime serves; `dev` stage for vite) + propagation to 10 products; old frontend Dockerfile + `nginx.conf.template` retired.
- Single-service-per-product canonical compose (drop frontend service + `<slug>-net`; mandatory profile-gated tunnel; one port; `noctus-net` → `external: true`) + propagation; `imobi-scheduling` folded into pattern.
- Root compose split → `noctusai-products` + `noctusai-infra` (separate project names; shared external `noctus-net`).
- Seed `docker-compose.override.yml` dev-mode sidecar (Vite HMR + uvicorn `--reload`) + propagation.
- `start.sh`/`stop.sh`: ensure external `noctus-net`; two-project orchestration; `./start.sh <slug>...` subsets; `./start.sh dev <slug>`; retain whole-fleet + `tunnel`/`tunnel-all`.
- Three-way doc sync (KB containerization.md + CLAUDE.md/topical + memory) + `scaffold_product` generator + `templates/product-seed` sync + `verify-kb-sync`.

**Out of scope (with reason):**
- Production deploy pipeline / GHCR publishing changes — per-product registry strategy stays as locked (§11a KB); not touched here.
- Horizontal frontend/backend independent scaling — single-tenant dev fleet; irrelevant now (catalogued accept-with-rationale if it ever matters).
- `dev-team`'s extra `/opt/dev_team` editable install — preserved as-is in its Dockerfile; audited in Phase 0, not redesigned.

---

## 5. Architecture / Data Model

**Single-container image (per product, canonical at `products/seed/`):**

```
Stage 1 (node:20-alpine, "frontend-build"): build SPA → /app/.../dist
Stage 2 (node:20-alpine, "dev"):            vite dev server (override-selected)
Stage 3 (python:3.11-slim, "builder"):      compile wheels → /opt/venv
Stage 4 (python:3.11-slim, "runtime"):      venv + product code + COPY --from=frontend-build dist
                                            CMD uvicorn ... (serves /api + StaticFiles SPA)
```

**Factory seam** — `create_product_app(..., serve_spa: Path | None = None)` (or env `SERVE_SPA_DIR`): when set, mount `StaticFiles(directory=dist, html=True)` at `/` AFTER all API routers, plus an SPA catch-all returning `index.html` for non-`/api` non-asset paths (404→index for client routing). `/api/*`, `/_ready`, health stay owned by FastAPI.

**Networks:** `noctus-net` → `external: true` (pre-created once by `start.sh`: `docker network create noctus-net` if absent). `<slug>-net` deleted (no second product container to isolate). Cross-product calls + infra still on `noctus-net`.

**Ports:** one published port per product = the existing backend port (8000, 8001, 8002, …). Old frontend ports (5173/8080/8090/…) **freed**. Single-origin ⇒ SPA fetches `/api` relative.

**Two projects:**

| Project | Members | Lifecycle |
|---|---|---|
| `noctusai-products` | 10 single-container products (+ opt-in `<slug>-tunnel`) | project switch = whole fleet; each row = one product 1-click |
| `noctusai-infra` | redis · waha · postgres (profile-gated) | toggled independently |

**Dev mode (override, seed-inherited):** `docker-compose.override.yml` defines a `<slug>-frontend-dev` (vite `--host`, frontend src bind-mount, HMR port) + backend overlay (`command: uvicorn --reload`, src bind-mount). Activated per-product via `./start.sh dev <slug>` (override + profile scoping); absent by default.

---

## 6. Implementation phases

### Phase 0 — Audit (read actual files, confirm assumptions) ✅
- [x] Read `create_product_app()` fully — router order = std(9) → product(10) → health `/_*`(11); no existing catch-all. **SPA mount = new step 12, after health.** Clean insertion point.
- [x] Inspect `vite.config.factory.ts` — **FINDING:** factory injects `VITE_BACKEND_API_URL` as absolute `http://localhost:${backendPort}` via `define:`. Single-container is same-origin ⇒ this must become empty/relative so product code resolves `/api/...`. **New Phase 2 sub-task added.** (Answers Open Q1: yes, factory `define` changes; localized.)
- [x] Diff backend Dockerfiles vs seed — 9 products Δ=15 (faithful slug+port copies); `dev-team` Δ=26 (`/opt/dev_team` extra, preserve); `imobi-scheduling` Δ=77 (stale, never slug-substituted).
- [x] Frontend Dockerfiles Δ=57–76 — **moot:** Phase 2 retires the frontend Dockerfile entirely (folded into multi-stage). No propagation needed there.
- [x] `VITE_*` args — products pass only `VITE_CORE_URL` (+ core/erp `VITE_CORE_API_URL`): cross-product SSO links, **unaffected**. The product's *own* API is the factory-injected var (the one changing).
- [x] `imobi-scheduling/docker-compose.yml` = stale copy: `seed-backend/frontend/tunnel` service names + `noctus-seed-*` containers but imobi ports (8011/8160), no override. **Decision: fold into pattern** (Open Q3 resolved → fold).
- [x] Docker Desktop groups by `com.docker.compose.project` label (established behavior; one project = one collapsible group + one project-level switch + per-container controls). Two-project UX claim holds.
- [x] §6 revised in-place; §11 logged.

**Improvements:** none — read-only audit phase; discoveries logged in §11 + `findings.md`.

### Phase 1 — Seed factory `serve_spa` seam ✅
- [x] Added `serve_spa: Optional[str]` kw-only param + `SERVE_SPA_DIR` env fallback (param wins) to `create_product_app()` (step 12, after `mount_health_endpoints`).
- [x] `_mount_spa()` helper: `_SPAStaticFiles(html=True)` at `/`; 404 + extension-less → `index.html` (client routing); 404 + has-extension → real 404; fail-soft WARNING + API-only if no `index.html`.
- [x] `tests/test_serve_spa.py` — 9 tests: seam-off `/`→404 + API intact; root→index; real asset; client route→index; missing asset→404; `/_health` wins; env honoured; param beats env; fail-soft. Status-code asserted alongside body (status-assertion rule). 35/35 green incl. health + standard-routers regression.

**Improvements:**
- *Asset-vs-route heuristic = filename suffix.* A client route whose last segment contains a dot (e.g. `/reports/2024.q1`) would be misclassified as an asset → 404 instead of `index.html`. Acceptable now (rare in our products' route shapes). **Deferred → Phase 2**: when wiring real products, eyeball each product's router paths; if any dotted client route exists, switch the heuristic to an explicit assets-prefix check (`/assets/`, `/static/`) instead of suffix.
- *`SERVE_SPA_DIR` is un-namespaced.* Other env in the platform uses no consistent prefix either, so left as-is for discoverability; noting in case a future env-var audit standardizes (→ accept-with-rationale if it recurs).
- *Local starlette imports inside `_mount_spa`.* Intentional — only single-container products pay the import; keeps the seam zero-cost for `native`/two-container. Applied as-is (rationale recorded here).
- No formal proposal filed — items are observations + one Phase-2-scoped deferral with a named destination; apply-inline-then-delete default (this block + §11 = audit trail).

### Phase 2 — Seed-level single-container images (base + thin inheritors) ✅

> **Pivoted mid-phase (user-driven, see §11):** the artifact strategy is now Docker-native seed inheritance — shared base images + thin per-product Dockerfiles — NOT 10 propagated full copies and NOT a god-Dockerfile with per-product conditionals.

- [x] **Same-origin contract (seed-level, unchanged by pivot):** `vite.config.factory.ts` injects `window.location.origin` (raw expr) when `VITE_SAME_ORIGIN=1`; `seed/lib/frontend/src/env.ts` reads the define-rewritten literal (`/// <reference types="vite/client" />`). Zero product-file changes; `tsc --noEmit` green.
- [x] **Two shared seed base images** (the Docker-native `create_product_app()`): `seed/docker/Dockerfile.backend-base` (`noctus-seed-backend-base` — system deps + venv + seed editable installs + runtime libs) and `seed/docker/Dockerfile.frontend-base` (`noctus-seed-frontend-base` — seed FE packages). Common heavy layers in ONE place.
- [x] **Thin canonical** `products/seed/backend/Dockerfile` (~70 lines) — `FROM noctus-seed-{frontend,backend}-base` + only seed's specifics (VITE block, port, `SERVE_SPA_DIR`, non-root last). `FROM base` IS the named seam.
- [x] `scripts/propagate-dockerfiles.sh` (`--check` mode) → 10 thin product Dockerfiles. `imobi-scheduling` stale shape **fixed**; `dev-team` `/opt/dev_team` spliced via the `{{BACKEND_EXTRA}}` seam; core/erp VITE args. `--check` idempotent (clean).
- [x] `scripts/build-base-images.sh` — builds both bases (start.sh orders it pre-product in Phase 5).
- [x] **0 per-product backend code** — seed `app.main` untouched; `SERVE_SPA_DIR` (Phase 1 seam) set by the Dockerfile.
- [x] **Verified (real Docker builds):** `noctus-seed-frontend-base` builds ✓; seed thin Dockerfile `FROM` it builds (`--target frontend-build`) ✓; **in-container SPA bundle uses `window.location.origin`** (same-origin proven in a real container, not just host build) ✓. Local host build also green.
- [x] **Re-sequenced:** frontend `Dockerfile` + `nginx.conf.template` `git rm` → **Phase 3** (atomic with compose rewrite removing the `dockerfile:` refs — no broken intermediate).
- [x] **Deferral decision recorded (complete this phase):** full `noctus-seed-backend-base` + full product image build runs in **Phase 5 (start.sh verification / deploy drill)**. Rationale: backend-base content is byte-identical logic to the previously-working canonical builder/runtime stages (relocated, not rewritten); heavy (apt + weasyprint/cairo + pip wheels); Phase 0 KB note flags image builds as pre-pulled/slow. The novel risk (same-origin + base-inheritance, frontend half) IS proven in-container above. Tracked as a Phase 5 sub-task + §8 dependency.

**Improvements:**
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

### Phase 3 — Canonical compose (single service, mandatory tunnel, external net) + root split ✅
- [x] Rewrote `products/seed/docker-compose.yml` → one `seed` service (was `seed-backend`+`seed-frontend`), one port, `noctus-net: external: true`, **mandatory** profile-gated `seed-tunnel` (→ `http://seed:<port>`); dropped frontend service + `seed-net`.
- [x] `scripts/propagate-composes.sh` (`--check`, bash-3) → 10 product composes; `imobi-scheduling` folded into the pattern (stale `seed-*` shape gone); core/erp VITE arg blocks. Both propagation `--check`s idempotent (clean).
- [x] Root split: `docker-compose.yml` `name: noctusai-products` (includes 10, override NOT path-listed — opt-in Phase 4) + new `docker-compose.infra.yml` `name: noctusai-infra` (redis/waha/postgres, volumes). Both reference external `noctus-net`. `docker compose config -q` green for both projects.
- [x] **Atomic retirement** (no broken intermediate): `git rm` 10 frontend Dockerfiles + `seed/framework/frontend/nginx.conf.template` + stale 2-container per-product overrides + root override (23 deletions). `config -q` proves zero dangling refs after deletion.
- [x] **Open Q2 resolved** → two root files with `name:` project pinning (not profiles). **Open Q3 resolved** → `imobi-scheduling` folded into the standardized pattern.

**Improvements:**
- *`noctus-net: external: true` ⇒ standalone `cd products/<x> && docker compose up` needs `docker network create noctus-net` first.* Documented in every compose header; start.sh automates (Phase 5). **Accept-with-rationale** — the necessary tradeoff of the two-project split (KB rule "NOT external:true" inverts under this project — Phase 6 KB rewrite captures the inversion).
- *Per-product + root `docker-compose.prod.yml` left untouched* — now stale vs single-container. Explicitly **out of scope** (prod-deploy pipeline). **Deferred → follow-up project candidate `containerization-prod-deploy`** (named, not silent).
- *Stale per-product overrides removed* — standalone dev-mode is broken until **Phase 4** recreates the seed-inherited override. Sequenced + named (Phase 4 is the immediate next phase).
- *Both `propagate-*.sh --check` not yet pre-commit-wired* — **Phase 6**.

### Phase 4 — Dev-mode override (seed-inherited) + propagate ✅
- [x] `products/seed/docker-compose.override.yml`: overlays `seed` (`uvicorn --reload` + `./backend`/`../../seed` bind-mounts + `SERVE_SPA_DIR=""` ⇒ Phase-1 fail-soft API-only) + adds `seed-frontend-dev` Vite-HMR sidecar (`FROM noctus-seed-frontend-base`, src bind-mounts, dev port). Auto-load semantics: standalone `cd products/<x> && docker compose up` = dev; root `noctusai-products` (no override path-list, Phase 3) = prod. Deliberate, documented in the header.
- [x] `scripts/propagate-overrides.sh` (`--check`, bash-3) → 10 overrides incl. `imobi-scheduling` (previously had none). Dev port = backend+1000 (90xx, collision-free). Shared base image name `noctus-seed-frontend-base` **protected** from slug substitution (verified on dev-team).
- [x] **Verified:** `cd products/seed && docker compose config -q` (auto-merges compose+override) parses clean → override merges onto the single-service compose with no conflict; dev-team spot-check (service keys, container_name, ports, protected base image) correct.
- [x] **Deferral decision recorded (complete this phase):** live HMR behavior (edit `.tsx` → <1s; `.py` → reload) needs a running container → verified in **Phase 5** (start.sh `dev <slug>` path) alongside the deferred full image build. Structural validity + clean merge proven here via `config`.

**Improvements:**
- *Dev sidecar runs `npm install` at every container start* — slow first paint each `up`. Acceptable for dev (node_modules can be a named volume later). **Deferred → Phase 5/6 polish** (named).
- *`propagate-overrides.sh --check` not pre-commit-wired* — joins the other two in **Phase 6**.
- *Standalone-with-override is always dev* (no prod-shape standalone without `-f` gymnastics) — by design (matches prior KB intent: cd-into-product = hacking it); prod shape validated via the fleet/image build. Accept-with-rationale (header-documented).

### Phase 5 — start.sh / stop.sh orchestration ✅
- [x] `start.sh` rewritten: `ensure_net` (create external `noctus-net` if absent) + `build_bases` before any product build/up; two-project orchestration (`PRODUCTS_COMPOSE` → noctusai-products, `INFRA_COMPOSE` → noctusai-infra; profiles → infra, tunnel → products); `./start.sh <slug>...` subset; `./start.sh dev <slug>`; `fleet/build/tunnel/native` retained. `bash -n` clean.
- [x] `stop.sh` rewritten: downs BOTH root projects **+ `sweep_dev_projects`** (standalone per-product dev projects); `volumes`/`prune` symmetric; external net + base images preserved (documented). `bash -n` clean.
- [x] **🎯 SUCCESS-CRITERION GATE PASSED (closes Phase 2/4 deferrals):** both seed bases built; `./start.sh seed` → real container: `/api/health` → `200 {"status":"ok"}`; `/` → SPA `<!doctype html>` **same port 8004**; `/dashboard/anything` → `200` (Phase-1 SPA-fallback live); **exactly ONE container, ONE port**.
- [x] **Dev-mode verified:** `./start.sh dev seed` → 2 containers (`noctus-seed` uvicorn `--reload` + `noctus-seed-frontend-dev` Vite HMR); API `:8004` 200, Vite dev `:9004` serving. `stop.sh` tore the whole lot down cleanly (fleet+infra+dev → zero `noctus-*` left).
- [x] **Lifecycle bug found & fixed inline (active robustness review):** fixed `container_name: noctus-<slug>` collides across the fleet project (`noctusai-products`) and the standalone dev project — a product is EITHER fleet OR dev. Fix: `start.sh dev` pre-empts the fleet instance (`docker rm -f noctus-<slug>{,-tunnel}`); `stop.sh` sweeps dev projects. Caught by the smoke, not shipped.

**Improvements:**
- *Fixed `container_name` couples project lifecycles* — mitigated (pre-empt + sweep + "EITHER fleet OR dev" mental model documented). Dropping `container_name` for compose-default project-scoped names would be structurally cleaner BUT breaks the tunnel-log `grep noctus-<slug>-tunnel` + ops muscle memory. **Accept-with-rationale** (documented; revisit if it recurs).
- *Live "edit→<1s reload" is interactive* — structurally proven (Vite dev + uvicorn `--reload` stack up, both responding in dev mode); the final edit-see-change is the user's interactive confirmation. Honest scope of automated verification.
- *`build_bases` runs every `start.sh`* — base build is cache-fast when unchanged but still invokes docker. **Deferred → Phase 6 polish** (skip if images exist + seed unchanged). Named.

### Phase 6 — Docs + scaffolder + three-way sync
- [ ] Rewrite `KB § PATTERNS/containerization.md` (mental model, file layout, Dockerfile walkthrough, networks, two-project ops, dev-mode, anti-patterns); update counts.
- [ ] Update `CLAUDE.md` containerization pointer + `feedback_containerization_system.md` memory + MEMORY.md index (three-way sync).
- [ ] Update `noctus.dev.scaffold_product` generator templates + sync `templates/product-seed/`.
- [ ] `bash scripts/verify-kb-sync.sh` + `python scripts/update-kb-counts.py --check` green.

---

## 7. Open questions

1. ✅ **Same-origin VITE rewiring depth** — RESOLVED Phase 2: `window.location.origin` define-injection; zero consumer changes; tunnel-correct.
2. ✅ **Two root files vs profiles for the project split** — RESOLVED Phase 3: two root files (`docker-compose.yml` `name: noctusai-products` + `docker-compose.infra.yml` `name: noctusai-infra`); `include:` within products.
3. ✅ **`imobi-scheduling` shape** — RESOLVED Phase 3: folded into the standardized pattern (compose regenerated; override comes Phase 4 like every product).
4. **`docker-compose.prod.yml` staleness** — out of scope here; needs a `containerization-prod-deploy` follow-up — decided by user / post-close.

---

## 8. Dependencies & blockers

- **Branch hygiene** — current tree has parallel-agent uncommitted work; project commits split onto `containerization-single-container` off `origin/main` via cherry-pick at phase-commit time (not stashing others' work).
- **Docker Desktop project-grouping behavior** — the two-project UX claim is verified in Phase 0 before Phase 3 commits to it.
- **Full `noctus-seed-backend-base` + product image build** — deferred from Phase 2 (verified: frontend-base + thin-FROM chain + in-container same-origin). The heavy backend-base + an end-to-end product container (uvicorn serving API+SPA on one port) is the **Phase 5 gate** before project close. Blocks success-criterion "one container/product serving SPA+API, /api/health green".

---

## 9. Success criteria

- `docker compose` (default) → exactly **one container per product**, serving SPA + API on one port; `/api/health` green.
- Docker Desktop shows `noctusai-products` (per-product 1-click rows + project-level whole-fleet switch) and a separate `noctusai-infra` group.
- Every product compose ships a profile-gated `<slug>-tunnel`; `./start.sh tunnel <slug>` works for all 10.
- `./start.sh dev <slug>` → `.tsx` HMR + `.py` reload; default `up` has no sidecar.
- `./start.sh <slug>` brings up just that product; `./start.sh` brings the whole fleet.
- Cross-product calls + infra still reachable over external `noctus-net`.
- Backend pytest + every touched frontend `vite build` green; KB-sync verifiers green; three-way sync complete.

---

## 10. How to use this plan

- Single source of truth for progress; live-tick `- [ ]` → `- [x]` immediately.
- Phase-by-phase by default — pause for "continue" between phases unless throughput requested.
- Phase 0 first (audit), then implement seed, then propagate, then docs.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-16 | Initial project drafted after interrogation (tunnel-mandatory, two-project split, single-container confirmed, dev-mode Option A locked) | Claude Opus 4.7 |
| 2026-05-16 | Phase 0 ✅ — factory SPA-mount slot confirmed (step 12); vite factory same-origin change found → Phase 2 sub-task added; backend Dockerfiles uniform (imobi/dev-team exceptions noted); frontend Dockerfiles retired (drift moot); Open Q1+Q3 resolved | Claude Opus 4.7 |
| 2026-05-16 | **Phase 2 PIVOT (seed-level, user-driven):** rejected both (a) 10 propagated full copies (drift class) and (b) single god-Dockerfile w/ per-product `if` conditionals (anti-pattern). Adopting the Docker-native seed pattern: **one shared `noctus-seed-base` image** (all common heavy layers) + **thin per-product Dockerfiles** `FROM` it that add only their specificities — `FROM base` IS the named seam (mirrors `create_product_app()` inherit-and-extend, never fork). Same-origin/factory work from Phase 2 unaffected. `propagate-dockerfiles.sh` → emits thin skeletons only (or retired). Cost: base builds before products (start.sh orders it; also caches the heavy layer once vs 10×) | Claude Opus 4.7 |
| 2026-05-16 | Phase 2 design refinement — same-origin: scattered `import.meta.env.VITE_BACKEND_API_URL \|\| 'http://localhost:80XX'` idiom (N≫3 across products) + mandatory tunnels make build-time absolute URLs wrong. Solution: Vite `define` raw-expression injection of `window.location.origin` in same-origin mode → runtime-correct (localhost/tunnel/deploy), zero consumer-file changes; only vite factory + env.ts hand-edited | Claude Opus 4.7 |
| 2026-05-16 | Phase 5 ✅ — start.sh/stop.sh two-project rewrite (ensure_net + build_bases + subset + dev + sweep_dev_projects). **Success-criterion gate PASSED**: real `noctus-seed` container = /api/health 200 + SPA + SPA-fallback on ONE port; dev mode = uvicorn --reload + Vite HMR 2-container stack; stop.sh clean teardown. Lifecycle collision bug (fixed container_name across fleet/dev projects) caught by smoke + fixed inline | Claude Opus 4.7 |
| 2026-05-16 | Phase 4 ✅ — seed-inherited dev-mode override (uvicorn --reload backend overlay + Vite-HMR sidecar from the shared frontend base; SERVE_SPA_DIR="" ⇒ Phase-1 API-only fail-soft); `propagate-overrides.sh` → 10 (imobi included; dev port=backend+1000; base image name protected). Standalone compose+override `config -q` clean. Live HMR → Phase 5 (named) | Claude Opus 4.7 |
| 2026-05-16 | Phase 3 ✅ — single-service canonical compose + `propagate-composes.sh`; root split into `noctusai-products` + `noctusai-infra` (external `noctus-net`); atomic `git rm` of 10 frontend Dockerfiles + nginx template + stale overrides (23 del; `config -q` proves no dangling refs); imobi-scheduling folded; Open Q2/Q3 resolved. KB "NOT external:true" rule inverts → Phase 6 sync | Claude Opus 4.7 |
| 2026-05-16 | Phase 2 ✅ — seed-level single-container images: 2 shared base images + thin per-product inheritors (`FROM base` = the seam); same-origin via vite-define `window.location.origin`; propagate + build-base scripts; `imobi-scheduling` stale shape fixed; dev-team `/opt/dev_team` via splice seam. Verified in real Docker: frontend-base + thin `FROM` chain + in-container same-origin bundle. Backend-base full build deferred → Phase 5 (named) | Claude Opus 4.7 |
| 2026-05-16 | Phase 1 ✅ — `serve_spa` seam in `noctusai_seed.app` (param + `SERVE_SPA_DIR` env, SPA-fallback `_mount_spa`, fail-soft); `test_serve_spa.py` 9 tests; 35/35 seed-factory regression green. Improvements captured; dotted-route heuristic deferred → Phase 2 | Claude Opus 4.7 |
