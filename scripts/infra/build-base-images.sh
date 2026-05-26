#!/usr/bin/env bash
# build-base-images.sh — build the SHARED seed base images that every
# product image inherits via `FROM noctus-seed-*-base:<tag>`.
#
# Project: containerization-single-container. The base images carry the
# common heavy layers (system deps, venv, seed editable installs, seed
# frontend packages). Building them ONCE — before product images — means
# that work is cached a single time instead of repeated per product.
# start.sh calls this before `docker compose build/up` (Phase 5).
#
# Usage: bash scripts/infra/build-base-images.sh [tag]   (default tag: dev)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
TAG="${1:-dev}"
GIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo dev)"

echo "[base] building noctus-seed-backend-base:${TAG}"
docker build \
  --build-arg GIT_SHA="${GIT_SHA}" \
  -f seed/docker/Dockerfile.backend-base \
  -t "noctus-seed-backend-base:${TAG}" .

echo "[base] building noctus-seed-frontend-base:${TAG}"
docker build \
  -f seed/docker/Dockerfile.frontend-base \
  -t "noctus-seed-frontend-base:${TAG}" .

# ── Dep-completeness gate (codified guardrail) ───────────────────────────────
# A base image whose installed node_modules drifts from the declared
# package.json (stale Docker cache layer, omitted install, lock skew) "works"
# only until a clean container recreate re-seeds anon volumes from the image —
# then every product's `vite build` dies on a missing module. PROD never hit
# this (CI rebuilds bases fresh on an ephemeral runner) but the locally-cached
# base did (2026-05-25, tailwindcss-animate). Verify every declared seed-FE dep
# is actually present in the freshly-built image; fail the build LOUDLY instead
# of shipping a stale base. See KB § PATTERNS/base-image-dep-freshness.md.
_check='const fs=require("fs");const dir=process.argv[1];const p=require(dir+"/package.json");const deps={...(p.dependencies||{}),...(p.devDependencies||{})};const miss=Object.keys(deps).filter(d=>!fs.existsSync(dir+"/node_modules/"+d));if(miss.length){console.error("[base] FAIL "+dir+" — base image MISSING declared deps: "+miss.join(", ")+" (stale base; rebuild --no-cache or sync the lockfile)");process.exit(1);}console.log("[base] OK "+dir+" — all "+Object.keys(deps).length+" declared deps installed");'
for _d in /app/seed/framework/frontend /app/seed/lib/frontend; do
  docker run --rm --entrypoint node "noctus-seed-frontend-base:${TAG}" -e "${_check}" "${_d}"
done

echo "[base] done — product images can now FROM noctus-seed-*-base:${TAG}"
