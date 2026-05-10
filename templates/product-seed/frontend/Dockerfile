# syntax=docker/dockerfile:1.7
# Canonical NoctusAI product frontend Dockerfile.
#
# Multi-stage: Node builds the SPA, nginx:alpine serves the static bundle.
# Build context: repo root (vite.config.factory resolves @noctusai/seed +
# @noctusai/lib via aliases pointing into seed/framework/frontend/src and
# seed/lib/frontend/src — both must be in the build context).
#
# nginx PORT substitution: nginx:alpine auto-templates ${PORT} from
# /etc/nginx/templates/*.template at container start. Single seed-side
# template (seed/framework/frontend/nginx.conf.template); all SPA frontends
# inherit it.

FROM node:20-alpine AS build

WORKDIR /app

# ─── Layer 1: seed frontend packages (factory + lib aliases) ────────────
# Copied first so changes to product code don't bust the seed cache layer.
# Install their deps too so jiti/tailwind can resolve transitive packages
# (tailwindcss-animate, lucide-react, etc.) when products import the
# seed factory — Node module resolution walks UP from the factory file's
# directory, not from the product's cwd.
COPY seed/framework/frontend ./seed/framework/frontend
COPY seed/lib/frontend ./seed/lib/frontend
WORKDIR /app/seed/framework/frontend
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund --include=peer
WORKDIR /app/seed/lib/frontend
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund --include=peer

# ─── Layer 2: product manifest ──────────────────────────────────────────
# package*.json copied alone so npm install caches across code-only diffs.
WORKDIR /app
COPY products/seed/frontend/package*.json ./products/seed/frontend/
WORKDIR /app/products/seed/frontend
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund

# ─── Layer 3: product code + build ──────────────────────────────────────
COPY products/seed/frontend ./
RUN npm run build

# ─── Runtime stage: nginx serves the static bundle ──────────────────────
FROM nginx:alpine

# OCI image labels — populated at build time via --build-arg GIT_SHA=$(git rev-parse HEAD).
# Defaults to "dev" so plain `docker build` still succeeds without the arg.
ARG GIT_SHA=dev
LABEL org.opencontainers.image.source="https://github.com/jraphaelsst/noctusai"
LABEL org.opencontainers.image.revision="${GIT_SHA}"

COPY --from=build /app/products/seed/frontend/dist /usr/share/nginx/html
COPY seed/framework/frontend/nginx.conf.template /etc/nginx/templates/default.conf.template

ENV PORT=8100
EXPOSE 8100

CMD ["nginx", "-g", "daemon off;"]
