#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# Custom git merge driver for gate-alignment-inventory.json  (git invokes: driver %O %A %B %P).
#
# WHY: `decisions[]` ids are hand-assigned (next D<n>) and appended at the list
# tail, and `gates` gains a row per new gate. Any two parallel branches that each
# add a decision conflict textually at the tail AND can mint a duplicate id
# (s1 `gate-inventory/decision-id-collision`; D18..D21 on 2026-11-07).
#
# WHAT: delegate to the pure `gate_alignment.merge_inventory(base, ours, theirs)`
# via `cli.py --merge-gate-inventory` — gates = union (same key edited differently
# on both sides conflicts), decisions = ours + theirs' new entries (renumbered on
# id collision, duplicates dropped), sorted + byte-stable output.
#
# Exit: 0 = clean, %A rewritten;  1 = conflicted, %A holds ours (merged where
# clean) so git reports the conflict;  1 with %A UNTOUCHED = merge itself failed.
#
# 🔴 THE DRIVER WRITES %A AND NOTHING ELSE (same contract as merge-kb-counts.sh).
# Registered by scripts/hooks/register-merge-drivers.sh (install-hooks + merge-queue CI).
# KB § PATTERNS/common/auto-generated-merge-drivers.md
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE="${1:?merge driver: missing %O}"
CURRENT="${2:?merge driver: missing %A}"
OTHER="${3:?merge driver: missing %B}"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

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

RENDERED="$(mktemp "${TMPDIR:-/tmp}/gate-inventory-merge.XXXXXX")"
trap 'rm -f "$RENDERED"' EXIT

if { command -v "$PY" >/dev/null 2>&1 || [[ -x "$PY" ]]; } && [[ -f "$CLI" ]]; then
    rc=0
    "$PY" "$CLI" --merge-gate-inventory "$BASE" "$CURRENT" "$OTHER" \
        --out "$RENDERED" --worktree-path "$REPO_ROOT" >/dev/null 2>&1 || rc=$?
    case "$rc" in
        0)  cp "$RENDERED" "$CURRENT"; exit 0 ;;
        10) cp "$RENDERED" "$CURRENT"; exit 1 ;;
    esac
fi
exit 1   # merge unavailable/failed: %A untouched, git reports the conflict
