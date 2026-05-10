# syntax=docker/dockerfile:1.7
# dev-team backend Dockerfile.
#
# Generated from the canonical pattern at products/seed/backend/Dockerfile.
# When the platform pattern evolves, update seed/ first and propagate.
#
# Build context: repo root.
# Build:    docker compose build dev-team-backend
# Standalone: docker build -f products/dev-team/backend/Dockerfile -t noctus-dev-team-backend .

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

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

# ─── dev-team engine package (slug-specific) ────────────────────────────
COPY dev_team /opt/dev_team
RUN --mount=type=cache,target=/root/.cache/pip pip install -e /opt/dev_team

# ─── Layer 2: product-specific dependencies ─────────────────────────────
COPY products/dev-team/backend/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    grep -v '^-e seed/' /tmp/requirements.txt > /tmp/requirements.clean.txt \
    && pip install -r /tmp/requirements.clean.txt

# ─── Layer 3: product code (changes most often) ─────────────────────────
COPY products/dev-team/backend/ ./products/dev-team/backend/

RUN useradd -m -u 1000 noctus \
    && chown -R noctus:noctus /app
USER noctus

EXPOSE 8009

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8009/api/health || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8009", \
     "--app-dir", "products/dev-team/backend"]
