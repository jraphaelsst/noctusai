#!/usr/bin/env bash
# Refresh the Cloudflare Quick Tunnel URL for local E2E testing.
#
# What it does:
#   1. Ensures the backend stack is up with the tunnel profile.
#   2. Recreates the cloudflared quick tunnel so Cloudflare prints a fresh URL.
#   3. Extracts the generated https://*.trycloudflare.com URL from logs.
#   4. Updates the local, gitignored .env with:
#        TUNNEL_HOSTNAME=<url>
#        YOUTUBE_REDIRECT_URI=<url>/api/youtube/oauth/callback
#        WAHA_WEBHOOK_URL=<url>/api/whatsapp/webhook
#        FRONTEND_BASE_URL=http://localhost:8150  (unless already set)
#   5. Recreates the app container so it reads the updated env values.
#   6. PUTs the new WAHA_WEBHOOK_URL into the existing WAHA `default`
#      session via WAHA's REST API. Narrow scope: only updates the
#      webhook URL on a session you've already set up + paired manually.
#      Skips with a warn if the session is missing or the key is wrong.
#
# Quick Tunnel URLs are ephemeral and last only while the cloudflared
# process/container keeps running. Re-run this script after restarting the
# tunnel container, Docker, or your machine.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "ERROR: .env missing. Create it from .env.example first." >&2
  exit 1
fi

echo "==> Starting required services (incl. reverse proxy)"
docker compose --profile tunnel up -d app frontend waha redis proxy

echo "==> Recreating Cloudflare quick tunnel"
# The tunnel service points at proxy:8090, which fronts backend + frontend
# + WAHA on one URL. Force-recreate so Cloudflare hands us a fresh URL
# (Quick Tunnels are ephemeral and tied to the cloudflared process).
docker compose --profile tunnel up -d --force-recreate tunnel

echo "==> Waiting for trycloudflare.com URL"
TUNNEL_URL=""
for _ in $(seq 1 45); do
  TUNNEL_URL="$(
    docker compose logs tunnel --no-color --tail=120 \
      | grep -Eo 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' \
      | tail -1 || true
  )"
  if [[ -n "$TUNNEL_URL" ]]; then
    break
  fi
  sleep 2
done

if [[ -z "$TUNNEL_URL" ]]; then
  echo "ERROR: Could not find trycloudflare.com URL in tunnel logs." >&2
  docker compose logs tunnel --no-color --tail=120 >&2
  exit 2
fi

CALLBACK_URL="${TUNNEL_URL}/api/youtube/oauth/callback"
WAHA_WEBHOOK_URL="${TUNNEL_URL}/api/whatsapp/webhook"

echo "==> Updating .env"
python3 - "$TUNNEL_URL" "$CALLBACK_URL" "$WAHA_WEBHOOK_URL" <<'PY'
from pathlib import Path
import sys

tunnel_url, callback_url, waha_webhook_url = sys.argv[1], sys.argv[2], sys.argv[3]
path = Path(".env")
# With the reverse proxy, FRONTEND_BASE_URL is the SAME URL as the
# backend — both share the tunnel hostname. YouTube OAuth redirects
# back to <tunnel>/... which the proxy routes correctly: /api/* to
# the backend, /chat etc. to the frontend.
updates = {
    "TUNNEL_HOSTNAME": tunnel_url,
    "YOUTUBE_REDIRECT_URI": callback_url,
    "WAHA_WEBHOOK_URL": waha_webhook_url,
    "FRONTEND_BASE_URL": tunnel_url,
}
default_frontend = tunnel_url  # superseded by updates[]; kept for clarity
default_dashboard = "http://localhost:3000/dashboard"

lines = path.read_text().splitlines()
seen = set()
out = []
for line in lines:
    if "=" not in line or line.lstrip().startswith("#"):
        out.append(line)
        continue
    key, value = line.split("=", 1)
    if key in updates:
        # FRONTEND_BASE_URL: only override if it was empty or pointed
        # at a localhost dev address; respect explicit prod overrides.
        if key == "FRONTEND_BASE_URL" and value and "localhost" not in value:
            out.append(line)
        else:
            out.append(f"{key}={updates[key]}")
        seen.add(key)
    elif key == "WAHA_DASHBOARD_URL":
        out.append(line if value else f"{key}={default_dashboard}")
        seen.add(key)
    else:
        out.append(line)

for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
if "FRONTEND_BASE_URL" not in seen:
    out.append(f"FRONTEND_BASE_URL={default_frontend}")
if "WAHA_DASHBOARD_URL" not in seen:
    out.append(f"WAHA_DASHBOARD_URL={default_dashboard}")

path.write_text("\n".join(out) + "\n")
PY

set -a
# shellcheck disable=SC1091
source .env
set +a

echo "==> Recreating app container with updated env"
docker compose --profile tunnel up -d --force-recreate app

echo "==> Restarting proxy so it picks up the new env-driven downstream config"
# The proxy itself is stateless (nginx.conf is mounted read-only), but
# the recreate is cheap and avoids head-scratching when something
# downstream needs a fresh upstream connection pool.
docker compose --profile tunnel up -d --force-recreate proxy

echo "==> Waiting for backend health (direct + via proxy)"
for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:8010/api/health" >/dev/null 2>&1 \
     && curl -fsS "http://localhost:8090/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! curl -fsS "http://localhost:8010/api/health" >/dev/null 2>&1; then
  echo "ERROR: backend (direct) did not become healthy after tunnel refresh." >&2
  docker compose logs app --no-color --tail=80 >&2
  exit 3
fi
if ! curl -fsS "http://localhost:8090/api/health" >/dev/null 2>&1; then
  echo "ERROR: backend via proxy at :8090 did not become healthy." >&2
  docker compose logs proxy --no-color --tail=80 >&2
  exit 3
fi

echo "==> Syncing new webhook URL into WAHA session"
bash "$ROOT_DIR/scripts/sync_waha_webhook.sh" || true

echo ""
echo "Cloudflare Quick Tunnel refreshed (single URL for the whole stack):"
echo "  Public frontend:       ${TUNNEL_URL}/"
echo "  Public chat (agent):   ${TUNNEL_URL}/chat"
echo "  Public backend API:    ${TUNNEL_URL}/api/health"
echo "  Public Swagger docs:   ${TUNNEL_URL}/docs"
echo "  Public WAHA dashboard: ${TUNNEL_URL}/waha/dashboard"
echo "  YouTube callback URI:  ${CALLBACK_URL}"
echo "  WAHA webhook URL:      ${WAHA_WEBHOOK_URL}"
echo ""
echo "Local equivalents (same single-URL routing, served by the proxy at :8090):"
echo "  http://localhost:8090/         → frontend"
echo "  http://localhost:8090/api/...  → backend"
echo "  http://localhost:8090/waha/... → WAHA"
echo ""
echo "Required manual follow-up:"
echo "  Register the callback URI above in Google Cloud Console for the OAuth client."
echo "  Confirm WAHA session status is WORKING in: ${WAHA_DASHBOARD_URL:-http://localhost:3000/dashboard}"
