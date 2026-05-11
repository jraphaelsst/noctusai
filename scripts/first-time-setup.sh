#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# first-time-setup.sh — Install frontend deps in every relevant location.
#
# WHY THIS EXISTS
# ───────────────
# `docker-compose.override.yml` (dev shape) bind-mounts the product's host
# `./frontend` directory ON TOP of the in-image `/app/products/<slug>/frontend`.
# That overlay clobbers the in-image `node_modules/` that the Dockerfile's
# `dev` stage installed at build time. If the host's `node_modules/` is empty
# or missing, dev startup fails with:
#
#   Error: Cannot find package 'vite' imported from /app/.../vite.config.ts
#
# Fresh-clone fix: run `npm install` on the host in every frontend location
# BEFORE `docker compose up`. This script automates that step.
#
# WHEN TO RUN
# ───────────
# - First time after `git clone`.
# - After pulling a branch that adds a product (new product = new node_modules).
# - After deleting `node_modules/` for any reason.
# - Re-runs are safe + fast (idempotent — npm install is a no-op when
#   package-lock.json hasn't changed since the last install).
#
# COVERAGE (drives off start.sh's PRODUCTS registry — auto-picks up new products)
# ──────────────────────────────────────────────────────────────────────
# 1. seed/framework/frontend
# 2. seed/lib/frontend
# 3. Every products/<slug>/frontend/ in the BEGIN/END_PRODUCTS_REGISTRY block.
#
# ALTERNATIVE (architectural, documented in KB §11d)
# ──────────────────────────────────────────────────
# Narrow the bind-mount to `./frontend/src:/app/.../frontend/src` so only
# source is overlaid and the in-image node_modules survives. That avoids
# the npm-install-per-clone step entirely but couples HMR coverage to the
# `src/` directory shape (no auto-reload on root-level config edits).
# Current shape uses the install-per-clone path — this script is the fix.
# ──────────────────────────────────────────────────────────────────────
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# ─── npm availability check ─────────────────────────────────────────────
if ! command -v npm >/dev/null 2>&1; then
  echo "ERRO: 'npm' not found on PATH."
  echo ""
  echo "  Install Node.js (which ships npm) before re-running this script."
  echo "  macOS:  brew install node"
  echo "  Linux:  https://nodejs.org/en/download/package-manager"
  echo ""
  exit 1
fi

NPM_VERSION="$(npm --version 2>/dev/null || echo unknown)"

echo "============================================"
echo "  NoctusAI Platform — first-time-setup"
echo "  npm: $NPM_VERSION"
echo "============================================"
echo ""

# ─── Source the PRODUCTS registry from start.sh (single source of truth) ─
# Same parsing approach used by scripts/smoke-fleet.sh. Auto-picks up new
# products scaffolded via `noctus.dev.scaffold_product`.
PRODUCTS=()
eval "$(awk '
  /^# BEGIN_PRODUCTS_REGISTRY/  {capture=1; next}
  /^# END_PRODUCTS_REGISTRY/    {capture=0}
  capture                       {print}
' start.sh)"

if [[ ${#PRODUCTS[@]} -eq 0 ]]; then
  echo "ERRO: PRODUCTS array empty. start.sh sentinels missing or renamed?" >&2
  exit 1
fi

# ─── Build the target list ──────────────────────────────────────────────
# Two seed targets + one per product (in registry order). Bash 3.2 compat:
# plain indexed array, no associative arrays / mapfile / readarray.
TARGETS=()
TARGETS+=("seed/framework/frontend")
TARGETS+=("seed/lib/frontend")
for entry in "${PRODUCTS[@]}"; do
  IFS=':' read -r slug _name _bp _fp <<< "$entry"
  TARGETS+=("products/$slug/frontend")
done

# ─── Run npm install in each target ─────────────────────────────────────
TOTAL=${#TARGETS[@]}
OK_COUNT=0
SKIP_COUNT=0
FAIL_COUNT=0
FAILED_DIRS=()
SKIPPED_DIRS=()

i=0
for target in "${TARGETS[@]}"; do
  i=$((i + 1))
  printf "[%2d/%2d] %s ... " "$i" "$TOTAL" "$target"

  if [[ ! -d "$ROOT_DIR/$target" ]]; then
    echo "skip (directory missing)"
    SKIP_COUNT=$((SKIP_COUNT + 1))
    SKIPPED_DIRS+=("$target (no directory)")
    continue
  fi

  if [[ ! -f "$ROOT_DIR/$target/package.json" ]]; then
    echo "skip (no package.json)"
    SKIP_COUNT=$((SKIP_COUNT + 1))
    SKIPPED_DIRS+=("$target (no package.json)")
    continue
  fi

  # Use `cd … && npm install && cd -` — npm's `--prefix` flag is finicky
  # with workspaces and resolver edge cases. Sub-shell isolation so a
  # failure doesn't leave $PWD dangling.
  if (cd "$ROOT_DIR/$target" && npm install --no-audit --no-fund >/dev/null 2>&1); then
    echo "ok"
    OK_COUNT=$((OK_COUNT + 1))
  else
    echo "FAIL"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    FAILED_DIRS+=("$target")
  fi
done

# ─── Summary ────────────────────────────────────────────────────────────
echo ""
echo "============================================"
echo "  Summary"
echo "============================================"
echo "  total:   $TOTAL"
echo "  ok:      $OK_COUNT"
echo "  skipped: $SKIP_COUNT"
echo "  failed:  $FAIL_COUNT"

if [[ $SKIP_COUNT -gt 0 ]]; then
  echo ""
  echo "  Skipped targets:"
  for dir in "${SKIPPED_DIRS[@]}"; do
    echo "    - $dir"
  done
fi

if [[ $FAIL_COUNT -gt 0 ]]; then
  echo ""
  echo "  Failed targets (re-run manually to see npm's error output):"
  for dir in "${FAILED_DIRS[@]}"; do
    echo "    - cd $dir && npm install"
  done
  echo ""
  exit 1
fi

echo ""
echo "  Done. You can now run: ./start.sh"
echo ""
