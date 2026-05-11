# Containerization Backlog Closure — Orchestration

> **This is a living document.** Filed 2026-05-10 by orchestrator after user-issued
> directive: "implement them all, even the deferable and even the ones that surfaces
> mid-flight and are deferable or too much work. Implement them all. No deferrals nor
> parks." Plus a methodology amendment (wave-based dispatch + pause-on-dependency +
> scoped-team economics) captured at three-way-sync time.

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** Phase 0 ✅ (methodology three-way-synced) · Phase 1 ⏳ (Wave 1 dispatch)
- **Owner / stakeholders:** Raphael (user) · Orchestrator (CLI agent) · Wave engineers (subagent dispatches)
- **Related docs:** `KB § PATTERNS/containerization.md §11` (backlog source of truth); `KB § PATTERNS/branching-and-merging.md §16-§18`; `feedback_wave_dispatch_and_pause_on_dependency.md` memory entry.
- **Project slug:** `containerization-backlog-closure` — cross-product / platform-infrastructure scope, lives at root `projects/`.

---

## 1. Context & Purpose

The containerization rollout (committed 2026-05-10 in `c98273c feat(infra): containerize platform + harden cloudflare tunnels with --protocol http2`) shipped with 11 explicit backlog items in `KB § PATTERNS/containerization.md §11` — 5 ✅ already applied this session + 11 🟡/🟢 deferred for "later" or "small lifts" or "strategic."

The user closed the deferred queue entirely: **implement all 11 deferred items**. No parks, no deferrals. Use orchestrator-managed wave dispatch with as many focused teams as needed; quality is the constraint, tokens are not.

The same directive surfaced a methodology amendment (wave-based dispatch + pause-on-dependency + scoped-team economics) captured first, before any team operates under it. See `KB § PATTERNS/branching-and-merging.md §18`.

---

## 2. Confirmed constraints (from user interrogation 2026-05-10)

| # | Q | A |
|---|---|---|
| Q1 | "Should we defer the strategic items (#12, #13, #14, #15)?" | **NO.** "No deferrals nor parks." Implement everything. |
| Q2 | "What if a chunk surfaces a mid-flight dependency?" | **Pause + dispatch dependency team + resume.** Engineers never absorb dependencies into their own scope. Architect decides team boundaries. |
| Q3 | "How many parallel teams are OK?" | "As many teams as the orchestrator needs to clear our todo tasks as quickly as possible." Token cost explicitly acceptable. |
| Q4 | "Speed vs. quality trade-off?" | **Quality wins.** "We praise for quality, so we won't give up quality to deliver fast." Speed comes from intelligent parallelism, not quality cuts. |
| Q5 | "Persist this methodology?" | **YES — three-way sync.** "Doc this team methodology... I want this to persist for future teams dispatches." |
| Q6 | "Image registry strategy?" | **Per-product registries** (user pre-decided in KB §11 #10 annotation: *"human decision: per-product registries."*) |
| Q7 | "Backend image multi-stage?" | **Yes** (user pre-decided in KB §11 #11 annotation: *"please do it."*) |

---

## 3. Source-of-truth backlog (from `KB § PATTERNS/containerization.md §11`)

11 deferred items to close:

| # | Item | Tier (KB) | Files touched (estimate) |
|---|---|---|---|
| 5 | `VITE_*` build-arg contract | 🟡 small lift | templates + KB docs + per-product compose audit |
| 6 | `@noctusai/seed` in product package.json | 🟡 small lift | 10× `products/<x>/frontend/package.json` + templates |
| 7 | OCI image labels (image.source + image.revision) | 🟡 small lift | `products/seed/{backend,frontend}/Dockerfile` + 9× propagation + templates |
| 8 | `docker-compose.override.yml` for dev | 🟡 soon | new root override + templates |
| 9 | Full-fleet CI matrix (not 4-of-20 smoke) | 🟡 soon | `.github/workflows/test.yml` |
| 10 | Image registry strategy (per-product registries) | 🟡 soon | all compose `image:` tags + CI push job + KB docs |
| 11 | Backend image multi-stage slim | 🟡 soon | `products/seed/backend/Dockerfile` + 9× propagation + templates |
| 12 | `docker-compose.prod.yml` overlay | 🟢 later | new file at root + templates |
| 13 | Local-postgres profile | 🟢 later | root `docker-compose.yml` (new service) + schema-init |
| 14 | Per-product healthcheck override (dev-team) | 🟢 later | `products/dev-team/docker-compose.yml` + scaffolder hook |
| 15 | Image scanning (trivy/grype/docker scout) | 🟢 later | `.github/workflows/test.yml` + registry hook |

---

## 3a. Seed-first analysis

| Concern | Cross-product? | Seed-first verdict |
|---|---|---|
| Backend Dockerfile shape (#11, #7) | Yes (10 products mirror seed) | **Seed-first.** Update `products/seed/backend/Dockerfile` first, propagate to 9 products + `templates/product-seed/backend/Dockerfile`. Pattern is well-established. |
| Frontend Dockerfile shape (#7) | Yes (10 products mirror seed) | **Seed-first.** Same propagation pattern. |
| `@noctusai/seed` in package.json (#6) | Yes (all 10 products) | **Seed-first.** Update `templates/product-seed/frontend/package.json` first; mirror to 10 products. |
| `VITE_*` build-arg contract (#5) | Yes (any product using VITE_*) | **Seed-first.** Contract documented at KB; scaffolder template adds the args block; per-product audit identifies which products need it. |
| Docker compose shape (#8, #12, #14) | Yes (override + prod compose pattern) | **Seed-first.** `products/seed/docker-compose.yml` is canonical; override + prod variants get the same propagation. |
| Registry strategy (#10) | Yes (all compose `image:` tags) | **Seed-first.** Decide once, propagate the tag pattern to all `image:` declarations + CI. |
| Postgres profile (#13) | Cross-product (every backend talks DB) | **Root compose.** Single service definition, not per-product. |
| CI workflow (#9, #15) | Single CI file (already shared) | **Single source.** All edits to `.github/workflows/test.yml`. |

Replication-to-seed symmetry check: per-product code count for cross-cutting concerns = **zero** (everything flows through seed + templates + scaffolder). ✅

---

## 6. Phases

### Phase 0 — Methodology three-way-sync ✅

Capture the orchestration methodology rules before any team operates under them.

- [x] Author `KB § PATTERNS/branching-and-merging.md §18` (pause-on-dependency + scoped-team economics + wave-based execution).
- [x] Update `CLAUDE.md §1` with new bullet pointing to §18.
- [x] Write `feedback_wave_dispatch_and_pause_on_dependency.md` memory entry.
- [x] Add `MEMORY.md` index line under "Foundational principles".
- [x] Scaffold this PROJECT.md + findings.md.

**Improvements:** captured at three-way-sync time. Methodology amendment is complete; teams operate under it from Phase 1 onward.

### Phase 1 — Wave 1 dispatch (parallel, no in-batch dependencies) ⏳

Six focused engineer dispatches in a single Task turn (true parallelism via `isolation: "worktree"`):

- [ ] **T1 — Backend Dockerfile shape (#11 + #7-backend).** Multi-stage slim (builder/runtime split, target ~200-400MB reduction from 600-900MB baseline) + OCI labels (`org.opencontainers.image.source` + `org.opencontainers.image.revision`). Files: `products/seed/backend/Dockerfile` (canonical) + 9× product propagation + `templates/product-seed/backend/Dockerfile`.
- [ ] **T2 — Frontend Dockerfile labels + package.json deps (#7-frontend + #6).** Add OCI labels to frontend Dockerfile (seed + 9 mirrors + template). Add `@noctusai/seed` + `@noctusai/lib` to product `package.json` dependencies as file: paths OR document the alias-only resolution. Decide and document.
- [ ] **T3 — `VITE_*` build-arg contract (#5).** Document the contract in `KB § PATTERNS/containerization.md` + scaffolder template (`templates/product-seed/docker-compose.yml`). Audit each product for `VITE_*` references in source; add args block where needed.
- [ ] **T4 — Local-postgres profile (#13).** Add `postgres` service to root `docker-compose.yml` (profile-gated). Schema-init script that runs each product's `001_<product>.sql` migration. Document the offline-dev workflow.
- [ ] **T5 — Registry strategy + per-product image tags (#10).** Decide tag pattern (e.g., `ghcr.io/noctusai/noctus-<slug>-backend:<git-sha>`). Update all per-product compose `image:` declarations to use the pattern (with local fallback for dev). Document in KB.
- [ ] **T6 — Per-product healthcheck override (dev-team) (#14).** Add deeper healthcheck for dev-team's agno engine (`/api/health/agno`). Scaffolder hook so future products can override with their own healthcheck. Surface as named seam in `templates/product-seed/docker-compose.yml`.

**Sync gate:** all 6 engineers report → architect transcribes findings → FF-merge all 6 → run `docker compose config --quiet` + sample backend pytest + frontend `npx vite build` → verify green → dispatch Wave 2.

**Improvements:** populate during/after dispatch.

### Phase 2 — Wave 2 dispatch (consumes Wave 1 outputs)

Two parallel dispatches after Wave 1 merges:

- [ ] **T7 — `docker-compose.override.yml` for dev (#8).** Build on T6's seam pattern. Root override + per-product override. Bind-mounts for source (hot-reload in dev), no resource limits, dev-specific env. Documented in KB.
- [ ] **T8 — `docker-compose.prod.yml` overlay (#12).** Build on T5's image tag pattern. Resource caps (memory/CPU limits), read-only filesystems where possible, log drivers, no bind-mounts. Documented in KB. Production deployment target.

**Sync gate:** both report → transcribe → FF-merge → verify → dispatch Wave 3.

### Phase 3 — Wave 3 dispatch (CI workflow consolidation) ⏳

Single engineer owns the CI workflow surface to avoid file conflicts:

- [ ] **T9 — CI full-fleet matrix + registry push + image scanning (#9 + #10 CI part + #15).** Matrix strategy in `.github/workflows/test.yml` to build all 20 product images (likely with `continue-on-error: false` + cache reuse). Registry push job (per T5's pattern). Image scanning step (trivy or docker scout — decide based on what GH Actions supports cleanly). Update KB §11 with the new CI shape.

**Sync gate:** engineer reports → transcribe → FF-merge → verify CI passes on a test PR.

### Phase 4 — Final audit + KB §11 reset + project close

- [ ] Run `noctus.hound.scan` to surface any cleanup the wave work introduced.
- [ ] Update `KB § PATTERNS/containerization.md §11` to reflect all items ✅ — convert the 🟡/🟢 lists to a closed-state historical record.
- [ ] Synthesize findings.md (close-time pass: curate from append-as-you-go log into knowledge artifact).
- [ ] Bundled proposal for the orchestration.
- [ ] Archive the project: `noctus.dev.archive` → `archive/projects/2026-05-10/NN-containerization-backlog-closure/`.
- [ ] Orchestrator FF-merges branch to main (project-close gate).

---

## 7. Open questions (architect-tracked)

None blocking. Q1-Q7 in §2 resolved at scaffold time.

---

## 11. Change log

- **2026-05-10 14:00** — User-issued directive to implement all KB §11 backlog with wave dispatch + pause-on-dependency methodology. Project scaffolded; Phase 0 (methodology three-way-sync) closed in single edit batch.
- **2026-05-10 14:00** — `KB § PATTERNS/branching-and-merging.md §18` authored.
- **2026-05-10 14:00** — `CLAUDE.md §1` bullet added.
- **2026-05-10 14:00** — `feedback_wave_dispatch_and_pause_on_dependency.md` memory entry + MEMORY.md index line.

---

## 12. Wave layout — dependency DAG

```
Wave 1 (parallel; no cross-chunk file collisions):
  T1: backend Dockerfile (#11 + #7-be)      → products/seed/backend/Dockerfile + 9 mirrors
  T2: frontend Dockerfile + package.json    → products/seed/frontend/Dockerfile + 9 mirrors + 10 package.json
  T3: VITE_* build-arg contract              → templates/ + KB + per-product compose args block
  T4: postgres profile                      → root docker-compose.yml + init scripts
  T5: registry strategy + image: tags        → all per-product compose image: lines + KB
  T6: dev-team healthcheck override          → products/dev-team/docker-compose.yml + seam in template

Wave 2 (after Wave 1 FF-merges):
  T7: docker-compose.override.yml (dev)      → consumes T6 seam pattern + new file
  T8: docker-compose.prod.yml                 → consumes T5 image tag pattern + new file

Wave 3 (after Wave 2 FF-merges):
  T9: CI workflow (matrix + registry push + scan) → .github/workflows/test.yml (single owner)
```

File-collision audit:
- **T1 ↔ T2:** different files (backend vs frontend Dockerfile). ✅
- **T1 ↔ T5:** T1 touches Dockerfile, T5 touches `image:` in compose. Different files. ✅
- **T3 ↔ T5:** T3 touches `args:` in compose (where present), T5 touches `image:`. Different compose blocks; potential merge conflict if both edit same compose file's YAML. **Mitigation:** T3 explicitly handles `args:` block only; T5 explicitly handles `image:` line only. Briefs forbid drift.
- **T6 ↔ T5:** T6 touches dev-team compose healthcheck block, T5 touches its `image:` line. Different lines. ✅
- **T4 ↔ T5:** T4 touches root compose `services:` (new service), T5 touches per-product compose `image:`. Different files. ✅
- **T2 ↔ T6:** Different concerns; no overlap.
- **All Wave 1 ↔ Wave 1:** No CI file edits in Wave 1 (CI consolidated to Wave 3).

Wave 1 is dispatchable in parallel. Wave 2 has T7+T8 in parallel (different new files). Wave 3 is single-engineer.

---

## Project lifecycle

This document is amended every time a wave dispatches, a finding lands, or a pause-on-dependency signal fires. See §11 for the change log.
