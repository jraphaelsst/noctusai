# containerization-backlog-closure — Orchestration Findings

> Per `KB § 01-PHILOSOPHY.md § Knowledge tracking` + `KB § PATTERNS/branching-and-merging.md §17`. Append-as-you-go during dispatch; synthesized at project close.

---

## Errors encountered

_(none yet — Wave 1 dispatch pending)_

---

## Mistakes / slips

_(none yet)_

---

## Lessons learned (durable rules)

- **(2026-05-10, orchestrator at scaffold time)** Three-way-syncing the methodology BEFORE dispatching teams under it is the right ordering. The teams operate under the rule that they're supposed to be exemplifying; if the rule isn't documented when they execute, the methodology amendment is post-hoc and weaker. Capture-first-execute-second.

---

## Interesting findings (surprises, discoveries)

_(none yet)_

---

## Knowledge pieces (durable patterns)

- **Pause-on-dependency event log shape.** Each pause-and-resume gets a row here:
  - **Event:** _(none yet)_
  - **Surfaced by:** engineer-name
  - **Gap:** what was missing
  - **Dependency team dispatched:** team-name + brief slug
  - **Resume signal:** when the original chunk re-dispatched
  - **Resumed brief delta:** what changed in the re-dispatch vs. the original

---

## Wave-by-wave speed-gain log (per `feedback_TEMP_methodology_validation_in_progress.md`)

| Wave | Engineers | Wall-clock parallel | Estimated serial | Speed gain | Tokens | Notes |
|---|---|---|---|---|---|---|
| 1 | 6 | _pending_ | _pending_ | _pending_ | _pending_ | T1-T6: backend Dockerfile / frontend / VITE args / postgres / registry / healthcheck |
| 2 | 2 | _pending_ | _pending_ | _pending_ | _pending_ | T7-T8: dev override / prod overlay |
| 3 | 1 | _pending_ | _pending_ | _pending_ | _pending_ | T9: CI workflow (matrix + registry push + scan) |
| **Cumulative** | **9** | **pending** | **pending** | **pending** | **pending** | First orchestration under §18 wave-dispatch methodology |

This is the first orchestration under the new §18 methodology. Track diligently for the validation log.

---

## T5 findings — Per-product registry strategy (engineer report, 2026-05-10)

### Errors encountered
- _(none — clean execution)_

### Mistakes / slips
- **Initial template `image:` substitution used `{{PRODUCT_SLUG}}`, corrected to literal `seed`.** First edit on `templates/product-seed/docker-compose.yml` put `{{PRODUCT_SLUG}}` into the image path, breaking the template's existing convention (every other identifier in that file uses literal `seed` — `seed-backend` service name, `noctus-seed-backend` container_name, `seed-net` network, `products/seed/backend/Dockerfile` path). Reverted to `noctus-seed-backend` to match the convention. Lesson: when editing a template, audit ALL substitution markers in the file FIRST — the existing pattern dictates the right placeholder.

### Lessons learned (durable rules)
- **Worktree HEAD drift between worktree-add and engineer dispatch.** The Agent tool's `isolation:"worktree"` was supposed to create from main, but this worktree started at a non-base SHA (`2f2a1b4` — recent unrelated merges from personal-finance/strict-mode-migration). Required an explicit `git fetch origin containerization-backlog-closure && git reset --hard` to align to the expected base. Confirms the §16.7 preamble's value — verify HEAD on every dispatch. Architect should consider whether to push-first when there's any chance the orchestrator's branch advanced after the worktree was carved.
- **`.env.example` did not exist at repo root yet.** Per-product `docker-compose.yml` files reference `env_file: ../../.env`, but noc never shipped a root `.env.example` template. T5 created it as part of in-scope work (brief authorized it explicitly) — the slot for `GHCR_USERNAME` / `GHCR_TOKEN` motivated the file but it now also documents the Supabase/LLM/WAHA/Vite slots. Could be flagged as a future small lift: make `.env.example` the canonical contract for what every product expects in `.env`.

### Interesting findings (surprises, discoveries)
- **Template-side `image:` doesn't need `{{PRODUCT_SLUG}}` substitution.** Even though `scaffold.py` knows how to substitute `{{PRODUCT_SLUG}}`, the template uses literal `seed` in `image:` paths and relies on a downstream tool/manual edit for the `seed → <slug>` swap (visible in how `core/docker-compose.yml` exists with `core-backend` everywhere). The same convention applies to my new registry-path edit — kept literal `seed`, will be swapped by whatever mechanism handles the rest.
- **`sync-seed-template.sh` only touches `templates/product-seed/`, not `products/seed/`.** The pre-commit hook syncs `products/seed/ → templates/product-seed/` (script step 1 of pre-commit). My edits to both `products/seed/docker-compose.yml` AND `templates/product-seed/docker-compose.yml` are parity-aligned so the sync is a no-op.

### Knowledge pieces (durable patterns)
- **`${NOCTUS_IMAGE_TAG:-dev}` shell-style interpolation in Compose.** Docker Compose evaluates `${VAR:-default}` at compose-parse time (not at runtime). Means: locally, `docker compose build` with `NOCTUS_IMAGE_TAG` unset produces a `:dev`-tagged image; in CI, exporting `NOCTUS_IMAGE_TAG=$(git rev-parse --short HEAD)` produces a SHA-tagged image. No runtime cost, no Dockerfile changes, no compose-file-per-environment.
- **Per-product registries chosen over monorepo with prefix.** User decision locked at §11 #10 annotation: each product gets its own GHCR namespace (`ghcr.io/jraphaelsst/noctus-<slug>-<role>`). Rationale: per-product access control, per-product retention policies, per-product publication cadence, aligns with the product-folder boundary used everywhere else. Documented at KB § PATTERNS/containerization.md §11a.
- **Container_name preservation discipline.** The brief explicitly called out "Don't change `container_name:`" as a common pitfall — and confirmed by the changes: only the `image:` line moves to the registry path; `container_name: noctus-<slug>-<role>` stays as the friendly local-docker name. Two separate identifiers serve two separate purposes (registry tagging vs local docker daemon name).
