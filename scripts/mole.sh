#!/usr/bin/env bash
# scripts/mole.sh — storage-hygiene orchestrator (the third agent: keeper / hound / mole).
#
# What this is
#   Active patrol of filesystem looking for safe storage optimizations.
#   Three orthogonal scopes:
#     - artifacts   : regenerable caches/builds (__pycache__, .pytest_cache, dist, etc.)
#     - environments: venv + node_modules duplication (advisory-only)
#     - worktrees   : stale .claude/worktrees/agent-*/ (delegates to cleanup-stale-worktrees.sh)
#
# Usage
#   bash scripts/mole.sh scan                  # all scopes, read-only
#   bash scripts/mole.sh scan --artifacts      # one scope
#   bash scripts/mole.sh scan --environments
#   bash scripts/mole.sh scan --worktrees
#   bash scripts/mole.sh sweep                 # dry-run; add --force to act
#   bash scripts/mole.sh sweep --artifacts --force
#   bash scripts/mole.sh sweep --worktrees --force
#   bash scripts/mole.sh report                # machine-readable JSON-ish
#
# See KB § PATTERNS/storage-hygiene.md for the full methodology + design.
#
# Bash 3.x compatible (macOS default ships 3.2.57).

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
[ -z "$REPO_ROOT" ] && { echo "ERR: not inside a git repo" >&2; exit 2; }
cd "$REPO_ROOT"

WORKTREE_DIR="$REPO_ROOT/.claude/worktrees"
LOG_FILE="$REPO_ROOT/scripts/mole-last-sweep.log"

# Severity thresholds (mirrors disk-usage-monitor.sh exit-code semantics).
ARTIFACT_WARNING_MB=2048    # 2 GB
ARTIFACT_CRITICAL_MB=5120   # 5 GB
WORKTREE_WARNING_COUNT=15
WORKTREE_CRITICAL_COUNT=30

# Patterns the artifact-scope matches (the deny-list of safe-to-wipe dirs).
# Order: most-specific first. Each entry is a directory name.
ARTIFACT_DIR_NAMES=(
  "__pycache__"
  ".pytest_cache"
  ".ruff_cache"
  ".mypy_cache"
  ".tsbuildinfo"
  "coverage"
)
# Frontend build outputs — only safe under products/*/frontend/, not at repo root.
ARTIFACT_FRONTEND_BUILD_NAMES=("dist" "build" ".next")

# Mode + scope parsing.
MODE="${1:-scan}"
shift || true
SCOPE_ARTIFACTS=0
SCOPE_ENVIRONMENTS=0
SCOPE_WORKTREES=0
FORCE=0
DRY_RUN=1
for arg in "$@"; do
  case "$arg" in
    --artifacts)    SCOPE_ARTIFACTS=1 ;;
    --environments) SCOPE_ENVIRONMENTS=1 ;;
    --worktrees)    SCOPE_WORKTREES=1 ;;
    --force)        FORCE=1; DRY_RUN=0 ;;
    --dry-run)      DRY_RUN=1; FORCE=0 ;;
    -h|--help)      sed -n '2,30p' "$0"; exit 0 ;;
    *)              echo "ERR: unknown arg: $arg" >&2; exit 2 ;;
  esac
done
# If no scope flag given, all three are active (default).
if [ "$SCOPE_ARTIFACTS" -eq 0 ] && [ "$SCOPE_ENVIRONMENTS" -eq 0 ] && [ "$SCOPE_WORKTREES" -eq 0 ]; then
  SCOPE_ARTIFACTS=1
  SCOPE_ENVIRONMENTS=1
  SCOPE_WORKTREES=1
fi

# =========================
# scan_artifacts
# =========================
# Outputs: total size in MB (via stdout, single line), and prints per-pattern subtotal to stderr.
scan_artifacts() {
  echo "─── ARTIFACTS scope ───" >&2
  local total_kb=0
  local count=0
  local name path size_kb
  for name in "${ARTIFACT_DIR_NAMES[@]}"; do
    # Exclude worktrees + venv-internal pycache (those are package-internal, regenerated on import).
    while IFS= read -r path; do
      [ -z "$path" ] && continue
      size_kb=$(du -sk "$path" 2>/dev/null | awk '{print $1}')
      [ -z "$size_kb" ] && continue
      total_kb=$((total_kb + size_kb))
      count=$((count + 1))
    done < <(find . \
      -path ./.claude/worktrees -prune -o \
      -path './*/.venv' -prune -o \
      -path './*/*/.venv' -prune -o \
      -path './venv' -prune -o \
      -path './node_modules' -prune -o \
      -name "$name" -type d -print 2>/dev/null)
  done
  # Frontend build outputs — restrict to products/*/frontend/ only.
  for name in "${ARTIFACT_FRONTEND_BUILD_NAMES[@]}"; do
    while IFS= read -r path; do
      [ -z "$path" ] && continue
      size_kb=$(du -sk "$path" 2>/dev/null | awk '{print $1}')
      [ -z "$size_kb" ] && continue
      total_kb=$((total_kb + size_kb))
      count=$((count + 1))
    done < <(find ./products -maxdepth 4 -type d -name "$name" 2>/dev/null \
      | grep '/frontend/' \
      | grep -v '/node_modules/')
  done
  local total_mb=$((total_kb / 1024))
  echo "  count: $count dirs   total: ${total_mb} MB" >&2
  echo "$total_mb"
}

# =========================
# sweep_artifacts
# =========================
sweep_artifacts() {
  echo "─── SWEEP artifacts (dry-run=$DRY_RUN) ───" >&2
  local removed_kb=0
  local removed_count=0
  local name path size_kb
  for name in "${ARTIFACT_DIR_NAMES[@]}"; do
    while IFS= read -r path; do
      [ -z "$path" ] && continue
      size_kb=$(du -sk "$path" 2>/dev/null | awk '{print $1}')
      [ -z "$size_kb" ] && continue
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "  [dry-run] would remove: $path (${size_kb} KB)" >&2
      else
        if rm -rf "$path" 2>/dev/null; then
          removed_kb=$((removed_kb + size_kb))
          removed_count=$((removed_count + 1))
        fi
      fi
    done < <(find . \
      -path ./.claude/worktrees -prune -o \
      -path './*/.venv' -prune -o \
      -path './*/*/.venv' -prune -o \
      -path './venv' -prune -o \
      -path './node_modules' -prune -o \
      -name "$name" -type d -print 2>/dev/null)
  done
  for name in "${ARTIFACT_FRONTEND_BUILD_NAMES[@]}"; do
    while IFS= read -r path; do
      [ -z "$path" ] && continue
      size_kb=$(du -sk "$path" 2>/dev/null | awk '{print $1}')
      [ -z "$size_kb" ] && continue
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "  [dry-run] would remove: $path (${size_kb} KB)" >&2
      else
        if rm -rf "$path" 2>/dev/null; then
          removed_kb=$((removed_kb + size_kb))
          removed_count=$((removed_count + 1))
        fi
      fi
    done < <(find ./products -maxdepth 4 -type d -name "$name" 2>/dev/null \
      | grep '/frontend/' \
      | grep -v '/node_modules/')
  done
  if [ "$DRY_RUN" -eq 0 ]; then
    echo "  removed: $removed_count dirs / $((removed_kb / 1024)) MB" >&2
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') artifacts: $removed_count dirs / $((removed_kb / 1024)) MB" >> "$LOG_FILE"
  fi
}

# =========================
# scan_environments (advisory-only)
# =========================
scan_environments() {
  echo "─── ENVIRONMENTS scope (advisory-only) ───" >&2
  local total_kb=0
  local count=0
  local path size_kb
  # Venvs.
  while IFS= read -r path; do
    [ -z "$path" ] && continue
    size_kb=$(du -sk "$path" 2>/dev/null | awk '{print $1}')
    [ -z "$size_kb" ] && continue
    total_kb=$((total_kb + size_kb))
    count=$((count + 1))
    echo "  $path  (${size_kb} KB)" >&2
  done < <(find . \
    -path ./.claude/worktrees -prune -o \
    -type d \( -name '.venv' -o -name 'venv' \) -print 2>/dev/null \
    | head -50)
  # node_modules at top-of-product level (1 per product, not nested).
  while IFS= read -r path; do
    [ -z "$path" ] && continue
    size_kb=$(du -sk "$path" 2>/dev/null | awk '{print $1}')
    [ -z "$size_kb" ] && continue
    total_kb=$((total_kb + size_kb))
    count=$((count + 1))
    echo "  $path  (${size_kb} KB)" >&2
  done < <(find ./products ./seed -maxdepth 4 -type d -name 'node_modules' 2>/dev/null \
    | grep -v '/node_modules/' | head -50)
  local total_mb=$((total_kb / 1024))
  echo "  count: $count   total: ${total_mb} MB   (advisory — NOT auto-swept)" >&2
  echo "$total_mb"
}

# =========================
# scan_worktrees + sweep_worktrees (delegates to cleanup-stale-worktrees.sh)
# =========================
scan_worktrees() {
  echo "─── WORKTREES scope ───" >&2
  if [ ! -d "$WORKTREE_DIR" ]; then
    echo "  (no worktree dir at $WORKTREE_DIR)" >&2
    echo "0"
    return 0
  fi
  local count
  count=$(find "$WORKTREE_DIR" -maxdepth 1 -type d -name 'agent-*' 2>/dev/null | wc -l | tr -d ' ')
  local total_kb
  total_kb=$(du -sk "$WORKTREE_DIR" 2>/dev/null | awk '{print $1}')
  [ -z "$total_kb" ] && total_kb=0
  local total_mb=$((total_kb / 1024))
  echo "  count: $count worktrees   total: ${total_mb} MB" >&2
  echo "$count"
}

sweep_worktrees() {
  echo "─── SWEEP worktrees (dry-run=$DRY_RUN) ───" >&2
  if [ ! -x "$REPO_ROOT/scripts/cleanup-stale-worktrees.sh" ]; then
    echo "  ERR: cleanup-stale-worktrees.sh not found or not executable" >&2
    return 1
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    bash "$REPO_ROOT/scripts/cleanup-stale-worktrees.sh" --dry-run
  else
    bash "$REPO_ROOT/scripts/cleanup-stale-worktrees.sh" --force
    # Surface locked-stale worktrees as UNRESOLVED findings — never auto-destroy.
    _report_unresolved_locked_stale
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') worktrees: cleanup invoked" >> "$LOG_FILE"
  fi
}

# "Resolve before sweep" — surface locked-stale worktrees for human review.
# A locked worktree means: another process holds the lock (agent harness, stale lock, etc.).
# Force-removing a lock could destroy uncommitted work / stashes / inflight artifacts.
# The mole's contract: report what NEEDS resolution; user decides whether to act.
_report_unresolved_locked_stale() {
  git fetch origin main --quiet 2>/dev/null || true
  local wt branch in_main empty_lines
  local -a unresolved_paths=()
  local -a unresolved_reasons=()
  while IFS= read -r entry; do
    case "$entry" in
      "worktree "*)   wt="${entry#worktree }" ;;
      "branch "*)
        branch="${entry#branch refs/heads/}"
        # Only consider .claude/worktrees/agent-* paths.
        case "$wt" in "$WORKTREE_DIR/agent-"*) ;; *) continue ;; esac
        # Skip if the worktree path no longer exists (already cleaned by Phase 1).
        [ -d "$wt" ] || continue
        # Check if branch is on main by ancestry OR patch-id.
        if git merge-base --is-ancestor "$branch" origin/main 2>/dev/null; then
          in_main=1
        else
          empty_lines=$(git cherry origin/main "$branch" 2>/dev/null | grep -c '^+' || true)
          local total
          total=$(git log --oneline "origin/main..$branch" 2>/dev/null | wc -l | tr -d ' ')
          if [ "$total" -gt 0 ] && [ "$empty_lines" = "0" ]; then
            in_main=1
          else
            in_main=0
          fi
        fi
        # Only surface if branch IS merged (otherwise it's active work — leave alone, NOT a finding).
        [ "$in_main" -ne 1 ] && continue
        # Branch IS merged but worktree retained. Diagnose WHY.
        local dirty stashes reason
        dirty=$(cd "$wt" 2>/dev/null && git status --porcelain 2>/dev/null | wc -l | tr -d ' ' || echo "?")
        stashes=$(cd "$wt" 2>/dev/null && git stash list 2>/dev/null | wc -l | tr -d ' ' || echo "?")
        if [ "$dirty" != "0" ] && [ "$dirty" != "?" ]; then
          reason="$dirty uncommitted file(s) — INVESTIGATE before removing"
        elif [ "$stashes" != "0" ] && [ "$stashes" != "?" ]; then
          reason="$stashes stash(es) — recover before removing"
        else
          reason="locked (clean dir) — safe to unlock+remove after PID check"
        fi
        unresolved_paths+=("$wt")
        unresolved_reasons+=("$reason")
        ;;
    esac
  done < <(git worktree list --porcelain)
  if [ "${#unresolved_paths[@]+x}" = "x" ] && [ "${#unresolved_paths[@]}" -gt 0 ]; then
    echo "" >&2
    echo "─── UNRESOLVED locked-stale worktrees (manual review required) ───" >&2
    echo "  Branch IS merged to main but worktree retained (lock held by another process)." >&2
    echo "  The mole NEVER auto-destroys locked dirs — uncommitted work could be lost." >&2
    echo "" >&2
    local i=0
    while [ "$i" -lt "${#unresolved_paths[@]}" ]; do
      echo "  • ${unresolved_paths[$i]}" >&2
      echo "      ${unresolved_reasons[$i]}" >&2
      i=$((i+1))
    done
    echo "" >&2
    echo "  Resolution recipes:" >&2
    echo "    Clean dir (just locked):" >&2
    echo "      git worktree unlock <path> && git worktree remove <path>" >&2
    echo "    Uncommitted work present:" >&2
    echo "      cd <path> && git status               # inspect what's there" >&2
    echo "      cd <path> && git stash push -u -m wip # if recoverable" >&2
    echo "      git worktree unlock <path> && git worktree remove <path>" >&2
    echo "    Stashes present:" >&2
    echo "      cd <path> && git stash list           # check what's stashed" >&2
    echo "      cd <path> && git stash pop / apply    # recover what you need" >&2
    echo "      git worktree unlock <path> && git worktree remove <path>" >&2
  fi
  git worktree prune 2>/dev/null || true
}

# =========================
# Severity grading
# =========================
grade_severity() {
  local artifacts_mb="$1"
  local worktree_count="$2"
  local sev="OK"
  if [ "$artifacts_mb" -ge "$ARTIFACT_CRITICAL_MB" ] || [ "$worktree_count" -ge "$WORKTREE_CRITICAL_COUNT" ]; then
    sev="CRITICAL"
  elif [ "$artifacts_mb" -ge "$ARTIFACT_WARNING_MB" ] || [ "$worktree_count" -ge "$WORKTREE_WARNING_COUNT" ]; then
    sev="WARNING"
  fi
  echo "$sev"
}

next_action() {
  local artifacts_mb="$1"
  local worktree_count="$2"
  local envs_mb="$3"
  # Highest-leverage scope wins.
  if [ "$worktree_count" -ge "$WORKTREE_CRITICAL_COUNT" ]; then
    echo "worktrees: $worktree_count stale → bash scripts/mole.sh sweep --worktrees --force"
  elif [ "$artifacts_mb" -ge "$ARTIFACT_CRITICAL_MB" ]; then
    echo "artifacts: ${artifacts_mb} MB → bash scripts/mole.sh sweep --artifacts --force"
  elif [ "$worktree_count" -ge "$WORKTREE_WARNING_COUNT" ]; then
    echo "worktrees: $worktree_count stale → bash scripts/mole.sh sweep --worktrees --force"
  elif [ "$artifacts_mb" -ge "$ARTIFACT_WARNING_MB" ]; then
    echo "artifacts: ${artifacts_mb} MB → bash scripts/mole.sh sweep --artifacts"
  elif [ "$envs_mb" -gt 3000 ]; then
    echo "environments: ${envs_mb} MB (advisory — pnpm-workspace candidate; see KB § PATTERNS/storage-hygiene.md §2.2)"
  else
    echo "ok — nothing to do"
  fi
}

# =========================
# Main dispatch
# =========================
case "$MODE" in
  scan|report)
    artifacts_mb=0
    envs_mb=0
    worktree_count=0
    [ "$SCOPE_ARTIFACTS"    -eq 1 ] && artifacts_mb=$(scan_artifacts)
    [ "$SCOPE_ENVIRONMENTS" -eq 1 ] && envs_mb=$(scan_environments)
    [ "$SCOPE_WORKTREES"    -eq 1 ] && worktree_count=$(scan_worktrees)
    sev=$(grade_severity "$artifacts_mb" "$worktree_count")
    na=$(next_action "$artifacts_mb" "$worktree_count" "$envs_mb")
    if [ "$MODE" = "report" ]; then
      # Machine-readable line; JSON-ish (single-line).
      printf '{"severity":"%s","artifacts_mb":%d,"environments_mb":%d,"worktrees_stale":%d,"next_action":"%s"}\n' \
        "$sev" "$artifacts_mb" "$envs_mb" "$worktree_count" "$na"
    else
      echo "" >&2
      echo "═══ MOLE SUMMARY ═══" >&2
      echo "  severity:       $sev" >&2
      echo "  artifacts:      ${artifacts_mb} MB" >&2
      echo "  environments:   ${envs_mb} MB  (advisory-only)" >&2
      echo "  worktrees:      $worktree_count stale" >&2
      echo "  next_action:    $na" >&2
    fi
    ;;
  sweep)
    [ "$SCOPE_ARTIFACTS" -eq 1 ] && sweep_artifacts
    [ "$SCOPE_ENVIRONMENTS" -eq 1 ] && echo "  environments: NEVER auto-swept (see KB § PATTERNS/storage-hygiene.md §3.2)" >&2
    [ "$SCOPE_WORKTREES" -eq 1 ] && sweep_worktrees
    ;;
  *)
    echo "ERR: unknown mode: $MODE (use: scan | sweep | report)" >&2
    exit 2
    ;;
esac
