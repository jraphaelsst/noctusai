#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# Custom git merge driver for docs carrying auto-generated
# `<!-- kb-counts:start:X -->…<!-- kb-counts:end:X -->` blocks
# (KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md, 06-AGENTS.md, AGENT-CONTEXT.md).
#
# WHY: those blocks are DETERMINISTICALLY regenerated from the tree by
# `cli.py --update-kb-counts` and auto-staged into every commit by the
# pre-commit hook. Under parallel feature branches, two commits that each add
# files to the SAME product both bump the same inventory row + grand-total line
# → git's default 3-way text merge reports a conflict on pure machine churn
# (observed 2026-06-05 integrating two file-disjoint social-wiring branches).
# A line-count conflict is never a real semantic conflict; re-deriving the block
# from the merged tree is always the correct resolution.
#
# WHAT THIS DRIVER DOES (git invokes:  driver %O %A %B %P):
#   1. write git's merge result (%A — may carry conflict markers, but ONLY inside
#      a counts block when the churn is count-only) to the real path %P;
#   2. run `--update-kb-counts` → regenerates EVERY kb-counts block from the tree,
#      overwriting the churn (and any conflict markers that sat between the
#      start/end markers) with fresh, correct numbers;
#   3. if NO conflict markers remain → exit 0 (resolved). If markers REMAIN
#      (a genuine concurrent PROSE edit outside the counts blocks) → restore %A
#      and exit 1 so git surfaces the real conflict to the human.
#
# Counts-only churn → silently correct. Real prose conflict → still surfaced.
# Mirrors the `.gitattributes merge=union` precedent for append-only ndjson;
# `union` is wrong for a TABLE (it duplicates rows), so we regenerate instead.
# Registered (local git config, not committed) by scripts/hooks/install-hooks.sh.
# KB § PATTERNS/common/auto-generated-merge-drivers.md
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

# %A current/ours-with-conflict (git wants the result written HERE);  %P real path.
CURRENT="${2:?merge driver: missing %A}"
PATHNAME="${4:-}"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Fallback: if git didn't pass %P (older git), we can't safely regenerate in place
# → behave like the default driver (leave %A as-is, signal conflict).
if [[ -z "$PATHNAME" ]]; then
    exit 1
fi
TARGET="$REPO_ROOT/$PATHNAME"

# venv-aware Python resolution — identical contract to scripts/hooks/pre-commit
# (worktrees have no venv of their own → fall back to the main repo's via
# --git-common-dir → finally python3).
if [[ -x "$REPO_ROOT/venv/bin/python" ]]; then
    PY="$REPO_ROOT/venv/bin/python"
else
    MAIN_REPO_GITDIR=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
    if [[ -n "$MAIN_REPO_GITDIR" ]]; then
        MAIN_REPO_ROOT=$(dirname "$MAIN_REPO_GITDIR")
        [[ -x "$MAIN_REPO_ROOT/venv/bin/python" ]] && PY="$MAIN_REPO_ROOT/venv/bin/python"
    fi
    PY="${PY:-${PYTHON:-python3}}"
fi
CLI="$REPO_ROOT/mcp/noctusai/cli.py"

has_markers() { grep -qE '^(<<<<<<<|=======|>>>>>>>)' "$1" 2>/dev/null; }

# 1. Materialize git's merge result into the real working-tree path.
cp "$CURRENT" "$TARGET"

# 2. Regenerate the counts blocks from the tree (best-effort: if python/CLI is
#    unavailable we fall through to the marker check below, which surfaces the
#    conflict rather than silently committing churn).
if { command -v "$PY" >/dev/null 2>&1 || [[ -x "$PY" ]]; } && [[ -f "$CLI" ]]; then
    "$PY" "$CLI" --update-kb-counts --worktree-path "$REPO_ROOT" >/dev/null 2>&1 || true
fi

# 3. Decide: clean → resolved; markers remain → real (prose) conflict, surface it.
if has_markers "$TARGET"; then
    cp "$CURRENT" "$TARGET"   # leave the conflicted version on disk for the human
    exit 1
fi
cp "$TARGET" "$CURRENT"       # hand the regenerated, conflict-free file back to git
exit 0
