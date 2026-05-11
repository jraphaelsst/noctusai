# syntax=docker/dockerfile:1.7
# youtube-crawler backend Dockerfile.
#
# Generated from the canonical pattern at products/seed/backend/Dockerfile.
# When the platform pattern evolves, update seed/ first and propagate.
#
# Build context: repo root.
# Build:    docker compose build youtube-crawler-backend
# Standalone: docker build --build-arg GIT_SHA=$(git rev-parse HEAD) \
#               -f products/youtube-crawler/backend/Dockerfile -t noctus-youtube-crawler-backend .
#
# Multi-stage layout:
#   builder  — installs dev headers + compiles all Python wheels into /opt/venv.
#   runtime  — copies the prebuilt venv + minimal shared-object runtime libs.
#
# Result: final image carries only what the app needs at execution time.
# Build-time tooling (build-essential, *-dev headers, git, pkg-config) is
# left behind in the builder stage and dropped by Docker.

ARG GIT_SHA=dev

# ╔════════════════════════════════════════════════════════════════════════╗
# ║ Stage 1 — builder: dev headers + wheel compilation                     ║
# ╚════════════════════════════════════════════════════════════════════════╝
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1

# Build-time system packages: compiler + dev headers for native extensions
# (cryptography → libffi-dev; psycopg2 → libpq-dev; weasyprint et al → cairo /
# pango / gdk-pixbuf / girepository dev headers); git for any git+ deps.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libpq-dev \
        git \
        pkg-config \
        libcairo2-dev \
        libgirepository1.0-dev \
        libpango1.0-dev \
        libgdk-pixbuf-2.0-dev \
    && rm -rf /var/lib/apt/lists/*

# Isolated venv so we can copy it verbatim into the runtime stage and avoid
# leaking pip / setuptools artifacts into the runtime image.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    VIRTUAL_ENV="/opt/venv"

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
COPY products/youtube-crawler/backend/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    grep -v '^-e seed/' /tmp/requirements.txt > /tmp/requirements.clean.txt \
    && pip install -r /tmp/requirements.clean.txt

# ╔════════════════════════════════════════════════════════════════════════╗
# ║ Stage 2 — runtime: prebuilt venv + minimal shared-object libs          ║
# ╚════════════════════════════════════════════════════════════════════════╝
FROM python:3.11-slim AS runtime

ARG GIT_SHA

# OCI image labels (KB § PATTERNS/containerization.md §11 #7-backend).
# revision is stamped via `--build-arg GIT_SHA=$(git rev-parse HEAD)` at build.
LABEL org.opencontainers.image.source="https://github.com/jraphaelsst/noctusai" \
      org.opencontainers.image.revision="${GIT_SHA}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    VIRTUAL_ENV="/opt/venv"

# Runtime-only system packages: shared-object versions of the libraries the
# wheels linked against in the builder stage, plus curl for the healthcheck.
# Crucially: NO `-dev` packages, NO build-essential, NO git, NO pkg-config.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libffi8 \
        libpq5 \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libgirepository-1.0-1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the prebuilt venv from the builder. Because the seed packages were
# installed editable (`pip install -e`), the venv's egg-link files reference
# the seed/ source tree on disk — so the source must also be present in the
# runtime image at the same paths.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/seed /app/seed

# ─── Layer 3: product code (changes most often) ─────────────────────────
COPY products/youtube-crawler/backend/ ./products/youtube-crawler/backend/

# Non-root user (security baseline for production-shape images).
RUN useradd -m -u 1000 noctus \
    && chown -R noctus:noctus /app /opt/venv
USER noctus

EXPOSE 8008

# Healthcheck uses the seed-provided /api/health endpoint (every product
# inherits it via createProductApp() / create_product_app()).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8008/api/health || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8008", \
     "--app-dir", "products/youtube-crawler/backend"]
