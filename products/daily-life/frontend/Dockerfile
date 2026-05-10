# syntax=docker/dockerfile:1.7
# daily-life frontend Dockerfile.
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
COPY products/daily-life/frontend/package*.json ./products/daily-life/frontend/
WORKDIR /app/products/daily-life/frontend
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund

# Layer 3: product code + build.
COPY products/daily-life/frontend ./
RUN npm run build

# Runtime: nginx serves the static bundle.
FROM nginx:alpine

COPY --from=build /app/products/daily-life/frontend/dist /usr/share/nginx/html
COPY seed/framework/frontend/nginx.conf.template /etc/nginx/templates/default.conf.template

ENV PORT=8110
EXPOSE 8110

CMD ["nginx", "-g", "daemon off;"]
