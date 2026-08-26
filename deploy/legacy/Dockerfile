# Legacy app — "Sistema de Permutas Imobiliárias" (ONE Consultoria Imobiliária)
# Standalone Django + DRF + Celery app preserved at legacy.noctusai.com.
#
# This is NOT a noctus-fleet product — it has its OWN container shape (it does
# NOT inherit the noctus-seed-* base images). It only joins the shared
# `noctus-net` network so the Cloudflare named tunnel can route to its :5000.
#
# Source layout assumed (the read-only reference clone, copied in at build):
#   ./frontend/            CRA React app  → builds to ./frontend/build/
#   ./backend/             Django project (backend.wsgi:application, backend.celery)
#   ./backend/requirements.txt
# The frontend build is copied into backend/frontend_build/ and served by
# Django via WhiteNoise on the single port 5000 (the app's deployment
# architecture — see its CLAUDE.md "Single-Port Deployment").
#
# Build context = the legacy app source root (the reference clone). Example:
#   docker build -f deploy/legacy/Dockerfile \
#     -t legacy-permutas:latest \
#     projects/production-deploy-migration/reference/one-permutas
#
# Build-time React env: CRA inlines REACT_APP_* at build time, so the Supabase
# URL/anon-key MUST be passed as --build-arg (they cannot be set at runtime for
# an already-built SPA bundle). See .env.example.

# ─── Stage A: build the React (CRA) frontend ──────────────────────────────────
FROM node:20-bookworm-slim AS frontend-build

WORKDIR /app/frontend

# Install deps from the lockfile first (cache layer). The frontend ships its
# own package-lock.json, so `npm ci` is reproducible.
COPY frontend/package.json frontend/package-lock.json ./
# NOTE: this used to also `npm install --no-save @supabase/supabase-js` for
# frontend/src/lib/supabase.ts, a root-hoisted (Replit) dep. That module was an
# UNUSED Supabase client whose only effect was inlining the anon key into the
# public CRA bundle; it was deleted upstream (one-permutas PR #1, `da8cf2d`), so
# nothing in frontend/src imports supabase any more and the extra install is dead.
RUN npm ci

# Build-time React config — CRA inlines these into the static bundle.
# Empty defaults keep the build green; pass real values via --build-arg.
#
# REACT_APP_SUPABASE_URL / _ANON_KEY are deliberately NOT passed any more. CRA
# inlines only env vars the source actually references, and the sole referrer
# (frontend/src/lib/supabase.ts) was deleted as dead code that published the anon
# key in the public bundle. Re-adding them here would put a credential back into
# a browser-served asset. Only REACT_APP_API_URL is real (services/api.ts).
ARG REACT_APP_API_URL=""
ENV REACT_APP_API_URL=$REACT_APP_API_URL

# Copy the rest of the frontend source and build.
# CI=false: CRA treats warnings as non-fatal (matches run.sh / root build script).
COPY frontend/ ./
RUN CI=false npm run build
# CRA emits to ./build/ ; Django expects it at backend/frontend_build/.

# ─── Stage B: Python runtime (Django + Gunicorn + Celery) ─────────────────────
FROM python:3.11-slim AS runtime

# psycopg2-binary ships wheels, but keep build-essential + libpq for safety on
# arch/version drift; curl for the compose healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# DJANGO_SETTINGS_MODULE points at the prod SHIM (deploy/legacy/settings_prod.py),
# which the deploy step copies into backend/ before build (see README). The shim
# imports the read-only base settings + overrides SECRET_KEY/DEBUG/ALLOWED_HOSTS
# /CSRF from env (the reference's hardcoded insecure key is never used).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=backend.settings_prod

WORKDIR /app

# Install backend deps first (cache layer).
COPY backend/requirements.txt ./backend/requirements.txt
# Pillow is NOT in requirements.txt but Django's ImageField (authsys.Profile.image)
# requires it — Replit's packager auto-installed it without writing it back (same
# class as the frontend @supabase root-hoist). Add it explicitly. See KB GUIDE §6.
RUN pip install --no-cache-dir -r backend/requirements.txt "Pillow>=10.0"

# Copy the Django project.
COPY backend/ ./backend/

# Bring the built SPA into the location Django/WhiteNoise serves it from
# (settings.FRONTEND_BUILD_DIR = backend/frontend_build).
COPY --from=frontend-build /app/frontend/build/ ./backend/frontend_build/

# Collect static at build time (WhiteNoise CompressedManifestStaticFilesStorage).
# NOTE: migrations are run at DEPLOY time (compose entrypoint / one-off), NOT
# here — the database is external (Supabase) and may be unreachable at build.
WORKDIR /app/backend
# STATICFILES_DIRS references backend/static (run.sh creates it); make it so
# collectstatic doesn't warn (staticfiles.W004).
RUN mkdir -p static
# settings_prod requires SECRET_KEY at import — pass a THROWAWAY one just for the
# build-time collectstatic (it's never used at runtime; the container gets the
# real key from the compose env_file). collectstatic doesn't need ALLOWED_HOSTS.
RUN SECRET_KEY=build-only-collectstatic-not-used-at-runtime python manage.py collectstatic --noinput

# Non-root runtime user; own the app tree (frontend_build, staticfiles, media).
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Production gunicorn — no --reload / watchmedo (those are run.sh dev aids).
# The compose `legacy-celery` service overrides this command to run the worker.
CMD ["gunicorn", "--bind=0.0.0.0:5000", "--timeout", "120", "--workers", "2", "backend.wsgi:application"]
