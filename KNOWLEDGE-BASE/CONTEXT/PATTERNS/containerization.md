# Containerization — single container per product

> **⚠️ ARCHITECTURE (2026-05-16, project `containerization-single-container`).**
> Migrated from 2-container-per-product (backend uvicorn + frontend
> nginx) to **ONE container per product**: uvicorn serves the API **and**
> the built SPA on one port via the seed factory `serve_spa` /
> `SERVE_SPA_DIR` seam. Consequences that **override the legacy prose
> below** (§§3, 6–11 didactic walkthrough is being rewritten — tracked as
> the named follow-up `containerization-doc-rewrite`; the **rule-bearing**
> sections §1/§2/§4/§5 + §11a below ARE current):
>
> - **Shared seed base images** `noctus-seed-{backend,frontend}-base`
>   (`seed/docker/Dockerfile.*-base`, built by
>   `scripts/build-base-images.sh`) + **thin per-product Dockerfiles**
>   that `FROM` them. `FROM base` IS the named seam — the Docker analog
>   of `create_product_app()` (inherit-and-extend, never fork; NOT
>   propagated full copies, NOT a god-Dockerfile with per-product `if`).
> - **Two compose projects:** `docker-compose.yml` (`name:
>   noctusai-products`, 10 single-container products) +
>   `docker-compose.infra.yml` (`name: noctusai-infra`,
>   Redis/WAHA/Postgres). Each product = one Docker-Desktop row = the
>   1-click on/off UX; whole-fleet = the project-level switch.
> - **`noctus-net` is `external: true`** — created once by `start.sh`.
>   This **INVERTS** the legacy "§4: NOT `external: true`" rule (the
>   two-project split means no single project may own the shared fabric).
> - Per-product `<slug>-net` is **removed** (one container ⇒ nothing to
>   isolate frontend-from-backend).
> - Same-origin SPA: `vite.config.factory.ts` define-injects
>   `window.location.origin` under `VITE_SAME_ORIGIN=1` (tunnel/deploy-
>   correct, zero consumer changes).
> - `<slug>-tunnel` is **mandatory in the pattern** (every product
>   compose ships it) but profile-gated (`tunnel-<slug>`/`tunnel-all`).
> - **NO dev/prod split — ONE container, ONE shape always**
>   (project `containerization-single-env`, superseded the earlier
>   2-container dev sidecar). The local per-product compose builds the
>   Dockerfile **`runtime-watch`** target with source bind-mounted:
>   `seed/docker/local-watch.sh` runs `vite build --watch` +
>   `uvicorn --reload` in the *same single container* — live feedback,
>   no sidecar, no `dev` command, no separate project. Deploy/CI build
>   the default slim **`runtime`** target (baked dist, node absent =
>   the shippable artifact). `docker-compose.override.yml` +
>   `propagate-overrides.sh` were **removed**.
> - `./start.sh` whole fleet · `./start.sh <slug>...` subset ·
>   `tunnel`/`build`/`native` retained.
> - Propagation: `scripts/propagate-{dockerfiles,composes}.sh`
>   (each `--check`); `products/seed/` is canonical. (The legacy
>   didactic body still references `docker-compose.override.yml` /
>   `dev <slug>` — banner-superseded; folded into the
>   `containerization-doc-rewrite` follow-up.)
>
> **Why native still exists.** `./start.sh native` (uvicorn + vite on
> host) remains the fastest hot-reload path; the container path is the
> reproducible/deployable twin. They coexist.

---

## 1 · Mental model

There is **no "container of containers"** — Docker doesn't work that way.
The right mental image is a **fleet of sibling containers on a shared
network**, with a single orchestrator file (root `docker-compose.yml`)
that **includes** each product's compose fragment.

```
┌─────────────────────────────────────────────────────────────────────┐
│                  noctus-net (shared platform fabric)                 │
│                                                                      │
│   ┌─core────────┐  ┌─erp────────┐  ┌─pf─────────┐  ┌─… 7 mais ──┐  │
│   │ backend +   │  │ backend +  │  │ backend +  │  │            │  │
│   │ frontend    │  │ frontend   │  │ frontend   │  │            │  │
│   │ (in core-net)│ │ (in erp-net)│ │ (in pf-net)│  │            │  │
│   └─────────────┘  └────────────┘  └────────────┘  └────────────┘  │
│                                                                      │
│   ┌─redis (profile)─┐    ┌─waha (profile)──┐                        │
│   │ shared service  │    │ WhatsApp HTTP   │                        │
│   └─────────────────┘    └─────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

Every product's two containers (backend + frontend) join **two** networks:

- **`noctus-net`** — the shared platform fabric. Anything on this
  network can talk to anything else on it (when products need to call
  each other, this is the path).
- **`<slug>-net`** — product-private. Only the backend and frontend of
  *that* product are here; this is where the frontend reaches its own
  backend by the service name `<slug>-backend`.

This split means: by default, products are **isolated** from each
other (frontend can't accidentally call another product's backend);
when you *want* cross-product calls (e.g., dev-team calling core's
notification hook), `noctus-net` is the bridge.

---

## 2 · File layout

```
noctusai/
├── docker-compose.yml                 ← root orchestrator (include + shared services)
├── .dockerignore                      ← shared (excludes venv, node_modules, .env, .git)
├── start.sh                           ← native default; --docker delegates to compose
├── stop.sh                            ← native default; --docker / --docker-volumes / --docker-prune
│
├── seed/                              ← editable into every backend image
│   ├── lib/backend/                   ← noctusai_lib (shared Python lib)
│   ├── lib/frontend/                  ← @noctusai/lib (Vite alias target)
│   ├── framework/backend/             ← noctusai_seed (factory + middleware)
│   └── framework/frontend/            ← @noctusai/seed (Vite alias target)
│       └── nginx.conf.template        ← single SPA nginx template; all frontends inherit
│
└── products/
    ├── seed/                          ← canonical reference (the "spec" Dockerfile)
    │   ├── docker-compose.yml         ← canonical per-product fragment
    │   ├── backend/Dockerfile         ← canonical backend pattern
    │   └── frontend/Dockerfile        ← canonical frontend pattern
    │
    ├── core/                          ← every product mirrors seed/, with slug + ports
    │   ├── docker-compose.yml         ← `services: core-backend, core-frontend`
    │   ├── backend/Dockerfile         ← `EXPOSE 8000`, healthcheck on :8000
    │   └── frontend/Dockerfile        ← `EXPOSE 5173`
    │
    ├── erp-imobiliario/   ← (8001 / 8080)
    ├── personal-finance/  ← (8002 / 8090)
    ├── therapy-platform/  ← (8003 / 8095)
    ├── daily-life/        ← (8005 / 8110)
    ├── mailing/           ← (8006 / 8120)
    ├── adconnect/         ← (8007 / 8130)
    ├── dev-team/          ← (8009 / 8123) + extra: /opt/dev_team editable install
    ├── imobi-scheduling/  ← (8011 / 8160)
    └── youtube-crawler/   ← (8008 / 8150)
```

**`products/seed/` is the canonical source.** When the pattern needs
to evolve (security update, base image bump, new layer, healthcheck
change), update seed first, then propagate to the other 9 products.
This is the same discipline as the rest of the platform: seed is the
spine; products inherit.

---

## 3 · The Dockerfile pattern (didactic walkthrough)

### 3.1 — Backend Dockerfile (every product)

Three layers, ordered by **change frequency** (rarest first → fastest
cache hits):

```dockerfile
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps: gcc + libffi (cryptography), libpq (psycopg2), curl
# (healthcheck), git (git+ deps).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev libpq-dev curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ─── Layer 1: seed packages ──────────────────────────────────────────
# Only changes when you touch seed/. Cached aggressively.
COPY seed/lib/backend ./seed/lib/backend
COPY seed/framework/backend ./seed/framework/backend
RUN pip install --no-cache-dir \
    -e ./seed/lib/backend \
    -e ./seed/framework/backend

# ─── Layer 2: product dependencies ────────────────────────────────────
# Strip already-installed seed editables to avoid pip resolver re-build.
COPY products/<slug>/backend/requirements.txt /tmp/requirements.txt
RUN grep -v '^-e seed/' /tmp/requirements.txt > /tmp/requirements.clean.txt \
    && pip install --no-cache-dir -r /tmp/requirements.clean.txt

# ─── Layer 3: product code ───────────────────────────────────────────
# Changes most often; everything below this is rebuilt on code edits.
COPY products/<slug>/backend/ ./products/<slug>/backend/

# Non-root user (security baseline).
RUN useradd -m -u 1000 noctus && chown -R noctus:noctus /app
USER noctus

EXPOSE <bp>

# Health uses the seed-provided /api/health (every product inherits).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:<bp>/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", \
     "--port", "<bp>", "--app-dir", "products/<slug>/backend"]
```

**Key decisions encoded here:**

| Decision | Why |
|---|---|
| `python:3.11-slim` (not `alpine`) | musl quirks + slow C-extension compiles. slim is the right floor. |
| Multi-line `apt-get` then `rm -rf /var/lib/apt/lists/*` | image stays under 250MB; package list cache adds 30+MB |
| Build context = repo root | seed/ is reachable; editable installs preserve the repo layout the runtime expects |
| Strip `-e seed/` lines from requirements | seed already installed in Layer 1; pip resolver wastes 30+s otherwise |
| `useradd -u 1000 noctus` | no root in container; supply chain hygiene |
| `HEALTHCHECK` on `/api/health` | the seed-provided endpoint; `depends_on: condition: service_healthy` works |

**Special case — dev-team:** also installs `/dev_team/` editable, since
the agno multi-agent engine ships at the repo root, not inside
`products/dev-team/`. The canonical pattern reserves a slot
between Layer 1 and Layer 2 for product-specific extras like this.

### 3.2 — Frontend Dockerfile (every product)

Multi-stage: Node builds the SPA → nginx:alpine serves the static bundle.

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app

# Layer 1: seed frontend packages (vite alias targets).
# @noctusai/seed → seed/framework/frontend/src
# @noctusai/lib  → seed/lib/frontend/src
COPY seed/framework/frontend ./seed/framework/frontend
COPY seed/lib/frontend ./seed/lib/frontend

# Layer 2: product manifest only (cache hits when only code changes).
COPY products/<slug>/frontend/package*.json ./products/<slug>/frontend/
WORKDIR /app/products/<slug>/frontend
RUN npm install --no-audit --no-fund

# Layer 3: product code + build.
COPY products/<slug>/frontend ./
RUN npm run build

# Runtime: nginx serves the built bundle.
FROM nginx:alpine
COPY --from=build /app/products/<slug>/frontend/dist /usr/share/nginx/html
COPY seed/framework/frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
ENV PORT=<fp>
EXPOSE <fp>
CMD ["nginx", "-g", "daemon off;"]
```

**The nginx template trick.** `nginx:alpine` automatically substitutes
`${PORT}` (and any `${VAR}`) in `/etc/nginx/templates/*.template` at
container start, then writes the resolved file to
`/etc/nginx/conf.d/`. So a **single template lives in the seed**
(`seed/framework/frontend/nginx.conf.template`) and every product
copies it; `ENV PORT=<fp>` is the only per-product variation.

```nginx
server {
    listen ${PORT};
    root /usr/share/nginx/html;
    index index.html;
    location / { try_files $uri $uri/ /index.html; }     # SPA fallback
    location ~* \.(js|css|png|...)$ {
        expires 1y; add_header Cache-Control "public, immutable";
    }
}
```

### 3.3 — Per-product `docker-compose.yml`

Two services, two networks. **Standalone-able** (`cd products/<slug> && docker compose up`) or **orchestrated** (root `docker compose up` includes it).

```yaml
services:
  <slug>-backend:
    build:
      context: ../..
      dockerfile: products/<slug>/backend/Dockerfile
    container_name: noctus-<slug>-backend
    image: noctus-<slug>-backend:dev
    env_file: [../../.env]
    ports: ["<bp>:<bp>"]
    networks: [noctus-net, <slug>-net]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:<bp>/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s

  <slug>-frontend:
    build:
      context: ../..
      dockerfile: products/<slug>/frontend/Dockerfile
    container_name: noctus-<slug>-frontend
    image: noctus-<slug>-frontend:dev
    ports: ["<fp>:<fp>"]
    depends_on:
      <slug>-backend: { condition: service_healthy }
    networks: [<slug>-net]    # frontend NOT on noctus-net — it only needs its own backend
    restart: unless-stopped

networks:
  noctus-net: { name: noctus-net, driver: bridge }
  <slug>-net: { driver: bridge }
```

**Why the frontend isn't on `noctus-net`.** The frontend is a static
bundle served by nginx — it makes no server-side calls to any
backend (the *user's browser* does). So putting it on the platform
fabric adds attack surface without value. It only needs `<slug>-net`
to talk to its own backend during dev (proxy passthrough, if any).

### 3.4 — Root `docker-compose.yml` (orchestrator)

```yaml
include:
  # BEGIN_PRODUCTS_INCLUDE
  - products/core/docker-compose.yml
  - products/erp-imobiliario/docker-compose.yml
  - ... (one line per product)
  # END_PRODUCTS_INCLUDE

services:
  redis:
    image: redis:7-alpine
    container_name: noctus-redis
    ports: ["6379:6379"]
    volumes: [redis_data:/data]
    networks: [noctus-net]
    profiles: [redis, full]
    restart: unless-stopped

  waha:                                  # WhatsApp HTTP API
    image: devlikeapro/waha:latest
    platform: linux/amd64
    profiles: [waha, full]
    # ...

  postgres:                              # Local Postgres (offline dev — §11.13)
    image: postgres:16-alpine
    container_name: noctus-postgres
    environment: { POSTGRES_USER: noctus, POSTGRES_PASSWORD: noctus_local, POSTGRES_DB: noctus }
    ports: ["5432:5432"]
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init-local-db:/docker-entrypoint-initdb.d:ro
    networks: [noctus-net]
    profiles: [postgres, full]
    # healthcheck: pg_isready -U noctus -d noctus

networks:
  noctus-net: { name: noctus-net, driver: bridge }

volumes:
  redis_data:
  waha_sessions:
  postgres_data:
```

**Profiles.** Anything that not all products need lives behind a
profile. Default `docker compose up` (no profile) brings up **only the
20 product services**; nothing else runs unless asked.

---

## 4 · Networks — the security & isolation story

| Network | Members | Purpose |
|---|---|---|
| `noctus-net` | All 10 backends + Redis + WAHA (when on) | Cross-product calls, shared infra access |
| `<slug>-net` | Just `<slug>-backend` + `<slug>-frontend` | Frontend reaches its own backend; nothing else |

**Threat model encoded:**

- A compromised frontend can hit only its own backend (private network).
- A compromised backend can hit other backends (platform fabric) — but
  only at *application-layer endpoints*, with the same auth they'd
  face from the outside (Supabase JWT, etc.).
- Shared infra (Redis) is on platform fabric — every backend that
  needs it can reach it.
- The host gets only the published ports; everything else is
  container-internal.

**Standalone vs orchestrated, network behavior:**

- **Standalone** (`cd products/core && docker compose up`): both
  `noctus-net` and `core-net` are auto-created scoped to that compose
  project. Cross-product calls don't work because no other product is
  up. That's correct — the use case is "test core in isolation."
- **Orchestrated** (root `docker compose up`): `noctus-net` is
  declared once at root, every included compose references the *same
  named* network. All products land on the same fabric.

The trick that makes this work: every per-product compose declares
`networks: noctus-net: { name: noctus-net, driver: bridge }` — same
name everywhere, **not** `external: true`. Compose merges duplicate
network definitions across includes and creates the network once.

---

## 5 · Operating it — start.sh / stop.sh

**Default mode is now Docker** (changed 2026-05-10). The native
uvicorn + vite path is preserved as `native` for hot-reload
iteration.

```bash
# Default — full fleet via docker compose
./start.sh                      # 10 products × backend+frontend (20 containers)
./start.sh redis                # + Redis profile
./start.sh waha                 # + WAHA (WhatsApp HTTP API)
./start.sh local-db             # + local Postgres (offline dev — see §11.13)
./start.sh full                 # + Redis + WAHA + Postgres
./start.sh build                # rebuild images (--no-cache --pull) then up

# Cloudflare tunnel — expose a product to the internet via *.trycloudflare.com
./start.sh tunnel <slug>        # one product (e.g., tunnel core)
./start.sh tunnel               # ALL products (10 ephemeral URLs)

# Native (legacy) — uvicorn + vite directly, fast hot-reload
./start.sh native               # all products on host

# Stopping
./stop.sh                       # docker compose down (volumes kept)
./stop.sh volumes               # + remove named volumes
./stop.sh prune                 # + remove images (full clean)
./stop.sh native                # kill native processes on registered ports
./stop.sh native --venv         # + remove venv/
./stop.sh native --node         # + remove products/*/frontend/node_modules
./stop.sh native --all          # ports + venv + node_modules

# Backward-compat aliases (still work)
./start.sh --docker [profile]   # alias of new default + profile
./stop.sh  --docker             # alias of default `./stop.sh`
./stop.sh  --docker-volumes     # alias of `./stop.sh volumes`
./stop.sh  --docker-prune       # alias of `./stop.sh prune`
```

Both scripts read the same `PRODUCTS` registry block in `start.sh`,
keeping a single source of truth.

### Why Docker is the default

User requested 2026-05-10: *"merge the compose to the start and stop
process, so we deal with containers upon acting."* Containers are
the deployment artifact and the path to online testing (tunnel
mode); making them the default of the operating scripts erases the
mental tax of remembering the `--docker` flag every time.

Native is preserved (not deleted) because hot-reload single-file
iteration is genuinely faster on a real Python interpreter than
through a docker filesystem mount + restart loop.

---

## 5b · Cloudflare tunnel — online testing without deploy

When you need a public URL pointing at a local backend — for OAuth
callbacks (Google / Meta / Stripe), webhook receivers (Stripe /
WhatsApp / GitHub), or sharing a working session with a teammate —
the cloudflare tunnel mode gives you exactly that, in seconds, with
no DNS / cert / firewall setup.

### What it does

- Each product's `docker-compose.yml` declares a `<slug>-tunnel`
  service running `cloudflare/cloudflared:latest` with the command
  `tunnel --no-autoupdate --url http://<slug>-backend:<bp>`.
- The service is profile-gated: `tunnel-<slug>` (single product)
  and `tunnel-all` (umbrella for the whole fleet). Default `up`
  doesn't start any tunnel.
- cloudflared registers an ephemeral subdomain at
  `*.trycloudflare.com` (no Cloudflare account needed) and proxies
  every request to the product's backend on the `<slug>-net`
  internal Docker network.
- `./start.sh tunnel <slug>` brings the fleet up + activates the
  product's tunnel profile + reads cloudflared logs to extract
  the public URL + prints it in a banner at the end.

### Usage

```bash
./start.sh tunnel core              # exposes core backend → https://<rand>.trycloudflare.com
./start.sh tunnel adconnect         # exposes adconnect backend
./start.sh tunnel                   # exposes ALL 10 backends (one URL each)
```

Output ends with a banner containing the public URL:

```
╔════════════════════════════════════════════════════════════╗
║  Public URL (core):  https://stripe-foo-bar.trycloudflare.com   ║
╚════════════════════════════════════════════════════════════╝

Use essa URL em webhooks de Stripe / Meta / Google OAuth callback.
A URL e EFEMERA — muda toda vez que o tunnel reinicia.
```

### Common workflows

**OAuth callback testing (Google / Meta).** Provider rejects
`localhost` redirect URIs. Solution:

```bash
./start.sh tunnel core
# copy the URL, register it as the callback in Google Cloud Console
# / Meta App Dashboard / etc.
# trigger the OAuth flow; provider redirects to your tunnel; tunnel
# proxies to your local backend. Test the full handshake without
# a deploy.
```

**Stripe webhook testing.** Same shape — register the tunnel URL as
the webhook endpoint in Stripe dashboard, trigger an event, watch
the local backend handle it.

**Shared demo with a teammate.** Tunnel runs as long as the
container runs. Share the URL; they hit your laptop's backend
directly through Cloudflare's edge. Stop with `./stop.sh` when
done.

### URL extraction details

cloudflared logs the public URL on stdout shortly after startup. The
extraction loop in `start.sh`:

```bash
extract_tunnel_url() {
  local container="$1"
  for i in $(seq 1 30); do
    url=$(docker logs "$container" 2>&1 | \
          grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" | head -1)
    [[ -n "$url" ]] && { echo "$url"; return 0; }
    sleep 2
  done
  return 1
}
```

Polls every 2s for up to 60s. If timeout — surfaces a hint to run
`docker logs noctus-<slug>-tunnel` manually.

### Trade-offs vs alternatives

| Approach | Pros | Cons |
|---|---|---|
| **`trycloudflare.com` (this)** | zero setup, instant URL, no account | URL changes on restart; Cloudflare branded; rate limits unclear |
| **Named Cloudflare tunnel** (with account + DNS) | stable URL, your domain, no rate limits | requires account, `cloudflared tunnel create`, DNS, token in env |
| **ngrok** | simpler in some ways | requires ngrok account, free tier has limits, separate tool |
| **localtunnel / serveo / bore** | OSS alternatives | flakier; some need SSH keys |
| **Real deploy to Cloudflare Pages / Vercel** | production-shape | minutes per iteration; not "online for testing" |

The pattern lifted from `noctusai-youtube-crawler` and
`whatsapp-google-scheduling` — both ship the trycloudflare quick-mode
because OAuth callback testing is the primary unblocking use case
and ephemeral URLs are fine for that.

### Future — promotion to named tunnel

When a product graduates from "demo" to "running on a stable URL
24/7," replace the quick-mode command with a named-tunnel config:

```yaml
<slug>-tunnel:
  image: cloudflare/cloudflared:latest
  command: tunnel run
  environment:
    TUNNEL_TOKEN: ${CLOUDFLARE_TUNNEL_TOKEN_<slug>}
```

The token comes from `cloudflared tunnel create` + DNS routing
(`cloudflared tunnel route dns ...`). Stable URL like
`api.noctusai.com` instead of `random-string.trycloudflare.com`.
Filed under §11 backlog item 16.

**Direct compose use is also fine.** If you prefer:

```bash
docker compose up                            # all products
docker compose --profile redis up            # + Redis
docker compose up core-backend core-frontend # just core
docker compose logs -f core-backend          # tail one service
docker compose exec core-backend bash        # shell in a running container
docker compose build --parallel              # build all images in parallel
docker compose pull                          # pull new redis/waha versions
```

`./start.sh --docker` is just sugar that adds a "URL summary at the end" to `docker compose up`.

---

## 6 · The build process — what happens when you `docker compose up`

1. **Compose resolves includes** — root file plus all 10
   per-product files merge into a single in-memory config.
2. **Compose checks images** — for each service, is there a built
   image (`noctus-<slug>-backend:dev`) already? If not → build.
3. **Build, in parallel** — Docker BuildKit reads each Dockerfile,
   pulls the base image (cached after first run), runs the layers.
   Layer 1 (seed) hits cache instantly after first build; only Layer
   3 (product code) typically rebuilds on file changes.
4. **Network creation** — `noctus-net` and per-product `<slug>-net`
   created if missing.
5. **Volume creation** — `redis_data`, `waha_sessions` if those
   profiles are active.
6. **Container start, in dependency order** — backends first;
   frontends wait for `service_healthy` (the `HEALTHCHECK` curl on
   `/api/health` must pass 3 times spaced 30s apart… in practice ~20s
   for the start_period).
7. **Ports published** — host:container mappings live; you can hit
   `http://localhost:<bp>` and `http://localhost:<fp>`.

**First build is slow** (5-15min depending on machine — fetching base
images, installing system packages, npm install, pip install). **Subsequent
builds are fast** (10-30s, only the changed layer).

---

## 7 · Image footprint

Approximate image sizes after first build (varies with deps):

| Image | Size | Rationale |
|---|---|---|
| `noctus-<slug>-backend:dev` | ~600-900 MB | python:3.11-slim base (~150 MB) + system pkgs + pip deps (cryptography, supabase, fastapi…) + seed editable + product code |
| `noctus-<slug>-frontend:dev` | ~30-50 MB | nginx:alpine final stage only — Node build stage is discarded; just static HTML/JS/CSS bundle |
| `redis:7-alpine` | ~30 MB | unchanged from upstream |
| `devlikeapro/waha:latest` | ~1.5 GB | WhatsApp engine (Chromium under the hood) — heavy, profile-gated |

10 products × 2 images = 20 images, roughly **6-9 GB total**. Plan
disk accordingly. `./stop.sh --docker-prune` reclaims everything.

---

## 8 · Adding a new product

`noctus.dev.scaffold_product` does it all automatically, end-to-end:

1. **Copies Docker artifacts from `templates/product-seed/`** —
   `Dockerfile` (backend), `Dockerfile` (frontend), `docker-compose.yml`,
   carrying `{{PRODUCT_SLUG}}` / `{{PRODUCT_NAME}}` / `{{BACKEND_PORT}}` /
   `{{FRONTEND_PORT}}` placeholders.
2. **Mechanical placeholder substitution** runs across every text file
   in the new `products/<slug>/` directory — the placeholders resolve
   to the new product's actual values.
3. **`_register_in_start_sh`** appends the new product to `start.sh`'s
   `PRODUCTS=()` registry between the `BEGIN_PRODUCTS_REGISTRY` /
   `END_PRODUCTS_REGISTRY` sentinels. Idempotent on re-scaffold.
4. **`_register_in_root_compose`** appends a `- products/<slug>/docker-compose.yml`
   line to the root `docker-compose.yml`'s `include:` list between the
   `BEGIN_PRODUCTS_INCLUDE` / `END_PRODUCTS_INCLUDE` sentinels. Idempotent
   on re-scaffold.
5. **`docker compose config --quiet`** is the post-scaffold smoke test
   the agent should run before declaring done.

`noctus.dev.delete_product` is the symmetric inverse — `_unregister_from_start_sh`
+ `_unregister_from_root_compose` undo both registrations. Roundtrip
verified to restore the file byte-for-byte.

**Two propagation paths, one canonical pattern:**

| Scaffolder | Reads from | Writes to | What it generates |
|---|---|---|---|
| `noctus.dev.scaffold_product` (in-noc) | `templates/product-seed/` | `products/<slug>/` | Per-product Docker artifacts that join root orchestrator's `include:` |
| `noctus.dev.create_testing_ground` (sibling workspace) | `templates/seed-workspace-docker/` + `bootstrap-seed-workspace.sh` | sibling workspace root | Single workspace-scoped Docker stack consuming noc seed via `additional_contexts: noc:` |

The two templates are intentionally different — sibling workspaces
have a flat layout (one workspace + one product), in-noc has the
multi-product orchestrator. They share the same canonical Dockerfile
*shape* (multi-stage, layer ordering, healthcheck, non-root, nginx
template). When the shape evolves, update `products/seed/` first
(in-noc canonical), `templates/product-seed/` second (in-noc scaffold
target), `templates/seed-workspace-docker/` third (sibling workspace).

---

## 9 · Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `network noctus-net not found` on standalone | per-product compose was `external: true` (legacy) | already fixed; `noctus-net` is declared, not external |
| Frontend builds but `@noctusai/seed` resolves to nothing | seed/framework/frontend missing from build context | confirm Dockerfile copies `seed/framework/frontend` and `seed/lib/frontend` |
| Backend `ImportError: noctusai_seed` | Layer 1 install failed silently | rebuild with `--no-cache` and watch for pip errors |
| Backend healthcheck never goes green | `/api/health` not registered (broken seed wiring?) | run native first to confirm endpoint exists; `docker compose logs <slug>-backend` |
| Port already in use | native `start.sh` running same port | `./stop.sh` first, then `./start.sh --docker` |
| Build context too large (`Sending build context to daemon: 2.3GB`) | `.dockerignore` not catching something | check `.dockerignore` excludes `venv/`, `.venv/`, `node_modules/`, `.git/`, `.claude/`, `dist/` |
| `docker compose config` errors | YAML typo or include path wrong | `docker compose config` shows line numbers |
| `dev-team` backend missing `agno` import | dev_team package not installed in image | special-case copy of `/dev_team/` to `/opt/dev_team` is intentional; verify Dockerfile has it |
| Out of disk during build | accumulated images/volumes | `./stop.sh prune` then rebuild |
| `failed to fetch oauth token` / `read: connection reset by peer` on first build | flaky Docker Hub on tethered/captive networks; BuildKit can't pull `docker/dockerfile:1.7` syntax frontend or base images | pre-pull when network is stable (recipe below); subsequent builds reuse cache |
| `Cannot find module 'tailwindcss-animate'` from `seed/framework/frontend/...` | seed frontend's own deps not installed in container | already fixed in canonical Dockerfile (Layer 1 runs `npm install --include=peer` inside `seed/framework/frontend` and `seed/lib/frontend` before product build) — confirm Dockerfile has those `WORKDIR` + `npm install` lines |
| `[vite]: Rollup failed to resolve import "clsx" from "/app/seed/lib/frontend/src/utils.ts"` | Vite's `resolve.dedupe: FRAMEWORK_DEPS` forces resolution from the product's own `node_modules`; if a product's `package.json` doesn't list a dep that the seed source imports, build fails — even though the seed package has it in devDeps | add the missing dep to the product's `package.json`. Full FRAMEWORK_DEPS list lives at `seed/framework/frontend/vite.config.factory.ts`. Audit all products with `python3 scripts/check-framework-deps.py [--fix]` (also gated in CI). |
| `Dependency lookup for cairo with method 'pkg-config' failed` (during pip install of a backend) | a Python wheel is being built from source and needs cairo system libs; happens when wheel isn't published for the platform/python version | already fixed in canonical backend Dockerfile: apt-get installs `pkg-config`, `libcairo2-dev`, `libgirepository1.0-dev`, `libpango1.0-dev`, `libgdk-pixbuf-2.0-dev` |
| `Package 'libgdk-pixbuf2.0-dev' has no installation candidate` | Debian Trixie (`python:3.11-slim` 2025+) renamed the package to `libgdk-pixbuf-2.0-dev` (extra dash) | use the new name; if you ever bump base to a newer Debian, `apt-cache search` first |
| `target erp-imobiliario-backend: failed to solve` after a long build | cache mount race or transient pip mirror failure during 8-way parallel build | retry the affected target alone: `docker compose build <slug>-backend`; or reduce parallelism: `docker compose build --parallel false` |
| Container exits immediately, `exec: "uvicorn": executable file not found` | product's `requirements.txt` doesn't pin `uvicorn` (relies on root reqs in native dev; root reqs aren't installed in container) | add `uvicorn[standard]==0.30.6` to the product's `requirements.txt`. Long-term: consider absorbing into `seed/lib/backend` deps |
| Container restart-loops on `ModuleNotFoundError: No module named '<X>'` | product code imports a package that's only in the ROOT requirements.txt, not in the product's | each container only installs its product's `requirements.txt` — declare every direct import there. Catch via grep: `grep -rE "^(import|from) <X>" products/<slug>/backend` |
| `ImportError: email-validator is not installed` from pydantic | Pydantic `EmailStr` field needs the `email-validator` package; pydantic doesn't pull it transitively | add `email-validator>=2.0.0` to the product's `requirements.txt` |
| `RuntimeError: Form data requires "python-multipart"` at startup | FastAPI route uses `Form()` or `UploadFile`; needs `python-multipart` | add `python-multipart>=0.0.9` to the product's `requirements.txt` |
| `AssertionError: Status code 204 must not have a response body` | FastAPI 0.115 strict assertion; `@router.delete(status_code=204)` with `-> None` return type still trips | drop `status_code=204` from the decorator; return `Response(status_code=status.HTTP_204_NO_CONTENT)` explicitly. Add `response_class=Response` for safety. Pattern in `products/adconnect/backend/app/routers/admin.py::delete_reward_rule` |
| Tunnel returns 502 / no URL after 60s | `<slug>-backend` not healthy yet, or cloudflared still negotiating | `docker logs noctus-<slug>-tunnel` shows the URL once registered; healthcheck on backend (`/api/health`) must pass first |
| Tunnel URL was working then suddenly `DNS_PROBE_FINISHED_NXDOMAIN`, container still "Up" | **The QUIC dropout pattern.** cloudflared default `--protocol auto` opens QUIC over UDP; home/office/mobile-tether NATs frequently kill the UDP session within 5-10min (`timeout: no recent network activity` in logs). Once dropped, cloudflared retries forever but **cannot re-register the same quick-tunnel hostname** — Cloudflare's edge deregistered it. The container stays "Up" because the binary is alive in retry loop. Docker healthchecks can't catch it (cloudflared image is `FROM scratch` — no shell). | **Already fixed** in all 11 compose files: command pins `--protocol http2`. HTTP2 over TCP doesn't suffer the NAT dropout. If you ever see this again: `docker compose --profile tunnel-<slug> up -d --force-recreate <slug>-tunnel` — gets a fresh URL. `start.sh` now curl-verifies the URL before reporting; ⚠ flag in output = registered but not actually serving. |

### Pre-pull recipe (one-time, when network is stable)

When you're on a stable connection, prime the local cache so future
builds don't need Docker Hub at all:

```bash
docker pull docker/dockerfile:1.7         # BuildKit syntax frontend
docker pull python:3.11-slim              # backend base (T1 multi-stage: builder + runtime)
docker pull node:20-alpine                # frontend base (used by build, dev, and HMR stages)
docker pull nginx:alpine                  # frontend runtime base (production target)
docker pull redis:7-alpine                # redis profile
docker pull postgres:16-alpine            # local-postgres profile (T4, §11g)
docker pull cloudflare/cloudflared:latest # tunnel profile
docker pull aquasec/trivy:0.49.1          # CI image scanning (T9, §11f)
```

After this, `./start.sh` works offline (only product layers rebuild
when product code changes; bases come from cache).

### Frontend deps pre-install (one-time per clone, parallel to the pull recipe)

The dev override bind-mounts the host's `./frontend` directory ON TOP
of the in-image `node_modules/` (see §11d pitfall) — fresh clones need
host `node_modules/` populated before `docker compose up` or vite
crashes with "cannot find package vite". Run once:

```bash
./scripts/first-time-setup.sh
```

The script runs `npm install` in `seed/framework/frontend`,
`seed/lib/frontend`, and every `products/<slug>/frontend/` (driving off
start.sh's `BEGIN/END_PRODUCTS_REGISTRY` so new products are picked up
automatically). Idempotent on re-runs (npm install with an unchanged
`package-lock.json` is a fast no-op). Architectural alternative (skips
the per-clone install) documented at §11d.

---

## 10 · Native vs Docker — which to use when

| Situation | Choose |
|---|---|
| Editing code, want hot-reload | Native (`./start.sh`) |
| Demoing to someone, want zero-setup | Docker (`./start.sh --docker`) |
| Reproducing a CI failure | Docker |
| Testing cross-product traffic on `noctus-net` | Docker (the network is the point) |
| New laptop without venv yet | Docker (no Python/Node setup needed) |
| Onboarding a teammate | Docker first; native after they understand the layout |
| Deploying to a server | Docker (it IS the deploy artifact) |
| Iterating on a single hot file | Native (Docker rebuild adds 10-30s round-trip even with cache) |

The two paths share the `.env` file and the same registry — they
agree on what exists; they differ only in how it runs.

---

## 11 · Known limits + improvement backlog — CLOSED 2026-05-10

> **Closure note (2026-05-10).** The backlog is fully closed via
> `projects/containerization-backlog-closure/` orchestration: 3 waves,
> 9 engineer dispatches (T1, T2, T3, T4, T5, T6, T6-A, T6-B, T7, T8, T9),
> 1 pause-on-dependency event (E1: T6 → T6-A → T6-B), 3 pause-on-environment
> events (T6-A, T6-B, T1 — Docker BuildKit overload under concurrent
> parallel-agent build pressure). Methodology amendments shipped: KB §18
> (wave-based dispatch + pause-on-dependency + scoped-team economics) +
> KB §18.4 (resource-bounded engineer parallelism). Every backlog item
> below is ✅ Applied. Historical record preserved; future improvements
> filed as separate projects.

Captured during the 2026-05-10 containerization rollout. ✅ = applied;
all items are applied as of the closure.

### ✅ Applied 2026-05-10

1. **Scaffolder generates Docker artifacts.** `templates/product-seed/`
   ships `backend/Dockerfile` + `frontend/Dockerfile` + `docker-compose.yml`
   with placeholders; `_register_in_root_compose` appends to root
   compose `include:` on scaffold; `_unregister_from_root_compose`
   removes on `delete_product`. Roundtrip verified byte-for-byte.
2. **BuildKit cache mounts on every Dockerfile.** `# syntax=docker/dockerfile:1.7`
   directive + `RUN --mount=type=cache,target=/root/.cache/pip` (backend)
   and `target=/root/.npm` (frontend). Speeds rebuilds 5–10× on
   dependency-stable changes. `PIP_NO_CACHE_DIR` removed from ENV
   (the cache mount is not in the image; safe to cache).
3. **`.dockerignore` hardened.** Now excludes `**/__pycache__`,
   `**/.pytest_cache`, `**/*.egg-info`, `playwright-report/`,
   `test-results/`, `archive/`, `projects/`, `features/`, all `.env*`
   except `.env.example`. Smaller build context, less leak surface.
4. **CI validates compose + builds smoke images.** Two new jobs in
   `.github/workflows/test.yml`: `docker-compose-validate` runs
   `docker compose config --quiet` on root + every per-product file;
   `docker-images-build` builds core + seed images on every PR.
   Catches Dockerfile regressions before merge.
5. **Tunnel pinned to `--protocol http2`.** All 11 compose files
   (10 products + template) had `tunnel --no-autoupdate --url ...`
   with cloudflared's default `auto` protocol, which opens QUIC over
   UDP. Diagnosed live: home NAT killed the UDP session after 4
   minutes; cloudflared then retried for 2 hours without ever
   re-registering the quick-tunnel hostname (Cloudflare's edge
   deregisters on dropout). Container stayed "Up" — Docker can't
   healthcheck a `FROM scratch` image (no shell to exec). Fixed by
   pinning `--protocol http2` (forces TCP from connect-time) +
   teaching `start.sh::extract_tunnel_url` to curl-verify the URL
   end-to-end before reporting it (so dead URLs surface as `⚠` at
   boot, not at first user visit). Lesson captured in §9
   Troubleshooting row "Tunnel URL was working then…".

### 🟡 Now — small lifts, high value

5. ✅ **`VITE_*` build-arg contract codified (2026-05-10).** Every
   `import.meta.env.VITE_*` referenced in code is now declared as
   both an `ARG` in the product's frontend Dockerfile build stage
   AND an `args:` key in the compose `frontend:` service, sourced
   from `.env` via `${VITE_FOO:-}` interpolation. Per-product audit
   done; seed canonical + templates carry the pattern; 9 of 10
   product compose+Dockerfile pairs updated (youtube-crawler has
   no Docker artifacts — surfaced as a separate gap). Full contract:
   `KB § PATTERNS/containerization.md § VITE_* build-arg contract`.
6. ✅ **`@noctusai/seed` in product `package.json` (T2, containerization-
   backlog-closure Wave 1, 2026-05-10).** Added `@noctusai/seed` +
   `@noctusai/lib` as `file:../../../seed/{framework,lib}/frontend` paths
   to every product's `package.json` `dependencies` block (10 products +
   template). Vite alias still wins at build time (path-shape unchanged);
   the `file:` dep makes npm aware so external `npm install` (IDE,
   typecheck, lint hooks) doesn't break. Verified: `npm install` outside
   Docker succeeds; `vite build` green on seed + core; alias precedence
   preserved.
7. ✅ **OCI image labels (T1 + T2 + T9, containerization-backlog-closure
   Wave 1 + Wave 3, 2026-05-10).** Every backend Dockerfile (T1) AND
   frontend Dockerfile (T2) ships `LABEL org.opencontainers.image.source=
   "https://github.com/jraphaelsst/noctusai"` + `LABEL org.opencontainers.
   image.revision="${GIT_SHA}"` in the runtime stage. `ARG GIT_SHA=dev`
   default lets standalone `docker build` work; CI (T9) passes
   `--build-arg GIT_SHA=$(git rev-parse --short HEAD)` for SHA-traceable
   images. Verified on T1's slim image: `docker inspect noctus-seed-backend:slim`
   showed the labels populated with the actual commit SHA at build time.

### 🟡 Soon — quality lifts

8. ✅ **Dev override compose (T7, containerization-backlog-closure
   Wave 2, 2026-05-10).** Each per-product `docker-compose.yml` now has
   a sibling `docker-compose.override.yml` that bind-mounts the product
   source for hot-reload and swaps the production CMD for
   `uvicorn --reload`. Root `docker-compose.override.yml` auto-enables
   the `redis` profile in dev and drops `restart:` on shared services.
   `docker compose up` (no -f flags) auto-merges every override; the
   production overlay (`docker-compose.prod.yml`) is T8's scope and is
   loaded via explicit `-f docker-compose.yml -f docker-compose.prod.yml`.
   Full pattern at **§11d · Dev override compose** below.
9. ✅ **Full-fleet matrix CI build (T9, containerization-backlog-closure
   Wave 3, 2026-05-10).** Replaced the 4-of-20 smoke build with a GitHub
   Actions matrix that builds all **20 images** (10 products ×
   {backend, frontend}). `fail-fast: false` so a single heavy product
   (e.g. dev-team's agno deps) can't cancel the other 19. Each cell
   uses `docker/build-push-action@v5` with `type=gha` layer cache
   (`mode=max`, per-cell `scope`) — cross-PR reuse plus per-product
   isolation. Full pattern at **§11f · CI workflow — full-fleet matrix
   + push + scan** below.
10. ✅ **Image registry strategy + automated push (T5 + T9, 2026-05-10).**
    T5 (Wave 2) locked the per-product registry pattern (rationale at
    §11a); every per-product `docker-compose.yml` `image:` line points
    at `ghcr.io/jraphaelsst/noctus-<slug>-<role>:${NOCTUS_IMAGE_TAG:-dev}`
    so local builds keep working (`:dev` fallback) and CI sets
    `NOCTUS_IMAGE_TAG=$(git rev-parse --short HEAD)` for immutable tags.
    T9 (Wave 3) landed the automated push workflow: on `main` push, each
    matrix cell logs in via `docker/login-action@v3` with
    `secrets.GITHUB_TOKEN` and publishes both `:<short-sha>` and `:latest`
    after a clean Trivy scan. PR builds verify-only (no push). Full pattern
    at **§11f · CI workflow — full-fleet matrix + push + scan** below.
11. ✅ **Backend image multi-stage slim (T1, containerization-backlog-closure
    Wave 1, 2026-05-10).** All 11 backend Dockerfiles (seed canonical + 9
    product mirrors + template) refactored to multi-stage builder + runtime.
    Builder retains dev libs (build-essential, libffi-dev, libpq-dev,
    libcairo2-dev, libgirepository1.0-dev, libpango1.0-dev, libgdk-pixbuf-
    2.0-dev, git, pkg-config) for wheel compilation; runtime keeps only
    shared-object versions (libffi8, libpq5, libcairo2, libpango-1.0-0,
    libpangocairo-1.0-0, libgdk-pixbuf-2.0-0, libgirepository-1.0-1) +
    curl for healthcheck. Editable installs (`pip install -e ./seed/...`)
    preserved via explicit `COPY --from=builder /app/seed /app/seed` in
    runtime stage (`.egg-link` files contain absolute paths that must
    resolve). dev-team gets a 3rd-editable carve-out for `/opt/dev_team`
    (agno engine). **Measured size delta:** seed-backend `981MB → 672MB
    = −309MB (−31.5%)` — right in the predicted 200-400MB range.

### 🟢 Later — strategic

12. ✅ **Production compose overlay (T8, containerization-backlog-closure
    Wave 2).** `docker-compose.prod.yml` shipped at root + per-product
    (10 products) + template. Activated via
    `NOCTUS_IMAGE_TAG=<sha> docker compose -f docker-compose.yml -f
    docker-compose.prod.yml up`. The `-f -f` pair is explicit so Compose
    does NOT auto-load `docker-compose.override.yml` (T7's dev-shape).
    Overlay tightens: image-only (no `build:`), bare `${NOCTUS_IMAGE_TAG}`
    (no `:-dev` fallback — fail-loud on unpinned deploys), `restart:
    always`, json-file log rotation (10MB × 3 files), `deploy.resources.
    limits` (1.0 CPU + 512MB backend; 0.5 CPU + 256MB frontend; bumped
    to 2.0 CPU + 1GB for dev-team's agno engine), `read_only: true` on
    frontend rootfs with tmpfs for nginx pidfile/cache/temp paths.
    Backend left writable (phase_learnings.db + temp uploads + log lines
    need rootfs writes — chasing each with another tmpfs is more risk
    than benefit at this stage). Full pattern at **§11e · Production
    compose overlay** below.
13. **Postgres profile.** Currently every backend talks to remote
    Supabase. For offline dev / fully-isolated CI, a `postgres` profile
    serving a local DB (with a schema-init script that mirrors
    migrations) would unlock more scenarios.
14. ✅ **Per-product healthcheck override (2026-05-10).** dev-team uses
    an `agno_ping` readiness_hook on `/_ready` (seed-native seam). Wired
    via `HealthEndpointConfig(readiness_hooks=[agno_ping])` passed to
    `create_product_app(...)` in `products/dev-team/backend/app/main.py`;
    the hook lives at `products/dev-team/backend/app/services/agno_health.py`
    and probes ANTHROPIC_API_KEY presence + leader model allowlist +
    `dev_team` package importability. Per-product compose override
    targets `http://localhost:8009/_ready` with `timeout=10s` +
    `start_period=30s`. Scaffolder template (`templates/product-seed/
    docker-compose.yml`) gains a commented healthcheck-override seam so
    future products can opt-in trivially. Full pattern at **§11c ·
    Per-product healthcheck override** below.

13. ✅ **Postgres profile — applied (T4, containerization-backlog-closure
    Wave 1).** `postgres:16-alpine` service in the root compose under
    `profiles: [postgres, full]`. Schema init via
    `scripts/init-local-db/`: `00-extensions.sql` (pgcrypto, uuid-ossp,
    citext) + `00a-supabase-shims.sql` (roles + `auth.jwt()`/`auth.uid()`
    stubs + `extensions` + `storage` schemas + minimal `auth.users` table)
    + `01-schemas.sql` + `02-migrations.sql` (last two regenerated from
    each product's first migration by `scripts/build-init-local-db.sh`).
    `./start.sh local-db` activates the profile alongside the fleet. See
    §11g below for the full mental model + caveats.
14. ✅ **Health endpoint per-product variation (T6 + T6-A + T6-B,
    containerization-backlog-closure Wave 1, 2026-05-10).** **First**
    documented pause-on-dependency event (E1). T6 brief assumed
    `/api/health/agno` existed in dev-team — it didn't. T6 engineer
    correctly STOPPED rather than absorbing endpoint creation; surfaced
    a seed-native alternative (`HealthEndpointConfig(readiness_hooks=[...])`
    mounted on `/_ready`). Architect dispatched T6-A to author `agno_ping`
    via the seed-native seam (not a new path-shape). T6-B resumed +
    wired Docker compose `healthcheck:` AND Dockerfile `HEALTHCHECK`
    directive (twin-sided change — T6-B's catch) targeting `/_ready` with
    `timeout=10s` + `start_period=30s` for agno warmup. KB §11c documents
    the rule; scaffolder template carries a commented healthcheck-override
    seam. Pause-resume loop closed cleanly — full reference for KB §18.1
    methodology.
15. ✅ **Image scanning via Trivy (T9, containerization-backlog-closure
    Wave 3, 2026-05-10).** Every matrix-built image is scanned by
    `aquasecurity/trivy-action@0.24.0` for `HIGH,CRITICAL` severity CVEs
    with `exit-code: 1` (vulnerable images fail the build BEFORE the push
    step runs — they never land in the registry). Scan results upload as
    SARIF to the GitHub Security tab via `github/codeql-action/upload-sarif@v3`,
    on every build (PR + main) so findings are visible regardless of
    whether the build pushed. `ignore-unfixed: true` so we don't fail on
    CVEs without a fix path. Trivy is **pinned** to `@0.24.0` (not `@master`)
    so a scanner-engine update can't silently break CI. Full pattern at
    **§11f · CI workflow — full-fleet matrix + push + scan** below.

### Anti-patterns to avoid

- **Don't put `.env` into `COPY` lines.** Secrets go through
  `env_file:` at runtime; build-time vars go through `args:`.
- **Don't skip `WORKDIR`** between layers — `cd` in `RUN` doesn't
  persist. WORKDIR is the persistent equivalent.
- **Don't `apt-get install` without `rm -rf /var/lib/apt/lists/*`** —
  adds 30+MB of apt cache to the final image.
- **Don't run as root in production.** Every Dockerfile here ends
  with `USER noctus` deliberately.
- **Don't hand-edit per-product Dockerfiles when fixing a pattern.**
  Update `products/seed/` first, propagate (or re-run the generator
  once the scaffolder is wired).

---

## 11a · Image registry strategy

**Per-product registries** — locked 2026-05-10 (T5 of
`projects/containerization-backlog-closure/`). Each product gets its
own GHCR namespace; the platform does **not** ship a single monorepo
registry with a `noctus-<slug>` prefix.

### Rationale

- **Per-product access control.** A read/write PAT scoped to one
  product's package can be handed to a per-product deploy pipeline
  without granting blast-radius on the rest of the fleet.
- **Per-product image lifecycle.** Older immutable tags can be pruned
  per product without affecting siblings (e.g. ERP keeps 30 days of
  SHA tags, mailing keeps 7 days — independent retention policies).
- **Per-product publication cadence.** When a product ships at a
  different rhythm (e.g. core every PR, daily-life weekly), the
  registry view stays clean — no interleaved cross-product noise.
- **Per-product ownership.** Aligns with the product-folder boundary
  used everywhere else in the repo (`products/<slug>/{backend,frontend}`,
  per-product `docker-compose.yml`, per-product start.sh registration).
  Same boundary, same registry slot.

### Tag pattern

```
ghcr.io/jraphaelsst/noctus-<slug>-<role>:<tag>
```

Where:
- `<slug>` is the product slug (matches `products/<slug>/` dir name).
- `<role>` is `backend` or `frontend`.
- `<tag>` is one of:
  - `dev` — local development build. Default fallback when
    `NOCTUS_IMAGE_TAG` is unset. Local `docker compose build` produces
    images at this tag.
  - `<git-sha>` — 7-char short SHA, immutable per commit. CI builds
    set `NOCTUS_IMAGE_TAG=$(git rev-parse --short HEAD)` to produce
    these. Deploys reference these for reproducibility.
  - `latest` — the most recent CI build on `main`. Moves on every push
    to main. Convenience tag for "pull whatever just shipped"; never
    use in production deploys (race-prone).
  - `<semver>` — tagged releases (e.g. `v1.4.2`). Future; reserved for
    when products start cutting versioned releases.

### How the compose plumbing works

Every per-product `docker-compose.yml` carries:

```yaml
services:
  <slug>-backend:
    image: ghcr.io/jraphaelsst/noctus-<slug>-backend:${NOCTUS_IMAGE_TAG:-dev}
  <slug>-frontend:
    image: ghcr.io/jraphaelsst/noctus-<slug>-frontend:${NOCTUS_IMAGE_TAG:-dev}
```

`${NOCTUS_IMAGE_TAG:-dev}` is shell-style interpolation that Docker
Compose evaluates natively at compose-parse time. Three modes:

1. **Local build (no env).** `docker compose build` produces images
   tagged `ghcr.io/jraphaelsst/noctus-<slug>-<role>:dev`. The registry
   path is just a canonical image name on the local Docker daemon —
   no push, no registry contact. This is exactly the old `:dev` flow,
   just with a longer name.
2. **CI build (per-commit).** Pipeline exports
   `NOCTUS_IMAGE_TAG=$(git rev-parse --short HEAD)` before
   `docker compose build`. Images get tagged with the short SHA;
   `docker push` lands them at GHCR; deploys reference the exact SHA.
3. **Manual override.** Anyone can `NOCTUS_IMAGE_TAG=test123 docker compose up`
   to swap which tag the compose pulls/builds — useful for testing a
   pre-built image without rebuilding locally.

### Manual push recipe

When you need to push a single image by hand (one-off deploys, debug,
pre-CI sanity):

```bash
# 1. Build locally (defaults to :dev tag)
cd products/core && docker compose build

# 2. Authenticate to GHCR
#    Use a fine-scoped PAT with write:packages (and read:packages).
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin

# 3. Push the dev tag
docker push ghcr.io/jraphaelsst/noctus-core-backend:dev

# 4. (Optional) re-tag for a specific SHA and push that too
docker tag ghcr.io/jraphaelsst/noctus-core-backend:dev \
           ghcr.io/jraphaelsst/noctus-core-backend:$(git rev-parse --short HEAD)
docker push ghcr.io/jraphaelsst/noctus-core-backend:$(git rev-parse --short HEAD)
```

`GHCR_USERNAME` + `GHCR_TOKEN` are declared (commented) in the root
`.env.example`. Local devs typically leave them unset.

### Container names are unchanged

`container_name: noctus-<slug>-<role>` (no registry path) stays the
same — that's the friendly local-docker name used by `docker ps`,
inter-service DNS within the compose network, and start.sh's
healthcheck logic. Only `image:` carries the registry path.

### What still has to happen

- **T9 (Wave 3) — automated push workflow.** A GitHub Actions workflow
  that on every `main` push:
    - builds all per-product images,
    - tags them `${short-sha}` + `latest`,
    - logs in to GHCR via `GITHUB_TOKEN`,
    - pushes both tags per product.
  Pairs with §11 #15 (image scanning via trivy/grype) once the images
  are in the registry.
- **Per-product retention policies.** Once images start landing in
  GHCR, configure per-package retention (e.g. keep last 30 SHA tags,
  always keep `latest` + `dev`). Done in the GHCR UI; future
  improvement to script via the API.

## 11b · `VITE_*` build-arg contract

### Rule

> Every `import.meta.env.VITE_*` referenced in product or seed code MUST
> be declared as both:
>
> 1. **`ARG VITE_FOO=`** (followed by `ENV VITE_FOO=${VITE_FOO}`) in
>    the product's `frontend/Dockerfile` build stage, AND
> 2. **`VITE_FOO: ${VITE_FOO:-}`** in the compose `frontend:` service's
>    `build.args:` block, sourced from the repo-root `.env`.
>
> **Carve-out:** `VITE_BACKEND_API_URL` and `VITE_PRODUCT_SCHEMA` are
> factory-injected at compile time via `define:` in
> `seed/framework/frontend/vite.config.factory.ts`. They are substituted
> into the Vite bundle regardless of `process.env`, so they do not need
> the ARG/args bridge. All other `VITE_*` vars come from `.env` and DO
> need the bridge.

### Why

Vite reads `.env` at build time via `envDir: repoRoot` in the seed
factory. But `.env` itself is excluded from the Docker build context
(`.dockerignore` carves it out — it carries runtime secrets that
should never bake into images). Without the build-arg bridge, the
Vite build inside the container sees an empty environment and every
`import.meta.env.VITE_FOO` silently resolves to `undefined`.

Build-args are the documented bridge:
- `docker compose` reads the repo-root `.env` natively for `${...}`
  interpolation in compose files (this is a compose feature, not
  Docker's — it does NOT bake `.env` into the image).
- The `args:` block hands those values to `docker build` as
  `--build-arg` flags.
- `ARG VITE_FOO=` in the Dockerfile declares them as build-time
  variables; `ENV VITE_FOO=${VITE_FOO}` promotes them to the
  `process.env` that Vite reads during `npm run build`.
- The image carries `VITE_*` baked into the static JS bundle (which is
  the intended outcome — they're public values).

### Public-by-design reminder

`VITE_*` vars are **public** by Vite's design — they ship to the
browser bundle as plain strings. Only put PUBLIC config here:

- URLs (`VITE_CORE_URL`, `VITE_SUPABASE_URL`)
- Anon / publishable keys (`VITE_SUPABASE_PUBLISHABLE_KEY`)
- Feature flags

Server-side secrets (service-role keys, signing keys, OAuth client
secrets) stay in **non-`VITE_*`** env vars and are loaded at runtime
by the backend via `env_file:`. Never bridge a non-`VITE_*` secret
through `args:` — anything that lands in the Vite bundle is world-
readable in the browser DevTools.

### Per-product flow

1. **Audit.** Grep product (+ seed) source for `import.meta.env.VITE_*`:
   ```bash
   grep -rho 'import\.meta\.env\.VITE_[A-Z_]*' products/<slug>/frontend/src \
     | sed 's/import\.meta\.env\.//' | sort -u
   ```
2. **Subtract the factory-injected carve-out** (`VITE_BACKEND_API_URL`,
   `VITE_PRODUCT_SCHEMA`).
3. **For each remaining var:**
   - Add `ARG VITE_FOO=` + `ENV VITE_FOO=${VITE_FOO}` to
     `products/<slug>/frontend/Dockerfile` (in a block before the
     `Layer 1: seed frontend packages` copy).
   - Add `VITE_FOO: ${VITE_FOO:-}` to the `frontend:` service's
     `build.args:` block in `products/<slug>/docker-compose.yml`.
4. **Declare the var in `.env.example`** so collaborators see what to
   fill in. Real values go in `.env` (git-ignored).
5. **Validate:** `docker compose -f products/<slug>/docker-compose.yml config --quiet`.
6. **Smoke-build:** `docker build --build-arg VITE_FOO=test -f products/<slug>/frontend/Dockerfile -t smoke:fe .`.

### Example (canonical seed)

**`products/seed/frontend/Dockerfile`**:
```dockerfile
FROM node:20-alpine AS build
WORKDIR /app

# VITE_* build-arg contract
ARG VITE_CORE_URL=
ENV VITE_CORE_URL=${VITE_CORE_URL}

# Layer 1: seed frontend packages
COPY seed/framework/frontend ./seed/framework/frontend
# … rest of the build
```

**`products/seed/docker-compose.yml`** (frontend service):
```yaml
seed-frontend:
  build:
    context: ../..
    dockerfile: products/seed/frontend/Dockerfile
    args:
      VITE_CORE_URL: ${VITE_CORE_URL:-}
  # … rest of the service
```

**`.env`** (repo root):
```
VITE_CORE_URL=https://core.noctus.ai
```

### Scaffolder behavior

`templates/product-seed/frontend/Dockerfile` + `docker-compose.yml`
carry the canonical block (with `VITE_CORE_URL` as the seed example).
A newly-scaffolded product inherits the contract out of the box.
When a product adds a new `VITE_FOO` usage, the engineer who adds
the `import.meta.env.VITE_FOO` reference is also responsible for
adding the ARG + args + `.env.example` triple (or filing a single-file
project to extend the seed if the var is shared across products).

### Why `${VITE_FOO:-}` and not `${VITE_FOO}`

The `:-` fallback yields an empty string when the env var is unset,
which keeps `docker compose config` validation green even when the
user hasn't filled `.env` yet (CI scenarios, fresh clones, smoke
tests). Without the fallback, validation hard-fails with "WARN…
not set" output. The empty-string default matches Vite's existing
behavior (`import.meta.env.VITE_FOO || "default"` patterns in code
already handle missing values gracefully).

### Anti-patterns

- **Don't `COPY .env` into Dockerfile.** `.env` carries runtime
  secrets and must stay out of the image.
- **Don't add `ENV` without `ARG`.** `ENV VITE_FOO=${VITE_FOO}`
  alone doesn't read anything from the build environment;
  `ARG VITE_FOO=` declares the build-time variable that becomes
  `${VITE_FOO}`.
- **Don't put secrets in `VITE_*`.** They're public. The bundle is
  world-readable.
- **Don't skip the `.env.example` update.** Out-of-band declaration
  surfaces what the product needs; collaborators shouldn't have to
  grep code to discover required env vars.

---

## 11c · Per-product healthcheck override

**Rule.** Products inherit the seed-default Docker healthcheck which
hits `/api/health` (a simple liveness probe — "FastAPI is up and
routing requests"). When a product needs a **deeper readiness probe**
(API key presence, model allowlist, downstream package importability,
external service reachability), attach a `HealthCheckHook` to the
seed's existing `/_ready` endpoint via `HealthEndpointConfig
(readiness_hooks=[<hook>])` passed to `create_product_app(...)`, then
override the per-product `docker-compose.yml` healthcheck to target
`/_ready` (or `/_health` for liveness-only) with timeouts and
`start_period` tuned for the deeper probe.

**Why prefer `/_ready` over inventing `/api/health/<concern>`.** The
seed-native `/_ready` endpoint is a NAMED SEAM (per the Seed-First
rule). Inventing a `/api/health/<concern>` URL shape is a structural
fork — it duplicates plumbing the seed already provides and creates a
per-product convention divergence. The `readiness_hooks` list **composes**:
every hook a product registers contributes a single entry to the
`/_ready` JSON `checks[]` array; `/_ready` aggregates and returns 503
when **any** hook reports `ok=False`. Multiple hooks per product, one
endpoint, one contract.

### dev-team example (concrete reference)

- **Hook**: `products/dev-team/backend/app/services/agno_health.py`
  defines `agno_ping`. Three sub-100ms local checks (no network):
  ANTHROPIC_API_KEY env truthy, leader model in known-Anthropic
  allowlist, `dev_team` package importable + `__version__` readable.
  Returns `(ok: bool, error_msg: str | None)` matching the seed's
  `HealthCheckHook` Protocol.
- **Wiring**: `products/dev-team/backend/app/main.py` passes
  `health_config=HealthEndpointConfig(readiness_hooks=[agno_ping])` to
  `create_product_app(...)`. The hook's `__name__` ("agno_ping")
  surfaces in `/_ready` JSON `checks[]` automatically.
- **Compose override**: `products/dev-team/docker-compose.yml` carries:

  ```yaml
  dev-team-backend:
    # ... build / image / env_file / ports / networks ...
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8009/_ready"]
      interval: 30s
      timeout: 10s            # agno_ping is sub-100ms but allow headroom
      retries: 3
      start_period: 30s        # agno warmup is genuinely slower
  ```

- **Why `start_period: 30s`.** dev-team's first import of
  `dev_team.configs` lazy-loads agno's adapter packages; the cold-start
  cost lands the first ready response in the 5–10s range on a warm
  daemon. The seed's default `start_period: 20s` cuts it too close on
  slower hosts.
- **Why `timeout: 10s`.** `agno_ping` itself is sub-100ms (all three
  pins are local lookups), but the override keeps headroom in case
  `load_config('default')` ever evolves to read more YAML or `dev_team
  .__init__` adds a heavier lazy attr.
- **503 contract is preserved.** When ANTHROPIC_API_KEY is unset,
  `agno_ping` reports `ok=False`; `/_ready` returns 503; Docker flips
  the container to `unhealthy`. This is correct behavior — the
  container truthfully reports it cannot dispatch team runs.

### Scaffolder template seam

`templates/product-seed/docker-compose.yml` ships a commented
override block under the default healthcheck, demonstrating the
shape for future products. Uncommenting + tweaking is a 30-second
operation; the discoverability cost of "where do I put this?" is
paid once by the template, not N times by readers.

### When NOT to override

- The product's actual health surface is "is FastAPI up?" — the
  seed default `/api/health` is correct and there's nothing deeper
  to probe.
- The "deeper" probe would do real I/O (network call, DB query) on
  every healthcheck interval — that's an anti-pattern. Healthchecks
  run frequently (every 30s by default); a hook that hits Anthropic
  per probe would generate cost and rate-limit pressure. Keep
  readiness hooks cheap and local; let runtime errors surface real
  network failures.

### Anti-patterns

- **Inventing `/api/health/<concern>` instead of using `/_ready`.**
  Structural fork; `/_ready` already exists in the seed and composes.
- **Healthcheck with side effects.** Probes must be read-only. A
  healthcheck that warms a cache or initializes a connection pool is
  doing real work on every interval.
- **Reducing `start_period` to chase faster boot reporting.** The
  start_period is a grace window — until it elapses, failures don't
  flip the container `unhealthy`. Too short → first agno warmup
  flips the container unhealthy → orchestrators restart it → loop.
- **Forgetting to update both the override AND the registration.**
  The compose healthcheck and the `readiness_hooks=[...]` list are
  twin sides of the same change; touching only one leaves either
  the deeper probe unwired (the readiness hook never runs because
  Docker's still hitting `/api/health`) or the override blind
  (Docker hits `/_ready` but no product-specific hooks are
  registered, so the deeper signal isn't surfaced).

## 11e · Production compose overlay

> **Status:** Applied 2026-05-10 (T8, containerization-backlog-closure
> Wave 2). Closes §11 backlog #12.

### Rule

Production runs the fleet via an explicit overlay pair:

```bash
NOCTUS_IMAGE_TAG=$(git rev-parse --short HEAD) \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The `-f docker-compose.yml -f docker-compose.prod.yml` pair is
**mandatory** — naming files explicitly tells Compose to NOT auto-load
`docker-compose.override.yml` (T7's dev-shape overrides: bind-mounts,
hot-reload, no resource caps). Without `-f`, Compose's default
`docker compose up` would pull the override in alongside the base.

### When to use it

- **Deployment to staging / prod** — replaces ad-hoc compose tweaks
  with a checked-in deployment artifact.
- **CI integration tests requiring prod shape** — runs against
  registry images at a specific SHA, with the same resource caps and
  restart policy the real deploy uses.
- **Resource-capped local runs** — when you want to test how the
  fleet behaves under the prod envelope without spinning up Swarm/k8s.

### Why image-only, no `build:`

Prod consumes registry images; if you need to rebuild for prod, you
**build in CI, push to the registry, then prod pulls**. The base
files keep their `build:` directives (used by dev `docker compose
build`); prod overlays simply don't override them, but the deploy
path is `docker compose pull && docker compose up` — `build:` is
never triggered.

The rationale: a prod box that can `build` is a prod box that has
build deps installed (gcc, dev libraries, full npm tree). That's a
larger attack surface, more disk, more variance. Pre-built artifacts
land at one SHA and stay there.

### Why bare `${NOCTUS_IMAGE_TAG}` (no `:-dev` fallback)

The base files use `${NOCTUS_IMAGE_TAG:-dev}` so local builds tag as
`:dev` automatically. Prod overlays use bare `${NOCTUS_IMAGE_TAG}` —
when the variable is unset, Compose renders `image: ghcr.io/.../...:`
(empty tag), which **fails at `docker compose pull`**. That's the
intent: a prod deploy without a pinned SHA is a misuse; fail at the
gate rather than silently shipping `:dev`.

CI deploys set `NOCTUS_IMAGE_TAG=$(git rev-parse --short HEAD)` and
push images with that tag (see §11a).

### Resource caps + log rotation

Per-product caps are conservative starting points; revise after the
first prod run with real traffic:

| Service              | CPUs    | Memory  | Rationale                              |
|----------------------|---------|---------|----------------------------------------|
| backend (default)    | 1.0     | 512 MB  | FastAPI + uvicorn + business logic     |
| frontend             | 0.5     | 256 MB  | nginx + static files (very light)      |
| dev-team backend     | 2.0     | 1024 MB | agno engine + 11 specialists in-proc   |
| redis (shared)       | 0.5     | 256 MB  | small key set                          |
| waha (shared)        | 1.0     | 512 MB  | WhatsApp HTTP API + node runtime       |

`deploy.resources.limits` is **enforced under Swarm / k8s**; under
plain `docker compose up` it's advisory (no enforcement). Documenting
it in the overlay is still valuable — the orchestrator reads from the
same compose file when it lands.

Log rotation (`logging.driver: json-file` + `max-size: 10m` +
`max-file: 3`) prevents the host disk filling with container logs;
default Docker behavior is unbounded growth, which is a known cause
of "container says it's up but the host ran out of disk" surprises.

### Read-only filesystems

Frontend gets `read_only: true` with three tmpfs mounts
(`/var/cache/nginx`, `/var/run`, `/tmp`) — nginx writes its pidfile,
cache, and client_body_temp_path under those paths. Everywhere else
on the rootfs is read-only, so an exploited frontend can't drop a
binary.

Backend left writable: phase_learnings.db, temp uploads, structlog
output, and a few seed-framework dirs all write to rootfs today.
Chasing each with a dedicated tmpfs is more breakage risk than the
hardening gain at this stage; revisit when the seed's IO surface is
audited.

### What's intentionally absent

- **`postgres` service in the prod overlay.** Prod talks to managed
  Supabase / RDS / Cloud SQL. The `postgres` profile (§11g) is for
  offline dev; bringing it up in prod is a misuse.
- **Cloudflared tunnels.** Prod uses real DNS + named tunnels (or
  the platform's hosting front-door); the `trycloudflare.com`
  quick-tunnel pattern is dev/demo-only.
- **`docker-compose.override.yml` auto-load.** The whole point of
  `-f -f` is to opt out.

### Files

- `docker-compose.prod.yml` (root) — overlay for shared services
  (redis, waha) + `include:` re-listing each product's pair
  `[base.yml, prod.yml]` so per-product hardening lands.
- `products/<slug>/docker-compose.prod.yml` — per-product overlay
  for the 10 active products (10 × 2 services).
- `templates/product-seed/docker-compose.prod.yml` — scaffolder
  template; new products inherit the shape on creation.

### Anti-patterns

- **Running `docker compose up` (no `-f`) in prod.** Auto-loads the
  dev override and silently undoes every prod hardening.
- **Setting `${NOCTUS_IMAGE_TAG:-dev}` in the prod overlay.** Defeats
  the fail-loud guard; defaults to `:dev` and ships dev images to
  prod.
- **Setting `build:` in the prod overlay.** Even if not triggered,
  it signals "this prod has build deps." Keep prod images
  consume-only.
- **Resource caps that exceed the host's real envelope.** Caps are
  the orchestrator's contract; if the cap can't be honored, the
  scheduler doesn't know that until it tries to start. Calibrate
  to the smallest production host, not the dev laptop.
- **`read_only: true` on the backend without auditing IO paths.**
  The backend writes in a half-dozen places today; flipping the bit
  without tracing those would cause silent failures (sqlite
  read-only errors logged but not bubbled; phase_learnings.db
  vanishing into a tmpfs that gets wiped on restart).

## 11g · Local-postgres profile (offline dev)

> **Status:** Applied 2026-05-10 (T4, containerization-backlog-closure
> Wave 1). Closes §11 backlog #13.

### When to use it

- **Offline dev** — flight, no internet, no Supabase reach.
- **Fully-isolated CI** — no network to remote services; reproducible
  schema applied identically every run.
- **Fresh laptop** — Supabase project credentials not yet provisioned;
  want to verify the stack starts.
- **Migration sanity-check** — apply every product's first migration
  against a clean Postgres to surface SQL errors *before* they hit
  staging.

Default `docker compose up` does NOT bring postgres up. Default `start.sh`
fleet mode does NOT bring it up. The profile is fully opt-in.

### How to activate

```bash
./start.sh local-db                                # fleet + postgres
docker compose --profile postgres up -d postgres   # postgres only
docker compose --profile full up                   # everything
```

The container exposes `5432` on the host, plus an internal alias
`postgres` reachable on `noctus-net`:

| From | URL |
|---|---|
| host shell (psql, pgcli, IDE) | `postgresql://noctus:noctus_local@localhost:5432/noctus` |
| inside any product container | `postgresql://noctus:noctus_local@postgres:5432/noctus` |

### What runs on first boot

Files under `scripts/init-local-db/` are bind-mounted to
`/docker-entrypoint-initdb.d/` (read-only). The official postgres image
runs every `.sql` / `.sh` in that directory in **alphabetical order**
on a fresh `postgres_data` volume:

| Order | File | Purpose |
|---|---|---|
| 1 | `00-extensions.sql` | `CREATE EXTENSION pgcrypto / "uuid-ossp" / citext` |
| 2 | `00a-supabase-shims.sql` | roles (`anon` / `authenticated` / `service_role`) + `auth.{jwt,uid,role,email}()` no-op functions + `auth.users` shim + `extensions` / `storage` schema placeholders |
| 3 | `01-schemas.sql` | `CREATE SCHEMA IF NOT EXISTS <slug>` per product **(generated)** |
| 4 | `02-migrations.sql` | concatenated `products/*/backend/migrations/<first>_*.sql` wrapped in `BEGIN; ... COMMIT;` per product **(generated)** |

### Regenerating the init scripts

When a product's first migration changes (rare — usually 001 is frozen),
regenerate the two generated files:

```bash
bash scripts/build-init-local-db.sh
```

The generator finds the lexicographically-first numeric-prefixed `.sql`
in each `products/*/backend/migrations/` directory (handles both
3-digit `001_*` and 4-digit `0001_*` zero-padding). Output is
deterministic; commit alongside the migration change.

### Caveat — schema init runs ONCE per volume

The postgres official image only runs `/docker-entrypoint-initdb.d/`
when the data directory is empty. After the first successful boot, the
volume has data and subsequent `docker compose up postgres` reuses it
unchanged. To re-init:

```bash
./stop.sh volumes        # drops the postgres_data volume
./start.sh local-db      # fresh init
```

### Caveat — RLS policies evaluate to FALSE under default settings

Every product migration references `auth.jwt()->>'org_id'` in its RLS
policies. The shim returns NULL (no JWT issuer in offline-dev), so RLS
filters reject all rows for non-superusers. Two workarounds:

1. **Connect as `noctus`** (the `POSTGRES_USER` — superuser; bypasses
   RLS). Default in `psql -U noctus`.
2. **Simulate a logged-in user per session** —
   `SET LOCAL request.jwt.claims = '{"org_id": "...", "sub": "..."}';`
   before queries. `auth.jwt()` will then return that JSON.

### Caveat — Supabase-specific features are best-effort

Some product migrations reference features `postgres:16-alpine` doesn't
ship: `CREATE EXTENSION vector`, `CREATE EXTENSION pg_cron`, `CREATE
EXTENSION pg_net`, Supabase `storage.objects` table. The generator
wraps each product's migration in `BEGIN; ... COMMIT;` so a single
product's failure rolls back THAT product's block only — the rest of
the fleet still applies. ERP is the typical casualty (uses pgvector
for embeddings); accept-with-rationale for offline-dev. To use those
features locally, install the extensions in the postgres image
(rebuild postgres with `pgvector/pgvector:pg16` base) or live with
that one product missing in offline-dev.

### Wiring a product at the local DB

Most products consume Supabase via PostgREST (`SUPABASE_URL` is an
HTTP endpoint, not a raw postgres URL). Pointing a product at the
local Postgres requires the product to swap its data-access path to
raw psycopg2/asyncpg — out of scope for T4. The local DB is shipped
today as a **schema + data substrate** for ad-hoc psql / pgcli /
direct-SQL workflows; a follow-up (or per-product carve-out) wires
runtime read/write through.

---

## 11d · Dev override compose

**Locked 2026-05-10** (T7 of `projects/containerization-backlog-closure/`,
Wave 2). Closes §11 backlog item #8.

Standard Docker pattern: split a single `docker-compose.yml` into a
production-shape base file + a `docker-compose.override.yml` that flips
runtime behavior toward dev. `docker compose up` (no `-f` flags) auto-
merges the override on top; production deployment uses an explicit
`-f docker-compose.yml -f docker-compose.prod.yml` combo (the prod
overlay — T8's scope — does NOT inherit the dev override).

### Rule

Per-product `docker-compose.override.yml` is auto-loaded by
`docker compose up` when no `-f` flags are given. Each override file
carries three flips relative to the base compose:

1. **Bind-mount the product source.** `./backend:/app/products/<slug>/backend`
   + `./frontend:/app/products/<slug>/frontend`. Edits propagate without
   rebuild — uvicorn's `--reload` watches the bind-mounted tree via
   `watchfiles` (bundled with `uvicorn[standard]`).
2. **`uvicorn --reload`.** The override replaces the production CMD
   (which runs without `--reload`) with a list-form `command:` that
   adds `--reload` while keeping the same `--host` / `--port` /
   `--app-dir` invocation. Required because the production Dockerfile
   CMD is the no-reload form (matches how it ships).
3. **`restart: "no"`.** Production carries `restart: unless-stopped` so
   container crashes auto-recover. In dev that hides the crash in logs
   between restart loops; flipping to `"no"` makes failures visible.
4. **`NODE_ENV=development`.** Frontend container env so any build-time
   conditional routes to the dev path.
5. **`build.target: dev` + vite dev server `command:` (frontend).** The
   override picks the `dev` stage from the multi-stage frontend
   Dockerfile (node + deps installed, no `npm run build`) and runs
   `npm run dev -- --host 0.0.0.0 --port <fp>` so vite watches the
   bind-mounted source for HMR. Production (`docker-compose.prod.yml`
   overlay) bypasses this override → default Dockerfile target = the
   nginx runtime stage, serving the pre-built static bundle as before.
   **The `--host 0.0.0.0` flag is non-negotiable** — vite's default
   `localhost` binding inside a container is unreachable from the host.
   Closes the HMR gap T7 deferred. See "Dev/prod target split" below.

### When the override applies

Two paths auto-load the override:

```bash
# Path A: standalone (one product at a time)
cd products/seed && docker compose up
# auto-finds docker-compose.yml + docker-compose.override.yml siblings.

# Path B: orchestrated (full fleet from root)
docker compose up
# root docker-compose.yml's `include:` uses extended `path:` syntax to
# pull each per-product compose + override as a 2-file list, so the
# override merges per product. See "How the root-compose merge works"
# below.
```

Production deployment uses an explicit flag combo that excludes the
override:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up
```

`start.sh` continues to work in dev — it shells out to `docker compose
up` with no `-f`, so the override auto-loads.

### How the root-compose merge works

Critical detail discovered empirically (2026-05-10, T7): Docker
Compose's auto-load of `docker-compose.override.yml` ONLY applies to
the override sibling of the invoked file. Files pulled in via
`include:` do NOT auto-pull their own overrides. Without intervention,
`docker compose up` at root would NOT apply per-product overrides.

The fix: root `docker-compose.yml`'s `include:` block uses the extended
`path:` list syntax (compose v2.20+) so each entry loads both the base
compose AND the override:

```yaml
include:
  # BEGIN_PRODUCTS_INCLUDE
  - path:
      - products/core/docker-compose.yml
      - products/core/docker-compose.override.yml
  - path:
      - products/seed/docker-compose.yml
      - products/seed/docker-compose.override.yml
  # ... etc per product
  # END_PRODUCTS_INCLUDE
```

The scaffolder's `_register_in_root_compose` emits this multi-line
shape for new products; `_unregister_from_root_compose` removes the
whole 4-line block (path: parent + base + override) on delete.

### Dev/prod target split

**Locked 2026-05-11** (follow-up dispatch from T7). Closes the HMR gap
the original T7 deferred. The canonical frontend Dockerfile is now
three-stage:

1. **`build`** stage (existing) — node + deps installed + `npm run
   build` produces `/app/products/<slug>/frontend/dist`.
2. **`dev`** stage (NEW) — node + deps installed, no `npm run build`.
   Default `CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]` lets
   `docker run` without compose still work; the dev override supplies
   the actual `command:` with `--port <fp>` so the published port
   matches the compose mapping.
3. **`nginx:alpine`** runtime stage (existing, unchanged) — `COPY
   --from=build .../dist` + nginx. **This is the default target** —
   `docker build` with no `--target` flag builds production-shape
   unchanged. T8's prod overlay continues to consume this image as-is.

Selection is per-environment:

```bash
# Dev — auto-loads override → frontend builds `dev` stage → vite dev server
docker compose up
# (root) or
cd products/seed && docker compose up

# Prod — explicit overlay bypasses override → frontend builds default
# (nginx) stage → serves static bundle, unchanged
docker compose -f docker-compose.yml -f docker-compose.prod.yml up
```

The `dev` stage adds image build time + image size, but only when
explicitly built (target=dev). Production images are untouched.

**Vite-in-docker is optional.** If you prefer running vite locally (`cd
products/<slug>/frontend && npm run dev`), the dev-in-docker shape is
opt-in. Both paths produce the same HMR experience; the docker shape
is for "I want the full fleet up in one command."

### Prod-overlay dev-reset discipline (formalized 2026-05-11)

**The mechanism.** Compose's `!reset` is **merge-operation-scoped, not service-name-scoped.** When `-f a.yml -f b.yml` is invoked, each file resolves its own `include:` tree first, then the top-level structures of `a` and `b` merge. A `!reset` declared inside an `include:`'d file of `b` (e.g. `products/<slug>/docker-compose.prod.yml`) cannot see values contributed by an `include:`'d file of `a` (e.g. `products/<slug>/docker-compose.override.yml`). The reset has to live at the **top-level of the outermost overlay file** (`docker-compose.prod.yml` at repo root) to fire across that boundary.

**The rule.** Every key the dev override sets that is NOT also set by the per-product prod overlay needs an explicit `!reset null` at the top-level of `docker-compose.prod.yml`. Per-product-prod-overlay-set keys do NOT need reset — compose's later-wins merge handles them naturally.

**Today's mapping (T7 dev override + HMR Option B):**

| Key | Set by dev override? | Set by per-product prod overlay? | Top-level reset needed? |
|---|---|---|---|
| `build.target: dev` | Yes (frontend) | No | ✅ Reset |
| `volumes` (bind-mounts) | Yes (both) | No | ✅ Reset |
| `command` (uvicorn --reload / npm run dev) | Yes (both) | No (image default CMD wins) | ✅ Reset |
| `restart: "no"` | Yes (both) | Yes (`restart: always`) | ❌ Per-product prod overrides directly |
| `environment.NODE_ENV: development` | Yes (frontend) | Yes (`NODE_ENV: production`) | ❌ Per-product prod overrides directly |

**The recurrence-rule trigger.** When the dev override gains a new runtime-affecting key:

1. Check if the per-product prod overlay sets the same key.
2. If yes → no top-level reset needed; later-wins handles it.
3. If no → add `<key>: !reset null` to every service entry in `docker-compose.prod.yml`'s top-level `services:` block.

N=2 today (two `!reset` rounds: HMR Option B's build+command, then 2026-05-11 expansion to volumes + backend-command). If a future dispatch adds another runtime-affecting key to the dev override → recurrence rule fires.

This rule is CI-enforced via `.github/workflows/test.yml::prod-render-clean` — any future override change that re-introduces a leak fails CI.

**Anti-patterns.**

- **Resetting at per-product-prod-overlay level** (inside `products/<slug>/docker-compose.prod.yml`). Doesn't fire — wrong merge-operation scope. HMR engineer hit this on first pass + fixed by hoisting to top level.
- **Resetting EVERY override key uniformly.** Over-aggressive — clobbers per-product prod overlay's intended values (`restart: always`, `NODE_ENV: production`). Reset ONLY keys without a per-product-prod-overlay counterpart.
- **Re-listing `include:` for prod overlay without the per-product prod overlay path.** A new product added to root's `include:` AND to start.sh PRODUCTS needs its `docker-compose.prod.yml` path added to THIS file's `include:` block — otherwise per-product prod hardening doesn't apply. youtube-crawler hit this gap (caught + fixed 2026-05-11).

### Common pitfalls

- **Bind-mount must NOT clobber `/opt/venv`.** The backend Dockerfile
  installs the virtualenv at `/opt/venv` (outside `/app`); the bind
  only replaces source under `/app/products/<slug>/backend`. If a
  future Dockerfile moves the venv into `/app`, the override needs an
  anonymous volume to protect it.
- **Frontend bind-mount overlays node_modules.** The `dev` stage
  installs npm deps inside the image at
  `/app/products/<slug>/frontend/node_modules`; the dev override
  bind-mounts the product's host `./frontend` directory ON TOP at the
  same path. The host directory typically has `node_modules/` (from
  local `npm install`) — that one wins. If the host's `node_modules` is
  stale or missing, dev startup fails with "cannot find package vite".
  Workaround: `./scripts/first-time-setup.sh` once per fresh clone;
  idempotent on re-runs (npm install with existing node_modules + an
  unchanged package-lock.json is a fast no-op). The script drives off
  start.sh's `BEGIN/END_PRODUCTS_REGISTRY` sentinels so newly-scaffolded
  products are auto-covered. Architectural alternative (no per-clone
  install): narrow the bind-mount to
  `./frontend/src:/app/products/<slug>/frontend/src` so only source is
  overlaid and the in-image `node_modules` survives — trade-off is HMR
  no longer auto-reloads on root-level config edits (vite.config.ts,
  package.json, tsconfig.json). Current shape uses the install path.
- **`--host 0.0.0.0` is non-negotiable.** Vite's default `localhost`
  binding inside a container = unreachable from the host. The
  override's `command:` MUST include it. The `dev` stage's default
  `CMD` does too as a safety fallback.
- **`--port <fp>` must match the compose port mapping.** Compose
  `ports: ["<fp>:<fp>"]` publishes the container port to host. Vite's
  `--port <fp>` flag tells vite which port to bind inside the
  container. They MUST match — HMR WebSocket rides on the same port,
  and a mismatch shows up as "WebSocket connection failed" in the
  browser console.
- **`--reload` requires `uvicorn[standard]`.** Every product's
  `requirements.txt` pins `uvicorn[standard]==0.30.6` which bundles
  watchfiles. Confirmed across all 10 products (T7 audit).
- **Don't override `image:` in the override.** Image tag stays shared
  with prod (the `ghcr.io/jraphaelsst/...` line from §11a). The
  override only changes runtime behavior (bind-mounts, command, env),
  not the built artifact.
- **Don't add `restart: unless-stopped` in the override.** Dev wants
  visible crashes.
- **dev-team agno warmup.** `--reload` works but every backend save
  re-runs the agno engine warmup (re-imports `dev_team/`, re-probes
  ANTHROPIC_API_KEY, re-validates the leader allowlist). Cold reload
  takes 10-20s on a warm Anthropic connection. If iteration becomes
  painful, drop `--reload` from `products/dev-team/docker-compose.override.yml`
  and use `docker compose restart dev-team-backend` for manual reload.
  Documented inline at the dev-team override.

### Root override

The root `docker-compose.override.yml` covers the shared platform
services (`redis`, `waha`, `postgres`):

- **Redis profile auto-on in dev.** `profiles: !reset []` clears the
  `[redis, full]` gate from the base file so `docker compose up`
  (no `--profile redis`) brings Redis up automatically. Many products
  use it (chatbot buffer, WhatsApp router, scheduling queues); having
  it default-on in dev is a usability win. Production excludes this
  override → profile gating returns → redis stays opt-in.
- **Redis verbose logging.** `redis-server --loglevel verbose` for dev
  command-level visibility (vs default `notice`).
- **`waha` stays gated** even in dev — heavy, only needed by chatbot
  products.
- **`restart: "no"`** on all shared services so dev crashes are visible.

### Scaffolder template

`templates/product-seed/docker-compose.override.yml` mirrors the
per-product pattern with `{{PRODUCT_SLUG}}` / `{{BACKEND_PORT}}`
placeholders. `scripts/sync-seed-template.sh` substitutes literal
`seed-*` service names + `products/seed/` paths in compose files into
`{{PRODUCT_SLUG}}` during sync, so the seed override at
`products/seed/docker-compose.override.yml` (literal `seed-backend`)
correctly mirrors to the template (`{{PRODUCT_SLUG}}-backend`) for
downstream scaffold consumption.

### imobi-scheduling carve-out

`products/imobi-scheduling/docker-compose.yml` still carries stale
literal `seed-*` service names (a pre-existing scaffold artifact, not
T7's regression). T7 deliberately did NOT author an override for
imobi-scheduling because the override would have to match the stale
service names (e.g. `seed-backend`) rather than the slug. Tracked as
a follow-up: rename imobi-scheduling's service names + add the
override. The compose `include:` keeps imobi-scheduling on the legacy
single-line syntax (no override path) until that gap closes.

---

## 11f · CI workflow — full-fleet matrix + push + scan

Landed T9 of `projects/containerization-backlog-closure/` (Wave 3,
2026-05-10). Closes backlog items #9 (full-fleet build), #10 CI half
(automated GHCR push), and #15 (image scanning) in one workflow update.
Lives in `.github/workflows/test.yml` as the `docker-images-build` job;
the existing pytest / frontend-build / e2e / compose-validate jobs are
preserved unchanged.

### Matrix shape

```yaml
strategy:
  fail-fast: false
  matrix:
    product:
      - core
      - erp-imobiliario
      - personal-finance
      - therapy-platform
      - daily-life
      - mailing
      - adconnect
      - dev-team
      - seed
    role: [backend, frontend]
```

**9 products × 2 roles = 18 matrix cells.** Each cell is one GitHub
Actions runner. `fail-fast: false` is non-negotiable: dev-team's
backend (~900MB with the agno engine) is the heaviest build and prone
to flake; without `fail-fast: false`, a single dev-team-backend failure
would cancel the other 17 builds and waste 20-30 minutes of compute.

**`youtube-crawler` and `imobi-scheduling` are intentionally absent**
from the matrix:
- `youtube-crawler` has no Docker artifacts yet (surfaced T3, tracked
  as a separate follow-up).
- `imobi-scheduling` still carries stale `seed-*` literal service
  names from a pre-T7 scaffold (see §11d carve-out). Add it to the
  matrix after the rename lands. (The earlier `media-scheduling` port
  of the same product was deleted 2026-05-11 — imobi consolidates.)

### Cache strategy

Every build step uses `docker/build-push-action@v5` with:

```yaml
cache-from: type=gha,scope=${{ matrix.product }}-${{ matrix.role }}
cache-to:   type=gha,mode=max,scope=${{ matrix.product }}-${{ matrix.role }}
```

- **`type=gha`** is the GitHub Actions cache backend — distinct from
  `actions/cache@v4` and the only cache type `docker/build-push-action`
  natively supports for buildx.
- **`mode=max`** keeps every intermediate layer (not just the final
  image), trading cache size for fastest rebuilds. Without `mode=max`,
  a one-line `requirements.txt` change re-runs the entire pip install.
- **Per-cell `scope`** isolates each product+role's cache so adconnect's
  build never invalidates seed's. Reduces cross-pollination evictions
  in the LRU.
- **10GB GHA cache cap per repo** evicts LRU when full. For 20 images ×
  ~500MB-1GB each, the cache fills; eviction is GHA's responsibility
  and it's tuned for "warm core, cold fringe" — fine for our cadence.

### Push trigger (main only)

The push step is gated:

```yaml
- name: Push to GHCR (main only, scan-clean only)
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
```

- **PRs build + scan but never push.** Verification only — image lands
  in the local daemon, Trivy scans it, SARIF uploads to the GH Security
  tab. The image is discarded when the runner shuts down.
- **`main` pushes trigger registry publication.** Both `:<short-sha>`
  (immutable, deploy-grade) and `:latest` (convenience, never use in
  production deploys per §11a) are pushed.
- **Auth via `secrets.GITHUB_TOKEN`** + `docker/login-action@v3`. The
  default token gets `packages: write` from the job-level `permissions:`
  block — no PAT setup needed.

### Build → scan → push ordering

The job runs three distinct build-push-action steps:

1. **Build to local daemon** (`load: true, push: false`) — every run.
2. **Trivy scan** of the local image — every run. `exit-code: 1` fails
   the job if HIGH or CRITICAL CVEs surface.
3. **Push to GHCR** (`push: true`) — main only, conditional.

The split exists so **a vulnerable image NEVER lands in the registry**.
Trivy gates the push: if step 2 fails, step 3 never runs, the SHA never
publishes. The cache-from in step 3 reuses the layers from step 1 — it
re-exports rather than re-builds, so the cost is buildx-cache-hit + a
network push, not a full second build.

### Scan trigger + SARIF upload

```yaml
- name: Scan image with Trivy (HIGH,CRITICAL — fail on findings)
  uses: aquasecurity/trivy-action@0.24.0
  with:
    image-ref: ghcr.io/jraphaelsst/noctus-${{ matrix.product }}-${{ matrix.role }}:${{ steps.sha.outputs.short }}
    format: sarif
    output: trivy-${{ matrix.product }}-${{ matrix.role }}.sarif
    severity: HIGH,CRITICAL
    exit-code: '1'
    ignore-unfixed: true

- name: Upload Trivy SARIF to GH Security tab
  if: always()
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: trivy-${{ matrix.product }}-${{ matrix.role }}.sarif
    category: trivy-${{ matrix.product }}-${{ matrix.role }}
```

- **SARIF upload runs on `if: always()`** so a failed Trivy scan still
  ships the report — seeing exactly which CVE failed is the value.
- **Per-cell `category`** prevents SARIF entries from one matrix cell
  overwriting another in the Security tab (default behavior would merge
  them by category).
- **`security-events: write` permission** at the workflow root (also
  re-declared at the job level for explicitness) — GH's default token
  lacks this by default.
- **`ignore-unfixed: true`** so we don't fail on CVEs without an
  upstream fix. Otherwise CI breaks the moment a base-image package
  picks up a CVE with no patched version available.

### When to bump Trivy

Pinned to `@0.24.0` deliberately — `@master` is a moving target that
can change scanner-engine internals between runs. Bump cadence:
- **Every 3-6 months** review the upstream release notes for new
  severity classifications, scanner-engine improvements, or new SARIF
  schema versions.
- **On a CVE-reporting gap** (a CVE that should fire but doesn't),
  check if a newer Trivy version covers it.
- **Treat the bump like any other pinned-action upgrade** — test on a
  PR before merging to main.

### Cost considerations

- **20 cells × ~5-10 min/cell (with cache) = ~100-200 runner-minutes
  per CI run.** Cold cache (first run after eviction): ~20-30 min/cell
  for the heaviest products. Warm cache (typical PR): ~2-5 min/cell.
- **Free GH runners give 2000 min/month for public repos** — this
  workflow consumes ~25-50 PR runs/month at warm-cache rates. Watch
  the budget if PR cadence is high.
- **Future optimization (§11 #11):** multi-stage backend Dockerfile to
  shave 200-400MB per backend image. Smaller images → faster pushes →
  faster scans → cheaper CI.
- **Self-hosted runners** are an option if the budget tightens — disk
  reuse across runs makes the cold-cache path cheap.

### Anti-patterns

- **Don't `docker push` from PR builds.** Only `main` push. PRs verify;
  main publishes. Anything else pollutes the registry with PR-author
  SHAs that have no permanent meaning.
- **Don't pin Trivy to `@master`.** `@<semver>` only. Same rule applies
  to every other action — `@v5` for major-version-pinned actions
  (build-push-action, login-action, setup-buildx-action) is acceptable
  because GitHub enforces backward compat within a major; Trivy is a
  third-party scanner with no such guarantee.
- **Don't use `${{ github.token }}` for GHCR push.** Use
  `secrets.GITHUB_TOKEN`. The two LOOK identical but `secrets.GITHUB_TOKEN`
  is the official secret-context reference; `github.token` is a
  context-shortcut that can behave differently in reusable workflows.
- **Don't skip `permissions:` at the workflow OR job level** for
  `packages: write` + `security-events: write`. GH's default token
  is read-only on packages and silent-fails on SARIF upload — both
  failure modes look like "the action ran fine" but produce nothing
  useful.
- **Don't combine matrix cells into a single job.** The whole point of
  the matrix is per-image runner isolation: independent runtimes,
  independent failure surfaces, independent caches.

### First-push grace period — playbook (NEW 2026-05-11)

**The problem.** The first time the matrix-build-push-scan workflow runs against `main`, Trivy will almost certainly flag CVEs against the existing dependency surface (Python 3.11-slim base, FastAPI versions, transitive npm deps). Many have no available fix yet (handled by `ignore-unfixed: true`), but a non-trivial subset will be HIGH/CRITICAL with available patches — and `exit-code: 1` fails the build, blocking the first push.

This is **expected** + **temporary** — the gate exists to keep new CVEs from accumulating, not to retroactively gate the first deploy. Below is the playbook for the grace window between "first push fires CVEs" and "team has investigated + patched."

**Three recovery paths (architect picks):**

1. **Patch to green** (preferred — long-term right shape). Read the SARIF findings (GH Security tab) or workflow logs; patch each actionable CVE. Bump Python base image to a CVE-clean patch tag if needed; update vulnerable npm deps in `seed/{framework,lib}/frontend/package.json`. Re-push; CI passes. Time cost: usually a few hours, depends on findings.
2. **Temporary grace flag** (medium-term, with explicit expiry). Add `continue-on-error: true` to the Trivy step:
   ```yaml
   - name: Trivy scan
     uses: aquasecurity/trivy-action@0.24.0
     continue-on-error: true   # GRACE: remove by 2026-06-15 once first-push CVE backlog cleared
     with:
       severity: HIGH,CRITICAL
       ...
   ```
   Scan still runs + surfaces findings to GH Security tab; build proceeds + push happens. Time cost: 1-line change + a calendar reminder. Use when the team needs to deploy before patching (time-sensitive release).
3. **Severity bump-down** (last resort). Change `severity: HIGH,CRITICAL` → `severity: CRITICAL` only. Reduces gate strictness without disabling it. Re-tighten once HIGH backlog is patched. Risk: HIGH-severity CVEs can land silently during the bump-down window.

**Order to try them.** (1) first — actually fixing is the right shape. (2) only if (1) blocks an urgent push. (3) only if (2) doesn't unblock (rare).

**Anti-patterns.**

- **Permanent `continue-on-error: true`.** That's not a grace; that's removing the gate. If the grace is becoming permanent, decide intentionally whether the gate is wrong (remove it explicitly) or whether the team is avoiding the work (escalate the CVE backlog).
- **Removing the Trivy step entirely.** Same shape — looks like a quick fix; actually drops the gate.
- **`exit-code: 0`.** Hides the intent. Use `continue-on-error: true` if you want failures allowed; don't fake-zero the exit code.

**When to remove the grace.** Once the first-push CVE backlog is at zero (or all remaining are documented accept-with-rationale entries), remove `continue-on-error: true` + the date-comment. CI is back to hard-gate.

---

## 12 · References

- Root compose: `docker-compose.yml`
- Canonical pattern: `products/seed/{backend/Dockerfile, frontend/Dockerfile, docker-compose.yml}`
- nginx template: `seed/framework/frontend/nginx.conf.template`
- Vite alias factory: `seed/framework/frontend/vite.config.factory.ts`
- Workspace template (sibling-product equivalent): `templates/seed-workspace-docker/`
- Local-postgres init scripts: `scripts/init-local-db/`
- Local-postgres generator: `scripts/build-init-local-db.sh`
- Deploy drill (when user says "put X online"): `KB § GUIDES/deploy-workspace-online.md`
- Operations: `start.sh`, `stop.sh`
- CI workflow (matrix build + GHCR push + Trivy scan): `.github/workflows/test.yml`
