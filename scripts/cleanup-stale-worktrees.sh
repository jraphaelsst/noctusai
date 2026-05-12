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
#   - Refuses to remove worktrees with uncommitted files or stashes — surfaces
#     them as manual-review findings instead. `--force` does NOT override this
#     (THE-P10 lesson: --force only suppresses the interactive prompt, never
#     overrides safety gating).
#   - Always runs `git worktree prune` after to clean .git/worktrees/ metadata.
#
# Enumeration alignment with mole.sh
#   This script SHARES the classification predicate with `scripts/mole.sh`:
#   `mole.sh scan --worktrees` reports the same target set this script would
#   sweep. Both apply the same merge + on-disk + uncommitted/stash gating.
#   2026-05-11 incident: prior version targeted 122 worktrees while scan
#   reported 33 stale — gap was on-disk gating + uncommitted-work gating in
#   the scan that this script lacked. Now aligned.

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

# Snapshot main-repo stashes for shared-stash subtraction (THE-P11 fix).
# Linked worktrees share `refs/stash` with main; counting shared stashes
# against a linked worktree's WIP produces false positives. See mole.sh
# `_classify_worktrees` header for full incident note.
MAIN_STASHES_FILE="$(mktemp -t cleanup-main-stashes.XXXXXX)"
trap 'rm -f "$MAIN_STASHES_FILE"' EXIT
(cd "$REPO_ROOT" && git stash list --pretty='%H' 2>/dev/null | sort -u) > "$MAIN_STASHES_FILE"

stale_paths=()      # safe to auto-remove (merged + clean + on-disk or phantom)
active_paths=()     # branch unmerged — skip (work-in-progress)
dirty_paths=()     # branch merged BUT uncommitted/stashed — manual review
dirty_reasons=()
locked_paths=()    # branch merged + locked — manual review (THE-P10 protection)

# Helper: classify a single (wt, branch) pair and route into the right bucket.
# Mirrors mole.sh `_classify_emit_registered`. Keep predicates in sync.
_classify_one() {
  local wt="$1" branch="$2" locked="$3"
  # Main repo or sibling workspace: ignore.
  [ "$wt" = "$REPO_ROOT" ] && return 0
  case "$wt" in
    "$WORKTREE_DIR/agent-"*) ;;
    *) return 0 ;;
  esac

  # Merge predicate: ancestry OR patch-id equivalence.
  local merged=0
  if git merge-base --is-ancestor "$branch" origin/main 2>/dev/null; then
    merged=1
  elif _all_commits_cherry_picked_to_main "$branch"; then
    merged=1
  fi

  if [ "$merged" -ne 1 ]; then
    active_paths+=("$wt")
    return 0
  fi

  # Branch IS merged. If the on-disk dir is gone, it's a PHANTOM — safe to
  # remove (git worktree remove --force will clean metadata).
  if [ ! -d "$wt" ]; then
    stale_paths+=("$wt")
    return 0
  fi

  # On-disk + merged. Check uncommitted/stashed/locked.
  local dirty stashes
  dirty="$(cd "$wt" 2>/dev/null && git status --porcelain 2>/dev/null | wc -l | tr -d ' ' || echo "0")"
  # Unique-stash count: subtract main's shared stashes (THE-P11 fix).
  if [ -f "$MAIN_STASHES_FILE" ]; then
    stashes="$(cd "$wt" 2>/dev/null && git stash list --pretty='%H' 2>/dev/null | sort -u \
      | comm -23 - "$MAIN_STASHES_FILE" | grep -c . || echo "0")"
  else
    stashes="$(cd "$wt" 2>/dev/null && git stash list 2>/dev/null | wc -l | tr -d ' ' || echo "0")"
  fi

  if [ "$dirty" != "0" ]; then
    dirty_paths+=("$wt")
    dirty_reasons+=("$dirty uncommitted file(s) — INVESTIGATE before removing")
  elif [ "$stashes" != "0" ]; then
    dirty_paths+=("$wt")
    dirty_reasons+=("$stashes stash(es) — recover before removing")
  elif [ "$locked" -eq 1 ]; then
    locked_paths+=("$wt")
  else
    stale_paths+=("$wt")
  fi
}

# Iterate registered worktrees. `git worktree list --porcelain` emits a block
# per entry: `worktree <path>`, `HEAD <sha>`, `branch refs/heads/<name>`,
# optionally `locked [<reason>]`. Blocks separated by blank lines.
wt=""
branch=""
locked=0
while IFS= read -r line; do
  case "$line" in
    "worktree "*)
      # Flush previous block.
      if [ -n "$wt" ] && [ -n "$branch" ]; then
        _classify_one "$wt" "$branch" "$locked"
      fi
      wt="${line#worktree }"
      branch=""
      locked=0
      ;;
    "branch "*)
      branch="${line#branch refs/heads/}"
      ;;
    "locked"*)
      locked=1
      # Auto-unlock dead-pid locks (THE-P11 fix). A crashed Claude session
      # leaves stale "(pid N)" locks that block prune + remove forever.
      if [[ "$line" == *"(pid "* ]]; then
        _pid="${line##*(pid }"
        _pid="${_pid%)*}"
        if [ -n "$_pid" ] && ! kill -0 "$_pid" 2>/dev/null; then
          git worktree unlock "$wt" 2>/dev/null && locked=0
        fi
      fi
      ;;
    "")
      if [ -n "$wt" ] && [ -n "$branch" ]; then
        _classify_one "$wt" "$branch" "$locked"
        wt=""
        branch=""
        locked=0
      fi
      ;;
  esac
done < <(git worktree list --porcelain)
# Final flush.
if [ -n "$wt" ] && [ -n "$branch" ]; then
  _classify_one "$wt" "$branch" "$locked"
fi

# Also catch dangling agent-* directories (rm'd manually but git metadata still
# missing). An orphan = on-disk dir whose path is NOT in `git worktree list`.
#
# Pre-existing bug fixed 2026-05-11: the prior implementation used
#   `git worktree list --porcelain | grep -qF "worktree $d"`
# under `set -o pipefail`. `grep -q` short-circuits on first match (closes
# stdin); the upstream `git worktree list` then writes to a closed pipe,
# receives SIGPIPE (exit 141), and `pipefail` propagates that as failure —
# so `! cmd` evaluates TRUE even when the path WAS in the list. Result: 5
# registered worktrees were falsely classified as orphans and double-listed
# under stale + dirty. Fix: precompute the registered-paths set in a
# variable, then test membership via `case`/string-grep with no pipe.
_registered_paths_blob="$(git worktree list --porcelain | awk '/^worktree / { print $2 }')"
while IFS= read -r d; do
  [ -d "$d" ] || continue
  # Use newline-anchored search via parameter expansion + check whether
  # removing the exact match yields a different string. This avoids any pipe.
  case $'\n'"$_registered_paths_blob"$'\n' in
    *$'\n'"$d"$'\n'*) ;;     # registered — skip
    *) stale_paths+=("$d") ;; # genuine orphan
  esac
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
echo "  · main:                     $REPO_ROOT"
echo "  · active (unmerged, kept):  ${#active_paths[@]}"
echo "  · dirty (merged + work):    ${#dirty_paths[@]} (manual review)"
echo "  · locked (merged + lock):   ${#locked_paths[@]} (manual review)"
echo "  · stale (target):           ${#stale_paths[@]}"

# Surface dirty entries explicitly — never silent.
if [ "${#dirty_paths[@]}" -gt 0 ]; then
  echo ""
  echo "─── DIRTY merged worktrees (NOT auto-removed; uncommitted/stashed work) ───"
  i=0
  while [ "$i" -lt "${#dirty_paths[@]}" ]; do
    echo "  • ${dirty_paths[$i]}"
    echo "      ${dirty_reasons[$i]}"
    i=$((i+1))
  done
fi

# Surface locked entries explicitly.
if [ "${#locked_paths[@]}" -gt 0 ]; then
  echo ""
  echo "─── LOCKED merged worktrees (NOT auto-removed; lock held by another process) ───"
  for wt in "${locked_paths[@]}"; do
    echo "  • $wt  (run: git worktree unlock <path> && git worktree remove <path>)"
  done
fi

if [ "${#stale_paths[@]}" -eq 0 ]; then
  echo "✓ Nothing stale to auto-remove. Disk usage already minimal."
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
    #
    # Membership test via `case` on a newline-anchored blob — NOT `| grep -q`.
    # Under `set -o pipefail`, `grep -q` short-circuits on first match, the
    # upstream `git worktree list` gets SIGPIPE (exit 141), and pipefail
    # propagates 141 — the `if !` evaluates TRUE even when the path WAS
    # in the list. Same footgun M fixed in the orphan-detection loop above;
    # this is the second site (missed in 3868058, surfaced by Stage 4
    # `check_pipefail_grep_q` detector 2026-05-11).
    _registered_now="$(git worktree list --porcelain | awk '/^worktree / { print $2 }')"
    case $'\n'"$_registered_now"$'\n' in
      *$'\n'"$wt"$'\n'*)
        # Git knows about it → lock held or active. SKIP destructively; surface.
        locked_skipped+=("$wt")
        failed=$((failed+1))
        ;;
      *)
        # Git doesn't know about it → true orphan, safe to direct-rm.
        rm -rf "$wt" 2>/dev/null && removed=$((removed+1)) || failed=$((failed+1))
        ;;
    esac
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
