# syntax=docker/dockerfile:1.7
# erp-imobiliario — thin product image (generated from products/seed/backend/Dockerfile; edit there + re-propagate).
#
# Project: containerization-single-container. Single container: uvicorn
# serves the API AND the built SPA on ONE port (the seed factory's
# `serve_spa` seam, fed by SERVE_SPA_DIR). The common heavy layers live in
# the shared bases (seed/docker/Dockerfile.{backend,frontend}-base) — this
# file only adds THIS product's specificities. `FROM noctus-seed-*-base`
# IS the named seam (inherit-and-extend, never fork).
#
# Prereq: the base images exist (scripts/infra/build-base-images.sh; start.sh
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
# VITE_SUPABASE_* are BOOT-CRITICAL and BAKED at build: the seed FE
# `createProductSupabase`/`assertSupabaseBuildEnv` hard-throw (blank
# page) when empty in the bundle. Vite inlines `import.meta.env.VITE_*`
# at `vite build`, so they MUST be present as ARG/ENV before the build.
# Distinct from VITE_BACKEND_API_URL, which stays runtime-detected
# (one image serves direct/tunnel/proxy) — do NOT bake the backend URL.
ARG VITE_SUPABASE_URL=
ENV VITE_SUPABASE_URL=${VITE_SUPABASE_URL}
ARG VITE_SUPABASE_PUBLISHABLE_KEY=
ENV VITE_SUPABASE_PUBLISHABLE_KEY=${VITE_SUPABASE_PUBLISHABLE_KEY}
ARG VITE_CORE_API_URL=
ENV VITE_CORE_API_URL=${VITE_CORE_API_URL}
ARG VITE_CORE_URL=
ENV VITE_CORE_URL=${VITE_CORE_URL}
COPY products/erp-imobiliario/frontend/package*.json ./products/erp-imobiliario/frontend/
WORKDIR /app/products/erp-imobiliario/frontend
# Drop the host lockfile before install: package-lock.json is generated on
# the dev's machine (darwin-arm64) and PINS the platform-optional native
# binaries (rollup/esbuild/lightningcss/@swc) to that os/cpu. npm honours
# the lockfile and SKIPS the linux binary → `vite build` crashes with
# "Cannot find module '@rollup/rollup-linux-*'" (npm/cli#4828). Removing it
# lets npm re-resolve optionals for THIS build platform/libc.
RUN --mount=type=cache,target=/root/.npm \
    rm -f package-lock.json \
    && npm install --no-audit --no-fund
COPY products/erp-imobiliario/frontend ./
RUN npm run build   # → /app/products/erp-imobiliario/frontend/dist

# ── runtime: API + SPA on one port ──────────────────────────────────────
FROM noctus-seed-backend-base:dev AS runtime
ARG GIT_SHA
LABEL org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.title="noctus-erp-imobiliario"
WORKDIR /app

# Product-specific Python deps (seed lib/framework already in the base
# venv; strip the `-e seed/` editable lines — they're inherited).
COPY products/erp-imobiliario/backend/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    apt-get update \
    && apt-get install -y --no-install-recommends gcc pkg-config libcairo2-dev \
    && grep -v '^-e seed/' /tmp/requirements.txt > /tmp/req.clean.txt \
    && pip install -r /tmp/req.clean.txt \
    && apt-get purge -y gcc pkg-config libcairo2-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
# (no product extras)

# Product backend code + the built SPA.
COPY products/erp-imobiliario/backend/ ./products/erp-imobiliario/backend/
COPY --from=frontend-build /app/products/erp-imobiliario/frontend/dist ./products/erp-imobiliario/frontend/dist
ENV SERVE_SPA_DIR=/app/products/erp-imobiliario/frontend/dist

# Non-root user — LAST (so the pip install above could write the venv).
RUN useradd -m -u 1000 noctus && chown -R noctus:noctus /app /opt/venv
USER noctus

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8001/api/health || exit 1
# Default CMD = plain uvicorn over the BAKED dist → this image is a
# self-contained, shippable artifact (deploy/CI run it as-is).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", \
     "--port", "8001", "--app-dir", "products/erp-imobiliario/backend"]

# ── runtime-watch: SAME single container, local live-rebuild ────────────
# ONE container, ONE shape, ONE command (`./start.sh`). The local
# per-product compose builds THIS target + bind-mounts source; the user
# never picks a mode. Adds node (so the one container can rebuild the
# SPA itself) + the watch entrypoint: `vite build --watch` keeps dist
# fresh, `uvicorn --reload` reloads .py. Deploy still uses the slim
# `runtime` above (node absent there). Source is bind-mounted at run, so
# THIS target is intentionally not a shippable artifact — `runtime` is.
FROM runtime AS runtime-watch
USER root
# Node for the in-container SPA rebuild. NodeSource keeps it one layer;
# only the local image carries it (deploy = `runtime`).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
         | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
         > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*
# Frontend deps installed HERE (glibc) — esbuild/vite ship platform
# binaries; the alpine frontend-base node_modules are not ABI-portable.
COPY products/erp-imobiliario/frontend/package*.json ./products/erp-imobiliario/frontend/
# Same lockfile-pins-wrong-platform-optional bug as frontend-build, here on
# glibc/arm64 — drop the host lock so npm fetches the linux native binary
# (otherwise local-watch's `vite build` crash-loops the container).
RUN --mount=type=cache,target=/root/.npm \
    cd products/erp-imobiliario/frontend \
    && rm -f package-lock.json \
    && npm install --no-audit --no-fund
COPY seed/docker/local-watch.sh /usr/local/bin/local-watch
RUN chmod +x /usr/local/bin/local-watch \
    && chown -R noctus:noctus /app
USER noctus
ENV PRODUCT_SLUG=erp-imobiliario PRODUCT_PORT=8001
ENTRYPOINT ["/usr/local/bin/local-watch"]
