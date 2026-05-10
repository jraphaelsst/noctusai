# syntax=docker/dockerfile:1.7
# dev-team frontend Dockerfile.
#
# Generated from the canonical pattern at products/seed/frontend/Dockerfile.
# Multi-stage: Node builds, nginx:alpine serves. Build context = repo root
# (Vite alias factory resolves @noctusai/seed + @noctusai/lib into seed/).

FROM node:20-alpine AS build

WORKDIR /app

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
COPY products/dev-team/frontend/package*.json ./products/dev-team/frontend/
WORKDIR /app/products/dev-team/frontend
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund

# Layer 3: product code + build.
COPY products/dev-team/frontend ./
RUN npm run build

# Runtime: nginx serves the static bundle.
FROM nginx:alpine

# OCI image labels — populated via --build-arg GIT_SHA=$(git rev-parse HEAD).
ARG GIT_SHA=dev
LABEL org.opencontainers.image.source="https://github.com/jraphaelsst/noctusai"
LABEL org.opencontainers.image.revision="${GIT_SHA}"

COPY --from=build /app/products/dev-team/frontend/dist /usr/share/nginx/html
COPY seed/framework/frontend/nginx.conf.template /etc/nginx/templates/default.conf.template

ENV PORT=8123
EXPOSE 8123

CMD ["nginx", "-g", "daemon off;"]
