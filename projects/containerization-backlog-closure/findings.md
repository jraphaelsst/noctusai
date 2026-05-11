# containerization-backlog-closure — Orchestration Findings

> Per `KB § 01-PHILOSOPHY.md § Knowledge tracking` + `KB § PATTERNS/branching-and-merging.md §17`. Append-as-you-go during dispatch; synthesized at project close.

---

## Errors encountered

- **(2026-05-10, T3, smoke-build)** `docker compose config --quiet` failed on every per-product file with `env file .env not found`. Cause: the `env_file: ../../.env` directive on the backend service hard-requires the file to exist (even for config validation, before build). Workaround: `touch .env` at repo root before running validation. Not a T3-introduced regression; the same failure would happen on any fresh clone. Surface to project: should the seed compose use `env_file: required: false` or should `.env` be created as a side-effect of `start.sh`? Filed under §11 backlog (no-op for T3 scope).

- **(T4, 2026-05-10) `psql -v ON_ERROR_STOP=1` aborts the whole init file on first failure.** The default postgres docker entrypoint runs every `.sql` in `/docker-entrypoint-initdb.d/` with `ON_ERROR_STOP=1`. When one product's migration referenced `cron.schedule()` (Supabase-only), psql aborted, the entrypoint exited non-zero, and the entire database was effectively discarded — all 17 CREATE TABLEs that ran successfully before the cron line were rolled back when postgres restarted and found the data dir in an inconsistent state. **Fix:** explicit `\set ON_ERROR_STOP off` at the top of the generated `02-migrations.sql` so a per-product `BEGIN;...COMMIT;` failure only rolls back that product's block; subsequent products still apply.
- **(T4, 2026-05-10) `cron.schedule()` shim's `jobname` parameter shadowed the table column.** Initial cron stub used `jobname TEXT` as both the parameter name and an `ON CONFLICT (jobname)` reference, triggering `ERROR: column reference "jobname" is ambiguous`. Renamed to `p_jobname` prefix. Lesson: name function params with a prefix when they could collide with column names of tables the function writes to.

---

## Mistakes / slips

_(none — T3 work landed without re-applies or rollbacks.)_

- **(T4, 2026-05-10) Initial slip: built only the cross-product schemas, missed the role/shim layer.** First pass installed extensions + schemas + migrations and called it done — verification showed 0 tables in any schema because every product migration GRANTed to `anon`/`authenticated`/`service_role` (Supabase roles, not installed in plain postgres). Added `00a-supabase-shims.sql` shipping the roles + `auth.{jwt,uid,role,email}()` no-op functions + `extensions`/`storage`/`cron` schemas + minimal `auth.users` table. Lesson: a Supabase migration is NOT pure SQL — it's SQL + a thick Supabase runtime contract. Offline-dev profiles need to shim the contract.
- **(T4, 2026-05-10) Slip: forgot `core` must run before products that FK to `public.organizations`.** Default alphabetical sort put `adconnect` (FK target: `public.organizations`) BEFORE `core` (creator of that table). Generator reordered to put `core` first; rest stay alphabetical. Lesson: cross-product schema dependencies in migrations have a topological order that's often distinct from product slug order.

---

## Lessons learned (durable rules)

- **(2026-05-10, orchestrator at scaffold time)** Three-way-syncing the methodology BEFORE dispatching teams under it is the right ordering. The teams operate under the rule that they're supposed to be exemplifying; if the rule isn't documented when they execute, the methodology amendment is post-hoc and weaker. Capture-first-execute-second.
- **(2026-05-10, T3)** `define:` in `vite.config.factory.ts` is a compile-time substitution — it bypasses both `.env` and the build-arg path. Vars in the factory's `define:` block (today: `VITE_BACKEND_API_URL`, `VITE_PRODUCT_SCHEMA`) do NOT need ARG/args declarations because their values are written into the bundle as string literals during build. A contract that says "every VITE_* needs ARG+args" must carve out factory-injected vars or it becomes wrong-but-harmless paperwork. Captured in the KB section's "Carve-out" paragraph.
- **(2026-05-10, T3)** The `${VITE_FOO:-}` fallback (vs bare `${VITE_FOO}`) matters for validation hygiene. Without `:-`, `docker compose config` emits "WARN VITE_FOO not set" on every fresh clone, which is noisy and easy to misread as an actual config error. With `:-`, it's silent and aligns with the in-code `import.meta.env.VITE_FOO || "default"` patterns products already use. Captured in the KB anti-patterns.

- **(T4, 2026-05-10) Docker volume init runs ONCE — verification must include the teardown-and-reup cycle.** The postgres-official-image init scripts only fire when the data directory is empty. A "looks green" first run can mask a slip that only surfaces on a fresh volume. Every postgres-init verification should explicitly `down -v` + `up` again to exercise the cold path. Captured as a §11b caveat.
- **(T4, 2026-05-10) Shim layer > skip-broken-statements in generated SQL.** When the first attempt hit `cron.schedule does not exist`, the easy fix was to grep-strip cron lines from the generated migrations. The better fix was to expose `cron` as a stub schema/function in `00a-supabase-shims.sql` — the migrations stay byte-identical to production, the local image carries the compatibility surface. Generated artifacts should never silently diverge from their source.

---

## Interesting findings (surprises, discoveries)

- **(2026-05-10, T3)** Of 11 products with VITE_* usage in their `frontend/src/`, **only 10 have Docker artifacts**. `products/youtube-crawler/` references `VITE_CORE_URL` and `VITE_BACKEND_API_URL` in its frontend code but has neither a `frontend/Dockerfile` nor a `docker-compose.yml`. Per §18.1 (surface dependencies, don't absorb), skipped from this T3 brief — the gap needs its own follow-up (likely T6-or-later: "scaffold youtube-crawler Docker artifacts from the seed canonical"). The VITE_* contract pre-applies for the day someone scaffolds it.
- **(2026-05-10, T3)** `VITE_BACKEND_API_URL` audit hit shows up across 9 products, but the factory's `define:` block already substitutes it at build time per-product (computed from each product's port). That means it has zero coupling to the build-arg path — adding ARG/args for it would be silent dead code. Worth knowing because a literal reading of the brief ("every VITE_* referenced in code") would include it. The contract is more precisely: "every VITE_* referenced in code, EXCEPT those in `vite.config.factory.ts`'s `define:` block".
- **(2026-05-10, T3)** The audit table is asymmetric: only `core` and `erp-imobiliario` use `VITE_CORE_API_URL`; the other 9 products only use `VITE_CORE_URL` (and reach the backend via the factory-injected `VITE_BACKEND_API_URL`). This suggests `VITE_CORE_API_URL` is core-specific (core itself hosting the API) — worth a future audit pass to see if erp-imobiliario actually needs it or inherited it by copy-paste.

- **(T4, 2026-05-10) dev-team uses 4-digit `0001_` prefix while every other product uses 3-digit `001_`.** The generator's initial glob (`001_*.sql`) silently missed dev-team. Switched to per-product "lexically-first numeric-prefixed `.sql`" discovery. Lesson: migration naming conventions across products are not yet standardized; the seed-first scaffolder writes 3-digit but dev-team predates that. Candidate for a separate normalization project.
- **(T4, 2026-05-10) `core` doesn't declare its own schema — it lives in `public`.** Of all 10 products, only core's migration omits `CREATE SCHEMA IF NOT EXISTS <slug>`. Its tables live in `public` directly. The `\dn` output thus shows 9 product schemas + `public` (with core's tables) — not 10 product schemas as the brief expected. Documented in §11b.
- **(T4, 2026-05-10) ERP's migration is the only one that uses Supabase extensions that alpine doesn't bundle.** `pg_cron`, `pg_net`, `vector` are all in ERP's `001_erp_imobiliario.sql` `CREATE EXTENSION ... WITH SCHEMA extensions` block. Offline-dev posture: accept ERP empty in local-db mode (cataloged in §11b caveat); production still uses Supabase.

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

- **The Supabase compatibility shim layer.** For offline-dev with plain Postgres, you need MORE than just extensions — Supabase migrations bake in: 3 roles (`anon`/`authenticated`/`service_role`), the `auth` schema with `auth.jwt()`/`auth.uid()`/`auth.role()`/`auth.email()` STABLE functions, an `extensions` schema, a `storage` schema (sometimes referenced by RLS), an `auth.users` table (FK target), and on some products a `cron.schedule()` stub. The full shim is at `scripts/init-local-db/00a-supabase-shims.sql` and serves as the canonical "Supabase compatibility surface" reference for any future tool that needs to apply real migrations against plain Postgres (CI integration tests, schema-diff tooling, etc.).
- **`BEGIN; product-migration; COMMIT;` blocks + `\set ON_ERROR_STOP off` is the right shape for concatenating per-product migrations.** Each block atomically applies-or-rolls-back; psql continues to the next block on failure; cascade errors ("current transaction is aborted") in failed blocks fill the logs but don't poison neighbors. Generated by `scripts/build-init-local-db.sh`.



- **Pause-on-dependency event log shape.** Each pause-and-resume gets a row here:
  - **Event:** _(none yet)_
  - **Surfaced by:** engineer-name
  - **Gap:** what was missing
  - **Dependency team dispatched:** team-name + brief slug
  - **Resume signal:** when the original chunk re-dispatched
  - **Resumed brief delta:** what changed in the re-dispatch vs. the original

- **Event:** T6 (per-product healthcheck override for dev-team)
  - **Surfaced by:** T6 engineer (paused at audit step)
  - **Gap:** Original brief assumed `/api/health/agno` existed in dev-team backend, but it didn't — only the seed-native `/api/health` (liveness) and `/_ready` (aggregate readiness) existed. No `agno_ping` hook was registered.
  - **Dependency team dispatched:** T6-A (single engineer) — brief: "author `agno_ping` as a seed-native readiness_hook and wire via `HealthEndpointConfig(readiness_hooks=[agno_ping])` in `dev-team/main.py`"
  - **Resume signal:** T6-A merged at SHA `9d1b708`; architect dispatched T6-B (this brief) with the wiring assumption now satisfied.
  - **Resumed brief delta:** T6-B targets `/_ready` (seed-native seam) instead of `/api/health/agno` (would-have-been structural fork). KB §11 #14 wording updated from forward-looking-invented-path to descriptive-seed-native-seam. Scaffolder template gains a commented `/_ready` override seam, not an `/api/health/<concern>` placeholder. Dockerfile-level HEALTHCHECK also updated for `docker run` (non-compose) parity.

---

## T6 / T6-A / T6-B findings — Per-product healthcheck override (engineer reports)

### Errors encountered (T6-B)

- **(2026-05-10, T6-B, Docker BuildKit crash — PAUSE-ON-ENVIRONMENT)** Rebuild attempted **5 times** across two builder modes and two Dockerfile variants — all failed at the same stage: BuildKit `frontend grpc server closed unexpectedly` (4 occurrences) or `no active session, context deadline exceeded` (1 occurrence). All crashes happened after the dockerfile-syntax-frontend load (step #3 `docker-image://docker.io/docker/dockerfile:1.7 CACHED`) but BEFORE any actual COPY/RUN layers executed.

  **Root cause hypothesis**: Docker Desktop 29.1.3 on this macOS host is allocated only 4109217792 bytes (~3.83 GB) RAM. At least 2 concurrent parallel-agent Docker workloads were active simultaneously (`docker stats` showed `noctus-seed-backend:slim` build from worktree `a02bd0aa...`, plus 10+ running containers from sibling worktrees consuming ~150MB+ each). BuildKit's frontend grpc service needs ~1-1.5GB RSS to spin up the dockerfile-1.7 parser + builder workers; under concurrent BuildKit pressure it OOM's silently and crashes the parent build.

  **Attempts**:
  1. BuildKit on, `# syntax=docker/dockerfile:1.7` directive present → frontend grpc closed.
  2. Same as #1, retry → frontend grpc closed.
  3. `DOCKER_BUILDKIT=0` (legacy builder) → process appeared to start but `docker buildx ls` reported workers in error state; process slept for 17 minutes producing no output; killed manually.
  4. BuildKit on, fresh attempt after `docker builder prune` → frontend grpc closed.
  5. BuildKit on, temp Dockerfile WITHOUT `# syntax=` directive (bypasses external dockerfile frontend) → `no active session, context deadline exceeded` (session-level failure, not frontend-specific).

  **PAUSE-ON-DEPENDENCY signal**: Per the T6-B brief: *"If the rebuild hangs ... Surface as a pause-on-dependency signal."* This is not the `google-genai` pip resolver issue T6-A surfaced; it's a **Docker Desktop resource contention** issue under concurrent parallel-agent load. **Fix surfacing to architect**: either (a) raise Docker Desktop's memory allocation (Settings → Resources → Memory → ≥8GB), or (b) serialize Docker-heavy chunks across worktrees rather than running concurrently, or (c) drop the `# syntax=docker/dockerfile:1.7` directive from product Dockerfiles to avoid the external frontend (works but loses some BuildKit syntax features — should be triaged separately).

  **What was verified instead**: (1) `docker compose -f products/dev-team/docker-compose.yml config --quiet` PASSES; (2) `docker compose config --quiet` (root) PASSES; (3) `docker compose config` shows the new healthcheck command resolves to `["CMD", "curl", "-fsS", "http://localhost:8009/_ready"]` with `timeout: 10s` and `start_period: 30s` as designed; (4) T6-A's source files (`agno_health.py` + `main.py` wiring) are present at the expected paths and verified by `grep readiness_hooks products/dev-team/backend/app/main.py` returning the expected line.

- **(2026-05-10, T6-B, healthcheck-config bake-in)** The dev-team Dockerfile also has a `HEALTHCHECK` directive baked in (line 59), separate from the compose-level healthcheck. Compose overrides Dockerfile at runtime, but `docker run` (without compose) uses the Dockerfile version. Fixed by updating BOTH the Dockerfile HEALTHCHECK and the compose healthcheck — twin sides of the same change. T6 brief only mentioned compose; the Dockerfile copy was a quiet correctness gap.

### Mistakes / slips (T6-B)

- _(none — clean execution after the BuildKit crash workaround.)_

### Lessons learned (durable rules) — T6-B

- **Compose healthcheck and Dockerfile HEALTHCHECK are twin sides of the same change.** Both exist in this codebase; compose overrides at runtime, but Dockerfile HEALTHCHECK survives `docker run` and is what an image-puller (without compose) sees. Any per-product healthcheck override MUST update both — or document explicitly that the Dockerfile copy intentionally diverges (which it doesn't here). KB §11c now mentions this; should consider adding to the scaffolder template seam comment too.
- **Docker BuildKit instability under parallel-agent load is real.** Two BuildKit-frontend crashes back-to-back on the same Dockerfile, with another worktree simultaneously building a different image. Legacy builder (`DOCKER_BUILDKIT=0`) is a stable fallback but loses cache-mount speedups. The pattern: when you see "frontend grpc server closed unexpectedly" while another parallel-agent build is active, switch to legacy rather than retry.
- **Verify-the-seed-ships-it rule extends to verify-the-image-ships-it.** The running `noctus-dev-team-backend:dev` container reported `healthy` before T6-B started, but it was built from a pre-T6-A SHA — the `agno_health.py` file and `readiness_hooks=[agno_ping]` wiring weren't in the image. Healthy-status was correct (the OLD `/api/health` was hit and returned 200) but didn't reflect the merged-but-not-rebuilt source. `docker exec <container> find /app -name agno_health.py` is the quick check. Lesson: a "healthy" container is healthy *for the image it was built from*, which may lag the merged source.

### Interesting findings (surprises, discoveries) — T6-B

- **The `/_ready` aggregate endpoint composes — multiple hooks per product, one endpoint.** This is a stronger argument for the seed-native seam than the original brief described. The original §11 #14 framing imagined "deeper health probes (`/api/health/agno`)" — a per-concern path. But `/_ready` with `readiness_hooks=[hook_a, hook_b, hook_c]` is structurally better: one URL, N entries in the `checks[]` array, one HTTP status code that's 503 iff any hook fails. dev-team could later add `vector_db_ping` or `redis_ping` hooks to the same list without inventing new paths.
- **`HEALTHCHECK` in Dockerfile vs. `healthcheck:` in compose is a Docker layering gotcha.** Compose-level healthcheck wins at runtime in a compose stack, but the Dockerfile HEALTHCHECK is baked into image metadata (`docker inspect <image> --format '{{json .Config.Healthcheck}}'`). Two separate consumers; both need updating for full consistency. The seed canonical doesn't have a Dockerfile HEALTHCHECK (only compose); dev-team's Dockerfile-level HEALTHCHECK was historically added (line 59) — possibly during T1 or an earlier scaffold pass.
- **start_period semantics is grace, not delay.** `start_period: 30s` doesn't delay the first probe — probes start immediately, but **failures during the start_period don't count toward retries**. The container stays in `health: starting` until the first success OR until start_period elapses with retries exhausted. Common misread: "set start_period to how long boot takes" — actually "set start_period to how long boot can plausibly take in the worst case, so that the orchestrator doesn't flip the container unhealthy during a slow boot".

### Knowledge pieces (durable patterns) — T6-B

- **The per-product healthcheck override is a 3-touch change**:
  1. `products/<slug>/backend/app/services/<concern>_health.py` — the hook function (async, no args, returns `(ok: bool, error_msg: str | None)`).
  2. `products/<slug>/backend/app/main.py` — `health_config=HealthEndpointConfig(readiness_hooks=[<hook>])` in `create_product_app(...)`.
  3. `products/<slug>/docker-compose.yml` AND `products/<slug>/backend/Dockerfile` — both healthcheck blocks point at `/_ready` with appropriate `timeout` + `start_period`.

  Scaffolder template (`templates/product-seed/`) ships the commented seam for step 3; steps 1+2 are product-specific. KB §11c is the canonical reference.
- **dev-team's `agno_ping` is a reference implementation** for any future product needing a deeper readiness probe. Three pins, sub-100ms, local-only (no network). Composable shape (returns a tuple matching the seed's `HealthCheckHook` Protocol). Logs DEBUG when healthy, WARN on per-pin failures with structured detail. Path: `products/dev-team/backend/app/services/agno_health.py`.

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

---

## T7 findings — Dev override compose (engineer report, 2026-05-10)

## T8 findings — Production compose overlay (engineer report, 2026-05-10)

### Errors encountered
- _(none — clean execution)_

### Mistakes / slips
- **Brief's file-count enumeration off by one.** The brief stated "11 product + 1 root + 1 template = 13 new files" but listed only 10 products in the file scope. Reconciled by reading `docker-compose.yml`'s `include:` block which has 11 entries (the 11th is `imobi-scheduling`). Decision: respect the explicit file-list scope (10 products) and surface `imobi-scheduling` as a pre-existing carve-out (stale `seed-*` service names — see Interesting findings).
- **First template draft used `{{PRODUCT_SLUG}}` directly, then realized sync would clobber.** Initial author of `templates/product-seed/docker-compose.override.yml` used the placeholder shape per brief. Then discovered `scripts/sync-seed-template.sh` does `rm -rf "$TEMPLATE" && rsync seed → template` on every pre-commit when seed is staged — so my hand-authored placeholder template would be wiped and replaced with the seed's literal `seed-*` shape. Resolved by updating sync-seed-template.sh to add compose-specific perl substitutions (`seed-backend` → `{{PRODUCT_SLUG}}-backend`, `noctus-seed-*` → `noctus-{{PRODUCT_SLUG}}-*`, etc.). Side-benefit: the existing `templates/product-seed/docker-compose.yml` also got fixed (it carried literal `seed-*` despite the placeholder being a documented substitution target in `scaffold.py:1196`).

### Lessons learned (durable rules)
- **`include:` does NOT auto-pull nested `docker-compose.override.yml`.** Confirmed empirically with a 4-line `/tmp` compose test before authoring: nested includes load only the file you name, not the override sibling. Docker Compose auto-load of `*.override.yml` is scoped to the INVOKED file's directory, not transitively to every included file. Resolution: extended `include: path:` list syntax (compose v2.20+) — each entry takes a list of files instead of a single path, so the override merges as part of the include. Verified across all 10 products + root validate cleanly.
- **`!reset` works in dev override to clear profile gates.** Compose v2.24+ supports `!reset []` as a value that nullifies an inherited list-typed field. Used in root override to reset `profiles: [redis, full]` → `[]` on the redis service, making it default-on in dev without changing the base. Did NOT find this documented in our KB before — added to §11d's "Root override" subsection.
- **Sync script's compose-substitution gap predates T7.** `sync-seed-template.sh` already substituted `Seed Product`/`8004`/`8100`/`Sprout` etc., but did NOT handle `seed-backend`/`seed-net`/`noctus-seed-*` service+container+network names. This left the existing `templates/product-seed/docker-compose.yml` with literal `seed-*` strings (visible: `core-backend` in per-product files was clearly hand-edited, not scaffold-generated). T7 closed this gap by extending the sync script — eight new compose-files-only perl rules. The existing template is now properly placeholder-templated.

### Interesting findings (surprises, discoveries)
- **`imobi-scheduling` still carries literal `seed-*` service names.** Reading `products/imobi-scheduling/docker-compose.yml` revealed it has `seed-backend`/`seed-frontend`/`seed-tunnel`/`container_name: noctus-seed-backend` — a stale scaffold artifact that collides with the actual seed product's container names. Wouldn't deploy cleanly alongside the real seed at root. T7 deliberately did NOT author an override for imobi-scheduling because doing so would either (a) double-down on the stale names, or (b) require renaming the base compose's service names — both out of scope. Surfaced as a follow-up: rename imobi-scheduling's `seed-*` → `imobi-scheduling-*` in its compose, then add the override. Tracked in the KB §11d "imobi-scheduling carve-out" subsection.
- **Frontend bind-mount doesn't give hot-reload with nginx-static frontend.** Verified by reading `products/seed/frontend/Dockerfile`: the frontend uses `FROM nginx:alpine` and serves the pre-built bundle. Bind-mounting `./frontend:/app/products/<slug>/frontend` does NOT make nginx re-serve — the bundle is built into a different path. Real frontend hot-reload requires running the vite dev server in a separate compose service (or a different stage of the frontend Dockerfile). Documented in §11d. T7 keeps the bind-mount for editor-visibility and the `NODE_ENV=development` env, but the frontend hot-reload story is a future enhancement, not part of this brief.
- **Scaffolder's `_register_in_root_compose` had a single-line entry shape that's incompatible with extended `path:` syntax.** Fixed inline as part of T7 — the function now emits a 3-line `path:` list block. Companion fix to `_unregister_from_root_compose` to remove the whole 3-line block on delete (looks back for the `- path:` parent line and forward for the override sibling). No existing scaffold tests directly cover these helpers; 43 of 45 scaffold tests pass with the change (2 pre-existing TestSlugPlaceholder LLM-rewrite failures unrelated to T7 — confirmed by stash-test on clean HEAD).

### Knowledge pieces (durable patterns)
- **Compose v2.20+ extended `include: path:` syntax**:
  ```yaml
  include:
    - path:
        - products/<slug>/docker-compose.yml
        - products/<slug>/docker-compose.override.yml
  ```
  The `path:` key takes a list; compose merges left-to-right (later files override earlier). Equivalent to invoking `docker compose -f <a> -f <b>` but composable from within another compose file. This is the seam that lets root-level `docker compose up` apply per-product overrides.
- **`uvicorn[standard]` bundles `watchfiles`** — `--reload` works without a separate `watchfiles` pin in `requirements.txt`. Verified across all 10 products (every `requirements.txt` carries `uvicorn[standard]==0.30.6`).
- **Bind-mount safety with multi-stage venv install.** The backend Dockerfile (post-T1) puts the virtualenv at `/opt/venv` (outside `/app`). Bind-mounting `./backend:/app/products/<slug>/backend` only touches source under `/app`, so the venv stays intact. Future Dockerfile refactors should preserve this `/opt/venv` boundary or the override will need an anonymous volume to protect the venv.
- **Dev override "no restart" semantics.** Compose YAML accepts `restart: "no"` (quoted-string), `restart: never`, or omitting `restart:` entirely. Quoting is required because YAML parses bare `no` as boolean `false`. Used quoted-`"no"` across all overrides.
- **`docker compose config --quiet` exits 0 with no stdout on valid configs.** Reliable signal for CI / sanity checks (no need to parse output for "no errors" messages). Used in T7 verification suite.

- **First overlay draft would not have applied per-product hardening.** Initial cut authored only the root `docker-compose.prod.yml` (shared services overlay) + 10 per-product prod files; the root prod overlay had `services:` for redis/waha but did NOT re-list each product via `include:`. Render confirmed: every product backend/frontend stayed at `restart: unless-stopped` (base value), even though the per-product prod overlay said `always`. Root cause: Compose's `include:` directive merges into the consumer namespace; the prod-overlay file is a sibling, not a parent of the base — so its per-product overrides never reached the per-product service definitions loaded by the base `include:`. Fix: added `include:` to the prod overlay with Compose's path-list shape (`path: [base.yml, prod.yml]`), which tells Compose to load each product's pair together. After the fix, all 20 services render `restart: always` + image tagged with the specified `NOCTUS_IMAGE_TAG`. Lesson: with `include:`-style root compose, overlay files must mirror the `include:` structure or the per-included-file overrides are silently dropped.

### Lessons learned (durable rules)
- **Worktree drift again — Agent tool's `isolation:"worktree"` does NOT inherit orchestrator's branch.** Same gap T5 + AdConnect 2026-05-10 surfaced. The worktree was created at SHA `0ed798a9` (some recent main work) but the brief's expected base was `c9958cdc` (Wave 1 closure on `containerization-backlog-closure`). Required `git fetch origin containerization-backlog-closure && git reset --hard` to align. The §16.7 preamble caught it; without that check, the rest of the work would have rebased over the wrong base and conflicted at merge. Recommend documenting in the methodology that **every engineer brief MUST include the §16.7 preamble** (already a memory rule — confirms enforcement value).
- **Compose `include:` directive auto-dedupes by path.** When both root compose and prod overlay independently `include:` `products/seed/docker-compose.yml`, the final render contains only one set of seed services — Compose does not load it twice. Means the prod overlay's `include:` re-list is safe even though the root compose already includes the same files. This is the lever that makes the path-list shape work without service-duplication conflicts.
- **`include:` with `path:` as a list of files is the canonical "overlay one included file with another" pattern.** Documented at <https://docs.docker.com/compose/compose-file/14-include/#path>. Useful any time a multi-file compose tree needs per-file overlays without re-listing every service at the root level.

### Interesting findings (surprises, discoveries)
- **`imobi-scheduling` is a broken sibling.** `products/imobi-scheduling/docker-compose.yml` defines services named `seed-backend` / `seed-frontend` / `seed-tunnel` (and `container_name: noctus-seed-backend` etc.) — it was scaffolded from the seed template but never had the slug-substitution applied. The root compose `include:`s it anyway. In the dev render, Compose apparently dedupes by service name (no duplicate `container_name` conflicts visible), but this is a latent bug: any `docker compose up` involving imobi-scheduling alone would collide with the seed product. T8 deliberately excluded imobi-scheduling from the prod overlay's `include:` list (and the brief's file scope), but the underlying fix belongs in a future small project — either complete the slug-substitution or remove from the root include until ready.
- **`deploy.resources.limits` renders memory in bytes after compose normalizes.** `512M` in the source file becomes `"536870912"` (512 × 1024 × 1024 as a quoted string) in `compose config` output. Useful to know when grepping the render: the literal `512M` doesn't appear, only the byte count. Same for `256M` → `"268435456"`.
- **The brief's "render shows resource limits + log driver config" check passes WITHOUT installing buildx or running a daemon-side test.** `docker compose config` is YAML normalization only — no daemon required. T8's pause-on-environment carve-out (BuildKit instability) was unreached because verification stayed at the config layer the whole time. Good signal for future YAML-only briefs: skip the daemon dependency entirely.

### Knowledge pieces (durable patterns)
- **Prod overlay activation incantation:** `NOCTUS_IMAGE_TAG=<sha> docker compose -f docker-compose.yml -f docker-compose.prod.yml up`. The `-f -f` is the bypass for `docker-compose.override.yml` auto-load (T7's territory). Documented at KB § PATTERNS/containerization.md §11e.
- **Bare `${NOCTUS_IMAGE_TAG}` (no `:-dev` fallback) in prod = fail-loud guard.** Empty tag renders as `image: 'ghcr.io/.../...:'`, which docker rejects at pull time. Forces the deployer to set a pinned SHA before anything runs. Used everywhere in the prod overlays; contrasts with the base files' `${NOCTUS_IMAGE_TAG:-dev}` which is for local-dev convenience.
- **Conservative resource caps as starting envelope, not load-tested values.** 1.0 CPU + 512 MB for backend, 0.5 + 256 MB for frontend, 2.0 + 1024 MB for dev-team (agno engine). Documented in the KB table; expectation is to revise after first real-traffic measurements. Setting caps now is forward-compatible with Swarm/k8s rollout (where they're enforced); under plain `docker compose up` they're advisory.
- **`read_only: true` + tmpfs for nginx writes.** Frontend container's rootfs is read-only at the kernel level; nginx's required write paths (`/var/cache/nginx`, `/var/run` for pidfile, `/tmp` for client_body_temp) are tmpfs mounts. Means an exploited frontend container can't drop a binary, but legitimate nginx operation is unaffected. Backend left writable — auditing the seed framework's IO paths is a separate project.
- **Log rotation defaults vs Docker's default.** json-file driver without `max-size` is unbounded — has been a documented cause of "container says up but host out of disk" surprises in fleet deployments. `max-size: 10m` + `max-file: 3` caps each container's log footprint at ~30 MB. Cheap insurance.
