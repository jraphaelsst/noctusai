# Production deploy runbook — Hostinger VPS + Cloudflare Tunnel

> **Target:** Permanent deployment at `https://bot.noctusai.com` on a
> Hostinger VPS, fronted by a Cloudflare Named Tunnel.
> **Reproducible:** all three deploy scripts are idempotent — re-run
> them after any change without fear.

## Prerequisites checklist

Before starting, you need:

- [ ] **Hostinger VPS** (Ubuntu 24.04 recommended, 2 vCPU / 4 GB RAM minimum)
- [ ] **SSH access** to the VPS (root, with your public key in `authorized_keys`)
- [ ] **`noctusai.com`** added to Cloudflare (Free plan is fine)
- [ ] **Nameservers** at the registrar (Replit) updated to Cloudflare's
- [ ] **DNS propagation confirmed** — `dig NS noctusai.com` returns Cloudflare nameservers
- [ ] **Cloudflare API token** with scopes:
  - `Account:Cloudflare Tunnel:Edit`
  - `Zone:DNS:Edit` on `noctusai.com`
  - `Zone:Zone Settings:Read` on `noctusai.com`
- [ ] **Cloudflare Account ID** (find at the bottom-right of any zone overview page in the dashboard)
- [ ] **All product credentials** ready to paste into env:
  - `META_APP_ID`, `META_APP_SECRET`, `META_SYSTEM_USER_TOKEN`
  - `OPENAI_API_KEY`
  - `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_MAPS_API_KEY`
  - `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
  - `ENCRYPTION_KEY` (Fernet; generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
  - `VISTA_BASE_URL`, `VISTA_API_KEY`
  - `WAHA_API_KEY`, `WAHA_DASHBOARD_USERNAME`, `WAHA_DASHBOARD_PASSWORD`
  - `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` (if YouTube uploads needed)
  - `SMTP_USER`, `SMTP_PASSWORD` (for email notifications)

## Step 1 — Provision the VPS

SSH into the VPS as root, then run:

```bash
ssh root@<VPS_IP> 'bash -s' < scripts/deploy/01-provision-vps.sh
```

This installs Docker, cloudflared, jq, creates the `noctus` deploy user
(with your SSH key copied over), configures UFW firewall (SSH-only),
and creates `/opt/noctus/`.

Idempotent — re-run anytime to verify state.

## Step 2 — Deploy the application stack

Switch to the deploy user, set the required env vars, run script 02:

```bash
ssh root@<VPS_IP>
su - noctus

# Create a secrets file (do NOT commit this anywhere)
cat > ~/secrets.env <<EOF
export GIT_REPO=https://github.com/<your-org>/noctusai-youtube-crawler.git
export GIT_BRANCH=integration/oauth-discovery
export NOC_REPO=https://github.com/<your-org>/noctusai.git
export TUNNEL_HOSTNAME=https://bot.noctusai.com

export META_APP_ID=...
export META_APP_SECRET=...
export META_SYSTEM_USER_TOKEN=...
export OPENAI_API_KEY=sk-proj-...
export GOOGLE_OAUTH_CLIENT_ID=...
export GOOGLE_OAUTH_CLIENT_SECRET=...
export GOOGLE_MAPS_API_KEY=...
export SUPABASE_URL=https://....supabase.co
export SUPABASE_KEY=...
export SUPABASE_SERVICE_ROLE_KEY=...
export ENCRYPTION_KEY=...
export VISTA_BASE_URL=...
export VISTA_API_KEY=...
export WAHA_API_KEY=...
export WAHA_DASHBOARD_USERNAME=...
export WAHA_DASHBOARD_PASSWORD=...
export YOUTUBE_CLIENT_ID=...
export YOUTUBE_CLIENT_SECRET=...
export SMTP_USER=...
export SMTP_PASSWORD=...
export WHATSAPP_AUTHORIZED_NUMBERS=+5511...
EOF
chmod 600 ~/secrets.env

source ~/secrets.env
bash /path/to/scripts/deploy/02-deploy-stack.sh
```

Script clones the repos, writes `.env`, runs `docker compose up -d --build`,
health-polls. Repository ships with the repo branch already pointing at
the integration tree; you don't need to install Python locally.

### Supabase migrations (production database)

The `DATABASE_BACKEND=sqlite` path applies the `*.sql` files automatically
via `apply_sqlite_migrations.py`. The Supabase production path does NOT —
each migration in `products/youtube-crawler/backend/migrations/*.sql` must
be applied manually after a deploy that adds new ones.

Apply via either:

- **Supabase Studio**: SQL editor → paste the file content → run.
- **Supabase CLI**: `supabase db push` against the linked project.
- **MCP `apply_migration` tool**: hand the file path to your tooling.

Migrations to date (apply in numeric order):

| # | Adds |
|---|---|
| `001_seed.sql` | Schema + base tables |
| `002_credentials.sql` | OAuth credential store |
| `003_upload_jobs.sql` | Upload pipeline |
| `004_video_cache.sql` | YT video metadata cache |
| `005_notifications.sql` | Notification recipients + log |
| `006_product_code.sql` | `upload_jobs.product_code` |
| `007_conversation_messages.sql` | WhatsApp message audit |
| `008_thumbnail_url.sql` | `upload_jobs.thumbnail_url` (post-upload tail) |

Always run them in order — each ALTER assumes prior columns exist. After
applying, restart the app container so the Pydantic schemas reload.

## Step 3 — Wire the Cloudflare Tunnel

As root (the systemd install needs it):

```bash
sudo -E bash <<'WRAP'
export CLOUDFLARE_API_TOKEN=cf_token_from_dashboard
export CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id
export ZONE=noctusai.com
export HOSTNAME=bot.noctusai.com
bash /path/to/scripts/deploy/03-setup-tunnel.sh
WRAP
```

Script creates the tunnel via API, writes credentials + config, creates
the DNS CNAME record (proxied), installs cloudflared as a systemd
service, starts it.

After ~10 seconds:
```bash
curl https://bot.noctusai.com/api/health
# → {"status":"ok","version":"0.1.0","product":"YouTube Crawler"}
```

## Step 4 — Update OAuth dashboards

Now that `bot.noctusai.com` is live, update the provider dashboards:

### Meta (developers.facebook.com)
- **App Domains** (Settings → Basic): replace tunnel host with `bot.noctusai.com`
- **Valid OAuth Redirect URIs** (Facebook Login → Settings): set to
  `https://bot.noctusai.com/api/meta/oauth/callback`
- (System User Token path doesn't actually need this for runtime, but
  having it correct lets you fall back to user OAuth later if needed.)

### Google (console.cloud.google.com)
- **APIs & Services → OAuth Consent Screen**: ensure all scopes you use
  are in the consent screen's scope list
- **APIs & Services → Credentials → OAuth 2.0 Client → Authorized
  redirect URIs**: add `https://bot.noctusai.com/api/calendar/oauth/callback`
- For YouTube OAuth client (if separate): add
  `https://bot.noctusai.com/api/youtube/oauth/callback`

## Step 5 — Re-pair WhatsApp

The new WAHA container has no logged-in session. Pair it:

1. Open `https://bot.noctusai.com/waha/dashboard` (or SSH-tunnel
   `localhost:3000/dashboard`).
2. Log in with `WAHA_DASHBOARD_USERNAME` / `WAHA_DASHBOARD_PASSWORD`.
3. **Sessions → Start New** → name `default` → start.
4. Open the session, scan the QR with your WhatsApp.
5. Wait for status `WORKING`.

Webhook URL on the session is auto-configured from the WAHA_WEBHOOK_URL
env var, but verify via the WAHA API:

```bash
curl -H "X-Api-Key: $WAHA_API_KEY" https://bot.noctusai.com/waha/api/sessions/default \
  | jq '.config.webhooks'
```

Expected:
```json
[{"url": "https://bot.noctusai.com/api/whatsapp/webhook", "events": [...]}]
```

If empty, register manually:
```bash
curl -X PUT -H "X-Api-Key: $WAHA_API_KEY" -H "Content-Type: application/json" \
  https://bot.noctusai.com/waha/api/sessions/default \
  -d '{"config":{"webhooks":[{"url":"https://bot.noctusai.com/api/whatsapp/webhook","events":["message","message.any","session.status"]}]}}'
```

## Step 6 — End-to-end smoke test

```bash
# 1. Health
curl https://bot.noctusai.com/api/health
# → {"status":"ok",...}

# 2. Meta status (should be system_user mode with real assets visible)
curl https://bot.noctusai.com/api/meta/status | jq
# → {"auth_mode":"system_user","pages_count":1,"instagram_accounts_count":1,...}

# 3. Google scope status
curl https://bot.noctusai.com/api/google/scopes | jq

# 4. Chat surface
# Open https://bot.noctusai.com/chat in your browser
# Ask: "quantos seguidores temos no Instagram?"
# Expected: bot calls list_instagram_accounts, replies with the real number

# 5. WhatsApp
# Send "oi" to your bot's WhatsApp number
# Expected: bot replies within ~5 seconds
```

## Maintenance — common operations

### View logs
```bash
# All services
ssh noctus@<VPS_IP> 'cd /opt/noctus/noctusai-youtube-crawler && docker compose logs -f --tail=100'

# Specific service
ssh noctus@<VPS_IP> 'cd /opt/noctus/noctusai-youtube-crawler && docker compose logs -f app'

# Cloudflare tunnel
ssh root@<VPS_IP> 'journalctl -u cloudflared -f'
```

### Update to latest branch
```bash
ssh noctus@<VPS_IP>
cd /opt/noctus/noctusai-youtube-crawler
git pull
docker compose up -d --build app
```

### Restart a service (env unchanged)
```bash
docker compose restart app    # keeps existing env
```

### Restart with NEW env values
```bash
# Edit /opt/noctus/noctusai-youtube-crawler/.env or rerun 02-deploy-stack.sh
docker compose up -d --force-recreate app
```

### Rotate Cloudflare tunnel secret
Re-run `03-setup-tunnel.sh` — it rotates the secret automatically and
restarts the cloudflared service.

### Backup the credential store
The encrypted Meta/Google/YouTube tokens live in the Supabase
`youtube_crawler.credentials` table. Supabase auto-backs-up; for an extra layer:
```bash
ssh noctus@<VPS_IP> 'cd /opt/noctus/noctusai-youtube-crawler && \
  docker compose exec -T app python -c "
from app.dependencies import get_admin_client
import json
client = get_admin_client()
rows = client.schema(\"youtube_crawler\").table(\"credentials\").select(\"*\").execute().data
print(json.dumps(rows, default=str, indent=2))
"' > backup-credentials-$(date +%Y%m%d).json
```

## Troubleshooting

| Symptom | First check |
|---|---|
| `curl https://bot.noctusai.com/api/health` returns 521/522/525 | `journalctl -u cloudflared` — tunnel not connected to edge |
| 502 from Cloudflare | App container down: `docker compose ps`, `docker compose logs app` |
| Meta `pages_count: 0` | `META_SYSTEM_USER_TOKEN` not set OR System User lost asset access in BM |
| WhatsApp bot not replying | WAHA session not WORKING OR webhook URL stale. Check `/waha/api/sessions/default` |
| OpenAI Connection error | DNS or upstream issue; this is server-side now so unlikely the macOS Docker issue. Check `journalctl` |
| Tunnel cert error | `cloudflared` not running. `systemctl restart cloudflared` |

## Disaster recovery — full rebuild from scratch

If the VPS dies / gets wiped:

1. Provision a new VPS (same provider or different — scripts are
   distro-agnostic-ish, tested on Ubuntu 24.04).
2. Paste your SSH pubkey into Authorized Keys.
3. Run `01-provision-vps.sh`.
4. Restore `~/secrets.env` from your password manager / safe backup.
5. Run `02-deploy-stack.sh` and `03-setup-tunnel.sh`.
6. DNS CNAME points at the **tunnel ID**, which is reused if same name —
   so the hostname doesn't change.
7. Restore the WhatsApp QR pair (re-scan).

Total time: ~15 min.

The Supabase credentials table survives because it's not on the VPS.
WAHA's session is on the VPS volume; if that's gone, re-scan QR is the
only step.
