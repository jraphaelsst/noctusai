# Legacy app deploy — `legacy.noctusai.com`

Production container artifacts for the **current live noctusai.com app**, the
*"Sistema de Permutas Imobiliárias"* (ONE Consultoria Imobiliária). It is being
preserved as a **standalone legacy app** at `legacy.noctusai.com` while the new
FastAPI fleet takes over `noctusai.com`.

This app is a **separate codebase** (Django + DRF + Celery + React CRA) — NOT a
noctus-fleet product. These artifacts give it a Linux/Docker shape that joins
the shared `noctus-net` network so the Cloudflare named tunnel can route to it.

## What's here

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage: node:20 builds the CRA frontend → python:3.11-slim runs gunicorn. Non-root. |
| `compose.legacy.yml` | Two services on the built image: `legacy` (gunicorn :5000) + `legacy-celery` (Celery worker). |
| `.env.example` | Every env var the app reads (names derived from the code), with comments. |
| `README.md` | This file. |

## Architecture (matches the app's own design)

- **Single port :5000.** Django serves the API under `/api/`, static assets via
  WhiteNoise, and the React SPA as a catch-all — all on one port. The compiled
  frontend lands in `backend/frontend_build/` at image-build time.
- **Celery worker is mandatory.** Bilateral matching is async; without the
  worker, match processing silently fails. `legacy-celery` runs it.
- **External backing services.** Postgres = Supabase (via `SUPABASE_DB_URL`);
  Redis = the shared fleet Redis (via `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`).
  Neither is a container in this compose.

## Deploy on the VPS (the source is NOT in the noc repo)

`one-permutas` is a gitignored read-only reference locally → on the VPS, clone it
from its **public** repo, drop in the prod shim, then build:

```bash
cd /opt/noctus
git clone https://github.com/jraphaelsst/one-permutas.git legacy-src
NOC=/opt/noctus/noctusai/projects/production-deploy-migration/deploy/legacy
cp "$NOC/settings_prod.py" legacy-src/backend/        # the env-driven prod shim
cp "$NOC/.env.example" legacy-src/.env                 # then fill REAL values (SECRET_KEY!, SUPABASE_DB_URL, CELERY_*)
cd legacy-src
docker compose -f "$NOC/compose.legacy.yml" --env-file .env build   # CRA REACT_APP_* baked from .env
docker compose -f "$NOC/compose.legacy.yml" --env-file .env up -d
docker compose -f "$NOC/compose.legacy.yml" --env-file .env run --rm legacy python manage.py migrate --noinput
```
Then the **edge**: add `A legacy → <VPS-IP>` at the registrar **FIRST**, *then*
add `legacy.noctusai.com { reverse_proxy legacy:5000 }` to `../caddy/Caddyfile`
+ `docker exec noctus-caddy caddy reload …`. **Never add the host to Caddy before
its A-record resolves** — it poisons LE's negative-cache (`KB § GUIDES/production-deploy.md §6`).
(When the domain later moves to Cloudflare, route via the tunnel ingress instead.)

## Build & run (reference — paths relative to THIS directory)

The build context is the legacy app **source root** (the cloned reference).

```bash
# 1. Configure
cp .env.example .env        # then fill in real values (see GAP note below)

# 2. Build (CRA REACT_APP_* are build args — must be set before build)
docker compose -f compose.legacy.yml --env-file .env build

# 3. Start both services
docker compose -f compose.legacy.yml --env-file .env up -d

# 4. Migrate ONCE, at deploy time (NOT at build time — the DB is external and
#    may be unreachable during build):
docker compose -f compose.legacy.yml --env-file .env \
  run --rm legacy python manage.py migrate --noinput

# (first deploy) create the Django superuser:
docker compose -f compose.legacy.yml --env-file .env \
  run --rm legacy python manage.py createsuperuser
```

Prerequisite: the shared network must exist (the fleet's `start.sh` creates it):

```bash
docker network create noctus-net   # one-time, if not already present
```

## Tunnel ingress

`legacy.noctusai.com` routes to this container's port **5000** via the
**Cloudflare named tunnel**, whose ingress is managed separately (the tunnel
artifacts live in `../tunnel/`). The ingress rule maps the hostname to
`http://legacy:5000` over `noctus-net`. Nothing here opens a host port — the
container only `expose`s 5000 on the shared network for the tunnel to reach.

## Environment variables

See `.env.example` for the full, commented list. Summary:

- **DB**: `SUPABASE_DB_URL` (Postgres; SQLite fallback if unset — do not leave blank in prod), `SUPABASE_URL`, `SUPABASE_ANON_KEY`.
- **Redis/Celery**: `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_ALWAYS_EAGER`.
- **Django**: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` — **see GAP note**.
- **Frontend (build-time only)**: `REACT_APP_SUPABASE_URL`, `REACT_APP_SUPABASE_ANON_KEY`, `REACT_APP_API_URL`.

## GAP / assumptions (read before deploying)

1. **`SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` ✅ RESOLVED via `settings_prod.py`.**
   The reference `settings.py` hardcodes an insecure key + `DEBUG=True`; rather
   than edit the read-only reference, the deploy ships a shim (`settings_prod.py`
   in this dir) that imports the base + overrides SECRET_KEY/DEBUG/ALLOWED_HOSTS
   /CSRF from env + adds `SECURE_PROXY_SSL_HEADER`. The build sets
   `DJANGO_SETTINGS_MODULE=backend.settings_prod`. **You MUST set a fresh
   `SECRET_KEY=` in `.env`** — the committed dev literal is public (forgery risk).
2. **Supabase Postgres** is configured via `SUPABASE_DB_URL` parsed by
   `dj-database-url` (`sslmode=require`, `conn_max_age=600`, health checks). The
   app does NOT use a `DATABASE_URL` name. If unset, Django silently falls back
   to local SQLite — never acceptable in production.
3. **Redis is external/shared.** The app reads `CELERY_BROKER_URL` /
   `CELERY_RESULT_BACKEND` (not a single `REDIS_URL`). Point both at the fleet's
   shared Redis on `noctus-net`, using a dedicated DB index to avoid collision.
4. **CRA env is build-time.** `REACT_APP_*` are inlined into the SPA bundle at
   build; changing them later requires a rebuild, not a restart.
5. **Migrations at deploy, not build.** The Dockerfile runs `collectstatic` at
   build but deliberately NOT `migrate` (external DB unreachable at build time).
6. **Production server hardening.** The image runs plain gunicorn (2 workers,
   120s timeout) with no `--reload`/`watchmedo` (those are `run.sh` dev aids).
