#!/usr/bin/env bash
# scripts/bootstrap-worktree.sh — hydrate a fresh worktree's env
#
# Why: fresh `git worktree add ...` worktrees inherit .git but NOT .gitignored
# directories like node_modules/. Engineers in fresh worktrees consistently waste
# ~5-10 min on env-parity issues (npm install in seed/lib + seed/framework + every
# products/*/frontend; python venv mismatch).
#
# N=5+ confirmed (Engineers G, Q, AA, N, S — 2026-05-10). Filed under PROJECT
# `worktree-bootstrap-script`.
#
# Usage:
#   bash scripts/bootstrap-worktree.sh           # full hydrate
#   bash scripts/bootstrap-worktree.sh --check   # report only, no installs
#
# Idempotent: re-running on a hydrated worktree is fast (skip-if-current
# node_modules guard via mtime comparison; if node_modules/.package-lock.json is
# newer than package-lock.json, we skip — that's the standard `npm ci` marker).
#
# Methodology hooks:
# - No silent errors: every step exits non-zero on failure; final recap reports
#   skipped/installed/failed counts.
# - Idempotent: re-run is fast; --check is read-only.
# - AST-first is N/A (no Python edit).
#
# References:
# - KB § PATTERNS/branching-and-merging.md §16.7 (worktree-base verification — Step 0)
# - projects/worktree-bootstrap-script/PROJECT.md

set -euo pipefail

# ─── Argument parsing ────────────────────────────────────────────────────────
CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --check)
      CHECK_ONLY=1
      ;;
    -h|--help)
      cat <<'EOF'
bootstrap-worktree.sh — hydrate a fresh worktree's env

Usage:
  bash scripts/bootstrap-worktree.sh           # full hydrate (npm ci everywhere)
  bash scripts/bootstrap-worktree.sh --check   # report only (no installs)

Runs `npm ci` in every frontend dir (seed/lib/frontend, seed/framework/frontend,
products/*/frontend) that's stale, then prints a Python recap.
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Run with --help for usage." >&2
      exit 2
      ;;
  esac
done

# ─── Locate worktree root ────────────────────────────────────────────────────
if ! WORKTREE_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "ERROR: not inside a git worktree (git rev-parse --show-toplevel failed)" >&2
  exit 1
fi
cd "$WORKTREE_ROOT"

echo "→ Hydrating worktree at $WORKTREE_ROOT"
if [[ $CHECK_ONLY -eq 1 ]]; then
  echo "  (--check mode — reporting only, no installs)"
fi
echo ""

# ─── Idempotency helper ──────────────────────────────────────────────────────
# Returns 0 (true) if dir needs install: missing node_modules OR
# node_modules/.package-lock.json older than package-lock.json (or absent).
needs_install() {
  local d="$1"
  [[ ! -d "$d/node_modules" ]] && return 0
  [[ ! -f "$d/node_modules/.package-lock.json" ]] && return 0
  if [[ -f "$d/package-lock.json" ]]; then
    [[ "$d/package-lock.json" -nt "$d/node_modules/.package-lock.json" ]] && return 0
  fi
  return 1
}

# ─── Frontend hydration ──────────────────────────────────────────────────────
INSTALLED=()
SKIPPED=()
FAILED=()

hydrate_frontend() {
  local d="$1"
  if [[ ! -f "$d/package.json" ]]; then
    return 0
  fi
  if needs_install "$d"; then
    # Pick install command: `npm ci` if lockfile present (deterministic),
    # else `npm install` (generates a lockfile). Some products don't yet
    # have a checked-in lockfile (imobi-scheduling, youtube-crawler as of
    # 2026-05-10 — finding #1 from worktree-bootstrap-script smoke).
    local cmd
    if [[ -f "$d/package-lock.json" ]]; then
      cmd="ci"
    else
      cmd="install"
    fi
    if [[ $CHECK_ONLY -eq 1 ]]; then
      echo "  · STALE  $d  (would npm $cmd)"
      INSTALLED+=("$d")  # in --check, "INSTALLED" means "would-install"
      return 0
    fi
    echo "  · npm $cmd  $d"
    if (cd "$d" && npm "$cmd" --silent --no-audit --no-fund 2>&1); then
      INSTALLED+=("$d")
    else
      echo "    ✗ FAILED" >&2
      FAILED+=("$d")
    fi
  else
    echo "  · skip    $d  (node_modules current)"
    SKIPPED+=("$d")
  fi
}

echo "[1/3] Seed frontends"
for d in seed/lib/frontend seed/framework/frontend; do
  hydrate_frontend "$d"
done
echo ""

echo "[2/3] Per-product frontends"
# Stable, sorted order — deterministic across runs.
while IFS= read -r d; do
  hydrate_frontend "$d"
done < <(find products -maxdepth 3 -name package.json -not -path "*/node_modules/*" -exec dirname {} \; 2>/dev/null | sort)
echo ""

# ─── Python recap (informational; venv is shared across worktrees) ───────────
echo "[3/3] Python recap"
if command -v python3.11 >/dev/null 2>&1; then
  PY="$(command -v python3.11)"
  PY_VER="$($PY --version 2>&1)"
  echo "  · python3.11 at $PY  ($PY_VER)"
else
  echo "  · ⚠️  python3.11 not on PATH"
  if command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
    echo "    fallback: $PY  ($($PY --version 2>&1))"
  else
    echo "    no python3 either; install before running pytest" >&2
  fi
fi

if [[ -d "$WORKTREE_ROOT/venv" ]]; then
  echo "  · venv exists at $WORKTREE_ROOT/venv"
else
  echo "  · no $WORKTREE_ROOT/venv  (shared venv lives at the parent worktree;"
  echo "    if PYTHONPATH issues surface, see KB § PATTERNS/branching-and-merging.md §16)"
fi
echo ""

# ─── Final recap ─────────────────────────────────────────────────────────────
echo "============================================"
if [[ $CHECK_ONLY -eq 1 ]]; then
  echo "Bootstrap CHECK summary"
else
  echo "Bootstrap summary"
fi
echo "============================================"
printf "  Installed: %d\n" "${#INSTALLED[@]}"
printf "  Skipped:   %d  (already current)\n" "${#SKIPPED[@]}"
printf "  Failed:    %d\n" "${#FAILED[@]}"

if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo ""
  echo "✗ Hydration failed for:"
  for d in "${FAILED[@]}"; do
    echo "    - $d"
  done
  echo ""
  echo "  Investigate manually: (cd <dir> && npm ci)"
  exit 1
fi

echo ""
if [[ $CHECK_ONLY -eq 1 ]]; then
  if [[ ${#INSTALLED[@]} -gt 0 ]]; then
    echo "→ Worktree is STALE; re-run without --check to hydrate."
    exit 1
  else
    echo "✓ Worktree is current; no installs needed."
  fi
else
  echo "✓ Worktree env hydrated. Suggested next steps:"
  echo "    export PYTHONPATH=\"$WORKTREE_ROOT/seed/lib/backend\""
  echo "    cd products/<slug>/frontend && npm run build   # smoke"
fi
