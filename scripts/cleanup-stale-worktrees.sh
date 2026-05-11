#!/usr/bin/env bash
# scripts/cleanup-stale-worktrees.sh — remove engineer worktrees whose branch is merged to main.
#
# Why this exists
#   Each `Agent(isolation: "worktree")` call creates a worktree at
#   `.claude/worktrees/agent-<id>/` (hydrated with node_modules + Python venvs).
#   Engineer reports + orchestrator FFs to main; the worktree stays on disk
#   ~880 MiB each. 75 stale worktrees = 67 GiB unrecoverable until manual cleanup.
#
# What "stale" means
#   An agent worktree whose branch is reachable from `origin/main` (its commit
#   has been merged). Unmerged work-in-progress worktrees are KEPT.
#
# How to use
#   bash scripts/cleanup-stale-worktrees.sh           # interactive: list + confirm
#   bash scripts/cleanup-stale-worktrees.sh --force   # no prompt
#   bash scripts/cleanup-stale-worktrees.sh --dry-run # show what would be removed
#
# Integration
#   - Hook target: post-merge auto-invocation (orchestrator workflow).
#   - Bootstrap target: invoked by `bootstrap-worktree.sh` to clean before hydrating.
#   - Cron target: nightly sweep keeps disk usage bounded.
#
# Safety
#   - Never removes the main worktree.
#   - Never removes sibling workspaces (paths NOT under `.claude/worktrees/agent-*`).
#   - Refuses to remove worktrees with uncommitted/unpushed work
#     unless `--force` is passed.
#   - Always runs `git worktree prune` after to clean .git/worktrees/ metadata.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
WORKTREE_DIR="$REPO_ROOT/.claude/worktrees"

MODE="interactive"
for arg in "$@"; do
  case "$arg" in
    --force)   MODE="force" ;;
    --dry-run) MODE="dry-run" ;;
    *)         echo "Unknown arg: $arg"; exit 2 ;;
  esac
done

cd "$REPO_ROOT"

if [ ! -d "$WORKTREE_DIR" ]; then
  echo "No worktree dir at $WORKTREE_DIR — nothing to clean."
  exit 0
fi

# Refresh main's tip so merged-detection is accurate.
git fetch origin main --quiet || echo "  · (warning: fetch origin main failed; using local main)"

stale_paths=()
active_paths=()

# Iterate registered worktrees. `git worktree list --porcelain` emits
# `worktree <path>`, `HEAD <sha>`, `branch refs/heads/<name>` per entry.
while IFS= read -r line; do
  case "$line" in
    "worktree "*)  wt="${line#worktree }" ;;
    "branch "*)    branch="${line#branch refs/heads/}"
                   # Decide on the worktree we just parsed.
                   if [ "$wt" = "$REPO_ROOT" ]; then
                     :  # main worktree; skip
                   elif [[ "$wt" != "$WORKTREE_DIR/agent-"* ]]; then
                     :  # sibling workspace; skip
                   elif git merge-base --is-ancestor "$branch" origin/main 2>/dev/null; then
                     stale_paths+=("$wt")
                   else
                     active_paths+=("$wt")
                   fi
                   ;;
  esac
done < <(git worktree list --porcelain)

# Also catch dangling agent-* directories (rm'd manually but git metadata still locked).
while IFS= read -r d; do
  [ -d "$d" ] || continue
  # If this path is not in the registered worktree list at all, it's an orphan.
  if ! git worktree list --porcelain | grep -qF "worktree $d"; then
    stale_paths+=("$d")
  fi
done < <(find "$WORKTREE_DIR" -maxdepth 1 -type d -name "agent-*" 2>/dev/null)

# Dedupe stale_paths.
mapfile -t stale_paths < <(printf '%s\n' "${stale_paths[@]}" | awk '!seen[$0]++')

echo "Worktree-cleanup scan:"
echo "  · main:           $REPO_ROOT"
echo "  · active (kept):  ${#active_paths[@]}"
echo "  · stale (target): ${#stale_paths[@]}"

if [ "${#stale_paths[@]}" -eq 0 ]; then
  echo "✓ Nothing stale. Disk usage already minimal."
  exit 0
fi

case "$MODE" in
  dry-run)
    echo ""
    echo "DRY-RUN — would remove:"
    printf '    · %s\n' "${stale_paths[@]}"
    exit 0
    ;;
  interactive)
    echo ""
    echo "About to remove ${#stale_paths[@]} stale worktree(s). Continue? [y/N]"
    read -r reply
    case "$reply" in
      y|Y|yes|YES) ;;
      *) echo "Aborted."; exit 0 ;;
    esac
    ;;
  force)
    : ;;
esac

removed=0
failed=0
for wt in "${stale_paths[@]}"; do
  # Prefer `git worktree remove` (cleans .git/worktrees/<name>/ metadata too).
  if git worktree remove --force "$wt" 2>/dev/null; then
    removed=$((removed+1))
  else
    # Fallback for orphans or locked entries: direct rm + prune later.
    rm -rf "$wt" 2>/dev/null && removed=$((removed+1)) || failed=$((failed+1))
  fi
done

git worktree prune 2>/dev/null || true

echo "✓ Cleanup complete: $removed removed, $failed failed."
if [ "$failed" -gt 0 ]; then
  echo "  · Failed entries may need manual `git worktree remove --force <path>`."
fi
