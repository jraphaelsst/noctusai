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
#   0. 3-WAY MERGE FIRST: `git merge-file` %A (ours) + %O (base) + %B (theirs)
#      into a scratch file. %A is ONLY "ours" — git does NOT pre-merge for a
#      custom driver. Rendering %A alone (the 2026-06..11-05 behaviour) silently
#      discarded every prose edit from the other side: in a rebase "ours" is the
#      upstream, so a branch's own roster-row rename vanished on every rebase
#      (nosnolimiar 02-LANDSCAPE.md, lost twice: d6d53e3fc, 510f392cd), and a
#      queue composition could drop a peer's edit the same way;
#   1. ask the CLI to render the MERGED content with every kb-counts block that
#      belongs to %P regenerated from the tree — `--render-kb-counts` writes
#      ONLY to the `--out` scratch file we hand it, never to a tracked file;
#   2. if NO conflict markers remain in that render → write it to %A, exit 0
#      (resolved). If markers REMAIN (a genuine concurrent PROSE edit outside
#      the counts blocks) → write the render, MARKERS INCLUDED, to %A and exit 1
#      so git surfaces the real conflict to the human.
#
# 🔴 ON EVERY CONFLICT EXIT, %A MUST HOLD THE 3-WAY MERGE (with markers). git
# takes %A as the merge RESULT; a non-zero exit only flags the path. Leaving %A
# as "ours" therefore shows a conflicted file with NO markers whose other-side
# lines are silently gone (2026-11-10: dev's `agent-creator` row vanished from
# 06-AGENTS.md during a feature-branch merge). The render-failure and no-%P
# exits hand back the plain 3-way merge for the same reason.
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
# Registered (per-repo git config, not committed) by scripts/hooks/register-merge-drivers.sh
# (called by install-hooks.sh and by .github/workflows/merge-queue.yml).
# KB § PATTERNS/common/auto-generated-merge-drivers.md
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

# %A current/ours-with-conflict (git wants the result written HERE);  %P real path.
BASE="${1:?merge driver: missing %O}"
CURRENT="${2:?merge driver: missing %A}"
OTHER="${3:?merge driver: missing %B}"
PATHNAME="${4:-}"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"


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
# Hand git a conflicted RESULT: copy $1 (a 3-way merge, markers included) into %A, exit 1.
surface_conflict() { cp "$1" "$CURRENT"; exit 1; }

# Scratch file for the render. Cleaned up on every exit path, including the
# `set -e` ones — a merge driver that litters temp files into the repo is the
# same class of side effect this driver was rewritten to stop having.
RENDERED="$(mktemp "${TMPDIR:-/tmp}/kb-counts-render.XXXXXX")"
MERGED="$(mktemp "${TMPDIR:-/tmp}/kb-counts-merged.XXXXXX")"
trap 'rm -f "$RENDERED" "$RENDERED.err" "$MERGED"' EXIT

# 0. Real 3-way merge of ours/base/theirs. Exit status = number of conflicts
#    (>0 is expected: counts churn conflicts inside the generated blocks, which
#    step 1 regenerates away); <0 / >127 is a real error → surface the conflict.
set +e
git merge-file -p -L ours -L base -L theirs "$CURRENT" "$BASE" "$OTHER" >"$MERGED"
MF_RC=$?
set -e
if (( MF_RC < 0 || MF_RC > 127 )); then
    echo "merge-kb-counts: git merge-file failed ($MF_RC) for $PATHNAME" >&2
    exit 1   # no merge to hand back; %A stays ours and git flags the path
fi

# Fallback: if git didn't pass %P (older git), we don't know WHICH doc's blocks
# to regenerate → hand back the plain 3-way merge and signal a conflict.
if [[ -z "$PATHNAME" ]]; then
    surface_conflict "$MERGED"
fi

# 1. Render the MERGED content with the counts blocks regenerated from the tree.
#    Pure — nothing is written to the working tree. If python/the CLI is
#    unavailable, or the render fails, exit 1 (a REAL conflict, %A untouched):
#    the old fallback kept %A's stale counts and reported success, a silent
#    wrong answer. On a runner/clone WITHOUT the toolkit deps (noctusai_lib)
#    this is where it bites — install them (merge-queue.yml does).
if ! { command -v "$PY" >/dev/null 2>&1 || [[ -x "$PY" ]]; } || [[ ! -f "$CLI" ]]; then
    echo "merge-kb-counts: no usable python ($PY) or CLI ($CLI); cannot re-derive counts for $PATHNAME" >&2
    surface_conflict "$MERGED"
fi
if ! "$PY" "$CLI" --render-kb-counts "$PATHNAME" --source "$MERGED" \
        --out "$RENDERED" --worktree-path "$REPO_ROOT" >/dev/null 2>"$RENDERED.err"; then
    echo "merge-kb-counts: render of $PATHNAME failed (missing toolkit deps?); refusing to keep stale counts:" >&2
    tail -n 5 "$RENDERED.err" >&2 || true
    rm -f "$RENDERED.err"
    surface_conflict "$MERGED"
fi
rm -f "$RENDERED.err"

# 2. Decide: clean → resolved; markers remain → real (prose) conflict: hand git
#    the render WITH its markers (counts already regenerated) and flag it.
if has_markers "$RENDERED"; then
    surface_conflict "$RENDERED"
fi
cp "$RENDERED" "$CURRENT"     # hand the regenerated, conflict-free file back to git
exit 0
