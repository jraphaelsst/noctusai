# syntax=docker/dockerfile:1.7
# seed — CANONICAL thin product image (the reference every product mirrors).
#
# Project: containerization-single-container. Single container: uvicorn
# serves the API AND the built SPA on ONE port (the seed factory's
# `serve_spa` seam, fed by SERVE_SPA_DIR). The common heavy layers live in
# the shared bases (seed/docker/Dockerfile.{backend,frontend}-base) — this
# file only adds THIS product's specificities. `FROM noctus-seed-*-base`
# IS the named seam (inherit-and-extend, never fork).
#
# Prereq: the base images exist (scripts/build-base-images.sh; start.sh
# orders this before product images). Build context: repo root.
#
# Per-product variance lives ONLY here (kept tiny, product-owned):
#   • the VITE_* build-arg block (public browser config bridged from .env)
#   • the product port (EXPOSE / uvicorn --port / healthcheck)
#   • any product extras (e.g. dev-team adds /opt/dev_team — see its file)

ARG GIT_SHA=dev

# ── frontend-build: this product's SPA bundle ───────────────────────────
FROM noctus-seed-frontend-base:dev AS frontend-build
WORKDIR /app
# Single-container ⇒ same-origin: the vite factory injects
# window.location.origin as the API base (tunnel/deploy-correct, zero
# per-file changes). Native/two-port dev leaves this unset.
ENV VITE_SAME_ORIGIN=1
# VITE_* build-arg contract — public browser config only; bridged from
# .env via compose `args:`. VITE_BACKEND_API_URL + VITE_PRODUCT_SCHEMA are
# factory-injected (no arg). {{VITE_ARGS}}
ARG VITE_CORE_URL=
ENV VITE_CORE_URL=${VITE_CORE_URL}
COPY products/seed/frontend/package*.json ./products/seed/frontend/
WORKDIR /app/products/seed/frontend
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund
COPY products/seed/frontend ./
RUN npm run build   # → /app/products/seed/frontend/dist

# ── runtime: API + SPA on one port ──────────────────────────────────────
FROM noctus-seed-backend-base:dev AS runtime
ARG GIT_SHA
LABEL org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.title="noctus-seed"
WORKDIR /app

# Product-specific Python deps (seed lib/framework already in the base
# venv; strip the `-e seed/` editable lines — they're inherited).
COPY products/seed/backend/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    grep -v '^-e seed/' /tmp/requirements.txt > /tmp/req.clean.txt \
    && pip install -r /tmp/req.clean.txt
# {{BACKEND_EXTRA}} — product extras (e.g. dev-team: COPY dev_team +
# pip install -e /opt/dev_team). Seed has none.

# Product backend code + the built SPA.
COPY products/seed/backend/ ./products/seed/backend/
COPY --from=frontend-build /app/products/seed/frontend/dist ./products/seed/frontend/dist
ENV SERVE_SPA_DIR=/app/products/seed/frontend/dist

# Non-root user — LAST (so the pip install above could write the venv).
RUN useradd -m -u 1000 noctus && chown -R noctus:noctus /app /opt/venv
USER noctus

EXPOSE 8004
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8004/api/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", \
     "--port", "8004", "--app-dir", "products/seed/backend"]
