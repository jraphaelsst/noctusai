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
