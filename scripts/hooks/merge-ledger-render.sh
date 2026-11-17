#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# Custom git merge driver for GENERATED renders  (git invokes: driver %O %A %B %P).
#   project-history/*/FINDINGS.md                      <- project-history/<ledger>/findings.ndjson
#   KNOWLEDGE-BASE/.../gate-alignment-inventory.md     <- gate-alignment-inventory.json
#
# WHY: every branch that reconciles a ledger / declares a gate rewrites the SAME render, so parallel
# branches ALWAYS conflict on machine churn (22 transcript hotspots). A render is a pure function of its
# source, so the right merge is to regenerate it from the MERGED source, never to hand-resolve it.
#
# WHAT: `cli.py --merge-ledger-render %P %O %A %B --out F` (pure; recovers the sources from the render
# blobs, merges them the way git merges them, renders). Exit 0 -> %A = the render. Exit 10 / failure ->
# %A = the plain 3-way merge (markers where the sides disagree, never "ours" alone), exit = its conflict
# state, so an unrenderable file still surfaces a REAL conflict and the CI queue's derived-set re-derive
# (merge_queue.DERIVED_SETS) is the backstop.
#
# 🔴 THE DRIVER WRITES %A AND NOTHING ELSE (same contract as merge-kb-counts.sh).
# Registered by scripts/hooks/register-merge-drivers.sh. KB § PATTERNS/common/auto-generated-merge-drivers.md
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE="${1:?merge driver: missing %O}"
CURRENT="${2:?merge driver: missing %A}"
OTHER="${3:?merge driver: missing %B}"
RELPATH="${4:-}"

# %A must end holding a 3-way merge (git takes %A as the RESULT); returns git merge-file's conflict state.
plain_merge_into_current() {
    local plain rc=0; plain="$(mktemp "${TMPDIR:-/tmp}/ledger-render-merge-plain.XXXXXX")"
    git merge-file -p -L ours -L base -L theirs "$CURRENT" "$BASE" "$OTHER" >"$plain" 2>/dev/null || rc=$?
    [[ -s "$plain" ]] && cp "$plain" "$CURRENT"
    rm -f "$plain"
    [[ "$rc" -eq 0 ]] && return 0
    return 1
}

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

RENDERED="$(mktemp "${TMPDIR:-/tmp}/ledger-render-merge.XXXXXX")"
trap 'rm -f "$RENDERED"' EXIT

if [[ -n "$RELPATH" ]] && { command -v "$PY" >/dev/null 2>&1 || [[ -x "$PY" ]]; } && [[ -f "$CLI" ]]; then
    rc=0
    "$PY" "$CLI" --merge-ledger-render "$RELPATH" "$BASE" "$CURRENT" "$OTHER" \
        --out "$RENDERED" --worktree-path "$REPO_ROOT" >/dev/null 2>&1 || rc=$?
    if [[ "$rc" -eq 0 && -s "$RENDERED" ]]; then
        cp "$RENDERED" "$CURRENT"; exit 0
    fi
fi
plain_merge_into_current && exit 0
exit 1
