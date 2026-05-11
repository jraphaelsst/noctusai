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
#   An agent worktree whose branch is either:
#     (a) reachable from `origin/main` by SHA ancestry (true merge), OR
#     (b) all commits already present on `origin/main` by PATCH-ID (cherry-pick).
#   The cherry-pick check is necessary because our orchestrator FFs branched
#   work to main via cherry-pick (new SHA, same patch). The plain ancestry
#   check would leak these branches forever — they accumulate as remote
#   detritus. `git cherry main <branch>` is the patch-id equivalent.
#   Unmerged work-in-progress worktrees are KEPT.
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

# Patch-id equivalence check: are all commits on $branch already on origin/main
# under different SHAs? Used to detect cherry-picked work, which plain
# `merge-base --is-ancestor` misses because cherry-pick rewrites SHAs.
#
# `git cherry origin/main <branch>` lists commits on $branch NOT on origin/main
# by patch-id. Output prefixes:
#   `+` = commit not on main (genuinely unmerged)
#   `-` = commit on main by patch-id (cherry-picked)
# Empty output OR only `-` lines = branch is fully on main by content.
_all_commits_cherry_picked_to_main() {
  local b="$1"
  local plus_lines
  plus_lines="$(git cherry origin/main "$b" 2>/dev/null | grep -c '^+' || true)"
  # The branch must have AT LEAST 1 commit and ZERO `+` lines.
  local total
  total="$(git log --oneline "origin/main..$b" 2>/dev/null | wc -l | tr -d ' ')"
  [ "$total" -gt 0 ] && [ "$plus_lines" = "0" ]
}

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
                   elif _all_commits_cherry_picked_to_main "$branch"; then
                     # Branch commits are already on main by patch-id (cherry-pick).
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

# Dedupe stale_paths. Portable for bash 3.x (macOS default) — `mapfile` is bash 4+.
# The `${arr[@]+"${arr[@]}"}` pattern handles empty arrays under `set -u`.
_dedup_paths=()
if [ "${#stale_paths[@]}" -gt 0 ]; then
  while IFS= read -r _p; do
    _dedup_paths+=("$_p")
  done < <(printf '%s\n' "${stale_paths[@]}" | awk '!seen[$0]++')
fi
stale_paths=("${_dedup_paths[@]+"${_dedup_paths[@]}"}")

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
locked_skipped=()
for wt in "${stale_paths[@]}"; do
  # Try git's safe removal (respects locks + uncommitted-work checks).
  if git worktree remove --force "$wt" 2>/dev/null; then
    removed=$((removed+1))
  else
    # 2026-05-11 incident: THE-P10 engineer's worktree was DESTROYED by an
    # earlier version of this script that fell back to `rm -rf "$wt"` when
    # `git worktree remove` refused due to a held lock. The lock meant
    # "active agent here"; the engineer was mid-verification and lost the
    # worktree filesystem (branch metadata intact, files gone).
    #
    # NEW CONTRACT: if git refuses to remove, we DO NOT bypass with rm -rf.
    # Locks exist for a reason. Surface the path as a manual-review finding
    # and let the user decide. Same shape as the mole's "resolve before
    # sweep" rule (KB § PATTERNS/storage-hygiene.md §2.3).
    #
    # For TRUE orphans (path exists but git doesn't know about it — caught
    # by the second loop at lines 80-86), `git worktree remove` will report
    # "is not a working tree" and we can safely rm -rf. But locks are NOT
    # orphans. Distinguish by re-asking git.
    if git worktree list --porcelain | grep -qF "worktree $wt"; then
      # Git knows about it → lock held or active. SKIP destructively; surface.
      locked_skipped+=("$wt")
      failed=$((failed+1))
    else
      # Git doesn't know about it → true orphan, safe to direct-rm.
      rm -rf "$wt" 2>/dev/null && removed=$((removed+1)) || failed=$((failed+1))
    fi
  fi
done

git worktree prune 2>/dev/null || true

echo "✓ Cleanup complete: $removed removed, $failed failed."
if [ "${#locked_skipped[@]+x}" = "x" ] && [ "${#locked_skipped[@]}" -gt 0 ]; then
  echo ""
  echo "─── SKIPPED (locked or active — NEVER auto-destroyed) ───"
  for wt in "${locked_skipped[@]}"; do
    echo "  • $wt"
  done
  echo ""
  echo "  These paths are git-registered worktrees whose lock was held"
  echo "  when removal was attempted. Lock = 'another process is using this'."
  echo "  DO NOT rm -rf manually — investigate first:"
  echo "    git worktree list --porcelain | grep -A 2 '<path>'   # see lock reason"
  echo "    lsof '<path>' 2>/dev/null                            # check for live PID"
  echo "    cd '<path>' && git status                            # check for uncommitted work"
  echo "  Only after verifying nothing is using it:"
  echo "    git worktree unlock '<path>' && git worktree remove '<path>'"
fi
