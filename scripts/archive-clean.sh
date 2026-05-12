#!/usr/bin/env bash
# scripts/archive-clean.sh — keep only today's + yesterday's archive folders; delete the rest.
#
# Trigger phrases (user-invoked, never automatic):
#   "clean the archive" / "clean archive" / "archive cleanup" / similar
#
# What it does
#   archive/projects/<DATE>/ folders are date-stamped YYYY-MM-DD. Anything older than
#   yesterday (D-2 and earlier) gets removed via `git rm -rf`. Today + yesterday are
#   preserved as the recent-work window.
#
# Safety
#   - Refuses without --force (dry-run default).
#   - Never touches archive/features/ or archive/<date>_<time>_<name>/ ad-hoc dirs.
#   - Only operates on archive/projects/YYYY-MM-DD/ folders.
#   - Uses `git rm -rf` so removals are tracked (you can `git reset --hard` to undo
#     pre-commit; post-commit, history retains them).
#
# Usage
#   bash scripts/archive-clean.sh           # dry-run
#   bash scripts/archive-clean.sh --force   # actually remove

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
[ -z "$REPO_ROOT" ] && { echo "ERR: not inside a git repo" >&2; exit 2; }
cd "$REPO_ROOT"

ARCHIVE_DIR="archive/projects"
if [ ! -d "$ARCHIVE_DIR" ]; then
  echo "No $ARCHIVE_DIR — nothing to clean."
  exit 0
fi

DRY_RUN=1
for arg in "$@"; do
  case "$arg" in
    --force)   DRY_RUN=0 ;;
    --dry-run) DRY_RUN=1 ;;
    *)         echo "ERR: unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# Compute today + yesterday in LOCAL time (BSD date for macOS; coreutils date for Linux).
#
# Local time chosen because user invokes archive cleanup based on local-day boundaries;
# using UTC caused tick 2 to flag `2026-05-10` as stale at 21:40 BRT (UTC `2026-05-12`),
# shifting the keep window forward by one day.
today=$(date '+%Y-%m-%d')
if date -v-1d '+%Y-%m-%d' >/dev/null 2>&1; then
  # BSD date (macOS)
  yesterday=$(date -v-1d '+%Y-%m-%d')
else
  # GNU date (Linux)
  yesterday=$(date -d 'yesterday' '+%Y-%m-%d')
fi

echo "Archive cleanup — keep window: $yesterday + $today"
echo "$ARCHIVE_DIR contents:"

stale_dirs=()
for dir in "$ARCHIVE_DIR"/*/; do
  [ -d "$dir" ] || continue
  name=$(basename "$dir")
  # Only operate on YYYY-MM-DD folders; skip anything else (README.md, etc.).
  if [[ ! "$name" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    echo "  · $name  (skipped — not a date folder)"
    continue
  fi
  if [ "$name" = "$today" ] || [ "$name" = "$yesterday" ]; then
    echo "  · $name  (KEPT)"
  else
    echo "  · $name  (STALE — D-2 or older)"
    stale_dirs+=("$dir")
  fi
done

if [ "${#stale_dirs[@]}" -eq 0 ]; then
  echo "✓ Nothing to remove."
  exit 0
fi

echo ""
echo "Stale folders: ${#stale_dirs[@]}"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY-RUN — re-run with --force to remove."
  exit 0
fi

removed=0
for dir in "${stale_dirs[@]}"; do
  if git rm -rf -q "$dir" 2>/dev/null; then
    removed=$((removed + 1))
  else
    # Fallback for non-git-tracked content.
    rm -rf "$dir" 2>/dev/null && removed=$((removed + 1))
  fi
done
echo "✓ Removed $removed stale folder(s). Stage with: git add archive/projects/ && git commit"
