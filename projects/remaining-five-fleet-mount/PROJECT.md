# Remaining-five fleet mount — Project Document

> Living document. Near-future scope, filed 2026-05-19.

- **Created:** 2026-05-19
- **Last updated:** 2026-05-19
- **Status:** Filed — not started (near-future; gated on the build-perf root fix)
- **Owner / stakeholders:** joaoraphaelsst · Claude (architect)
- **Related docs:** `KB § PATTERNS/containerization.md` · `projects/frontend-deps-base-consolidation/PROJECT.md` (the build-perf root) · `KB § PATTERNS/branching-and-merging.md § 9a`
- **Project slug:** `remaining-five-fleet-mount` — `projects/` (cross-product platform-infra; intent = rollout)

---

## 1. Context & Purpose

The single-click Docker fleet is wired + drift-free for all 9 products; all container fixes shipped (chown −3.3 GB, `staggered_up`, WAHA arm64, SPA-race, pre-commit-scope, §9a). To unblock work *today* the user chose to build a **4-product subset** — `social-wiring`, `seed`, `core`, `erp-imobiliario` (dispatched on `fleet/build-isolated`). This project tracks **mounting the remaining 5 products** when they're next needed: `personal-finance`, `therapy-platform`, `daily-life`, `adconnect`, `dev-team`.

Why deferred, not done now: a full cold fleet build is structurally **multi-hour** because each product's `pip install -r requirements.txt` fights the base venv's pinned versions (massive uninstall→reinstall→source-recompile + pip backtracking; measured ~53 min for one heavy product, step `#75`). That root defect is owned by `frontend-deps-base-consolidation` (backend-deps sibling). This project is the **rollout** of the remaining 5 once that perf root is addressed (or on-demand per product, which is already fast enough light-product-by-light-product).

---

## 2. Confirmed constraints

- **Subset now, rest later** — user: "build only social wiring, seed, core, and erp for now. File the implementation of the rest as a new project." *(This doc IS that project; single project, not five.)*
- **Single-project implementation** — one doc covers all 5; do not fragment per-product. *(Phases may batch them, but one tracked artifact.)*
- **Mind the other agent / §9a** — a concurrent agent is active on `feat/social-wiring-youtube` + its own worktree; all work here stays on isolated branches, never the contended primary.
- **Per-product on-demand already works** — `./start.sh <slug>` builds one product; a user needing e.g. `therapy-platform` later doesn't strictly need this project, just the subset command. This project exists for the *coordinated* remaining-fleet bring-up + the perf-root dependency.

---

## 3. Design principles

1. **No new container work** — all 5 already have propagated, chown-fixed Dockerfiles + composes; this is *build + validate + bring-up*, not authoring.
2. **Gated on build-perf root** — sequence after (or alongside) `frontend-deps-base-consolidation` Phase 2+ so the bring-up isn't multi-hour; otherwise per-product on-demand.
3. **Branching-first** — executed via dispatched engineer(s) on an isolated worktree/branch, never the shared primary (§9a).
4. **Pilot cadence already satisfied** — `seed`/`core`/`social-wiring` are pilots and validated in the subset; the remaining 5 are the non-pilot extend wave.

---

## 3a. Seed-first analysis

1. **Contract identical for every product?** YES — all 9 inherit the same canonical Dockerfile/compose via `noctus.dev.propagate`; the remaining 5 carry zero per-product container divergence.
2. **Data source product-specific?** N/A (build/runtime infra, not data).
3. **Placement product-specific?** NO — the build mechanism is the shared seed canonical + propagate.
4. **Visibility/permission rule same?** N/A.
5. **Seam already in seed?** YES — `FROM noctus-seed-*-base` + `staggered_up` + the propagate pipeline; nothing new.
6. **Default-on or opt-in?** DEFAULT-ON — all 9 are registered fleet members; this is just the build/bring-up of the 5 not in the immediate subset.

**Litmus — per-product code count:** 0. Pure rollout of an existing shared mechanism; §6 phases batch the 5, never author per-product container code.

---

## 4. Scope

**In scope:** build + healthcheck-validate + bring-up of `personal-finance`, `therapy-platform`, `daily-life`, `adconnect`, `dev-team` into `noctusai-products`; confirm `staggered_up` waves + chown-light images + per-product `/api/health` + SPA serve; verify the §11 Docker-Desktop/`docker ps` reality.

**Out of scope:** the build-perf root defect (→ `frontend-deps-base-consolidation`); any product feature/code work; the 4-product subset (already dispatched on `fleet/build-isolated`).

---

## 6. Implementation phases

### Phase 1 — Gate check
- [ ] Confirm `frontend-deps-base-consolidation` build-perf state (is a heavy cold build still multi-hour?) — decides batch vs on-demand
- [ ] Confirm the 4-product subset converged healthy (proves the pipeline end-to-end before extending)

### Phase 2 — Light products (fast pip)
- [ ] Build + bring up `daily-life`, `adconnect`, `dev-team` (lighter requirement sets) via dispatched engineer on an isolated worktree; each `/api/health` 200 + SPA serves
- [ ] dev-team: confirm `/_ready` healthcheck override (ANTHROPIC_API_KEY-gated, KB §11)

### Phase 3 — Heavy products (pip-thrash path)
- [ ] Build + bring up `personal-finance`, `therapy-platform` (heavy: the ~50-min/product pip path unless the perf root landed) — staggered, isolated worktree
- [ ] Full fleet 9/9 healthy verified via `docker ps` (not Docker-Desktop, KB §8)

### Phase 4 — Close
- [ ] `docker system df` after; confirm chown-light fleet footprint
- [ ] Three-way sync if anything surfaced; archive

---

## 9. Success criteria

- All 5 remaining products build, go `healthy`, serve API + SPA; full fleet 9/9 one-click in `noctusai-products`.
- Zero new per-product container code (pure propagated-mechanism rollout).
- Executed entirely on isolated branches/worktrees (§9a) — never the contended primary.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-19 | Filed per user ("file the rest as a new project, single-project"); subset (social-wiring/seed/core/erp) dispatched separately on `fleet/build-isolated`; gated on the build-perf root (`frontend-deps-base-consolidation`) | Claude |
