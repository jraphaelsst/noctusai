#!/usr/bin/env bash
# build-and-push.sh — build the slim PRODUCTION images for the product fleet
# and push them to GHCR.
#
# DURABLE HOME: scripts/infra/ (NOT projects/). This is permanent build/CI
# tooling referenced by .github/workflows/build-and-push.yml — it MUST live
# outside projects/ so archiving a project never breaks it. It previously
# lived at projects/production-deploy-migration/deploy/fleet/ and broke CI
# (exit 127) when that project was archived 2026-05-23 — the recurring
# "durable config anchored to a projects/ path" class. See KB §
# 01-PHILOSOPHY.md § "Durable docs are self-contained" + the archive tool's
# durable-refs gate (noctus.dev.archive refuses to archive a project that
# durable surfaces still point into).
#
# This is the build/CI side of the prod deploy. It produces the artifacts
# that the VPS then `pull`s — the VPS itself never builds.
#
# What it does, in order:
#   1. Build the two SHARED seed base images (delegates to the canonical
#      scripts/infra/build-base-images.sh — DRY, single source of the base
#      build recipe). Product images FROM these.
#   2. For each product: `docker build --target runtime` (slim, baked dist,
#      node-absent — the shippable image; NOT runtime-watch), passing the
#      per-product VITE_* build args + an `org.opencontainers.image.revision`
#      label (the git sha this image was built from — how
#      `noctus.dev.deploy_image`'s PROD-PIN ancestry guard later verifies a
#      pulled `:latest` actually came from a promoted commit). BAKE the
#      VITE_* values at BUILD time — Vite inlines import.meta.env.VITE_* into
#      the bundle; they CANNOT be supplied at runtime (see README "CRITICAL").
#   3. Tag each ghcr.io/jraphaelsst/noctus-<slug>:${NOCTUS_IMAGE_TAG:-latest}.
#   4. docker login ghcr.io (GHCR_USERNAME / GHCR_TOKEN) + push all.
#
# PROD-PIN HOLE (2026-07-20) — the safe-by-default tag contract:
#   The floating `:latest` tag is what the fleet's `docker-compose.prod.yml`
#   actually pulls (`${NOCTUS_IMAGE_TAG:-latest}`). Moving it on EVERY build
#   (as this script used to do unconditionally) meant `:latest` tracked
#   whatever branch happened to trigger a build — independent of the `prod`
#   promote-gate (KB § GUIDES/production-deploy.md § 2b). `:latest` now moves
#   ONLY when the caller explicitly passes `--move-latest` (the CI workflow
#   passes it ONLY on a `prod`-ref build — see .github/workflows/
#   build-and-push.yml). Every other run (a routine `main` push, a manual
#   `workflow_dispatch`) tags the convenience floating pointer `:edge`
#   instead — visible + pullable for testing, but never what the fleet's
#   compose file resolves.
#
# Run from a CI runner or build host with the repo checked out and the
# VITE_* + GHCR_* vars set in the environment (CI secrets) or a .env that
# this script sources. The VPS does NOT run this.
#
# Usage:
#   export GHCR_USERNAME=jraphaelsst GHCR_TOKEN=ghp_...
#   export VITE_SUPABASE_URL=https://<proj>.supabase.co
#   export VITE_SUPABASE_PUBLISHABLE_KEY=<anon-key>
#   export VITE_CORE_URL=https://<core-host> VITE_CORE_API_URL=https://<core-host>
#   export NOCTUS_IMAGE_TAG=$(git rev-parse --short HEAD)   # optional; default latest
#   bash scripts/infra/build-and-push.sh
#   bash scripts/infra/build-and-push.sh --no-push          # build only
#   bash scripts/infra/build-and-push.sh --no-base          # skip seed bases
#   bash scripts/infra/build-and-push.sh --move-latest       # ALSO move :latest (prod-ref builds only)
set -euo pipefail

# ── resolve repo root (this file is scripts/infra/) ───────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# Optionally source a build .env so a build host can keep VITE_*/GHCR_*
# out of the shell history. Real env vars already exported take precedence.
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

REGISTRY="ghcr.io/jraphaelsst"
TAG="${NOCTUS_IMAGE_TAG:-latest}"
PUSH=1
BUILD_BASE=1
MOVE_LATEST=0   # safe default (2026-07-20 PROD-PIN fix) — :latest moves ONLY on --move-latest
ALL_SLUGS=(core erp-imobiliario personal-finance therapy-platform daily-life adconnect dev-team social-wiring orbity seed)
REQUESTED=()   # optional subset of product slugs to build/push (default: all)
for arg in "$@"; do
  case "$arg" in
    --no-push) PUSH=0 ;;
    --no-base) BUILD_BASE=0 ;;
    --move-latest) MOVE_LATEST=1 ;;
    --*) echo "unknown flag: $arg" >&2; exit 2 ;;
    *) if printf '%s\n' "${ALL_SLUGS[@]}" | grep -qx "$arg"; then REQUESTED+=("$arg")
       else echo "unknown product slug: $arg (valid: ${ALL_SLUGS[*]})" >&2; exit 2; fi ;;
  esac
done
# want <slug> → true iff no subset was requested, or <slug> is in the subset.
want() { [[ ${#REQUESTED[@]} -eq 0 ]] || printf '%s\n' "${REQUESTED[@]}" | grep -qx "$1"; }

# The git sha every image is labeled with (org.opencontainers.image.revision)
# — how noctus.dev.deploy_image later verifies a pulled :latest actually came
# from a commit that reached origin/prod, not just any main push.
GIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"

# ── VITE_* build args (BAKED into the bundle at build time) ────────────
# Names mirror each product's docker-compose.yml `args:` block (ground
# truth — those are the ARGs the Dockerfiles actually declare). Empty ⇒
# the seed FE throws a configured-error page; the values MUST be the real
# prod Supabase project + the public core host.
: "${VITE_SUPABASE_URL:=}"
: "${VITE_SUPABASE_PUBLISHABLE_KEY:=}"
: "${VITE_CORE_URL:=}"
: "${VITE_CORE_API_URL:=}"

if [[ -z "$VITE_SUPABASE_URL" || -z "$VITE_SUPABASE_PUBLISHABLE_KEY" ]]; then
  echo "WARNING: VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY are empty." >&2
  echo "         Images will bake a non-functional (configured-error) frontend." >&2
  echo "         Set them before building a real prod image (see README CRITICAL)." >&2
fi

# Common Supabase args every product needs.
COMMON_VITE_ARGS=(
  --build-arg "VITE_SUPABASE_URL=${VITE_SUPABASE_URL}"
  --build-arg "VITE_SUPABASE_PUBLISHABLE_KEY=${VITE_SUPABASE_PUBLISHABLE_KEY}"
)

# ── 1. shared seed base images ────────────────────────────────────────
# IMPORTANT: the product Dockerfiles HARDCODE `FROM noctus-seed-*-base:dev`
# (they do NOT parameterize the seed base tag). So the seed bases MUST be
# tagged `dev` for the product `FROM` to resolve — regardless of the
# product image tag (NOCTUS_IMAGE_TAG). We therefore build the bases at
# `dev` here, NOT at ${TAG}. (Latent coupling — surfaced to the architect:
# parameterizing the base tag via an ARG would let CI tag bases per-commit
# too. Until then, `dev` is the fixed contract the Dockerfiles expect.)
SEED_BASE_TAG="dev"
if [[ "$BUILD_BASE" == "1" ]]; then
  echo "[fleet] building shared seed base images (tag: ${SEED_BASE_TAG} — pinned to match product Dockerfiles' hardcoded FROM)"
  bash "$REPO_ROOT/scripts/infra/build-base-images.sh" "${SEED_BASE_TAG}"
else
  echo "[fleet] --no-base: skipping seed base build (assuming noctus-seed-*-base:${SEED_BASE_TAG} exist)"
fi

# ── 2. per-product build + tag ────────────────────────────────────────
# Each product's VITE arg set differs (verified against the per-product
# composes): core uses VITE_CORE_API_URL; erp uses BOTH; the rest use
# VITE_CORE_URL. The Dockerfile declares only the ARGs it needs — passing
# an undeclared --build-arg is a harmless no-op warning, but we pass each
# product exactly its declared set for cleanliness.
build_product() {
  local slug="$1"; shift
  local image="${REGISTRY}/noctus-${slug}:${TAG}"
  echo "[fleet] building ${image} (--target runtime, revision=${GIT_SHA})"
  docker build \
    --target runtime \
    -f "products/${slug}/backend/Dockerfile" \
    -t "${image}" \
    --label "org.opencontainers.image.revision=${GIT_SHA}" \
    "$@" \
    .
}

if want core; then
  build_product core \
    "${COMMON_VITE_ARGS[@]}" \
    --build-arg "VITE_CORE_API_URL=${VITE_CORE_API_URL}"
fi

if want erp-imobiliario; then
  build_product erp-imobiliario \
    "${COMMON_VITE_ARGS[@]}" \
    --build-arg "VITE_CORE_API_URL=${VITE_CORE_API_URL}" \
    --build-arg "VITE_CORE_URL=${VITE_CORE_URL}"
fi

for slug in personal-finance therapy-platform daily-life adconnect dev-team social-wiring orbity seed; do
  want "$slug" || continue
  build_product "$slug" \
    "${COMMON_VITE_ARGS[@]}" \
    --build-arg "VITE_CORE_URL=${VITE_CORE_URL}"
done

# ── 3. login + push ───────────────────────────────────────────────────
if [[ "$PUSH" == "1" ]]; then
  if [[ -z "${GHCR_USERNAME:-}" || -z "${GHCR_TOKEN:-}" ]]; then
    echo "ERROR: GHCR_USERNAME / GHCR_TOKEN must be set to push." >&2
    echo "       Re-run with --no-push to build only." >&2
    exit 1
  fi
  echo "[fleet] docker login ghcr.io as ${GHCR_USERNAME}"
  echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USERNAME}" --password-stdin
  pushed=0
  for slug in "${ALL_SLUGS[@]}"; do
    want "$slug" || continue
    image="${REGISTRY}/noctus-${slug}:${TAG}"
    echo "[fleet] pushing ${image}"
    docker push "${image}"
    # PROD-PIN fix (2026-07-20): :latest — what the fleet's compose file
    # actually pulls — moves ONLY when the caller explicitly opted in via
    # --move-latest (the CI workflow does this ONLY for a prod-ref build).
    # Every other run gets the convenience floating pointer :edge instead,
    # so there is always a pullable "latest built from this ref" tag without
    # ever silently touching the tag production trusts.
    if [[ "$TAG" != "latest" ]]; then
      if [[ "$MOVE_LATEST" == "1" ]]; then
        docker tag "${image}" "${REGISTRY}/noctus-${slug}:latest"
        docker push "${REGISTRY}/noctus-${slug}:latest"
      else
        docker tag "${image}" "${REGISTRY}/noctus-${slug}:edge"
        docker push "${REGISTRY}/noctus-${slug}:edge"
      fi
    fi
    pushed=$((pushed + 1))
  done
  moved="edge"; [[ "$MOVE_LATEST" == "1" ]] && moved="latest"
  echo "[fleet] pushed ${pushed} product image(s) at tag ${TAG}$( [[ "$TAG" != "latest" ]] && echo " (+ :${moved})" )"
else
  echo "[fleet] --no-push: built ${#ALL_SLUGS[@]} product images locally (tag ${TAG}), not pushed"
fi

echo "[fleet] done."
