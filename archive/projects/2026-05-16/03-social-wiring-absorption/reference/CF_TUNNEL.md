# Cloudflare Quick Tunnel Runbook

This repo uses a **Cloudflare Quick Tunnel** for local real-device testing.
The tunnel is created by the `cloudflare/cloudflared` Docker service in
`docker-compose.yml`.

## How The URL Is Created

The compose service runs:

```bash
cloudflared tunnel --no-autoupdate --url http://app:8010
```

That command asks Cloudflare for a temporary random
`https://*.trycloudflare.com` hostname and proxies traffic from that
hostname to the backend container at `http://app:8010`.

I got the current URL by reading the tunnel container logs:

```bash
docker compose logs tunnel --no-color --tail=100
```

Cloudflare prints a block like:

```text
Your quick Tunnel has been created! Visit it at:
https://module-absolute-sudden-laboratory.trycloudflare.com
```

The current URL is also written into local `.env` by
`./refresh_cf_tunnel.sh`.

## Refresh The URL

Run:

```bash
./refresh_cf_tunnel.sh
```

The script:

1. Starts the Docker Compose stack with the `tunnel` profile.
2. Recreates the `tunnel` service to force a fresh Quick Tunnel URL.
3. Extracts the generated `https://*.trycloudflare.com` URL from logs.
4. Updates local `.env`:
   - `TUNNEL_HOSTNAME=<new-url>`
   - `YOUTUBE_REDIRECT_URI=<new-url>/api/youtube/oauth/callback`
   - `WAHA_WEBHOOK_URL=<new-url>/api/whatsapp/webhook`
   - `FRONTEND_BASE_URL=http://localhost:8150` when unset
5. Recreates the backend app container so it reads the new env values.
6. Best-effort updates the WAHA `default` session webhook config when
   WAHA is reachable.

## How Long Does It Last?

Cloudflare documents Quick Tunnels as temporary, anonymous development
tunnels. They generate a random `trycloudflare.com` subdomain and last
for the lifetime of the running `cloudflared` process/container. They are
for testing and development, not production. Cloudflare also states that
Quick Tunnels do not have uptime guarantees; production should use a
named/remotely-managed tunnel.

Practical rule:

- If Docker and the `tunnel` container are still running, keep using the
  same URL.
- If you restart Docker, recreate the tunnel service, reboot the machine,
  or see tunnel connectivity fail, run `./refresh_cf_tunnel.sh` again.
- You do **not** need to refresh on a schedule during a single active
  testing session.

References:

- Cloudflare Quick Tunnels docs:
  https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/
- Cloudflare setup docs, Quick tunnels section:
  https://developers.cloudflare.com/tunnel/setup/
- Wrangler quick-start docs note the quick tunnel lasts for the process:
  https://developers.cloudflare.com/workers/wrangler/commands/tunnel/

## Where The URL Must Be Set

### Local `.env`

The script sets:

```env
TUNNEL_HOSTNAME=https://<random>.trycloudflare.com
YOUTUBE_REDIRECT_URI=https://<random>.trycloudflare.com/api/youtube/oauth/callback
WAHA_WEBHOOK_URL=https://<random>.trycloudflare.com/api/whatsapp/webhook
```

`TUNNEL_HOSTNAME` is added to CORS by `CrawlerSettings.model_post_init`.
`YOUTUBE_REDIRECT_URI` is passed into the Google OAuth client code.

### Google Cloud Console

Every new Quick Tunnel URL must be registered as an authorized redirect
URI in the Google OAuth client:

```text
https://<random>.trycloudflare.com/api/youtube/oauth/callback
```

Google rejects OAuth callbacks that do not exactly match an authorized
redirect URI.

### WAHA Dashboard

The script sets this local `.env` value:

```env
WAHA_WEBHOOK_URL=https://<random>.trycloudflare.com/api/whatsapp/webhook
```

It also tries to push that URL into the WAHA session config through the
local WAHA API. If that best-effort update fails, set the same URL in the
WAHA dashboard manually.

If `WAHA_WEBHOOK_HMAC_SECRET` is configured, WAHA must also send the
matching `X-Webhook-Hmac-SHA256` header. Leave the secret empty when
using a WAHA setup that cannot sign webhook bodies.

## WAHA URL Naming

Use one variable per network context:

```env
# Backend container -> WAHA container. Browsers cannot resolve this name.
WAHA_BASE_URL=http://waha:3000

# Human/operator browser -> WAHA dashboard.
WAHA_DASHBOARD_URL=http://localhost:3000/dashboard

# WAHA -> public backend webhook through Cloudflare.
WAHA_WEBHOOK_URL=https://<random>.trycloudflare.com/api/whatsapp/webhook
```

`WAHA_BASE_URL=http://waha:3000` is correct inside Docker Compose. It is
not the dashboard URL and not the webhook URL.

## WAHA Image Architecture

On Apple Silicon, use the ARM image:

```env
WAHA_IMAGE=devlikeapro/waha:arm
```

The generic `devlikeapro/waha:latest` tag is amd64-only. Running it on an
arm64 Mac uses Docker emulation and can make the browser-based WEBJS
engine slow or stuck before the WAHA session reaches `WORKING`.

## Current Local Endpoints

- Local backend health: `http://localhost:8010/api/health`
- Public backend health: `https://<random>.trycloudflare.com/api/health`
- Local frontend: `http://localhost:8150`
- WAHA dashboard: `http://localhost:3000/dashboard`
