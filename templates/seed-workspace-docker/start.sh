#!/usr/bin/env bash
# {{PRODUCT_NAME}} — start the local stack.
#
# Convention: every workspace inherits this script alongside the docker
# artifacts. Source of truth: noc/templates/seed-workspace-docker/start.sh.
# scaffold_product substitutes the placeholders.
#
# Usage:
#   ./start.sh                full stack (app + frontend + redis + waha)
#   ./start.sh minimal        backend smoke (app + redis only)
#   ./start.sh tunnel         full stack + cloudflared (public URL for OAuth)
#   ./start.sh -- <args>      pass extra args to `docker compose up`
#
# Exit codes: 0 healthy, 1 misconfig (missing .env / NOCTUSAI_HOME), 2 unhealthy.

set -euo pipefail

WORKSPACE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKSPACE_DIR"

BACKEND_PORT="{{BACKEND_PORT}}"
FRONTEND_PORT="{{FRONTEND_PORT}}"
WAHA_PORT="3000"

PROFILE="${1:-full}"
shift || true

# ----- preflight -----
if [[ ! -f .env ]]; then
  echo "ERROR: .env missing. Run:  cp .env.example .env  (then fill in keys)" >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a; source .env; set +a

if [[ -z "${NOCTUSAI_HOME:-}" ]]; then
  echo "ERROR: NOCTUSAI_HOME unset in .env. The Docker build needs it to" >&2
  echo "       reach the seed packages via additional_contexts: noc." >&2
  exit 1
fi
if [[ ! -d "$NOCTUSAI_HOME" ]]; then
  echo "ERROR: NOCTUSAI_HOME=$NOCTUSAI_HOME is not a directory." >&2
  exit 1
fi

# ----- profile dispatch -----
COMPOSE_ARGS=()
case "$PROFILE" in
  full)     ;;  # default
  minimal)  COMPOSE_ARGS+=(--profile minimal) ;;
  tunnel)   COMPOSE_ARGS+=(--profile tunnel) ;;
  --) ;;  # caller passed -- to forward extra args; treat as 'full'
  *)
    echo "ERROR: unknown profile '$PROFILE'. Use full | minimal | tunnel." >&2
    exit 1
    ;;
esac

# ----- bring up -----
echo "==> docker compose up -d --build  (profile: $PROFILE)"
docker compose ${COMPOSE_ARGS[@]+"${COMPOSE_ARGS[@]}"} up -d --build "$@"

# ----- health-poll -----
echo "==> waiting for backend at http://localhost:${BACKEND_PORT}/api/health"
HEALTHY=0
for i in $(seq 1 30); do
  if curl -fsS "http://localhost:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
    HEALTHY=1
    break
  fi
  sleep 2
done

if [[ $HEALTHY -ne 1 ]]; then
  echo ""
  echo "ERROR: backend did not become healthy within 60s." >&2
  echo "       docker compose logs app | tail -50" >&2
  docker compose logs app | tail -50 >&2
  exit 2
fi

# ----- summary -----
echo ""
echo "{{PRODUCT_NAME}} is online."
echo ""
echo "  Backend:        http://localhost:${BACKEND_PORT}/api/health"
if [[ "$PROFILE" != "minimal" ]]; then
  echo "  Frontend:       http://localhost:${FRONTEND_PORT}/"
  echo "  WAHA dashboard: http://localhost:${WAHA_PORT}/dashboard"
  echo "    user: ${WAHA_DASHBOARD_USERNAME:-admin}  pass: ${WAHA_DASHBOARD_PASSWORD:-admin}"
fi
echo ""
echo "  Logs:           docker compose logs -f app"
echo "  Stop:           ./stop.sh"
echo ""
