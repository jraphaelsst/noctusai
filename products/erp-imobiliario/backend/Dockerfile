# syntax=docker/dockerfile:1.7
# erp-imobiliario backend Dockerfile.
#
# Generated from the canonical pattern at products/seed/backend/Dockerfile.
# When the platform pattern evolves, update seed/ first and propagate.
#
# Build context: repo root.
# Build:    docker compose build erp-imobiliario-backend
# Standalone: docker build -f products/erp-imobiliario/backend/Dockerfile -t noctus-erp-imobiliario-backend .

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

# ─── Layer 2: product-specific dependencies ─────────────────────────────
COPY products/erp-imobiliario/backend/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    grep -v '^-e seed/' /tmp/requirements.txt > /tmp/requirements.clean.txt \
    && pip install -r /tmp/requirements.clean.txt

# ─── Layer 3: product code (changes most often) ─────────────────────────
COPY products/erp-imobiliario/backend/ ./products/erp-imobiliario/backend/

RUN useradd -m -u 1000 noctus \
    && chown -R noctus:noctus /app
USER noctus

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8001/api/health || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8001", \
     "--app-dir", "products/erp-imobiliario/backend"]
