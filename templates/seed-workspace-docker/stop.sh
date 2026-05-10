#!/usr/bin/env bash
# {{PRODUCT_NAME}} — stop the local stack.
#
# Convention: every workspace inherits this script alongside the docker
# artifacts. Source of truth: noc/templates/seed-workspace-docker/stop.sh.
#
# Usage:
#   ./stop.sh                graceful: stop containers, keep volumes + images
#   ./stop.sh --volumes      stop + remove named volumes (DB / redis state lost)
#   ./stop.sh --prune        stop + remove volumes + dangling images
#
# Exit code: 0 always (down is idempotent — already-down is a no-op).

set -euo pipefail

WORKSPACE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKSPACE_DIR"

MODE="${1:-graceful}"

case "$MODE" in
  graceful)
    echo "==> docker compose down  (keep volumes + images)"
    docker compose down
    ;;
  --volumes)
    echo "==> docker compose down --volumes  (volumes wiped)"
    docker compose down --volumes
    ;;
  --prune)
    echo "==> docker compose down --volumes --rmi local  (volumes wiped, images removed)"
    docker compose down --volumes --rmi local
    ;;
  *)
    echo "ERROR: unknown mode '$MODE'. Use: (none) | --volumes | --prune" >&2
    exit 1
    ;;
esac

echo ""
echo "{{PRODUCT_NAME}} is offline."
echo "  Restart:  ./start.sh"
echo ""
