# syntax=docker/dockerfile:1.7
# personal-finance — thin product image (generated from products/seed/backend/Dockerfile; edit there + re-propagate).
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
ARG VITE_CORE_URL=
ENV VITE_CORE_URL=${VITE_CORE_URL}
COPY products/personal-finance/frontend/package*.json ./products/personal-finance/frontend/
WORKDIR /app/products/personal-finance/frontend
# Drop the host lockfile before install: package-lock.json is generated on
# the dev's machine (darwin-arm64) and PINS the platform-optional native
# binaries (rollup/esbuild/lightningcss/@swc) to that os/cpu. npm honours
# the lockfile and SKIPS the linux binary → `vite build` crashes with
# "Cannot find module '@rollup/rollup-linux-*'" (npm/cli#4828). Removing it
# lets npm re-resolve optionals for THIS build platform/libc.
RUN --mount=type=cache,target=/root/.npm \
    rm -f package-lock.json \
    && npm install --no-audit --no-fund
COPY products/personal-finance/frontend ./
RUN npm run build   # → /app/products/personal-finance/frontend/dist

# ── runtime: API + SPA on one port ──────────────────────────────────────
FROM noctus-seed-backend-base:dev AS runtime
ARG GIT_SHA
LABEL org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.title="noctus-personal-finance"
WORKDIR /app

# Product-specific Python deps (seed lib/framework already in the base
# venv; strip the `-e seed/` editable lines — they're inherited).
COPY products/personal-finance/backend/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    grep -v '^-e seed/' /tmp/requirements.txt > /tmp/req.clean.txt \
    && pip install -r /tmp/req.clean.txt
# (no product extras)

# Product backend code + the built SPA.
COPY products/personal-finance/backend/ ./products/personal-finance/backend/
COPY --from=frontend-build /app/products/personal-finance/frontend/dist ./products/personal-finance/frontend/dist
ENV SERVE_SPA_DIR=/app/products/personal-finance/frontend/dist

# Non-root user — created LAST (pip install above ran as root, before this).
# chown ONLY /app — NOT /opt/venv. /opt/venv (~276MB) comes from the SHARED
# backend base layer and is read-only at runtime (no runtime pip; editable
# seed installs resolve via .pth → bind-mounted /app/seed). `chown -R
# /opt/venv` would rewrite every file into a NEW unshared ~311MB per-product
# layer (measured 2026-05-19) — defeating base sharing for zero benefit
# (venv is world-readable from `python -m venv`; noctus only needs read+exec).
# Anti-pattern: never `chown -R` a large inherited base path. ~2.5GB fleet.
RUN useradd -m -u 1000 noctus && chown -R noctus:noctus /app
USER noctus

EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8002/api/health || exit 1
# Default CMD = plain uvicorn over the BAKED dist → this image is a
# self-contained, shippable artifact (deploy/CI run it as-is).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", \
     "--port", "8002", "--app-dir", "products/personal-finance/backend"]

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
# Node for the in-container SPA rebuild — from the OFFICIAL nodejs.org binary
# tarball (node 20 + npm 10 BUNDLED). Only the local runtime-watch image
# carries node (deploy = slim `runtime`, node absent). Two deliberate NOTs:
#  • NOT NodeSource — the Docker build VM persistently fails the TLS handshake
#    to deb.nodesource.com ("curl: (35) ...unexpected eof while reading", every
#    retry) while host + deb.debian.org + nodejs.org all work (§3.19). nodejs.org
#    is a DIFFERENT, reachable host.
#  • NOT Debian's `apt install nodejs npm` — trixie bundles npm 9.2.0, whose
#    peer-dep resolver chokes on the file:-linked @noctusai/lib
#    ("ERESOLVE ... @supabase/supabase-js@undefined"); npm 10 (the tarball's)
#    resolves it correctly. The tarball lands npm in /usr/local/bin (ahead of
#    Debian's /usr/bin in PATH) so there's no dpkg-vs-global shadowing fight.
# (Bit 2026-05-24: the §3.19 Debian swap silently downgraded npm 10→9.2.0,
# regressing the FE install — caught by a faithful repro: npm 9.2.0 ERESOLVE
# vs npm 10 EXIT=0 on the same package.json set. KB §3.19/§3.21.)
ARG NODE_VERSION=v20.19.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl xz-utils \
    && rm -rf /var/lib/apt/lists/* \
    && case "$(dpkg --print-architecture)" in \
         amd64) NODE_ARCH=x64 ;; \
         arm64) NODE_ARCH=arm64 ;; \
         *) echo "unsupported arch: $(dpkg --print-architecture)" >&2; exit 1 ;; \
       esac \
    && curl -fsSL --retry 5 --retry-all-errors --retry-delay 3 --connect-timeout 30 \
         "https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" \
         -o /tmp/node.tar.xz \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.xz \
    && node --version && npm --version
# Frontend deps installed HERE (glibc) — esbuild/vite ship platform
# binaries; the alpine frontend-base node_modules are not ABI-portable.
# Seed framework/lib FE deps too: local-watch's `vite build` loads the
# tailwind/vite factory at /app/seed/framework/frontend/*.factory.ts
# which `require("tailwindcss-animate")` etc. — Node resolves from THAT
# path, not the product's. runtime-watch is FROM the backend base
# (glibc, no seed FE node_modules) and the compose bind-mounts ../../seed
# (node_modules-less in any clean checkout/CI/worktree) → without this
# the factory require fails → vite build fails → local-watch restart-loop
# → never healthy. The alpine frontend-base installs these for the
# build stage; runtime-watch (glibc) must install them itself. The
# compose pairs this with anon volumes on these nested node_modules so
# the ../../seed bind-mount doesn't re-mask them (§3.2b).
COPY products/personal-finance/frontend/package*.json ./products/personal-finance/frontend/
COPY seed/framework/frontend/package*.json /app/seed/framework/frontend/
COPY seed/lib/frontend/package*.json /app/seed/lib/frontend/
# Same lockfile-pins-wrong-platform-optional bug as frontend-build, here on
# glibc/arm64 — drop the host lock so npm fetches the linux native binary
# (otherwise local-watch's `vite build` crash-loops the container).
# NPM fetch retries — these installs pull ~300-700 packages each from
# npmjs.org; a single ECONNRESET tarball fetch (~5% of long installs)
# aborts the whole RUN with exit 1 and loses 50+ min of work. Bumping
# `--fetch-retries` to 5 with backoff (20s..120s) absorbs transient
# blips. `--fetch-timeout=300000` extends per-request ceiling for big
# tarballs. Cache mount above amortizes after the first successful pass.
ARG NPM_RETRY="--fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 --fetch-timeout=300000"
RUN --mount=type=cache,target=/root/.npm \
    cd products/personal-finance/frontend \
    && rm -f package-lock.json \
    && npm install --no-audit --no-fund ${NPM_RETRY} \
    && cd /app/seed/framework/frontend \
    && rm -f package-lock.json \
    && npm install --no-audit --no-fund --include=peer ${NPM_RETRY} \
    && cd /app/seed/lib/frontend \
    && rm -f package-lock.json \
    && npm install --no-audit --no-fund --include=peer ${NPM_RETRY}
COPY seed/docker/local-watch.sh /usr/local/bin/local-watch
RUN chmod +x /usr/local/bin/local-watch \
    && chown -R noctus:noctus /app
USER noctus
ENV PRODUCT_SLUG=personal-finance PRODUCT_PORT=8002
# Same-origin SPA, single-container — local-watch builds the SPA via
# `vite build --watch` at container-start; vite's `define` rewrites
# `import.meta.env.VITE_BACKEND_API_URL` to `window.location.origin`
# ONLY when this env is set. Without it the build falls back to a
# PRODUCT_MAP lookup → defaults to http://localhost:8000 for products
# whose FE port isn't in the map → silent cross-product CORS failures.
# The `frontend-build` stage already sets this; runtime-watch must too
# because it rebuilds the bundle on every container start. (Bit
# 2026-05-20 on social-wiring.) Placed AFTER all RUN layers so a future
# toggle invalidates only this trivial layer, not the apt+npm cache.
ENV VITE_SAME_ORIGIN=1
ENTRYPOINT ["/usr/local/bin/local-watch"]
