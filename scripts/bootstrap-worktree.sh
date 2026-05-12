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
  bash scripts/bootstrap-worktree.sh           # full hydrate
  bash scripts/bootstrap-worktree.sh --check   # report only (no installs)

Steps:
  [1/4] Seed frontends            — npm ci in seed/lib/frontend + seed/framework/frontend
  [2/4] Per-product frontends     — npm ci in every products/*/frontend
  [3/4] Python recap              — discover shared venv + probe cli.py deps
  [4/4] Per-product backend reqs  — pip install -r every products/*/backend/requirements.txt
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

# ─── Pre-flight: cleanup stale worktrees from prior sessions ────────────────
# Per KB § PATTERNS/branching-and-merging.md §19 (Worktree lifecycle), every
# agent worktree whose branch is merged to main is removable. Sweeping before
# hydrate keeps disk usage bounded — a 76-worktree accumulation cost 67 GiB
# 2026-05-11 + blocked Engineer III at preamble (disk hit 100%).
#
# Skipped in --check mode (read-only) and when invoked from inside an agent
# worktree (engineers don't sweep peers — only main-tree invocations do).
CLEANUP_SCRIPT="$WORKTREE_ROOT/scripts/cleanup-stale-worktrees.sh"
NOC_ROOT="$(cd "$WORKTREE_ROOT" && git rev-parse --git-common-dir 2>/dev/null | xargs -I{} dirname {})"
if [[ $CHECK_ONLY -eq 0 && "$WORKTREE_ROOT" != *".claude/worktrees/agent-"* && -x "$CLEANUP_SCRIPT" ]]; then
  echo "→ Pre-flight: sweep stale agent worktrees"
  bash "$CLEANUP_SCRIPT" --force 2>&1 | sed 's/^/  /'
  echo ""
fi

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

echo "[1/4] Seed frontends"
for d in seed/lib/frontend seed/framework/frontend; do
  hydrate_frontend "$d"
done
echo ""

echo "[2/4] Per-product frontends"
# Stable, sorted order — deterministic across runs.
while IFS= read -r d; do
  hydrate_frontend "$d"
done < <(find products -maxdepth 3 -name package.json -not -path "*/node_modules/*" -exec dirname {} \; 2>/dev/null | sort)
echo ""

# ─── Python recap + shared-venv discovery ────────────────────────────────────
# Worktrees do NOT carry their own Python venv (gitignored + duplication-prone:
# 15 worktrees × ~300 MB = ~4.5 GiB of redundant site-packages). Instead, the
# MAIN repo's venv is shared. This block discovers it (same shape as
# scripts/pre-commit) and probes for the deps engineers need to run
# `python mcp/noctusai/cli.py --review` (and the pre-commit hook's
# `--check-phase-state`).
#
# N=3 recurrence formalization (2026-05-11 — DL-P2 + MAI-P2 + PF-AUTH-MIG):
# engineers in worktrees hit `ModuleNotFoundError: pydantic_settings` invoking
# cli.py because system `python3` lacks the platform's deps. Pointing them at
# the main venv closes the gap.
echo "[3/4] Python recap"
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

# Discover the main repo's venv (worktree-aware, mirrors scripts/pre-commit:135-145).
SHARED_VENV_PY=""
if [[ -x "$WORKTREE_ROOT/venv/bin/python" ]]; then
  # In-tree venv (this worktree is itself the main checkout).
  SHARED_VENV_PY="$WORKTREE_ROOT/venv/bin/python"
  echo "  · in-tree venv at $WORKTREE_ROOT/venv"
else
  MAIN_REPO_GITDIR="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  if [[ -n "$MAIN_REPO_GITDIR" ]]; then
    MAIN_REPO_ROOT="$(dirname "$MAIN_REPO_GITDIR")"
    if [[ -x "$MAIN_REPO_ROOT/venv/bin/python" ]]; then
      SHARED_VENV_PY="$MAIN_REPO_ROOT/venv/bin/python"
      echo "  · shared venv at $MAIN_REPO_ROOT/venv  (no per-worktree venv — by design)"
    else
      echo "  · ⚠️  no shared venv found at $MAIN_REPO_ROOT/venv"
      echo "    run from the main checkout: python3.11 -m venv venv && venv/bin/pip install -r mcp/noctusai/requirements.txt -e seed/lib/backend"
    fi
  fi
fi

# Probe the shared venv for the deps cli.py needs (pydantic_settings via
# noctusai_lib.config; noctusai_lib itself for logging_config; mcp for the
# stdio server). Reports missing deps + the one-line fix.
if [[ -n "$SHARED_VENV_PY" ]]; then
  MISSING_DEPS=""
  for mod in noctusai_lib pydantic_settings mcp; do
    if ! "$SHARED_VENV_PY" -c "import $mod" 2>/dev/null; then
      MISSING_DEPS="$MISSING_DEPS $mod"
    fi
  done
  if [[ -n "$MISSING_DEPS" ]]; then
    echo "  · ⚠️  shared venv missing modules:$MISSING_DEPS"
    echo "    fix (from the main checkout):"
    echo "      $SHARED_VENV_PY -m pip install -r mcp/noctusai/requirements.txt -e seed/lib/backend"
  else
    echo "  · shared venv has noctusai_lib + pydantic_settings + mcp  (cli.py --review ready)"
  fi
fi
echo ""

# ─── Per-product backend requirements hydration ─────────────────────────────
# Closes the N=2 defusedxml recurrence (2026-05-11 — adconnect 12 tests
# uncollected + erp 940 collection errors). Root requirements.txt is a unified
# superset but lags per-product requirements; the structural fix is to install
# every products/*/backend/requirements.txt into the shared venv at bootstrap.
#
# pip install -r is naturally idempotent (already-installed packages no-op).
# Quiet flag (-q) suppresses noise on already-satisfied; one summary line per
# product (installed / failed / skipped-no-venv).
#
# Per-product pyproject.toml fallback is not needed today (no products use one
# 2026-05-11) — extend here if that changes.
echo "[4/4] Per-product backend requirements"
PRODUCT_REQS_INSTALLED=()
PRODUCT_REQS_FAILED=()
if [[ -z "$SHARED_VENV_PY" ]]; then
  echo "  · skip (no shared venv discovered above — re-run after main-checkout venv exists)"
else
  if [[ $CHECK_ONLY -eq 1 ]]; then
    while IFS= read -r req; do
      [[ -z "$req" ]] && continue
      product="$(basename "$(dirname "$(dirname "$req")")")"
      echo "  · WOULD install: $product ($req)"
      PRODUCT_REQS_INSTALLED+=("$product")
    done < <(find products -maxdepth 4 -name requirements.txt -path '*/backend/*' -not -path '*/.*/*' 2>/dev/null | sort)
  else
    while IFS= read -r req; do
      [[ -z "$req" ]] && continue
      product="$(basename "$(dirname "$(dirname "$req")")")"
      if "$SHARED_VENV_PY" -m pip install -q -r "$req" 2>/dev/null; then
        echo "  · installed: $product"
        PRODUCT_REQS_INSTALLED+=("$product")
      else
        # Re-run without -q to surface the reason on failure.
        err="$("$SHARED_VENV_PY" -m pip install -r "$req" 2>&1 | tail -3 | tr '\n' ' ')"
        echo "  · failed:    $product — $err"
        PRODUCT_REQS_FAILED+=("$product")
      fi
    done < <(find products -maxdepth 4 -name requirements.txt -path '*/backend/*' -not -path '*/.*/*' 2>/dev/null | sort)
  fi
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
printf "  Frontend installed: %d\n" "${#INSTALLED[@]}"
printf "  Frontend skipped:   %d  (already current)\n" "${#SKIPPED[@]}"
printf "  Frontend failed:    %d\n" "${#FAILED[@]}"
printf "  Product reqs OK:    %d\n" "${#PRODUCT_REQS_INSTALLED[@]}"
printf "  Product reqs fail:  %d\n" "${#PRODUCT_REQS_FAILED[@]}"

if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo ""
  echo "✗ Frontend hydration failed for:"
  for d in "${FAILED[@]}"; do
    echo "    - $d"
  done
  echo ""
  echo "  Investigate manually: (cd <dir> && npm ci)"
  exit 1
fi

if [[ ${#PRODUCT_REQS_FAILED[@]} -gt 0 ]]; then
  echo ""
  echo "✗ Per-product requirements install failed for:"
  for p in "${PRODUCT_REQS_FAILED[@]}"; do
    echo "    - $p"
  done
  echo ""
  echo "  Investigate manually: $SHARED_VENV_PY -m pip install -r products/<slug>/backend/requirements.txt"
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
  if [[ -n "${SHARED_VENV_PY:-}" ]]; then
    echo "    # Run cli.py / pre-commit checks via the shared venv:"
    echo "    $SHARED_VENV_PY mcp/noctusai/cli.py --review"
    echo "    # (or alias:  export NOC_PY=\"$SHARED_VENV_PY\"  &&  \$NOC_PY mcp/noctusai/cli.py --review )"
  else
    echo "    export PYTHONPATH=\"$WORKTREE_ROOT/seed/lib/backend\"   # shared venv not found"
  fi
  echo "    cd products/<slug>/frontend && npm run build   # smoke"
fi
