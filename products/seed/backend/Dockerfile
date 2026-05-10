# syntax=docker/dockerfile:1.7
# Canonical NoctusAI product backend Dockerfile.
#
# This file at products/seed/ is the reference; every other product's
# backend/Dockerfile is a copy with slug + port substituted. When the
# pattern needs to evolve, update this file first and propagate.
#
# Build context: repo root (so seed/ + product code are reachable).
# Build:    docker compose build seed-backend
# Standalone: docker build -f products/seed/backend/Dockerfile -t noctus-seed-backend .

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System packages: gcc + libffi for cryptography (Fernet, JWT signing),
# libpq for psycopg2 if used, curl for healthcheck, git for any git+ deps.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libpq-dev \
        curl \
        git \
        pkg-config \
        libcairo2-dev \
        libgirepository1.0-dev \
        libpango1.0-dev \
        libgdk-pixbuf-2.0-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ─── Layer 1: seed packages (changes infrequently, cached aggressively) ─
COPY seed/lib/backend ./seed/lib/backend
COPY seed/framework/backend ./seed/framework/backend
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install \
    -e ./seed/lib/backend \
    -e ./seed/framework/backend

# ─── Layer 2: product-specific dependencies ─────────────────────────────
# Strip already-installed seed editables to avoid pip resolver re-build.
COPY products/seed/backend/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    grep -v '^-e seed/' /tmp/requirements.txt > /tmp/requirements.clean.txt \
    && pip install -r /tmp/requirements.clean.txt

# ─── Layer 3: product code (changes most often) ─────────────────────────
COPY products/seed/backend/ ./products/seed/backend/

# Non-root user (security baseline for production-shape images).
RUN useradd -m -u 1000 noctus \
    && chown -R noctus:noctus /app
USER noctus

EXPOSE 8004

# Healthcheck uses the seed-provided /api/health endpoint (every product
# inherits it via createProductApp() / create_product_app()).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8004/api/health || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8004", \
     "--app-dir", "products/seed/backend"]
