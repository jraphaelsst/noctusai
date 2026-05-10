# containerization-backlog-closure — Orchestration Findings

> Per `KB § 01-PHILOSOPHY.md § Knowledge tracking` + `KB § PATTERNS/branching-and-merging.md §17`. Append-as-you-go during dispatch; synthesized at project close.

---

## Errors encountered

- **(2026-05-10, T3, smoke-build)** `docker compose config --quiet` failed on every per-product file with `env file .env not found`. Cause: the `env_file: ../../.env` directive on the backend service hard-requires the file to exist (even for config validation, before build). Workaround: `touch .env` at repo root before running validation. Not a T3-introduced regression; the same failure would happen on any fresh clone. Surface to project: should the seed compose use `env_file: required: false` or should `.env` be created as a side-effect of `start.sh`? Filed under §11 backlog (no-op for T3 scope).

---

## Mistakes / slips

_(none — T3 work landed without re-applies or rollbacks.)_

---

## Lessons learned (durable rules)

- **(2026-05-10, orchestrator at scaffold time)** Three-way-syncing the methodology BEFORE dispatching teams under it is the right ordering. The teams operate under the rule that they're supposed to be exemplifying; if the rule isn't documented when they execute, the methodology amendment is post-hoc and weaker. Capture-first-execute-second.
- **(2026-05-10, T3)** `define:` in `vite.config.factory.ts` is a compile-time substitution — it bypasses both `.env` and the build-arg path. Vars in the factory's `define:` block (today: `VITE_BACKEND_API_URL`, `VITE_PRODUCT_SCHEMA`) do NOT need ARG/args declarations because their values are written into the bundle as string literals during build. A contract that says "every VITE_* needs ARG+args" must carve out factory-injected vars or it becomes wrong-but-harmless paperwork. Captured in the KB section's "Carve-out" paragraph.
- **(2026-05-10, T3)** The `${VITE_FOO:-}` fallback (vs bare `${VITE_FOO}`) matters for validation hygiene. Without `:-`, `docker compose config` emits "WARN VITE_FOO not set" on every fresh clone, which is noisy and easy to misread as an actual config error. With `:-`, it's silent and aligns with the in-code `import.meta.env.VITE_FOO || "default"` patterns products already use. Captured in the KB anti-patterns.

---

## Interesting findings (surprises, discoveries)

- **(2026-05-10, T3)** Of 11 products with VITE_* usage in their `frontend/src/`, **only 10 have Docker artifacts**. `products/youtube-crawler/` references `VITE_CORE_URL` and `VITE_BACKEND_API_URL` in its frontend code but has neither a `frontend/Dockerfile` nor a `docker-compose.yml`. Per §18.1 (surface dependencies, don't absorb), skipped from this T3 brief — the gap needs its own follow-up (likely T6-or-later: "scaffold youtube-crawler Docker artifacts from the seed canonical"). The VITE_* contract pre-applies for the day someone scaffolds it.
- **(2026-05-10, T3)** `VITE_BACKEND_API_URL` audit hit shows up across 9 products, but the factory's `define:` block already substitutes it at build time per-product (computed from each product's port). That means it has zero coupling to the build-arg path — adding ARG/args for it would be silent dead code. Worth knowing because a literal reading of the brief ("every VITE_* referenced in code") would include it. The contract is more precisely: "every VITE_* referenced in code, EXCEPT those in `vite.config.factory.ts`'s `define:` block".
- **(2026-05-10, T3)** The audit table is asymmetric: only `core` and `erp-imobiliario` use `VITE_CORE_API_URL`; the other 9 products only use `VITE_CORE_URL` (and reach the backend via the factory-injected `VITE_BACKEND_API_URL`). This suggests `VITE_CORE_API_URL` is core-specific (core itself hosting the API) — worth a future audit pass to see if erp-imobiliario actually needs it or inherited it by copy-paste.

---

## Knowledge pieces (durable patterns)

### T3 audit table (final, 2026-05-10)

| Product | VITE_* in code | Of which need ARG+args | Patched? |
|---|---|---|---|
| adconnect | VITE_BACKEND_API_URL, VITE_CORE_URL | VITE_CORE_URL | ✅ |
| core | VITE_CORE_API_URL | VITE_CORE_API_URL | ✅ |
| daily-life | VITE_BACKEND_API_URL, VITE_CORE_URL | VITE_CORE_URL | ✅ |
| dev-team | VITE_CORE_URL | VITE_CORE_URL | ✅ |
| erp-imobiliario | VITE_BACKEND_API_URL, VITE_CORE_API_URL, VITE_CORE_URL | VITE_CORE_API_URL, VITE_CORE_URL | ✅ |
| mailing | VITE_BACKEND_API_URL, VITE_CORE_URL | VITE_CORE_URL | ✅ |
| media-scheduling | VITE_BACKEND_API_URL, VITE_CORE_URL | VITE_CORE_URL | ✅ |
| personal-finance | VITE_BACKEND_API_URL, VITE_CORE_URL | VITE_CORE_URL | ✅ |
| seed (canonical) | VITE_BACKEND_API_URL, VITE_CORE_URL | VITE_CORE_URL | ✅ |
| therapy-platform | VITE_BACKEND_API_URL, VITE_CORE_URL | VITE_CORE_URL | ✅ |
| youtube-crawler | VITE_BACKEND_API_URL, VITE_CORE_URL | VITE_CORE_URL | ⛔ no Docker artifacts — separate gap |

`VITE_BACKEND_API_URL` + `VITE_PRODUCT_SCHEMA` are factory-injected via `define:` in `seed/framework/frontend/vite.config.factory.ts` — they don't need the ARG/args bridge.

### Pause-on-dependency event log

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
