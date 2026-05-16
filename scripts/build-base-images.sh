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
# Usage: bash scripts/build-base-images.sh [tag]   (default tag: dev)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

echo "[base] done — product images can now FROM noctus-seed-*-base:${TAG}"
