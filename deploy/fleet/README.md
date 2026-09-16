# NoctusAI fleet — PRODUCTION deploy runbook

The production deploy of the 8-product NoctusAI fleet onto **one VPS**, from
slim `runtime` images pulled from GHCR, behind a Cloudflare **named** tunnel.

This `deploy/fleet/` layer is one of three on the shared external network
`noctus-net`:

| Layer | Dir | What it is |
|---|---|---|
| **fleet** (this) | `deploy/fleet/` | the 8 product containers + Redis/WAHA infra |
| **tunnel** | `deploy/tunnel/` | the Cloudflare **named** tunnel (hostname → `http://<service>:<port>`) |
| **legacy** | `deploy/legacy/` | the pre-existing legacy app container |

All three join `noctus-net`, so the tunnel reaches every product by service
name with **no host ports published**.

---

## ⚠️ CRITICAL — `VITE_*` Supabase vars are baked at BUILD time

The frontend is a Vite SPA. Vite **inlines** `import.meta.env.VITE_*` into the
JS bundle **at build time** — they are NOT read at container runtime. So:

- `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, and the per-product
  `VITE_CORE_URL` / `VITE_CORE_API_URL` **MUST be set in the build/CI
  environment when `build-and-push.sh` runs**.
- Setting them only in the VPS `.env` is **too late** — an image built with
  empty `VITE_SUPABASE_*` ships a frontend that throws a configured-error page
  (blank app), and no amount of runtime env fixes it. You must **rebuild**.
- Backend-side config (`SUPABASE_URL`, service keys, `ANTHROPIC_API_KEY`,
  `REDIS_URL`, OAuth secrets, …) IS read at runtime from the root `.env` via
  `env_file` — only the `VITE_*` browser-public bridge is build-time.

> One Supabase project bridges build-time (`VITE_SUPABASE_*` → bundle) and
> runtime (`SUPABASE_URL` + service key → backend). Same project, two surfaces.

---

## Step 0 — one-time VPS prep

```bash
# external shared network (fleet + tunnel + legacy all join it)
docker network create noctus-net

# root .env on the VPS — runtime config + secrets for env_file
#   SUPABASE_URL=... + service key, ANTHROPIC_API_KEY=..., REDIS_URL=...,
#   WAHA_* (only if using WhatsApp), OAuth client secrets, etc.
#   (VITE_* values are NOT consumed here — they were baked at build time.)
cp .env.example .env && $EDITOR .env

# pin the image tag you intend to run (default :latest — moves ONLY on a
# prod-ref build, KB § GUIDES/production-deploy.md § 2b; pin a git-sha for
# an immutable, rollback-able deploy; :edge is the non-fleet-facing
# convenience tag a bare `main` build pushes for manual testing)
echo 'NOCTUS_IMAGE_TAG=<git-sha-or-latest>' >> .env
```

### 🔴 `deploy/fleet/.env` — required, and NOT the same file as the root `.env`

```bash
# In deploy/fleet/, next to docker-compose.prod.yml:
ln -sfn .env.fleet .env
```

**Why this is not optional.** Two different mechanisms are at play and they
do not substitute for each other:

| Mechanism | Reads | Feeds |
|---|---|---|
| `env_file: ../../.env` | the ROOT `.env` | variables INSIDE the container |
| `${VAR}` interpolation | a file named `.env` in the compose project dir, or the shell | the compose file TEXT before it is parsed |

`x-cache-env` builds the cache DSN by interpolation
(`postgresql://noctus_cache:${NOCTUS_CACHE_PG_PASSWORD}@…`). Declaring that
variable in `.env.fleet` alone does **nothing** for interpolation — compose
never reads a file by that name. Without the symlink the password expands to
the empty string and every product silently gets
`postgresql://noctus_cache:@noctus-cache-pg:5432/…`.

That is precisely what production was running until 2026-08-18. It failed
quietly: the containers were healthy, `/api/health` returned `ok`, and only
an out-of-fleet connection attempt surfaced it (`fe_sendauth: no password
supplied`) — the role has had a real SCRAM password all along, so the
credential was never missing, only never interpolated.

Compose auto-reads `.env` from the project directory, so the symlink keeps
ONE source of truth (`.env.fleet`) and fixes every future invocation
— including `noctus.dev.deploy_image`, which shells out to
`docker compose` without `--env-file`. Verify with:

```bash
# expect 0 — any hit is an un-interpolated (empty-password) DSN
docker compose -f docker-compose.prod.yml config | grep -c 'noctus_cache:@'
```

> `deploy/fleet/.env` is gitignored, so this is HOST state. It does not
> travel with the repo — re-create it on any rebuilt or additional VPS.

`deploy/fleet/env.fleet.keys` is the tracked, names-only manifest of every
`${VAR}` either prod compose file interpolates this way (no values — real
values live only in the gitignored `.env.fleet`). `check_prod_compose_env_
manifest_sync` (pre-commit-gated when either compose file or the manifest
is staged) cross-checks it and flags a secret-shaped var (`*_KEY`/`*_TOKEN`/
`*_SECRET`/`*_PASSWORD`) that has no enforced non-empty default — the exact
`JULIA_ANTHROPIC_API_KEY` failure mode (§ "Julia / agents + academia-de-
reciclagem env keys" below). It cannot see whether the VPS's `.env.fleet`
actually carries a VALUE for a listed key — that live half has no repo-only
witness; verify manually (or via `noctus.dev.predeploy_check`'s optional
`env_fleet_manifest` leg, fed a `.env.fleet` snapshot).

## Step 1 — build + push images (on the BUILD HOST / CI, NOT the VPS)

```bash
export GHCR_USERNAME=<gh-user> GHCR_TOKEN=<PAT-with-write:packages>
# build-time browser config (BAKED — see CRITICAL above):
export VITE_SUPABASE_URL=https://<project>.supabase.co
export VITE_SUPABASE_PUBLISHABLE_KEY=<supabase-anon/publishable-key>
export VITE_CORE_URL=https://<core-public-host>
export VITE_CORE_API_URL=https://<core-public-host>
export NOCTUS_IMAGE_TAG=$(git rev-parse --short HEAD)   # optional; default latest

bash scripts/infra/build-and-push.sh
```

This builds the two shared seed bases (`noctus-seed-{backend,frontend}-base:dev`
— pinned to `dev` because the product Dockerfiles hardcode that `FROM`), then
each of the 8 products `--target runtime` (slim, baked dist, node-absent),
tags `ghcr.io/jraphaelsst/noctus-<slug>:${NOCTUS_IMAGE_TAG:-latest}`, and pushes.
The floating `:edge` tag also moves by default (a convenience pointer for
manual testing); pass `--move-latest` to ALSO move the fleet-facing `:latest`
— reserve that for a genuinely promoted build (KB § GUIDES/production-deploy.md
§ 2b PROD-PIN fix); the CI workflow does this automatically only for a
`prod`-ref build.

> **In CI**, supply `VITE_*` and `GHCR_*` as repository/organization **secrets**
> and export them into the job environment before invoking the script. Set
> `NOCTUS_IMAGE_TAG=${{ github.sha }}` so each commit yields an immutable image.

## Step 2 — pull + bring up on the VPS

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin

# infra first (Redis always; add --profile waha only if WhatsApp is wired)
docker compose -f deploy/fleet/compose.infra.prod.yml up -d
# docker compose -f deploy/fleet/compose.infra.prod.yml --profile waha up -d

# product fleet — NAME THE SERVICES (see the warning below)
docker compose -f deploy/fleet/docker-compose.prod.yml pull
docker compose -f deploy/fleet/docker-compose.prod.yml up -d \
  core erp-imobiliario igig orbity p-studio seed social-wiring
```

> 🔴 **A bare `up -d` starts EVERY service in the file, including the
> deliberately-dormant products.** The compose file is the *fleet* set (what
> CAN run); `deploy/fleet/build-scope.txt` is the *live* set (what SHOULD).
> Products that are `ativo=false` in the catalog are stopped on purpose, and
> a bare `up -d` silently restarts all of them — measured 2026-08-18, when it
> brought back five dormant containers.
>
> This does **not** re-expose them publicly: un-exposure lives in the
> Cloudflare tunnel ingress, which compose never touches, so they came back
> as `running` but still `404` at the edge. The cost is VPS RAM and CPU, not
> exposure. Re-stop with `docker stop noctus-<slug>` per container.
>
> Derive the live list rather than copying it:
> `grep -v '^#' deploy/fleet/build-scope.txt | grep -v '^$'`

## Step 3 — verify health (+ stagger note)

Each product healthchecks `GET /api/health` (30s interval, 20s start_period).
Watch them turn healthy:

```bash
docker compose -f deploy/fleet/docker-compose.prod.yml ps
watch 'docker ps --format "table {{.Names}}\t{{.Status}}"'
```

> **Stagger note.** All 8 containers `up -d` at once is fine in prod — these
> are slim `runtime` images with **dist already baked** (no first-boot
> `vite build`, unlike the dev `runtime-watch` shape). They start in seconds.
> If the VPS is small and you still see CPU contention, bring them up in waves:
> `docker compose -f docker-compose.prod.yml up -d core erp-imobiliario ...`.
> `restart: unless-stopped` keeps them up across reboots/crashes.

## Step 4 — wire the tunnel + legacy (separate layers)

The named tunnel (`deploy/tunnel/`) routes each public hostname to
`http://<service>:<port>` over `noctus-net` — e.g. `core:8000` (APEX),
`social-wiring:8011`, etc. The legacy container (`deploy/legacy/`) is another
service on the same network. Bring those up per their own READMEs **after** the
fleet is healthy; nothing in this fleet layer publishes host ports, so the
tunnel is the only public ingress.

---

## Reference

| Item | Value |
|---|---|
| Image pattern | `ghcr.io/jraphaelsst/noctus-<slug>:${NOCTUS_IMAGE_TAG:-latest}` |
| Build target | `runtime` (slim, baked dist, node-absent) |
| Seed bases | `noctus-seed-{backend,frontend}-base:dev` (built first; Dockerfile `FROM` is hardcoded to `:dev`) |
| Network | `noctus-net` (external, created once) |
| Ports | INTERNAL (`expose:`) — no host publishing; tunnel is the ingress |
| Restart policy | `unless-stopped` |
| Runtime config | root `.env` via `env_file` |

### Products

| slug | port | notes |
|---|---|---|
| core | 8000 | APEX |
| erp-imobiliario | 8001 | |
| personal-finance | 8002 | |
| therapy-platform | 8003 | |
| seed | 8004 | canonical living reference / canary |
| daily-life | 8005 | |
| adconnect | 8007 | |
| dev-team | 8009 | needs `ANTHROPIC_API_KEY` (runtime); `dev_team/` engine baked into image (no mount) |
| social-wiring | 8011 | |
| orbity | 8010 | |
| academia-de-reciclagem | 8015 | see § Julia/agents env keys below |
| igig | 8013 | |
| p-studio | 8014 | |
| agents | 8016 | see § Julia/agents env keys below |

### Julia / agents + academia-de-reciclagem env keys

Roadmap `julia-agents-academia-2026-09`, M6 cutover. Both containers are
hardened (`cap_drop: ALL`, `read_only: true`, per-slug tmpfs — see the
service comments in `docker-compose.prod.yml`); the env keys below are the
only NEW ones this cutover adds on top of the fleet-wide keys already
documented in Step 0 (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, etc.).

🔴 **All but one of these are root `.env` keys read through `env_file:`.**
`JULIA_ANTHROPIC_API_KEY` is the ONE exception — `docker-compose.prod.yml`
maps it onto the `agents` container as `ANTHROPIC_API_KEY: ${JULIA_ANTHROPIC_API_KEY:-}`,
a compose `${...}` **interpolation**, resolved at compose-PARSE time from
`deploy/fleet/.env.fleet` (see "🔴 `deploy/fleet/.env`" above) — `environment:`
wins over `env_file:`, so it is NEVER read from the root `.env` regardless of
what that file carries for the name. An earlier version of this table said
"root `.env`" for it too; that mistake is exactly what shipped 2026-09-16 —
the key silently interpolated to `''` and every Julia turn failed at the
CLI-spawn step while `/api/health` stayed 200. It must be listed (names
only) in `deploy/fleet/env.fleet.keys` — `check_prod_compose_env_manifest_
sync` gates that — **and actually set, with a value, in
`deploy/fleet/.env.fleet` on the VPS**, which no repo-only check can see.

**REFUSES TO BOOT without these** (`required_prod_config` — the container
starts, fails its own guard, and exits; `docker compose up` reports it as
crash-looping, not merely degraded):

| Key | Used by | Notes |
|---|---|---|
| `APPROVAL_ASSERTION_SECRETS` | agents **and** academia-de-reciclagem | comma-separated HS256 signing keys (contract §D). Raw CSV string, NOT a JSON array — a `["a","b"]`-shaped value fails loud at boot by design. `agents` signs with element `[0]`; either side accepts any element. |
| `SOCIAL_WIRING_API_TOKEN` | agents only | the `social-wiring:one-chat:read`+`:toggle`-scoped product token for the One Chat bridge (contract §E.6). |

**Boots without these, but the feature they gate silently degrades** (no
boot-time refusal — verify at first real use, not just `/api/health`):

| Key | Used by | Effect if unset |
|---|---|---|
| `JULIA_ANTHROPIC_API_KEY` 🔴 `deploy/fleet/.env.fleet`, NOT root `.env` — see callout above | agents (mapped to the container's `ANTHROPIC_API_KEY` in `docker-compose.prod.yml` — **never** the bare/shared `ANTHROPIC_API_KEY` dev-team reads, contract §E.5) | every Julia turn fails at the CLI-spawn step. |
| `ACADEMIA_API_TOKEN` | agents only | agents' in-process MCP tool proxies can't authenticate to academia's API — Julia's academia-scoped tools 401. |
| `JULIA_AGENT_ID` | agents only | must equal `ACADEMIA_API_TOKEN`'s minted `principal_agent_id` exactly (contract §D step 5) — a mismatch fails every academia-side principal check, not just an empty-string default. |
| `PRIMARY_SOURCE_ALLOWLIST` | academia-de-reciclagem only | comma-separated hostnames (contract §B.5 `POST /api/sources`); empty means every host triggers the AVISO warn-path, never a hard block. |

**Managed from the UI since 2026-09-16 (Agentes → Credenciais e integrações).**
`ANTHROPIC_API_KEY` (Julia), `ACADEMIA_API_TOKEN`, `SOCIAL_WIRING_API_TOKEN`,
`APPROVAL_ASSERTION_SECRETS` and `JULIA_AGENT_ID` now resolve DB-first
(`agents.app_integration_config`, Fernet with the fleet `ENCRYPTION_KEY`),
env-fallback. The `.env` values above stay as the bootstrap —
`required_prod_config` still reads `APPROVAL_ASSERTION_SECRETS` and
`SOCIAL_WIRING_API_TOKEN` from env at boot — but a stored value wins over
them without a redeploy (≤ 30 s across workers), so never rotate them by
hand again. One-time move, as a platform admin (`noctus_users.role = 'admin'`):

1. Apply `products/agents/backend/migrations/010_credentials_and_runtime_settings.sql`
   (`noctus.dev.migrate_product product=agents`, dry-run first).
2. Confirm `ENCRYPTION_KEY` is set in the root `.env` (social-wiring already
   requires it), then deploy the agents AND academia-de-reciclagem images from
   the same commit (academia must read the ring before a rotation).
3. On **Credenciais e integrações**, press **Importar do ambiente** on each of
   the five cards (the value is copied server-side; it never reaches the
   browser). Each card then shows source `banco`.
4. Press **Testar** on the three live credentials; expect `OK`.
5. From now on: **Renovar** the two product tokens (mints a 90-day token in
   the target product, verifies it, stores it, revokes the old one);
   **Substituir** the Anthropic key; **Rotacionar chave** for §D (staged 120 s,
   old keys retire 24 h later, pruned by the daily job). A daily 09:00 job
   notifies platform admins 30/14/7/3/1/0 days before a token expires; the
   dashboard shows the same warning.

**Already covered by `x-prod-env`/compose, no `.env` action needed:**
`NOCTUS_SCHEDULERS_ENABLED`, `DEBUG`, `NOCTUS_CACHE_BACKEND`,
`NOCTUS_CACHE_POSTGRES_DSN` (from `NOCTUS_CACHE_PG_PASSWORD`, already
required fleet-wide).

**CORS / PRODUCT_URL — no repo change needed.** Both slugs' `cors_origins`
default to `@registry:own:<slug>` and both are already rows in the
`start.sh` `PRODUCTS` registry, so `noctusai_lib.config.cors_registry`
resolves their origin automatically via the existing `PRODUCT_URL_PATTERN`
(or a per-slug `PRODUCT_URL_AGENTS` / `PRODUCT_URL_ACADEMIA_DE_RECICLAGEM`
override) the VPS `.env` already carries for every other product. At
cutover, run `noctus.dev.ensure_product_url_roster` (dry-run first) so
core's CORS allowlist and each product's SSO origin close by construction —
same step every prior product promotion used, nothing agents/academia-
specific to add here.

### Infra

| service | when | notes |
|---|---|---|
| redis | always | chatbot buffer/worker + rate-limiter |
| waha | profile `waha` | WhatsApp HTTP API; absent ⇒ FakeWahaClient fallback |
| postgres | n/a in prod | remote Supabase is used |
