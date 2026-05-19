# Frontend deps → seed base consolidation — Project Document

> Living document. Revise phases as evidence lands.

- **Created:** 2026-05-19
- **Last updated:** 2026-05-19
- **Status:** Design locked → Phase 1 ready (Phase 0 measurement gated on in-flight fleet build freeing the Docker daemon)
- **Owner / stakeholders:** joaoraphaelsst · Claude (architect)
- **Related docs:** `KB § PATTERNS/containerization.md` (§3.1 base images · §3.2/§3.2b frontend stages · §6 footprint) · canonical `seed/docker/Dockerfile.frontend-base` · `products/seed/backend/Dockerfile` · `mcp/noctusai/tools/noctus/dev/propagate.py`
- **Project slug:** `frontend-deps-base-consolidation` — `projects/` (cross-product platform-infra; intent = consolidation)

---

## 1. Context & Purpose

The user asked whether container storage can be optimized — "one-build something that repeats" — fearing it bites at scale. Evidence gathered this session:

- **Python heavy closure is already one-built** in `noctus-seed-backend-base` (shared layer, one disk copy). Backend side = already DRY-correct.
- **Frontend `node_modules` is the unoptimized DRY violation.** 82 distinct FE deps across 9 products; **51 shared by ≥6**; ~20 (react, react-dom, vite, typescript, tailwind*, @radix-ui/*, @tanstack/react-query, @supabase/supabase-js, zustand, lucide-react, clsx, postcss, autoprefixer, @vitejs/plugin-react-swc, @types/*) in **all 9**. `noctus-seed-frontend-base` ships only the *seed-alias* deps (`seed/framework/frontend`, `seed/lib/frontend`), **not** this common product app closure. So every product `npm install`s the ~50-dep closure into its **own unshared layer** — and it happens **twice per product** (alpine `frontend-build` stage + glibc `runtime-watch` stage; the latter's node_modules is not ABI-portable from the alpine base, per the Dockerfile's own comment). Effective duplication ≈ **2 envs × 9 products** of a ~50-dep closure.

Win: lift the common FE closure into the shared base(s) so it is one disk-shared layer (mirrors the proven Python pattern + the §3.2a "N≥2 → lift to base" escalation). DRY recurrence here is **N=9 → MUST formalize**.

---

## 2. Confirmed constraints

- **Proceed mode** — user chose "File + execute now" (not file-only / measure-first). *(Execute pilot-first; do not block the whole project on df numbers — structural decision is already evidence-justified.)*
- **Run all 9 locally** — user wants the whole fleet single-click runnable, not a subset. *(So the local `runtime-watch` glibc node_modules cost — Phase 2 — is in scope, not dismissable as "deploy is slim".)*
- **Scale fear is the driver** — optimization, not correctness (the switch already works; solo-seed boot proved healthy + API + SPA).

---

## 3. Design principles

1. **Mirror the proven Python pattern** — common closure installed once in the shared base; product layer = thin delta only. No new mechanism invented.
2. **Canonical-only edits + propagate** — changes land in `seed/docker/Dockerfile.frontend-base` and canonical `products/seed/backend/Dockerfile`; the 9 regenerate via `noctus.dev.propagate`. Zero hand-edited per-product Dockerfiles (§3 anti-pattern). Pre-commit `--check` gate stays green.
3. **Pilot-products-first** — prove on `seed` → `core` → `social-wiring` before fleet-wide rebuild (`KB § project-execution §2.12`).
4. **Evidence-based win claim** — no "saves X GB" asserted without `docker system df` before/after.
5. **No-collision with the in-flight validation** — the staggered_up validation build currently saturates the daemon; rebuild/measure steps are gated on it (don't corrupt that evidence or double-thrash the daemon).

---

## 3a. Seed-first analysis

1. **Contract identical for every product?** YES — every product's FE is React+Vite+Tailwind+Radix+Tanstack+supabase-js+zustand; the common closure is uniform.
2. **Data source product-specific?** N/A (build-time dep set, not runtime data). The *delta* deps are product-specific; the closure is not.
3. **Placement product-specific?** NO — belongs in `noctus-seed-frontend-base` (+ a glibc sibling for runtime-watch), universal.
4. **Visibility/permission rule same?** N/A.
5. **Seam already in seed?** PARTIAL — `noctus-seed-frontend-base` exists and is the exact named seam (`FROM noctus-seed-frontend-base AS frontend-build`); it just doesn't carry the app closure yet. Phase 2 needs a glibc-node base seam for `runtime-watch` (currently `FROM runtime` = backend base, debian; no shared FE node layer there).
6. **Default-on or opt-in?** DEFAULT-ON — every product benefits, zero per-product code.

**Litmus — per-product code count:** **0 lines.** The closure moves into the base image; product Dockerfiles are *regenerated* by propagate, not hand-touched. Textbook 0-line cross-product concern. §6 phases work in seed, never walk product-by-product (rebuild fan-out is pilot-cadence validation, not replication).

---

## 4. Scope

**In scope:**
- Lift the common FE dep closure into `noctus-seed-frontend-base` (alpine) → benefits the `frontend-build` stage (= the slim CI/deploy `runtime` path too).
- Solve the glibc `runtime-watch` half so the heavy local-dev node_modules is also shared, not 9× duplicated.
- `propagate` flow + pre-commit `--check` stays green; canonical-only edits.
- Before/after `docker system df` measurement; KB §3.2b/§6 + CLAUDE.md + memory three-way sync at close.

**Out of scope (for now):**
- Build-cache reclamation / the §6 base-invalidation cascade — separate concern, filed adjacent (`docker-build-cache-cascade` follow-up); cheap `mole`/`builder prune` is operational, not this structural lift.
- Trimming individual product dep lists (a different optimization).

---

## 5. Architecture / Data Model

**Two node_modules environments (the crux):**

```
frontend-build  : FROM noctus-seed-frontend-base (node:20-ALPINE / musl)
                  → npm install product ~50 deps → vite build → dist/
                  → this is ALSO the slim CI/deploy `runtime` build path
runtime-watch   : FROM runtime (= noctus-seed-backend-base, DEBIAN / glibc)
                  + apt nodejs → npm install product ~50 deps AGAIN
                  → vite build --watch (local live-edit; the heavy local image)
```

**Phase 1 (alpine, clean):** add a common-closure install layer to `seed/docker/Dockerfile.frontend-base`. Approach mirrors the existing "Node resolution walks UP" design already relied on there: a root `/app` manifest carrying the ≥6-shared closure + `npm install` → `/app/node_modules` shared base layer; product `frontend-build` `npm install` at `/app/products/<slug>/frontend` resolves the closure up the tree, installing only its delta. Shared layer = one disk copy across 9.

**Phase 2 (glibc runtime-watch):** the harder half. Candidate designs (decide in Phase 2 on evidence):
- (a) a new shared base `noctus-seed-frontend-glibc-base` (debian + node + the common closure) that `runtime-watch` `COPY --from=`s the closure node_modules from; product adds delta.
- (b) fold a glibc common-closure node_modules into the backend base (heavier base, but one image).
- Both must respect §3.2b: host lockfile drop (×2) + the anonymous `node_modules` volume shadow in the local compose. The anon-volume currently masks the *image* node_modules with a per-container one seeded from the image layer — the closure must live in the image layer the anon volume is seeded FROM.

---

## 6. Implementation phases

> **Evidence-driven pivot (2026-05-19).** Phase 0 `docker history` measurement
> redirected priorities — see §5. The biggest, safest, cheapest disk win was
> NOT the planned alpine closure lift; it is the `chown -R /opt/venv`
> anti-pattern (~2.5–2.8 GB, ~1-token canonical fix). The alpine
> frontend-base closure is real but build-*speed*, low disk (discarded
> stage). Phases re-ordered by measured disk-value × inverse-risk.

### Phase 0 — Measurement baseline ✅
- [x] `docker system df -v`: ≈62 GB total → ≈37 GB after a ~25 GB regenerable reclaim (build cache 35→13 GB, dangling images, 2 retired-product volumes)
- [x] `docker history noctus-seed:dev`: **`RUN useradd … chown -R … /app /opt/venv` = 311 MB UNSHARED per product** (rewrites the 276 MB shared-base venv); glibc `runtime-watch` `npm install` ≈ 215 MB + post-npm `chown -R /app` ≈ 227 MB; alpine `frontend-build` node_modules **absent** (discarded stage → alpine lift = build-speed, not disk)

**Improvements:** none identified — Phase 0 is pure measurement; the actionable findings (the chown anti-pattern pivot, the alpine-vs-glibc split, the deeper serve_spa-resilience) are captured in §5, the Phase 1 `**Improvements:**` block, and §11. No phase proposal needed.

### Phase 1 — Kill the `chown -R /opt/venv` layer-bloat anti-pattern ✅ (pilot: seed → core → social-wiring; validated 2026-05-19)
- [x] Canonical `products/seed/backend/Dockerfile` runtime stage: `chown -R … /app` only (drop `/opt/venv`; venv read-only at runtime, stays shared base layer) + rationale comment
- [x] `noctus.dev.propagate` → 9 products; `--check` in-sync (zero drift)
- [x] Controlled pilot rebuild (seed/core/social-wiring) — **measured ≈370–430 MB/product off; fleet ≈3.3 GB; unique footprint −35–40%** (beat ~2.8 GB estimate)
- [x] Functional smoke: healthy 55s, `/api/health` 200, **non-root `noctus` imports the root-owned world-readable venv OK** (confirms the chown was pure waste), no perm errors
- [x] **Fix-on-contact (separate pre-existing bug found during validation):** `seed/docker/local-watch.sh` declared but didn't *enforce* "dist before uvicorn" — the bg `vite --watch` initial pass transiently empties `dist/`, `exec uvicorn` raced into `serve_spa`'s startup-only check → SPA 404 the whole boot (healthcheck only probes `/api/health` so it still "healthy"). Fixed: block on `dist/index.html` stable (3 consecutive ticks) before `exec uvicorn`, bounded `LOCAL_WATCH_DIST_TIMEOUT` (proceed+⚠, never silent). Shared file (no propagate); revalidating via seed rebuild
- [x] Confirmed SPA serves post-fix: log shows `dist ready (stable 3s) → starting uvicorn → SPA served (single-container mode)`; `/` returns `<title>Seed Product</title>`, healthy 65s

**Improvements:**
- *Deeper root (surfaced, NOT ballooned):* `serve_spa` in `seed/framework/backend/noctusai_seed/app.py` is **startup-only + fail-soft-permanent** — a transient missing `dist/` at boot disables the SPA for the container's life. The local-watch poll closes the race for `runtime-watch`, but request-time SPA-fallback resolution in the seed factory would make it resilient for *all* products + any future race. Recommended follow-up project `serve-spa-request-time-resilience` (seed-framework change → needs its own cross-product validation; correctly out-of-scope here per fix-on-contact's "balloons into a project → file it").

### Phase 2 — runtime-watch chown-after-npm + glibc FE closure share
- [ ] runtime-watch: the post-`npm install` `chown -R /app` (line ~123) rewrites the fresh ~215 MB glibc node_modules → restructure (install as `noctus` / `COPY --chown` / scoped chown) so node_modules isn't duplicated into a chown layer
- [ ] glibc common FE closure shared (design (a) separate `noctus-seed-frontend-glibc-base` vs (b) fatter backend base — decide on Phase 1 evidence); honor §3.2b (lockfile drop ×2, anon-volume seed source)
- [ ] Pilot rebuild + live-edit smoke (edit a pilot .tsx → watch rebuild) + size delta

### Phase 3 — alpine frontend-base closure (build-SPEED — cascade mitigation, low disk)
- [ ] Lift ≥9-shared closure into `seed/docker/Dockerfile.frontend-base`; reframed as cold-rebuild-cascade speedup, not disk
- [ ] Pilot build-time before/after

### Phase 4 — Fleet extend + measure + three-way sync
- [ ] Non-pilots extend (gated pilots-green) — fleet rebuild via fixed `./start.sh` (also validates `staggered_up` end-to-end, >4 products = real waves)
- [ ] `docker system df -v` after; record before/after; staggered boot still 9/9 healthy
- [ ] Three-way sync: KB containerization anti-patterns §12 + §3.2b/§6 + CLAUDE.md pointer + memory (the `chown -R inherited-base-path` anti-pattern is a generalizable methodology lesson) + §11

---

## 7. Open questions

1. **Shared-closure threshold (≥6 vs ≥9)?** — decided in Phase 1 from `/tmp/fe_overlap.txt`; ≥9 is safest (zero risk of forcing an unused dep on a product), ≥6 maximizes dedup. Recommendation: ≥9 first (the ~20 all-in deps = biggest, safest win), widen if delta worth it.
2. **Phase 2 design (a) separate glibc base vs (b) fatter backend base?** — needs Phase 0 node_modules size; (a) keeps images role-clean, (b) keeps "one base per layer". Recommendation: (a).
3. **df baseline** — blocked on daemon; Phase 0 gate.

---

## 8. Dependencies & blockers

- **In-flight staggered_up validation build** saturates the Docker daemon → Phase 0 measurement + any rebuild is gated on it completing. (Non-negotiable: perturbing it corrupts the staggered_up fix's validation evidence and double-thrashes the daemon.)
- **Other context's uncommitted work in this tree** (`mcp/n8n/`, `mcp/waha/`, `01-PHILOSOPHY.md`, `MCP-SERVERS/README.md`) — NOT this project's; never staged/swept by this work.

---

## 9. Success criteria

- The ~50-dep common FE closure exists as **one shared base layer**, not 9× (×2 env) unshared.
- `docker system df` shows a measured Images-size reduction (before/after recorded) with no functional regression: pilot products `vite build` produce byte-equivalent `dist/`; `runtime-watch` live-edit still rebuilds; staggered fleet boot still 9/9 healthy.
- Canonical-only: `propagate --check` + pre-commit green; zero hand-edited per-product Dockerfiles.
- Three-way doc sync complete.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-19 | Filed after user "File + execute now"; evidence (FE overlap 51@≥6, 20@all-9; two-env duplication) gathered pre-filing; Phase 0 gated on in-flight daemon | Claude |
| 2026-05-19 | Aborted+consolidated (user-chosen): ~25 GB regenerable reclaimed, daemon freed, Phase 0 measured. **Evidence pivot**: `chown -R /opt/venv` = 311 MB/product anti-pattern is the top win, not the alpine lift. Phases re-ordered. Phase 1 canonical fix applied + propagated (in-sync); pilot rebuild in flight | Claude |
| 2026-05-19 | **Phase 1 ✅** — measured ≈3.3 GB fleet (≈370–430 MB/product, unique −35–40%); functionally validated (healthy, API 200, non-root venv import OK, SPA serves). Fix-on-contact: `local-watch.sh` SPA startup race fixed (enforce dist-stable before uvicorn); deeper `serve_spa` startup-only-resilience surfaced as follow-up. Three-way synced (KB §12 anti-pattern + memory). Committed local | Claude |
