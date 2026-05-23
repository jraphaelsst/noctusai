# PROJECT — Container-first codification + absorb knowledge-extractor

> **Created:** 2026-05-23 · **Owner:** rapha · **Branch:** `feat/container-first-codify-and-absorb-ke`
> **Driver:** architect (this session). **findings.md:** sibling file.

---

## 1 · Goal

Two coupled deliverables, in order:
1. **Codify container-first** ("create the container first, develop the platform *inside* it") as the documented, enforced default of noc's product-creation + absorption methodology — **full codification**: doc + scaffold wiring + a keeper.
2. **Absorb `../knowledge-extractor`** into `products/knowledge-extractor/` (the 10-gate procedure) and **containerize it to the house single-container model**, validating the methodology from (1) on the first real pilot.

## 2 · User ask (verbatim intent)

> "absorb the repo as a new product inside noc's context and body … before, add to the product creation methodology the containerization … after it's defined and done, containerize it." + (discussion) chose **container-first / develop-inside** and **full codification (+ keeper)**.

## 3 · Why container-first (the locked decision)

noc already embodies it: the house model is **ONE container, ONE shape, always** — `runtime-watch` (bind-mount + `vite build --watch` + `uvicorn --reload`) is dev *inside* the container; slim `runtime` is deploy. "Build on host, containerize last" is the exact anti-pattern behind the platform's #1 drift class ([[dev-prod-parity]], N≥3). Container-first kills it by construction; the bind-mount+watch trick keeps host-speed iteration. The DB stays external (managed Supabase) — containerizing the app never containerizes the DB.

## 3a · Seed-first analysis (required before §6)

- **Concern:** "every in-noc product conforms to the house single-container model + container-first is the default." Cross-cutting ⇒ the right per-product code count for the *rule* is **0**: the shape is defined once (`products/seed/backend/Dockerfile` + `docker-compose.yml`), propagated by `scripts/propagate-{dockerfiles,composes}.sh`, and enforced once by a seed-level keeper.
- **Canonical shape (what the keeper checks):** `products/<slug>/backend/Dockerfile` multi-stage `FROM noctus-seed-frontend-base AS frontend-build` → `FROM noctus-seed-backend-base AS runtime` → `FROM runtime AS runtime-watch`; `SERVE_SPA_DIR`/`serve_spa`; `VITE_SAME_ORIGIN=1`; single-service `docker-compose.yml` w/ `target: runtime-watch`, source bind-mounts + anon node_modules volumes, `noctus-net external`, mandatory profile-gated `<slug>-tunnel --protocol http2`.
- **Two container shapes today (drift to close):** the seed-WORKSPACE scaffold (pre-absorption sibling) emits a TWO-Dockerfile workspace-root shape (`templates/seed-workspace-docker/`); the in-noc product shape is the single-container house model. The absorb guide's container gate is the bridge. Codification makes the house model the documented endpoint + enforces it for in-noc products.

## 4 · Phases

| Phase | Deliverable | Gate |
|---|---|---|
| **P1** | **Codify container-first.** (a) doc: `new-product.md` + `absorb-seed-workspace.md` container gate + `containerization.md` "container-first" principle + CLAUDE.md pointer + INDEX. (b) scaffold/propagation: confirm a new in-noc product gets the house artifacts; document it. (c) keeper: `check_product_container_shape` (in-noc products conform to house model) + colocated test + three-way-sync. | keeper green on the fleet baseline; verify-kb-sync; tests pass |
| **P2** | **Absorb knowledge-extractor** → `products/knowledge-extractor/` (move → `create_product_app` → swap local seams to `noctusai_lib` → re-pin deps). Per `KB § GUIDES/absorb-seed-workspace.md`. | product imports; pytest green; landscape roster updated |
| **P3** | **Containerize to house model** (thin `backend/Dockerfile` FROM bases + `docker-compose.yml` via propagation) + bring up `runtime-watch` + verify in container shape (incl. live Supabase env). The P1 keeper goes green on knowledge-extractor = methodology validated on the pilot. | container healthy; `/api/health` 200; keeper green; live-probe |

P1→P2→P3 are dependency-chained (sequential). Within P1, doc/keeper/scaffold are file-disjoint (parallelizable if dispatched).

## 5 · Scope guards

- Keeper targets **in-noc products** (`products/<slug>/`, excluding `seed` = the canonical reference). Pre-absorption seed-workspace shape is out of scope (the absorb gate handles the refactor).
- DB is external/managed (Supabase); not containerized. The live `knowledge_extractor` schema work is the separate authorized note in `../knowledge-extractor/doc/live-db-authorization.md`.
- No new Supabase project (2-project cap). No push to `main` without explicit go.

## 6 · Status log
- 2026-05-23 — **P3 COMPLETE — project DONE.** Backend-only house Dockerfile (`FROM noctus-seed-backend-base` → `runtime` → `runtime-watch`; +ffmpeg; no frontend stage/`SERVE_SPA_DIR`) + `docker-compose.yml` (single service, `target: runtime-watch`, external `noctus-net`, profile-gated `knowledge-extractor-tunnel`). Registered: `start.sh` PRODUCTS (`8012:8012`), root compose `include:`, core migration `034_seed_knowledge_extractor_product.sql`. **`check_product_container_shape` GREEN for KE** (validation loop closed). **Container built + brought up + live-verified**: `/api/health` → `{"status":"ok",...}` 200, `Up (healthy)`, `create_product_app` boots + `uvicorn --reload` (runtime-watch develop-inside loop). Dev-prod-parity VINDICATED: a stripped requirements.txt (missing `uvicorn`) passed the venv but failed the container — caught in the real shape, fixed (mirror seed canonical app stack). Migration 034 NOT applied to live Supabase (KE backend-only/no UI; dev+prod share one project → a live tile would link to localhost — applies when KE gets a UI + deploys).
- 2026-05-23 — project opened; grounded the canonical house shape + the two-shape drift; branch created. P1 starting.
- 2026-05-23 — **P2 COMPLETE.** `Settings`→`ProductSettings` subclass (REPO_ROOT depth fixed to `parents[4]`); `create_product_app` boots clean ("Product app 'Knowledge Extractor' created"). **LLM seam SWAPPED** to `noctusai_lib` (transcribe/chat/embeddings re-exported; 4 local adapters deleted). **google_drive/media/vectors = GAPS kept local** + filed `projects/seed-lift-ke-gap-seams/` (vectors/pgvector = high-value cross-product lift). **131/131 tests pass** in a verification venv (seed editables installed). Fixed `test_no_credentials_raises` via a factory contract clarification (None=fallback / ""=assert-no-creds — no monkeypatch). Polish: MASTER-PROMPT §3 seam-status note, kb_ingest docstring, live-db doc self-refs redated. Registration (start.sh + core migration) deferred to P3 (correct — pre-container registration breaks the fleet build). → P3 containerize.
- 2026-05-23 — **P2 FOUNDATION done (review point).** Copied `../knowledge-extractor` → `products/knowledge-extractor/` (source untouched; secrets/venv/data/git excluded). Cleaned non-product artifacts (`.claude`/`.githooks`/`.gitignore`/root-`requirements.txt`); `CLAUDE.md`→`MASTER-PROMPT.md`; re-pinned `backend/requirements.txt` (seed editables + domain deps); added `app/main.py` (`create_product_app`, health-only — backend-only, no SPA) + `settings` singleton; added the 02-LANDSCAPE roster row (8012/—, `knowledge_extractor`). **Hand-ported (not scaffold_product) — accept-with-rationale:** KE is backend-only ∧ already product-shaped; scaffold's FE template would be pure churn. **REMAINING (review → then P3):** (a) `Settings` subclass ProductSettings + boot-verify `create_product_app`; (b) swap the 4 local seams (`google_drive`/`llm`/`media`/`vectors`) → `noctusai_lib` (verify-seed-ships-it per seam); (c) reconcile the 14 tests green; (d) register in `start.sh` PRODUCTS + core seed-row migration (deferred to P3 — registering pre-container would break the fleet build). The `check_product_container_shape` keeper now FLAGS knowledge-extractor (no Dockerfile) = the validation loop, expected; P3 containerizes → green.
- 2026-05-23 — **P1 DONE.** Keeper `check_product_container_shape` (compliance.py, warning; universal markers + frontend-gated SPA markers + compose target/external/tunnel) + 11-case `tests/test_container_shape.py` (meta-detector satisfied; 0 on live fleet). Docs: containerization.md §1a (container-first principle) + absorb Gate 9 (container-first gate + keeper) + new-product.md (in-noc house-model note) + CLAUDE.md §2 pointer. Memory `feedback_container_first` + MEMORY.md. Scaffold wiring = already by-construction (copies seed template; documented, no code change). Fix-on-contact: pre-existing `≫` symbology drift at containerization.md:592 fixed. verify-kb-sync ✓, symbology ✓, compliance score 100, keeper 0-findings. → P2 (absorb knowledge-extractor).
