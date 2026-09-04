# syntax=docker/dockerfile:1.7
# permutas — thin product image (house single-container shape).
#
# DIVERGENT-ARCHITECTURE ABSORPTION (KB § PATTERNS/devops/containerization.md §12a).
# This product is the absorbed legacy "Sistema de Permutas Imobiliárias"
# (Django 4.2 + DRF + Celery + React CRA), NOT a seed FastAPI product. The
# house contract it DOES honour, and the reason there is no fleet carve-out:
#   • ONE container, ONE port (Django serves /api/ AND the SPA via WhiteNoise
#     — the Django-native equivalent of the seed factory's `serve_spa` seam)
#   • `FROM noctus-seed-*-base` — inherit-and-extend, never fork
#   • non-root, healthcheck, GIT_SHA label — same as every other product
# The seed's VITE_* build-arg block does NOT apply: this SPA is CRA
# (react-scripts), whose public env is the REACT_APP_* prefix, inlined at
# build time exactly like Vite's.
#
# Prereq: base images exist (scripts/infra/build-base-images.sh).
# Build context: repo root.

ARG GIT_SHA=dev

# ── frontend-build: the CRA bundle ──────────────────────────────────────
FROM noctus-seed-frontend-base:dev AS frontend-build
WORKDIR /app
# CRA inlines REACT_APP_* at build time — public browser config only.
# Empty default ⇒ the SPA calls its own origin (single-container correct).
ARG REACT_APP_API_URL=
ENV REACT_APP_API_URL=${REACT_APP_API_URL}
COPY products/permutas/frontend/package*.json ./products/permutas/frontend/
WORKDIR /app/products/permutas/frontend
# Drop the host lockfile before install — it pins darwin-arm64 optional
# native binaries that npm then SKIPS on linux (npm/cli#4828). Same
# reasoning as the seed products' Dockerfile.
RUN --mount=type=cache,target=/root/.npm \
    rm -f package-lock.json \
    && npm install --no-audit --no-fund
COPY products/permutas/frontend ./
RUN npm run build   # CRA → /app/products/permutas/frontend/build

# ── runtime: Django API + SPA on one port ───────────────────────────────
FROM noctus-seed-backend-base:dev AS runtime
ARG GIT_SHA
LABEL org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.title="noctus-permutas"
WORKDIR /app

# Product Python deps. Pillow is NOT in the upstream requirements.txt but
# Django's ImageField hard-requires it (`fields.E210` at system-check time)
# — the platform-auto-installed-dep gap that broke the 2026-05-21 build
# (KB § GUIDES/production-deploy.md §6). Pinned here, at the seam, rather
# than editing the vendored upstream manifest.
COPY products/permutas/backend/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && pip install -r /tmp/requirements.txt "Pillow>=10.0" \
    && apt-get purge -y gcc libpq-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Django project + the built SPA (WhiteNoise serves it from frontend_build/).
COPY products/permutas/backend/ ./products/permutas/backend/
COPY --from=frontend-build /app/products/permutas/frontend/build \
     ./products/permutas/backend/frontend_build

WORKDIR /app/products/permutas/backend
ENV DJANGO_SETTINGS_MODULE=backend.settings_prod \
    PYTHONUNBUFFERED=1

# collectstatic at BUILD (no DB needed); `migrate` stays a DEPLOY step —
# the database is external and unreachable during build.
RUN python manage.py collectstatic --noinput --clear

RUN useradd -m -u 1000 noctus && chown -R noctus:noctus /app
USER noctus

EXPOSE 8015
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS -H "Host: permutas.noctusai.com" http://localhost:8015/ || exit 1

CMD ["gunicorn", "backend.wsgi:application", \
     "--bind", "0.0.0.0:8015", "--workers", "2", "--timeout", "120"]
