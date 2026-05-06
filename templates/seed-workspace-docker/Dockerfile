FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System packages: gcc + libffi for cryptography (Fernet token encryption,
# JWT signing), curl for healthcheck, git for any git+ deps the seed
# packages may carry.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libpq-dev \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# ─── Seed packages (from noc, via additional build context) ──────────────
# The workspace symlinks `seed/` into the noc repo. Docker COPY does not
# follow directory symlinks at build time, so we use Buildx's named
# additional-context (declared in docker-compose.yml as `noc`) to pull the
# real seed/ directory into the image.
COPY --from=noc seed/lib/backend ./_seed/lib/backend
COPY --from=noc seed/framework/backend ./_seed/framework/backend
RUN pip install --no-cache-dir \
    -e ./_seed/lib/backend \
    -e ./_seed/framework/backend

# ─── Product backend dependencies ────────────────────────────────────────
# Strip seed editable lines (already installed above) before pip install so
# the resolver doesn't rebuild them.
COPY products/{{PRODUCT_SLUG}}/backend/requirements.txt /tmp/requirements.txt
RUN grep -v '^-e seed/' /tmp/requirements.txt > /tmp/requirements.clean.txt \
    && pip install --no-cache-dir -r /tmp/requirements.clean.txt

# Product code (mounted as volume in dev; copied here so the image is
# runnable standalone for staging / smoke tests).
COPY products/{{PRODUCT_SLUG}}/backend/app ./products/{{PRODUCT_SLUG}}/backend/app
COPY products/{{PRODUCT_SLUG}}/backend/migrations ./products/{{PRODUCT_SLUG}}/backend/migrations
COPY products/{{PRODUCT_SLUG}}/backend/tests ./products/{{PRODUCT_SLUG}}/backend/tests

EXPOSE {{BACKEND_PORT}}

# Health check uses the seed-provided /api/health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:{{BACKEND_PORT}}/api/health || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "{{BACKEND_PORT}}", \
     "--app-dir", "products/{{PRODUCT_SLUG}}/backend"]
