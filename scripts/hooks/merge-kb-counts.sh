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
#   1. ask the CLI to render %A's content with every kb-counts block that
#      belongs to %P regenerated from the tree — `--render-kb-counts` writes
#      ONLY to the `--out` scratch file we hand it, never to a tracked file;
#   2. if NO conflict markers remain in that render → write it to %A, exit 0
#      (resolved). If markers REMAIN (a genuine concurrent PROSE edit outside
#      the counts blocks) → leave %A untouched and exit 1 so git surfaces the
#      real conflict to the human.
#
# Counts-only churn → silently correct. Real prose conflict → still surfaced.
# Mirrors the `.gitattributes merge=union` precedent for append-only ndjson;
# `union` is wrong for a TABLE (it duplicates rows), so we regenerate instead.
#
# 🔴 THE DRIVER WRITES %A AND NOTHING ELSE. That is git's contract for a merge
# driver, and breaking it broke rebase. The original implementation copied %A
# over the real path, ran `--update-kb-counts` (which rewrites EVERY kb-counts
# doc in the tree, not just the merged one), and copied back — leaving the
# working tree modified as a side effect. A single merge hides that, because
# git overwrites the working tree from %A immediately afterwards. A REBASE does
# not: the sequencer applies one commit per pick, and the counts written during
# pick N reflect the intermediate tree, so pick N+1 aborts with "Your local
# changes to the following files would be overwritten by merge" — forever.
# `git rebase --continue` then reschedules the same pick, so the rebase cannot
# finish and the todo list grows on every attempt. Observed 2026-08-17 replaying
# 10 commits over `dev`; the tempting fix is to neutralise the driver for the
# rebase (`-c merge.kb-counts.driver=true`), which is a workaround around a
# defect in this file. Keep this driver side-effect-free instead.
#
# Registered (local git config, not committed) by scripts/hooks/install-hooks.sh.
# KB § PATTERNS/common/auto-generated-merge-drivers.md
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

# %A current/ours-with-conflict (git wants the result written HERE);  %P real path.
CURRENT="${2:?merge driver: missing %A}"
PATHNAME="${4:-}"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Fallback: if git didn't pass %P (older git), we don't know WHICH doc's blocks
# to regenerate → behave like the default driver (leave %A as-is, signal
# conflict) rather than guess.
if [[ -z "$PATHNAME" ]]; then
    exit 1
fi

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

# Scratch file for the render. Cleaned up on every exit path, including the
# `set -e` ones — a merge driver that litters temp files into the repo is the
# same class of side effect this driver was rewritten to stop having.
RENDERED="$(mktemp "${TMPDIR:-/tmp}/kb-counts-render.XXXXXX")"
trap 'rm -f "$RENDERED"' EXIT

# 1. Render %A's content with the counts blocks regenerated from the tree.
#    Pure — nothing is written to the working tree. If python/the CLI is
#    unavailable, or the render fails for any reason, we fall through to the
#    marker check with the UNRENDERED merge result, which surfaces the conflict
#    rather than silently committing churn.
if { command -v "$PY" >/dev/null 2>&1 || [[ -x "$PY" ]]; } && [[ -f "$CLI" ]]; then
    if ! "$PY" "$CLI" --render-kb-counts "$PATHNAME" --source "$CURRENT" \
            --out "$RENDERED" --worktree-path "$REPO_ROOT" >/dev/null 2>&1; then
        cp "$CURRENT" "$RENDERED"
    fi
else
    cp "$CURRENT" "$RENDERED"
fi

# 2. Decide: clean → resolved; markers remain → real (prose) conflict, surface
#    it with %A exactly as git left it.
if has_markers "$RENDERED"; then
    exit 1
fi
cp "$RENDERED" "$CURRENT"     # hand the regenerated, conflict-free file back to git
exit 0
