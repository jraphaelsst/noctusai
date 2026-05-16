#!/usr/bin/env bash
# recreate.sh — env-aware container restart for this workspace.
#
# Why this exists: `docker compose restart <svc>` does NOT re-read .env;
# env vars are baked in at container CREATION. Editing .env then doing
# `restart` leaves the container running with stale env, producing
# infuriating "I set the value but the app doesn't see it" debugging.
#
# This script forces a recreate (which DOES re-read .env), then polls
# the app's health endpoint when the app container was touched.
#
# Usage:
#   ./scripts/recreate.sh                 # recreate the app container (most common)
#   ./scripts/recreate.sh app             # same as above, explicit
#   ./scripts/recreate.sh waha            # recreate WAHA (e.g. after WAHA_API_KEY change)
#   ./scripts/recreate.sh app waha        # multiple services
#   ./scripts/recreate.sh --all           # recreate every service in the active profile
#
# Exit codes: 0 healthy, 1 docker error, 2 health-check timeout.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "${1:-}" == "--all" ]]; then
  TARGETS=(--all)
elif [[ $# -eq 0 ]]; then
  TARGETS=(app)
else
  TARGETS=("$@")
fi

# Friendly reminder of what this script just saved you from.
echo "==> recreate (NOT restart) — re-reads .env into the container env"

if [[ "${TARGETS[0]}" == "--all" ]]; then
  echo "==> docker compose up -d --force-recreate (all services)"
  docker compose up -d --force-recreate
else
  echo "==> docker compose up -d --force-recreate ${TARGETS[*]}"
  docker compose up -d --force-recreate "${TARGETS[@]}"
fi

# Health-poll the backend if app was in the target set (or --all).
NEED_HEALTH=0
for svc in "${TARGETS[@]}"; do
  if [[ "$svc" == "app" || "$svc" == "--all" ]]; then
    NEED_HEALTH=1
    break
  fi
done

if [[ $NEED_HEALTH -eq 1 ]]; then
  echo "==> waiting for backend at http://localhost:8010/api/health"
  for i in $(seq 1 20); do
    if curl -fsS http://localhost:8010/api/health >/dev/null 2>&1; then
      echo "    ✓ healthy (after ${i} attempt(s))"
      exit 0
    fi
    sleep 2
  done
  echo "    ✗ backend did not become healthy within 40s." >&2
  echo "       docker compose logs --tail=50 app" >&2
  docker compose logs --tail=50 app >&2 || true
  exit 2
fi

echo "==> done. Services up:"
docker compose ps --format "table {{.Service}}\t{{.Status}}" 2>/dev/null || \
  docker compose ps
