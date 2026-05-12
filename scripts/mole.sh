#!/usr/bin/env bash
# scripts/mole.sh — storage-hygiene orchestrator (the third agent: keeper / hound / mole).
#
# What this is
#   Active patrol of filesystem looking for safe storage optimizations.
#   Three orthogonal scopes:
#     - artifacts   : regenerable caches/builds (__pycache__, .pytest_cache, dist, etc.)
#     - environments: venv + node_modules duplication (advisory-only)
#     - worktrees   : stale .claude/worktrees/agent-*/ — scan + sweep share ONE
#                     classifier (_classify_worktrees) emitting categorized TSV
#                     records; counts are parity-guaranteed by construction.
#                     scripts/cleanup-stale-worktrees.sh shares the same predicate.
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
# Worktree classification — SINGLE SOURCE OF TRUTH used by both scan + sweep.
# =========================
#
# Why this exists
#   The 2026-05-11 enumeration-mismatch incident: scan_worktrees counted only
#   on-disk agent-* dirs (33), sweep_worktrees delegated to a script that
#   targeted registered-merged-branch worktrees INCLUDING phantom registry
#   entries with no on-disk dir (122). User couldn't trust either number.
#
#   Fix: one classifier — `_classify_worktrees` — emits TSV records that BOTH
#   scan and sweep consume. Counts are guaranteed parity by construction.
#
# Categories (the only authoritative taxonomy)
#   STALE          — agent-* worktree, on-disk, registered, branch merged
#                    (or cherry-picked) to origin/main, removable by
#                    `git worktree remove`. SWEEP TARGET.
#   STALE_LOCKED   — same as STALE but git refuses removal due to lock.
#                    Surface as manual-review finding; NEVER auto-destroy.
#   STALE_DIRTY    — STALE branch but uncommitted files / stashes present.
#                    Surface for human review; NEVER auto-destroy.
#   ACTIVE         — agent-* worktree, registered, branch NOT merged.
#                    Work-in-progress. SKIP (not a finding).
#   ORPHAN         — on-disk agent-* dir NOT registered with git.
#                    Safe to `rm -rf`. SWEEP TARGET.
#   PHANTOM        — registered agent-* worktree path with NO on-disk dir.
#                    `.git/worktrees/<id>/` metadata leak; clear via
#                    `git worktree prune` or `git worktree remove`. SWEEP TARGET.
#
# Output format (TSV, one record per line, written to $1 = tempfile path)
#   <category>\t<path>\t<branch>\t<reason>
#
# Bash 3.x compatible — no associative arrays, no mapfile.
_classify_worktrees() {
  local outfile="$1"
  : >"$outfile"  # truncate

  # Refresh origin/main once for accurate merge detection.
  git fetch origin main --quiet 2>/dev/null || true

  local wt="" branch="" locked=0
  local seen_paths_file
  seen_paths_file="$(mktemp -t mole-seen.XXXXXX)"
  : >"$seen_paths_file"

  # Pass 1: walk registered worktrees and classify each agent-* entry.
  while IFS= read -r line; do
    case "$line" in
      "worktree "*)
        # Flush previous record (handles last entry without trailing blank line).
        if [ -n "$wt" ] && [ -n "$branch" ]; then
          _classify_emit_registered "$wt" "$branch" "$locked" "$outfile" "$seen_paths_file"
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
        ;;
      "")
        if [ -n "$wt" ] && [ -n "$branch" ]; then
          _classify_emit_registered "$wt" "$branch" "$locked" "$outfile" "$seen_paths_file"
          wt=""
          branch=""
          locked=0
        fi
        ;;
    esac
  done < <(git worktree list --porcelain)
  # Final flush.
  if [ -n "$wt" ] && [ -n "$branch" ]; then
    _classify_emit_registered "$wt" "$branch" "$locked" "$outfile" "$seen_paths_file"
  fi

  # Pass 2: walk on-disk agent-* dirs and classify ones not in the seen set
  # as ORPHAN.
  if [ -d "$WORKTREE_DIR" ]; then
    local d
    while IFS= read -r d; do
      [ -z "$d" ] && continue
      # Normalize to absolute path (find already gives absolute since WORKTREE_DIR is).
      if ! grep -qxF "$d" "$seen_paths_file"; then
        printf 'ORPHAN\t%s\t-\ton-disk but not git-registered (safe to rm -rf)\n' "$d" >>"$outfile"
      fi
    done < <(find "$WORKTREE_DIR" -maxdepth 1 -type d -name 'agent-*' 2>/dev/null)
  fi

  rm -f "$seen_paths_file"
}

# Helper: classify ONE registered worktree entry. Writes one TSV line to
# $outfile, records the path in $seen_paths_file. Filters non-agent-* paths
# (main repo, sibling workspaces) silently.
_classify_emit_registered() {
  local wt="$1" branch="$2" locked="$3" outfile="$4" seen_file="$5"

  # Filter: only agent-* worktrees under WORKTREE_DIR. Non-agent paths
  # (the main repo, sibling workspaces) are ignored entirely — neither
  # classified nor recorded in seen (so they can't be mis-classified
  # as ORPHAN in Pass 2 either — Pass 2's `find` is already scoped to
  # WORKTREE_DIR/agent-*).
  case "$wt" in
    "$WORKTREE_DIR/agent-"*) ;;
    *) return 0 ;;
  esac

  # Always record we've seen this path BEFORE the self-skip below — Pass 2
  # walks on-disk dirs and would otherwise mis-flag the engineer's OWN
  # worktree as ORPHAN when mole.sh runs from inside an agent-* worktree.
  printf '%s\n' "$wt" >>"$seen_file"

  # Skip classifying the worktree we're running from — that's the
  # script's own working tree (REPO_ROOT may equal an agent worktree
  # when invoked from inside one). Mirrors cleanup-stale-worktrees.sh
  # which also excludes "$REPO_ROOT".
  [ "$wt" = "$REPO_ROOT" ] && return 0

  # Merge check: ancestry OR patch-id equivalence. Do this BEFORE on-disk check
  # so a phantom (no on-disk dir) with UNMERGED branch is correctly classified
  # as ACTIVE (work-in-progress, branch metadata still valuable) rather than
  # PHANTOM (silently sweep-eligible). The cleanup-stale-worktrees.sh script
  # mirrors this ordering — keep them in sync.
  local merged=0
  if git merge-base --is-ancestor "$branch" origin/main 2>/dev/null; then
    merged=1
  else
    local plus_lines total
    plus_lines="$(git cherry origin/main "$branch" 2>/dev/null | grep -c '^+' || true)"
    total="$(git log --oneline "origin/main..$branch" 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$total" -gt 0 ] && [ "$plus_lines" = "0" ]; then
      merged=1
    fi
  fi

  if [ "$merged" -ne 1 ]; then
    printf 'ACTIVE\t%s\t%s\tbranch has unmerged commits (work-in-progress)\n' \
      "$wt" "$branch" >>"$outfile"
    return 0
  fi

  # On-disk check (after merge check — we only PHANTOM-classify merged ones).
  if [ ! -d "$wt" ]; then
    printf 'PHANTOM\t%s\t%s\tregistered + merged but on-disk dir missing (safe to remove)\n' \
      "$wt" "$branch" >>"$outfile"
    return 0
  fi

  # Branch is merged. Check for uncommitted / stashes / lock.
  local dirty stashes
  dirty="$(cd "$wt" 2>/dev/null && git status --porcelain 2>/dev/null | wc -l | tr -d ' ' || echo "0")"
  stashes="$(cd "$wt" 2>/dev/null && git stash list 2>/dev/null | wc -l | tr -d ' ' || echo "0")"

  if [ "$dirty" != "0" ]; then
    printf 'STALE_DIRTY\t%s\t%s\t%s uncommitted file(s) — INVESTIGATE before removing\n' \
      "$wt" "$branch" "$dirty" >>"$outfile"
  elif [ "$stashes" != "0" ]; then
    printf 'STALE_DIRTY\t%s\t%s\t%s stash(es) — recover before removing\n' \
      "$wt" "$branch" "$stashes" >>"$outfile"
  elif [ "$locked" -eq 1 ]; then
    printf 'STALE_LOCKED\t%s\t%s\tlocked (clean dir) — safe to unlock+remove after PID check\n' \
      "$wt" "$branch" >>"$outfile"
  else
    printf 'STALE\t%s\t%s\tbranch merged to origin/main; safe to remove\n' \
      "$wt" "$branch" >>"$outfile"
  fi
}

# =========================
# scan_worktrees + sweep_worktrees — driven by the shared classifier.
# =========================
scan_worktrees() {
  echo "─── WORKTREES scope ───" >&2
  if [ ! -d "$WORKTREE_DIR" ]; then
    echo "  (no worktree dir at $WORKTREE_DIR)" >&2
    echo "0"
    return 0
  fi

  local classfile
  classfile="$(mktemp -t mole-classify.XXXXXX)"
  _classify_worktrees "$classfile"

  # Tally by category (bash 3.x — no associative arrays).
  local n_stale n_locked n_dirty n_active n_orphan n_phantom n_total
  n_stale=$(grep -c '^STALE\b'        "$classfile" 2>/dev/null || echo 0)
  n_stale=$(echo "$n_stale" | head -1 | tr -d ' \n')
  [ -z "$n_stale" ] && n_stale=0
  n_locked=$(grep -c '^STALE_LOCKED'  "$classfile" 2>/dev/null || echo 0)
  n_locked=$(echo "$n_locked" | head -1 | tr -d ' \n')
  [ -z "$n_locked" ] && n_locked=0
  n_dirty=$(grep -c '^STALE_DIRTY'    "$classfile" 2>/dev/null || echo 0)
  n_dirty=$(echo "$n_dirty" | head -1 | tr -d ' \n')
  [ -z "$n_dirty" ] && n_dirty=0
  n_active=$(grep -c '^ACTIVE'        "$classfile" 2>/dev/null || echo 0)
  n_active=$(echo "$n_active" | head -1 | tr -d ' \n')
  [ -z "$n_active" ] && n_active=0
  n_orphan=$(grep -c '^ORPHAN'        "$classfile" 2>/dev/null || echo 0)
  n_orphan=$(echo "$n_orphan" | head -1 | tr -d ' \n')
  [ -z "$n_orphan" ] && n_orphan=0
  n_phantom=$(grep -c '^PHANTOM'      "$classfile" 2>/dev/null || echo 0)
  n_phantom=$(echo "$n_phantom" | head -1 | tr -d ' \n')
  [ -z "$n_phantom" ] && n_phantom=0
  n_total=$((n_stale + n_locked + n_dirty + n_active + n_orphan + n_phantom))

  local on_disk_count
  on_disk_count=$(find "$WORKTREE_DIR" -maxdepth 1 -type d -name 'agent-*' 2>/dev/null | wc -l | tr -d ' ')
  local total_kb total_mb
  total_kb=$(du -sk "$WORKTREE_DIR" 2>/dev/null | awk '{print $1}')
  [ -z "$total_kb" ] && total_kb=0
  total_mb=$((total_kb / 1024))

  # Per-category breakdown (always shown so user sees WHY non-stale entries
  # weren't swept).
  echo "  on-disk dirs:   $on_disk_count   total: ${total_mb} MB" >&2
  echo "  classified:     $n_total" >&2
  echo "    STALE         $n_stale (safe to sweep)" >&2
  echo "    STALE_LOCKED  $n_locked (locked — manual review)" >&2
  echo "    STALE_DIRTY   $n_dirty (uncommitted/stashes — manual review)" >&2
  echo "    ACTIVE        $n_active (unmerged branch — work-in-progress, skipped)" >&2
  echo "    ORPHAN        $n_orphan (on-disk, unregistered — safe to sweep)" >&2
  echo "    PHANTOM       $n_phantom (registered, no on-disk dir — metadata leak)" >&2

  # Surface non-sweepable entries explicitly so they don't go silent.
  _print_category_entries "$classfile" "STALE_LOCKED"   "─── LOCKED stale (manual review) ───"
  _print_category_entries "$classfile" "STALE_DIRTY"    "─── DIRTY stale (manual review — uncommitted work) ───"
  _print_category_entries "$classfile" "ACTIVE"         "─── ACTIVE (unmerged work — skipped, NOT a finding) ───"

  rm -f "$classfile"

  # Return value to next_action / severity grading: the actionable count
  # (STALE + ORPHAN + PHANTOM). Locked/dirty/active are NOT actionable by
  # automated sweep — they need human attention.
  local actionable=$((n_stale + n_orphan + n_phantom))
  echo "$actionable"
}

# Helper: print all entries of a given category. No-op when zero.
_print_category_entries() {
  local classfile="$1" category="$2" header="$3"
  if grep -q "^${category}	" "$classfile" 2>/dev/null; then
    echo "" >&2
    echo "$header" >&2
    while IFS=$'\t' read -r cat path branch reason; do
      [ "$cat" != "$category" ] && continue
      echo "  • $path" >&2
      echo "      branch: $branch" >&2
      echo "      $reason" >&2
    done <"$classfile"
  fi
}

sweep_worktrees() {
  echo "─── SWEEP worktrees (dry-run=$DRY_RUN) ───" >&2

  local classfile
  classfile="$(mktemp -t mole-classify.XXXXXX)"
  _classify_worktrees "$classfile"

  # Target set = STALE + ORPHAN + PHANTOM. Never STALE_LOCKED / STALE_DIRTY / ACTIVE.
  local n_target n_skipped
  n_target=$(grep -cE '^(STALE|ORPHAN|PHANTOM)	' "$classfile" 2>/dev/null || echo 0)
  n_target=$(echo "$n_target" | head -1 | tr -d ' \n')
  [ -z "$n_target" ] && n_target=0
  n_skipped=$(grep -cE '^(STALE_LOCKED|STALE_DIRTY|ACTIVE)	' "$classfile" 2>/dev/null || echo 0)
  n_skipped=$(echo "$n_skipped" | head -1 | tr -d ' \n')
  [ -z "$n_skipped" ] && n_skipped=0

  echo "  target:       $n_target (STALE + ORPHAN + PHANTOM)" >&2
  echo "  skipped:      $n_skipped (LOCKED + DIRTY + ACTIVE)" >&2

  if [ "$n_target" -eq 0 ]; then
    echo "  nothing to sweep." >&2
    # Still surface skipped findings for visibility.
    _print_category_entries "$classfile" "STALE_LOCKED"   "─── LOCKED stale (manual review) ───"
    _print_category_entries "$classfile" "STALE_DIRTY"    "─── DIRTY stale (manual review) ───"
    rm -f "$classfile"
    return 0
  fi

  # Dry-run path: list targets, do not touch disk.
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "" >&2
    echo "DRY-RUN — would remove:" >&2
    while IFS=$'\t' read -r cat path branch reason; do
      case "$cat" in
        STALE|ORPHAN|PHANTOM)
          echo "  [${cat}] $path" >&2
          echo "          branch: $branch" >&2
          echo "          $reason" >&2
          ;;
      esac
    done <"$classfile"
    _print_category_entries "$classfile" "STALE_LOCKED"   "─── SKIPPED — LOCKED (manual review) ───"
    _print_category_entries "$classfile" "STALE_DIRTY"    "─── SKIPPED — DIRTY (manual review) ───"
    rm -f "$classfile"
    return 0
  fi

  # Live sweep — act only on the targeted categories.
  local removed=0 failed=0
  local cat path branch reason
  while IFS=$'\t' read -r cat path branch reason; do
    case "$cat" in
      STALE|PHANTOM)
        if git worktree remove --force "$path" 2>/dev/null; then
          removed=$((removed+1))
        else
          # Registered but git refuses: lock appeared between classify and act,
          # OR another concurrent process touched it. Skip; do NOT rm -rf
          # (KB § PATTERNS/storage-hygiene.md §2.3 — THE-P10 incident).
          echo "  WARN: git refused to remove $path (lock raced between scan and sweep)" >&2
          failed=$((failed+1))
        fi
        ;;
      ORPHAN)
        # Not registered → safe to direct-rm.
        if rm -rf "$path" 2>/dev/null; then
          removed=$((removed+1))
        else
          failed=$((failed+1))
        fi
        ;;
    esac
  done <"$classfile"

  git worktree prune 2>/dev/null || true

  echo "  removed: $removed   failed: $failed" >&2
  echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') worktrees: removed=$removed failed=$failed targeted=$n_target skipped=$n_skipped" >> "$LOG_FILE"

  # Surface skipped findings so the operator sees what was held back.
  _print_category_entries "$classfile" "STALE_LOCKED"   "─── SKIPPED — LOCKED (manual review) ───"
  _print_category_entries "$classfile" "STALE_DIRTY"    "─── SKIPPED — DIRTY (manual review) ───"

  rm -f "$classfile"
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
