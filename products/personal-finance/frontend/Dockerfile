# syntax=docker/dockerfile:1.7
# personal-finance frontend Dockerfile.
#
# Generated from the canonical pattern at products/seed/frontend/Dockerfile.
# Multi-stage: Node builds, nginx:alpine serves. Build context = repo root
# (Vite alias factory resolves @noctusai/seed + @noctusai/lib into seed/).

FROM node:20-alpine AS build

WORKDIR /app

# ─── VITE_* build-arg contract ──────────────────────────────────────────
# Every `import.meta.env.VITE_*` referenced in product or seed code must be
# declared as ARG here AND as args: in the compose `frontend:` service,
# sourced from `.env` via ${VITE_FOO} interpolation. See
# KB § PATTERNS/containerization.md § VITE_* build-arg contract.
# Note: `VITE_BACKEND_API_URL` + `VITE_PRODUCT_SCHEMA` are factory-injected
# via `define:` in vite.config.factory.ts (no build-arg needed for those).
ARG VITE_CORE_URL=
ENV VITE_CORE_URL=${VITE_CORE_URL}

# Layer 1: seed frontend packages (factory + lib aliases) + install
# their deps so jiti/tailwind can resolve transitive packages like
# tailwindcss-animate when product code imports the seed factory.
COPY seed/framework/frontend ./seed/framework/frontend
COPY seed/lib/frontend ./seed/lib/frontend
WORKDIR /app/seed/framework/frontend
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund --include=peer
WORKDIR /app/seed/lib/frontend
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund --include=peer

# Layer 2: product manifest.
WORKDIR /app
COPY products/personal-finance/frontend/package*.json ./products/personal-finance/frontend/
WORKDIR /app/products/personal-finance/frontend
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund

# Layer 3: product code + build.
COPY products/personal-finance/frontend ./
RUN npm run build

# Dev stage: vite dev server with HMR. Selected by docker-compose.override.yml
# via `build.target: dev`. Same first-two layers as `build` (no source COPY,
# no `npm run build`) — dev override bind-mounts product source at runtime
# and vite runs `npm run dev`. See KB § PATTERNS/containerization.md §11d.
FROM node:20-alpine AS dev
WORKDIR /app
COPY seed/framework/frontend ./seed/framework/frontend
COPY seed/lib/frontend ./seed/lib/frontend
WORKDIR /app/seed/framework/frontend
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund --include=peer
WORKDIR /app/seed/lib/frontend
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund --include=peer
WORKDIR /app
COPY products/personal-finance/frontend/package*.json ./products/personal-finance/frontend/
WORKDIR /app/products/personal-finance/frontend
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund
EXPOSE 8090
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Runtime: nginx serves the static bundle.
FROM nginx:alpine

# OCI image labels — populated via --build-arg GIT_SHA=$(git rev-parse HEAD).
ARG GIT_SHA=dev
LABEL org.opencontainers.image.source="https://github.com/jraphaelsst/noctusai"
LABEL org.opencontainers.image.revision="${GIT_SHA}"

COPY --from=build /app/products/personal-finance/frontend/dist /usr/share/nginx/html
COPY seed/framework/frontend/nginx.conf.template /etc/nginx/templates/default.conf.template

ENV PORT=8090
EXPOSE 8090

CMD ["nginx", "-g", "daemon off;"]
