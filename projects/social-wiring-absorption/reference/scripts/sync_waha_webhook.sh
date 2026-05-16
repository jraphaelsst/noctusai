#!/usr/bin/env bash
# Push the current WAHA_WEBHOOK_URL from .env into WAHA's existing `default`
# session via PUT /api/sessions/<name>. Narrow on purpose:
#   - Does NOT create the session (404 -> warn, exit 0).
#   - Does NOT start/stop the session.
#   - Does NOT touch the API key.
#
# The operator sets up the session + pairs WhatsApp manually in the WAHA
# dashboard once. After that, every Cloudflare Quick Tunnel refresh hands
# WAHA a new public URL, and this script flips the webhook config to it
# without any dashboard click.
#
# Called by:
#   - refresh_cf_tunnel.sh (right after .env is rewritten with the new URL)
#   - operator manually (after editing WAHA_WEBHOOK_URL by hand)
#
# Required env (sourced by the caller from .env):
#   WAHA_API_KEY      plain key sent as X-Api-Key
#   WAHA_WEBHOOK_URL  the new public URL WAHA should POST events to
#   WAHA_SESSION      optional, defaults to "default"

set -euo pipefail

WAHA_LOCAL_URL="${WAHA_LOCAL_URL:-http://localhost:3000}"
SESSION_NAME="${WAHA_SESSION:-default}"

if [[ -z "${WAHA_API_KEY:-}" ]]; then
  echo "WARN: WAHA_API_KEY is empty in .env; skipping webhook sync." >&2
  exit 0
fi
if [[ -z "${WAHA_WEBHOOK_URL:-}" ]]; then
  echo "WARN: WAHA_WEBHOOK_URL is empty in .env; skipping webhook sync." >&2
  exit 0
fi

# Wait briefly for WAHA to answer — refresh_cf_tunnel.sh recreates containers
# right before this runs, so /ping may take a few seconds to come back.
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "${WAHA_LOCAL_URL%/}/ping" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "${WAHA_LOCAL_URL%/}/ping" >/dev/null 2>&1; then
  echo "WARN: WAHA at ${WAHA_LOCAL_URL} not reachable; skipping webhook sync." >&2
  exit 0
fi

PAYLOAD="$(
  WEBHOOK_URL="${WAHA_WEBHOOK_URL}" python3 - <<'PY'
import json, os
print(json.dumps({
    "config": {
        "webhooks": [{
            "url": os.environ["WEBHOOK_URL"],
            "events": ["message", "message.any", "session.status"],
        }]
    }
}))
PY
)"

HTTP_STATUS="$(
  curl -s -o /dev/null -w '%{http_code}' \
    -X PUT "${WAHA_LOCAL_URL%/}/api/sessions/${SESSION_NAME}" \
    -H "X-Api-Key: ${WAHA_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD"
)"

case "$HTTP_STATUS" in
  200|201|204)
    echo "==> WAHA webhook URL synced for session '${SESSION_NAME}':"
    echo "    ${WAHA_WEBHOOK_URL}"
    ;;
  404)
    echo "WARN: WAHA session '${SESSION_NAME}' not found." >&2
    echo "      Create it manually in the dashboard, then re-run this script." >&2
    ;;
  401|403)
    echo "WARN: WAHA rejected the API key (HTTP ${HTTP_STATUS})." >&2
    echo "      Check WAHA_API_KEY in .env matches the value WAHA booted with." >&2
    echo "      If you just changed it: docker compose up -d --force-recreate waha" >&2
    ;;
  *)
    echo "WARN: WAHA returned HTTP ${HTTP_STATUS}; webhook not synced." >&2
    ;;
esac

exit 0
