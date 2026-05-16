#!/usr/bin/env bash
# 03-setup-tunnel.sh — wire a permanent Cloudflare Named Tunnel for the
# Docker stack on this VPS.
#
# Unlike Cloudflare Quick Tunnels (which get an ephemeral
# *.trycloudflare.com URL that rotates on every restart), a Named Tunnel:
#   - Has a stable URL on YOUR domain (e.g. bot.noctusai.com)
#   - Survives reboots when installed as a systemd service
#   - Doesn't require open inbound ports on the VPS
#   - Auto-renews TLS via Cloudflare's edge
#
# Runs AS ROOT (the systemd service install + DNS record creation need
# the cert + token).
#
# Required env vars:
#   CLOUDFLARE_API_TOKEN  Token with Account:Cloudflare Tunnel:Edit,
#                         Zone:DNS:Edit, Zone:Zone Settings:Read scopes
#                         scoped to the noctusai.com zone.
#   CLOUDFLARE_ACCOUNT_ID Cloudflare account id (find at the bottom-right
#                         of any zone overview page, or via the API).
#   ZONE                  noctusai.com
#   HOSTNAME              bot.noctusai.com
#   TUNNEL_NAME           noctusai-bot
#
# Usage:
#   export CLOUDFLARE_API_TOKEN=...
#   export CLOUDFLARE_ACCOUNT_ID=...
#   export ZONE=noctusai.com
#   export HOSTNAME=bot.noctusai.com
#   sudo -E bash 03-setup-tunnel.sh

set -euo pipefail

CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:?required}"
CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:?required}"
ZONE="${ZONE:?required e.g. noctusai.com}"
HOSTNAME="${HOSTNAME:?required e.g. bot.noctusai.com}"
TUNNEL_NAME="${TUNNEL_NAME:-noctusai-bot}"

CF_API="https://api.cloudflare.com/client/v4"
H_AUTH=(-H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json")

echo "==> setting up Cloudflare Named Tunnel: $TUNNEL_NAME → $HOSTNAME"

# ----- 1. Find or create the tunnel -----
TUNNEL_ID="$(
  curl -sS "${H_AUTH[@]}" \
    "$CF_API/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel?name=$TUNNEL_NAME&is_deleted=false" \
  | jq -r '.result[0].id // empty'
)"

if [[ -z "$TUNNEL_ID" ]]; then
  # 32 random bytes → base64 → tunnel secret
  TUNNEL_SECRET="$(openssl rand -base64 32)"
  TUNNEL_ID="$(
    curl -sS "${H_AUTH[@]}" -X POST \
      "$CF_API/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel" \
      --data "$(jq -nc --arg n "$TUNNEL_NAME" --arg s "$TUNNEL_SECRET" '{name:$n,tunnel_secret:$s}')" \
    | jq -r '.result.id'
  )"
  echo "   created tunnel id=$TUNNEL_ID"
else
  echo "   reusing existing tunnel id=$TUNNEL_ID"
  # Re-derive the secret by rotating (cloudflared needs the secret to run)
  TUNNEL_SECRET="$(openssl rand -base64 32)"
  curl -sS "${H_AUTH[@]}" -X PATCH \
    "$CF_API/accounts/$CLOUDFLARE_ACCOUNT_ID/cfd_tunnel/$TUNNEL_ID" \
    --data "$(jq -nc --arg s "$TUNNEL_SECRET" '{tunnel_secret:$s}')" >/dev/null
  echo "   rotated tunnel secret"
fi

# ----- 2. Write tunnel credentials (~/.cloudflared/<id>.json shape) -----
mkdir -p /etc/cloudflared
CREDS_FILE="/etc/cloudflared/${TUNNEL_ID}.json"
jq -nc \
  --arg a "$CLOUDFLARE_ACCOUNT_ID" \
  --arg t "$TUNNEL_ID" \
  --arg n "$TUNNEL_NAME" \
  --arg s "$TUNNEL_SECRET" \
  '{AccountTag:$a,TunnelID:$t,TunnelName:$n,TunnelSecret:$s}' \
  > "$CREDS_FILE"
chmod 600 "$CREDS_FILE"
echo "   credentials written to $CREDS_FILE"

# ----- 3. Tunnel config (ingress rules → local proxy on :8090) -----
cat > /etc/cloudflared/config.yml <<YAML
tunnel: $TUNNEL_ID
credentials-file: $CREDS_FILE

# Send everything to the local nginx reverse proxy that fronts:
#   /api/*  → backend (app:8010)
#   /waha/* → WAHA dashboard + API (waha:3000)
#   /*      → frontend SPA (frontend:8150, with React Router fallback)
ingress:
  - hostname: $HOSTNAME
    service: http://localhost:8090
  - service: http_status:404
YAML
echo "   tunnel config written to /etc/cloudflared/config.yml"

# ----- 4. Find the zone id + create/update DNS CNAME -----
ZONE_ID="$(
  curl -sS "${H_AUTH[@]}" "$CF_API/zones?name=$ZONE" \
  | jq -r '.result[0].id // empty'
)"
if [[ -z "$ZONE_ID" ]]; then
  echo "ERROR: zone $ZONE not found on this Cloudflare account." >&2
  exit 2
fi

CNAME_TARGET="${TUNNEL_ID}.cfargotunnel.com"
RECORD_NAME="$HOSTNAME"

EXISTING_RECORD_ID="$(
  curl -sS "${H_AUTH[@]}" \
    "$CF_API/zones/$ZONE_ID/dns_records?type=CNAME&name=$RECORD_NAME" \
  | jq -r '.result[0].id // empty'
)"

PAYLOAD="$(jq -nc \
  --arg name "$RECORD_NAME" \
  --arg content "$CNAME_TARGET" \
  '{type:"CNAME",name:$name,content:$content,proxied:true,ttl:1}')"

if [[ -z "$EXISTING_RECORD_ID" ]]; then
  echo "==> creating DNS CNAME $RECORD_NAME → $CNAME_TARGET (proxied)"
  curl -sS "${H_AUTH[@]}" -X POST \
    "$CF_API/zones/$ZONE_ID/dns_records" --data "$PAYLOAD" \
  | jq -r '.success' | grep -q true || {
    echo "ERROR: DNS create failed." >&2
    exit 2
  }
else
  echo "==> updating existing CNAME $RECORD_NAME → $CNAME_TARGET (proxied)"
  curl -sS "${H_AUTH[@]}" -X PUT \
    "$CF_API/zones/$ZONE_ID/dns_records/$EXISTING_RECORD_ID" --data "$PAYLOAD" \
  | jq -r '.success' | grep -q true || {
    echo "ERROR: DNS update failed." >&2
    exit 2
  }
fi

# ----- 5. Install + enable cloudflared systemd service -----
echo "==> installing cloudflared as a systemd service"
cloudflared service install --config /etc/cloudflared/config.yml || true
systemctl daemon-reload
systemctl enable --now cloudflared
sleep 3
systemctl --no-pager status cloudflared --lines=10 || true

echo ""
echo "✓ Cloudflare Named Tunnel deployed."
echo ""
echo "  Tunnel ID:     $TUNNEL_ID"
echo "  Tunnel name:   $TUNNEL_NAME"
echo "  Hostname:      $HOSTNAME"
echo "  Local target:  http://localhost:8090 (your proxy)"
echo ""
echo "Verify (give it ~10s for Cloudflare to propagate the route):"
echo "  curl https://$HOSTNAME/api/health"
echo ""
echo "logs:    journalctl -u cloudflared -f"
echo "restart: systemctl restart cloudflared"
