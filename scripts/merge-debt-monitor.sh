#!/usr/bin/env bash
# scripts/merge-debt-monitor.sh — warn before an unmerged-to-main backlog
# becomes a base-mismatch lockout.
#
# Why this exists
#   Long-lived feature branches accumulate large unmerged-to-`origin/main`
#   backlogs. Engineer Agent-worktrees fork stale `origin/main`, so the
#   bigger the backlog the more often a dispatched engineer's base diverges
#   from the branch the work actually targets (the WORKTREE-BASE-DIVERGE
#   stop). During mcp-connector-expansion this cost two full re-dispatch
#   waves. The fix is a phased-push policy (push in phases; push only when
#   100% sure of the work); this monitor is the CUSTODIAL enforcement
#   sibling of scripts/disk-usage-monitor.sh / scripts/mole.sh /
#   noctus.hound.scan — it makes the backlog VISIBLE before it bites.
#
# What it does
#   Computes, for the current branch vs origin/main:
#     · commits-ahead       — git rev-list --count origin/main..HEAD
#     · closed-projects-unmerged — commits in that range whose subject
#       matches the repo's project-close convention. Heuristic derived by
#       inspecting recent history (see CLOSE_RE below): a project close is
#       a `chore(archive): close <slug> — git mv to archive/...` commit
#       (the canonical convention, e.g. 3463c43), with `: close ` and a
#       generic `close ... — git mv to archive` fallback for older shapes.
#       This is the high-signal axis: a closed (shipped) project still
#       sitting unmerged on a feature branch is exactly the debt the
#       phased-push policy targets.
#
# The policy it enforces
#   Phased-push: push completed phases to the integration branch as they
#   close; never let shipped/closed projects pile up unmerged. Push only
#   when 100% sure (custodial — surfaces, never mutates git state).
#
# Exit codes  (mirrors disk-usage-monitor.sh 0/1/2/3 semantics)
#   0  — OK       (≤1 closed-project unmerged AND < CAUTION commits)
#   1  — CAUTION  (commits-ahead ≥ COMMITS_CAUTION, still 0 closed-projects)
#   2  — WARNING  (≥1 closed-project unmerged → phase-push before next dispatch)
#   3  — CRITICAL (≥ CLOSED_CRITICAL closed-projects OR ≥ COMMITS_CRITICAL commits)
#
# Usage
#   bash scripts/merge-debt-monitor.sh           # human summary + exit code
#   bash scripts/merge-debt-monitor.sh --json    # machine-readable (gate wiring)
#   bash scripts/merge-debt-monitor.sh --help
#
# Integration (durable policy doc is the architect's Wave-3 KB deliverable)
#   - Pre-dispatch gate: read exit code; ≥2 → phase-push before dispatching
#     engineers (stops the stale-fork re-dispatch waves at the source).
#   - Project-close gate: run at close; ≥2 → push the close commit now.
#
# Bash 3.x compatible (macOS default ships 3.2.57; no mapfile/readarray —
# the documented mole-incident lesson, 2026-05-11).

set -uo pipefail

# ─── Thresholds (named, with rationale) ──────────────────────────────────────
# A single closed-project unmerged is already WARNING (exit 2): a shipped
# project must not ride a long-lived branch — that is the precise debt the
# phased-push policy exists to prevent. Commit-count axis is the coarse
# secondary signal (large diffs raise base-mismatch probability even with
# zero closed projects).
COMMITS_CAUTION=25      # CAUTION: backlog growing; plan a phased push soon.
COMMITS_CRITICAL=60     # CRITICAL: backlog so large stale-fork divergence is near-certain.
CLOSED_CRITICAL=3       # CRITICAL: 3+ shipped projects unmerged = systemic phased-push failure.

# ─── Args ────────────────────────────────────────────────────────────────────
JSON=0
for arg in "$@"; do
  case "$arg" in
    --json) JSON=1 ;;
    -h|--help)
      sed -n '2,57p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

# ─── Read git state (read-only — never mutates) ──────────────────────────────
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"

# Best-effort refresh so the count reflects the true remote tip. Read-only;
# `git fetch` does not touch the working tree or local branches.
git fetch origin main --quiet 2>/dev/null || true

# Resolve the comparison base: prefer origin/main; fall back to main if the
# remote ref is absent (detached / no remote configured).
BASE_REF="origin/main"
if ! git rev-parse --verify --quiet "$BASE_REF" >/dev/null 2>&1; then
  BASE_REF="main"
fi

COMMITS_AHEAD="$(git rev-list --count "${BASE_REF}..HEAD" 2>/dev/null || echo 0)"
[ -z "$COMMITS_AHEAD" ] && COMMITS_AHEAD=0

# Project-close convention (derived from `git log` inspection — see header).
# Canonical: `chore(archive): close <slug> — git mv to archive/...`.
CLOSE_RE='chore\(archive\)|close .*— git mv to archive|: close '
CLOSED_UNMERGED="$(git log --format='%s' "${BASE_REF}..HEAD" 2>/dev/null \
  | grep -cE "$CLOSE_RE" || true)"
CLOSED_UNMERGED="$(echo "$CLOSED_UNMERGED" | head -1 | tr -d ' \n')"
[ -z "$CLOSED_UNMERGED" ] && CLOSED_UNMERGED=0

# ─── Severity classification ─────────────────────────────────────────────────
if [ "$CLOSED_UNMERGED" -ge "$CLOSED_CRITICAL" ] || [ "$COMMITS_AHEAD" -ge "$COMMITS_CRITICAL" ]; then
  SEVERITY="CRITICAL"
  EXIT_CODE=3
  NEXT_ACTION="phase-push NOW — ${CLOSED_UNMERGED} closed project(s) + ${COMMITS_AHEAD} commits unmerged; merge ${BRANCH} → main before any further dispatch"
elif [ "$CLOSED_UNMERGED" -ge 1 ]; then
  SEVERITY="WARNING"
  EXIT_CODE=2
  NEXT_ACTION="phase-push before next dispatch — ${CLOSED_UNMERGED} closed (shipped) project(s) sitting unmerged on ${BRANCH}"
elif [ "$COMMITS_AHEAD" -ge "$COMMITS_CAUTION" ]; then
  SEVERITY="CAUTION"
  EXIT_CODE=1
  NEXT_ACTION="plan a phased push soon — ${COMMITS_AHEAD} commits ahead of ${BASE_REF} (stale-fork divergence risk rising)"
else
  SEVERITY="OK"
  EXIT_CODE=0
  NEXT_ACTION="ok — nothing to do"
fi

# ─── Report ──────────────────────────────────────────────────────────────────
if [ "$JSON" -eq 1 ]; then
  printf '{"severity":"%s","branch":"%s","base":"%s","commits_ahead":%d,"closed_projects_unmerged":%d,"exit_code":%d,"next_action":"%s"}\n' \
    "$SEVERITY" "$BRANCH" "$BASE_REF" "$COMMITS_AHEAD" "$CLOSED_UNMERGED" "$EXIT_CODE" "$NEXT_ACTION"
else
  echo "Merge-debt monitor — $(date '+%Y-%m-%d %H:%M:%S')"
  echo "  · Branch:                   $BRANCH (vs $BASE_REF)"
  echo "  · Commits ahead:            $COMMITS_AHEAD"
  echo "  · Closed projects unmerged: $CLOSED_UNMERGED"
  echo "  · Severity:                 $SEVERITY"
  echo "  · next_action:              $NEXT_ACTION"
fi

exit "$EXIT_CODE"
