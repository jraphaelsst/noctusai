#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# Custom git merge driver for LGPD-WARNINGS.md  (git invokes: driver %O %A %B %P).
#
# WHY: `noctus.dev.lgpd_flag` always inserts a new entry at the top of the file,
# so any two branches that each flag a concern insert at the SAME anchor and git's
# text merge conflicts every time. The 2026-10-10 resolution of exactly that
# conflict REPLACED one unresolved entry with the other and silently lost a
# concern. `merge=union` is no answer (it duplicates/mangles multi-line blocks).
#
# WHAT: delegate to the pure `lgpd.merge_warnings(base, ours, theirs)` via
# `cli.py --merge-lgpd-warnings` — entries are keyed by (concern, path) identity;
# additions from both sides are all kept (newest first), a one-sided change takes
# that side, a both-sides change conflicts in markers around just that block.
# Deletes are NOT re-policed here: keeper `check_lgpd_entry_removal`
# (commit-msg + CI) governs them.
#
# Exit: 0 = clean, %A rewritten;  1 = conflicted, %A holds the merge with
# markers around the conflicting block;  1 with %A UNTOUCHED = the render itself
# failed (no python / CLI error) → git surfaces its own conflict, never silence.
#
# 🔴 THE DRIVER WRITES %A AND NOTHING ELSE (same contract as merge-kb-counts.sh:
# touching the working tree breaks `git rebase`). The render goes to a scratch
# file that is removed on every exit path.
#
# Registered (local git config, not committed) by scripts/hooks/install-hooks.sh.
# KB § PATTERNS/common/auto-generated-merge-drivers.md · lgpd-entry-keeper.md
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE="${1:?merge driver: missing %O}"
CURRENT="${2:?merge driver: missing %A}"
OTHER="${3:?merge driver: missing %B}"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# venv-aware Python resolution — identical to merge-kb-counts.sh / pre-commit.
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

RENDERED="$(mktemp "${TMPDIR:-/tmp}/lgpd-merge.XXXXXX")"
trap 'rm -f "$RENDERED"' EXIT

if { command -v "$PY" >/dev/null 2>&1 || [[ -x "$PY" ]]; } && [[ -f "$CLI" ]]; then
    rc=0
    "$PY" "$CLI" --merge-lgpd-warnings "$BASE" "$CURRENT" "$OTHER" \
        --out "$RENDERED" --worktree-path "$REPO_ROOT" >/dev/null 2>&1 || rc=$?
    case "$rc" in
        0)  cp "$RENDERED" "$CURRENT"; exit 0 ;;
        10) cp "$RENDERED" "$CURRENT"; exit 1 ;;
    esac
fi
exit 1   # render unavailable/failed: %A untouched, git reports the conflict
