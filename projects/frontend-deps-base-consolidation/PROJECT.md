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

### Phase 0 — Measurement baseline (gated on daemon free)
- [ ] `docker system df -v` true disk (Images / Build Cache / reclaimable) — *blocked: in-flight staggered_up validation build saturates the daemon*
- [ ] Per-product `node_modules` size in a built `runtime-watch` image (`docker run --rm <img> du -sh .../node_modules`)
- [ ] Record baseline numbers here (the before half of the evidence-based win claim)

### Phase 1 — Alpine frontend-base closure lift (pilot: seed → core → social-wiring)
- [ ] Derive the canonical shared closure (deps shared by ≥ threshold; threshold decided from `/tmp/fe_overlap.txt` — start ≥6, sanity-check ≥9 set)
- [ ] Edit `seed/docker/Dockerfile.frontend-base`: add root-manifest + closure `npm install` layer
- [ ] Edit canonical `products/seed/backend/Dockerfile` `frontend-build` stage if the up-tree resolution needs an anchor
- [ ] `noctus.dev.propagate --check` then propagate; pre-commit `--check` green
- [ ] `build-base-images.sh` rebuild frontend base; pilot-build seed + core + social-wiring `frontend-build`; assert dist parity + image-size delta
- [ ] `bash -n start.sh`; `docker compose config -q` both projects

### Phase 2 — glibc runtime-watch closure share
- [ ] Decide design (a) vs (b) from Phase 0 evidence
- [ ] Implement on canonical seed + propagate; honor §3.2b (lockfile drop ×2, anon-volume seed source)
- [ ] Pilot rebuild + live-edit smoke (edit a pilot product's .tsx, confirm watch rebuild) + size delta

### Phase 3 — Fleet extend + measure + three-way sync
- [ ] Non-pilot products extend (gated on pilots-green) — rebuild fleet via fixed `./start.sh` (staggered)
- [ ] `docker system df -v` after; record before/after; confirm the staggered_up boot still healthy 9/9
- [ ] KB §3.2b/§6 update + CLAUDE.md pointer + memory + MEMORY.md (three-way sync); update §11

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
