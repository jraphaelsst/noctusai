#!/usr/bin/env bash
# scripts/disk-usage-monitor.sh — warn before disk pressure becomes a 100% lockout.
#
# Why this exists
#   2026-05-11 incident: data volume hit 100% mid-session (664 MiB free of 460 GiB)
#   blocking Engineer III + the orchestrator's own Bash output staging. Recovery
#   via worktree sweep recovered 68 GiB. This monitor catches the pressure
#   BEFORE it locks the harness — at 70% (caution) and 80% (action-required).
#
# What it does
#   Reports current % used on the data volume + estimates how much worktree
#   cleanup would free. Emits clear severity-tagged output so it slots into
#   any consumer: orchestrator startup, pre-dispatch gate, cron warning,
#   manual ops check.
#
# Exit codes
#   0  — under 70% (healthy)
#   1  — 70-79% (CAUTION; recommend running cleanup-stale-worktrees.sh)
#   2  — 80-89% (WARNING; cleanup REQUIRED before new dispatches)
#   3  — 90-100% (CRITICAL; harness lockout imminent; immediate manual recovery)
#
# Usage
#   bash scripts/disk-usage-monitor.sh                # status report
#   bash scripts/disk-usage-monitor.sh --quiet        # exit code only (cron)
#   bash scripts/disk-usage-monitor.sh --auto-clean   # if ≥70%, run cleanup-stale-worktrees.sh --force
#
# Integration
#   - Orchestrator startup: read exit code; warn user if ≥70%.
#   - bootstrap-worktree.sh: pre-flight gate (refuse to hydrate if ≥80%).
#   - Cron: nightly + on each new shell session via `~/.zshrc` opt-in.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
QUIET=0
AUTO_CLEAN=0

for arg in "$@"; do
  case "$arg" in
    --quiet)      QUIET=1 ;;
    --auto-clean) AUTO_CLEAN=1 ;;
    -h|--help)
      sed -n '4,30p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

# ─── Read disk state ─────────────────────────────────────────────────────────
# Use the data volume (/System/Volumes/Data on macOS; / on Linux).
# `df -P` gives POSIX-portable output: Filesystem 1024-blocks Used Available Capacity Mountpoint
DISK_LINE="$(df -P / | tail -1)"
PCT_USED="$(echo "$DISK_LINE" | awk '{print $5}' | tr -d '%')"
AVAIL_KB="$(echo "$DISK_LINE" | awk '{print $4}')"
AVAIL_GB="$(awk "BEGIN {printf \"%.1f\", $AVAIL_KB / 1024 / 1024}")"
TOTAL_KB="$(echo "$DISK_LINE" | awk '{print $2}')"
TOTAL_GB="$(awk "BEGIN {printf \"%.0f\", $TOTAL_KB / 1024 / 1024}")"

# ─── Estimate worktree footprint ─────────────────────────────────────────────
WTREE_DIR="$REPO_ROOT/.claude/worktrees"
WTREE_SIZE="(none)"
WTREE_COUNT=0
if [ -d "$WTREE_DIR" ]; then
  WTREE_SIZE="$(du -sh "$WTREE_DIR" 2>/dev/null | awk '{print $1}')"
  WTREE_COUNT="$(find "$WTREE_DIR" -maxdepth 1 -type d -name "agent-*" 2>/dev/null | wc -l | tr -d ' ')"
fi

# ─── Severity classification ─────────────────────────────────────────────────
if [ "$PCT_USED" -ge 90 ]; then
  SEVERITY="CRITICAL"
  EXIT_CODE=3
  HINT="Harness lockout imminent. Manual recovery required NOW: bash scripts/cleanup-stale-worktrees.sh --force; docker system prune -a -f; sudo purge"
elif [ "$PCT_USED" -ge 80 ]; then
  SEVERITY="WARNING"
  EXIT_CODE=2
  HINT="Cleanup REQUIRED before new dispatches. Run: bash scripts/cleanup-stale-worktrees.sh --force"
elif [ "$PCT_USED" -ge 70 ]; then
  SEVERITY="CAUTION"
  EXIT_CODE=1
  HINT="Schedule a sweep soon. Run: bash scripts/cleanup-stale-worktrees.sh"
else
  SEVERITY="OK"
  EXIT_CODE=0
  HINT=""
fi

# ─── Report ──────────────────────────────────────────────────────────────────
if [ "$QUIET" -eq 0 ]; then
  echo "Disk-usage monitor — $(date '+%Y-%m-%d %H:%M:%S')"
  echo "  · Data volume: ${PCT_USED}% used, ${AVAIL_GB} GiB free of ${TOTAL_GB} GiB"
  echo "  · Agent worktrees: $WTREE_COUNT directories ($WTREE_SIZE)"
  echo "  · Severity: $SEVERITY"
  if [ -n "$HINT" ]; then
    echo "  · Action: $HINT"
  fi
fi

# ─── Auto-clean trigger ──────────────────────────────────────────────────────
if [ "$AUTO_CLEAN" -eq 1 ] && [ "$EXIT_CODE" -ge 1 ]; then
  CLEANUP_SCRIPT="$REPO_ROOT/scripts/cleanup-stale-worktrees.sh"
  if [ -x "$CLEANUP_SCRIPT" ]; then
    [ "$QUIET" -eq 0 ] && echo ""
    [ "$QUIET" -eq 0 ] && echo "→ Auto-clean triggered (severity $SEVERITY)..."
    bash "$CLEANUP_SCRIPT" --force
    # Re-run report (without auto-clean) to show new state.
    [ "$QUIET" -eq 0 ] && echo ""
    [ "$QUIET" -eq 0 ] && bash "$0"
  else
    echo "  · Auto-clean requested but $CLEANUP_SCRIPT not executable; skipping." >&2
  fi
fi

exit "$EXIT_CODE"
