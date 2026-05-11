# Containerization — multi-layer compose orchestration

> **What this is.** The body of the platform: how every product becomes
> a portable container, how containers wire into a fleet, and how the
> fleet ships intact to any host. Built around `docker compose include:`
> with a registry-driven root orchestrator + per-product fragments + a
> shared platform network.
>
> **Why it exists.** Native `./start.sh` (uvicorn + vite) is fast for
> dev iteration but tied to whatever the laptop has installed. The
> container path is the **reproducible, deployable** twin: same image
> on dev laptop, staging, prod, or a teammate's machine. They coexist;
> use whichever fits the moment.

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
    └── media-scheduling/  ← (8096 / 8140)
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
docker pull docker/dockerfile:1.7   # BuildKit syntax frontend
docker pull python:3.11-slim        # backend base
docker pull node:20-alpine          # frontend build base
docker pull nginx:alpine            # frontend runtime base
docker pull redis:7-alpine          # redis profile
docker pull cloudflare/cloudflared:latest  # tunnel profile
```

After this, `./start.sh` works offline (only product layers rebuild
when product code changes; bases come from cache).

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

## 11 · Known limits + improvement backlog

Captured during the 2026-05-10 containerization rollout. ✅ = applied
this session; 🟡 = pending. Some are "flag and continue" — not blockers
— but worth recording so they don't go silent.

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
6. **`@noctusai/seed` is missing from product `package.json`
   `dependencies`.** It's resolved purely by Vite alias — works at
   build time, but `npm install` doesn't know about it. If anyone
   ever runs `npm install` outside of the build (typecheck, IDE), it
   could miss. Either add as `file:../../../seed/framework/frontend`
   (npm workspaces) or document the alias as the only resolution.
7. **OCI image labels.** Standard practice missing:
   `LABEL org.opencontainers.image.source=...`,
   `LABEL org.opencontainers.image.revision=$(git rev-parse HEAD)`.
   Cheap traceability — image → commit. Update canonical seed,
   propagate.

### 🟡 Soon — quality lifts

8. **No `docker-compose.override.yml` for dev.** Today the same compose
   shape is used for dev and (would-be) prod. Splitting into
   `docker-compose.yml` (production-shape: no volume binds, no
   reload) + `docker-compose.override.yml` (dev: bind product source
   for hot-reload) is the standard pattern.
9. **CI builds only 4 of 20 images (smoke).** Full-fleet build is
   ~30 minutes on free GH runners — current job builds core + seed
   only. Future: matrix strategy with one job per product, or move
   to a self-hosted runner with disk + cache reuse.
10. ✅ **Image registry strategy — per-product registries (2026-05-10).**
    Decision locked: per-product registries (rationale at §11a). Every
    per-product `docker-compose.yml` `image:` line now points at
    `ghcr.io/jraphaelsst/noctus-<slug>-<role>:${NOCTUS_IMAGE_TAG:-dev}`
    so local builds keep working (`:dev` fallback) and CI can set
    `NOCTUS_IMAGE_TAG=$(git rev-parse --short HEAD)` for immutable tags.
    See **§11a · Image registry strategy** for the full pattern + manual
    push recipe. T9 (Wave 3) will land the automated push workflow.
11. **Backend image is fat (600-900MB).** A second pass with
    multi-stage (build deps in one stage, runtime-only in another)
    could shave 200-400MB. Standard pattern; deferred for later. <- please do it

### 🟢 Later — strategic

12. **Production compose vs dev compose.** Today's compose is dev-shaped
    (`:dev` image tags, `restart: unless-stopped`, no resource limits).
    A `docker-compose.prod.yml` overlay defining resource caps + log
    drivers + read-only filesystems would be the deployment artifact.
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
    §11b below for the full mental model + caveats.
14. **Health endpoint per-product variation.** All products use the
    seed's `/api/health` — fine, but dev-team's agno engine has
    deeper health probes (`/api/health/agno`) that the docker
    healthcheck doesn't surface. Consider per-product healthcheck
    customization in the scaffolder.
15. **No image scanning.** Once images land in a registry, `trivy` /
    `grype` / `docker scout` should be in the loop to catch CVEs in
    base images and pip/npm deps. Pair with #10 (registry strategy).

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

## 11b · Local-postgres profile (offline dev)

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
