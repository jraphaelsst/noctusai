#!/usr/bin/env bash
# noc pre-push leg (agent-packages CONTRACT §F / A5): publish changed Agent Packages to Studio.
#
#   noc-pre-push-publish.sh <python> <repo_root>      # pre-push ref lines on stdin
#
# NO-OP (instant, no python spawned) unless a push to `dev` changed products/agents/packages/<key>/** (dist/
# excluded) in the pushed range, OR a previous run left `.agents-sync-pending` (retry). Runs
# agent_sync_runner.py publish, which does build -> import -> evals -> publish-if-gate-passes per key.
# NEVER blocks the push (always exit 0) and is never silent: failures are loud on stderr + the runner
# writes `.agents-sync-pending` in the PRIMARY checkout (so a retry from any worktree finds it).
# Only pushes to `refs/heads/dev` publish: a feature-branch push must not put unreviewed content into prod Studio.
ZERO_RE='^0+$'
PY="${1:-}"
ROOT="${2:-}"
[[ -n "$ROOT" ]] || { echo "[agents-publish] usage: noc-pre-push-publish.sh <python> <repo_root>" >&2; exit 0; }

PRIMARY="$(cd "$(git -C "$ROOT" rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd || echo "$ROOT")"
MARKER="$PRIMARY/.agents-sync-pending"

keys=""
while read -r l_ref l_oid r_ref r_oid; do
    [[ "${r_ref:-}" == "refs/heads/dev" ]] || continue
    [[ "${l_oid:-0}" =~ $ZERO_RE ]] && continue
    if [[ "${r_oid:-0}" =~ $ZERO_RE ]]; then
        base="$(git -C "$ROOT" merge-base "$l_oid" origin/dev 2>/dev/null || true)"
        [[ -n "$base" ]] || continue
        names="$(git -C "$ROOT" diff --name-only "$base" "$l_oid" -- products/agents/packages 2>/dev/null || true)"
    else
        names="$(git -C "$ROOT" diff --name-only "$r_oid" "$l_oid" -- products/agents/packages 2>/dev/null || true)"
    fi
    [[ -n "$names" ]] || continue
    keys+=$'\n'"$(printf '%s\n' "$names" | grep -E '^products/agents/packages/[^/]+/' | grep -vE '^products/agents/packages/[^/]+/dist/' | cut -d/ -f4 || true)"
done
keys="$(printf '%s\n' "$keys" | sed '/^$/d' | sort -u | paste -sd, - || true)"

if [[ -z "$keys" && ! -f "$MARKER" ]]; then
    exit 0   # fast no-op: nothing under packages changed, nothing pending
fi

echo "[agents-publish] packages to publish: ${keys:-<none — retrying pending marker>}" >&2
RUNNER="$ROOT/scripts/agent-hooks/agent_sync_runner.py"
if [[ -z "$PY" || ! -x "$PY" || ! -f "$RUNNER" ]]; then
    echo "" >&2
    echo "🔴 agents-publish: cannot run (no interpreter '$PY' or runner '$RUNNER') — push NOT blocked; will retry on the next push." >&2
    printf '{"keys":[%s],"failures":[{"step":"hook","errors":["interpreter or runner not found"]}]}\n' \
        "$(printf '%s' "$keys" | sed 's/[^,][^,]*/"&"/g')" > "$MARKER"
    exit 0
fi
"$PY" "$RUNNER" publish --repo-root "$ROOT" --keys "$keys" --marker-dir "$PRIMARY" || {
    echo "🔴 agents-publish: runner crashed (exit $?) — push NOT blocked; will retry on the next push." >&2
    printf '{"keys":[%s],"failures":[{"step":"hook","errors":["runner crashed"]}]}\n' \
        "$(printf '%s' "$keys" | sed 's/[^,][^,]*/"&"/g')" > "$MARKER"
}
exit 0
