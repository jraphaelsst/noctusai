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

# ── deployable slug set — the SINGLE SOURCE OF TRUTH (2026-07-22 fix) ──
# Previously a hand-maintained `ALL_SLUGS` literal array here, which drifted
# from the real prod fleet: `products/knowledge-extractor/` is a real,
# on-disk, start.sh-registered product that was never added to
# `deploy/fleet/docker-compose.prod.yml` (never deployed). The CI workflow
# derives its build-scope slugs from *changed files* under `products/<slug>/`
# — the moment knowledge-extractor got a commit, CI passed it as an arg here,
# it failed the (hardcoded, stale) membership check, and the script's fatal
# `exit 2` killed the ENTIRE fleet build — no image pushed for ANY product.
#
# Root fix: derive the deployable set from `deploy/fleet/docker-compose.prod.yml`
# itself — the file that actually defines "what's in the prod fleet" — instead
# of maintaining a second hand-copied list that can only ever drift from it.
# Extracted from the `image: ghcr.io/.../noctus-<slug>:` lines (not the nested
# `services:` YAML keys) so no YAML parser is needed and non-product blocks
# (the `networks:` section, any future infra-only service) are never swept in.
FLEET_COMPOSE="$REPO_ROOT/deploy/fleet/docker-compose.prod.yml"
if [[ ! -f "$FLEET_COMPOSE" ]]; then
  echo "ERROR: $FLEET_COMPOSE not found — cannot derive the deployable product set." >&2
  exit 1
fi
# `while read` (not `mapfile`/`readarray` — bash 4+ only) so this also runs
# on macOS's stock bash 3.2 (a "build host" per the header's usage doc), not
# just the ubuntu-latest CI runner.
ALL_SLUGS=()
while IFS= read -r slug; do
  [[ -n "$slug" ]] && ALL_SLUGS+=("$slug")
done < <(
  grep -oE 'ghcr\.io/jraphaelsst/noctus-[a-z0-9-]+:' "$FLEET_COMPOSE" \
    | sed -E 's#^ghcr\.io/jraphaelsst/noctus-##; s/:$//' \
    | sort -u
)
if [[ ${#ALL_SLUGS[@]} -eq 0 ]]; then
  echo "ERROR: derived an EMPTY deployable product set from $FLEET_COMPOSE — refusing to build nothing (likely a parse regression)." >&2
  exit 1
fi

REQUESTED=()    # deployable subset of product slugs to build/push (default: all)
ANY_SLUG_ARG=0  # true iff >=1 positional (non-flag) arg was passed at all —
                # tracked SEPARATELY from REQUESTED so that passing ONLY a
                # real-but-undeployed slug (e.g. `knowledge-extractor` alone)
                # means "build nothing" (deliberately skipped), NOT "no subset
                # requested -> build the whole fleet" (the empty-REQUESTED
                # fallback below is for the true no-args case only).
for arg in "$@"; do
  case "$arg" in
    --no-push) PUSH=0 ;;
    --no-base) BUILD_BASE=0 ;;
    --move-latest) MOVE_LATEST=1 ;;
    --*) echo "unknown flag: $arg" >&2; exit 2 ;;
    *)
      ANY_SLUG_ARG=1
      if printf '%s\n' "${ALL_SLUGS[@]}" | grep -qx "$arg"; then
        REQUESTED+=("$arg")
      elif [[ -d "$REPO_ROOT/products/$arg" ]]; then
        # A REAL, on-disk product (e.g. knowledge-extractor) that simply
        # isn't in the prod fleet yet — deliberate skip, never fatal. This
        # is the exact case that used to abort the whole fleet build.
        echo "[fleet] skipping '$arg' — real product, not in the prod fleet (absent from deploy/fleet/docker-compose.prod.yml); nothing to build/push for it" >&2
      else
        # Not on disk at all — a genuine typo/bogus slug. Fatal is correct
        # here: there is nothing real this could plausibly mean.
        echo "unknown product slug: $arg (not a real product, and not one of the deployable slugs: ${ALL_SLUGS[*]})" >&2
        exit 2
      fi
      ;;
  esac
done
# want <slug> → true iff no slug arg was requested at all (default: build
# everything), or <slug> is in the resolved deployable subset. A run given
# ONLY undeployed real slugs (ANY_SLUG_ARG=1, REQUESTED empty) correctly
# builds nothing rather than falling back to "build all".
want() {
  [[ "$ANY_SLUG_ARG" == "0" ]] && return 0
  [[ ${#REQUESTED[@]} -gt 0 ]] && printf '%s\n' "${REQUESTED[@]}" | grep -qx "$1"
}

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

# The rest of the fleet (everything in ALL_SLUGS except core + erp-imobiliario,
# which are special-cased above for their extra VITE_CORE_API_URL arg). Derived
# from ALL_SLUGS — same root fix as above: this used to be its own hand-copied
# slug list, a SECOND drift vector alongside ALL_SLUGS itself (a product added
# to the prod fleet would pass the membership check above but silently never
# get built here).
for slug in "${ALL_SLUGS[@]}"; do
  case "$slug" in
    core|erp-imobiliario) continue ;;  # handled above with their extra arg
  esac
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
  # Pre-existing bug fixed in passing: this used to unconditionally report
  # `${#ALL_SLUGS[@]}` regardless of what `want` actually filtered down to
  # (wrong whenever a subset — or, as of the ANY_SLUG_ARG fix, nothing — was
  # requested). Count what `want` actually said yes to.
  built=0
  for slug in "${ALL_SLUGS[@]}"; do
    want "$slug" && built=$((built + 1))
  done
  echo "[fleet] --no-push: built ${built} product image(s) locally (tag ${TAG}), not pushed"
fi

echo "[fleet] done."
