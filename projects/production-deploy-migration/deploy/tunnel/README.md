# NoctusAI named-tunnel — VPS production ingress runbook

One persistent Cloudflare **named** tunnel fronts the whole self-hosted
fleet on a single VPS: apex `noctusai.com` → `core`, each
`<slug>.noctusai.com` → its container, `legacy.noctusai.com` → the
standalone legacy container on `:5000`.

**Single source of truth:** [`ingress.yml`](./ingress.yml). To remap a slug,
edit ONE line there → regenerate the `config.yml` `ingress:` block →
re-create the DNS route → restart the tunnel. Nothing else hardcodes the
hostname→service map.

Files in this dir:

| File | Role |
|---|---|
| `ingress.yml` | THE map (hostname → `service:port`). Edit this. |
| `config.yml` | cloudflared named-tunnel config (derived from `ingress.yml`). |
| `compose.tunnel.yml` | runs the named tunnel on the VPS, on `noctus-net`. |
| `README.md` | this runbook. |

---

## NAMED vs the ephemeral quick-tunnel — why named persists

The repo today ships **quick tunnels** (`./start.sh tunnel <slug>` →
`cloudflare/cloudflared` with `--url http://<slug>:<port>`). A quick tunnel
mints a **random `*.trycloudflare.com` hostname that changes on every
restart** — no account, no DNS, fine for OAuth/webhook/demo testing, useless
for a stable public site.

A **named** tunnel is registered against your Cloudflare account and gets a
durable **`<TUNNEL_ID>`** + a credentials file. You attach **your own
hostnames** (`noctusai.com`, `social-wiring.noctusai.com`, …) to it via DNS
CNAMEs that point at `<TUNNEL_ID>.cfargotunnel.com`. Those CNAMEs are stable,
so the public URLs **survive container/tunnel restarts and VPS reboots** —
exactly what production needs. One named tunnel can serve unlimited
hostnames through one `ingress:` list (this is why we run ONE tunnel for the
whole fleet, not one per product).

Both modes pin **`--protocol http2`** — cloudflared's default `auto` opens
QUIC/UDP, which NATs drop in ~5–10 min and cannot re-register
(KB § PATTERNS/containerization.md § "The `--protocol http2` rule").

---

## One-time setup (on the VPS, or anywhere with the Cloudflare login)

`<PLACEHOLDERS>`: `<TUNNEL_NAME>` (e.g. `noctusai-prod`), `<TUNNEL_ID>` (UUID
printed by `create`), `<PATH>` (credentials JSON path).

### 1. Authenticate cloudflared to your Cloudflare account

```bash
cloudflared tunnel login
```

Opens a browser; pick the `noctusai.com` zone. Writes a cert to
`~/.cloudflared/cert.pem`.

### 2. Create the named tunnel

```bash
cloudflared tunnel create <TUNNEL_NAME>
```

Prints:
- the **`<TUNNEL_ID>`** (UUID) — paste into `config.yml` `tunnel:`.
- a **credentials file** at `~/.cloudflared/<TUNNEL_ID>.json` — this is the
  `<PATH>`. Copy it next to `config.yml` in this dir (or adjust the mount in
  `compose.tunnel.yml`). Keep it `chmod 600`.

### 3. Fill in `config.yml`

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /etc/cloudflared/<TUNNEL_ID>.json
```

(The in-container path; the host file is bind-mounted by
`compose.tunnel.yml`.) The `ingress:` block is already filled from today's
registry — keep it in sync with `ingress.yml`.

### 4. Create the stable DNS CNAMEs (one per hostname in `ingress.yml`)

`cloudflared tunnel route dns` creates a proxied CNAME
`<hostname> → <TUNNEL_ID>.cfargotunnel.com`:

```bash
cloudflared tunnel route dns <TUNNEL_NAME> noctusai.com
cloudflared tunnel route dns <TUNNEL_NAME> core.noctusai.com
cloudflared tunnel route dns <TUNNEL_NAME> erp-imobiliario.noctusai.com
cloudflared tunnel route dns <TUNNEL_NAME> personal-finance.noctusai.com
cloudflared tunnel route dns <TUNNEL_NAME> therapy-platform.noctusai.com
cloudflared tunnel route dns <TUNNEL_NAME> seed.noctusai.com
cloudflared tunnel route dns <TUNNEL_NAME> daily-life.noctusai.com
cloudflared tunnel route dns <TUNNEL_NAME> adconnect.noctusai.com
cloudflared tunnel route dns <TUNNEL_NAME> dev-team.noctusai.com
cloudflared tunnel route dns <TUNNEL_NAME> social-wiring.noctusai.com
cloudflared tunnel route dns <TUNNEL_NAME> legacy.noctusai.com
```

These records are durable. Run once; they persist across restarts.

> **Alternative — no `route dns`.** You can create the same records via the
> Cloudflare **dashboard** (DNS → add **CNAME**, name `<hostname>`, target
> `<TUNNEL_ID>.cfargotunnel.com`, **Proxied / orange cloud ON**) or the
> Cloudflare **API** (`POST /zones/<zone_id>/dns_records` with
> `{"type":"CNAME","name":"<hostname>","content":"<TUNNEL_ID>.cfargotunnel.com","proxied":true}`).
> Use this if the tunnel runs somewhere without the zone-scoped cert from
> step 1.

### 5. Run the tunnel (on the VPS, alongside the fleet)

```bash
docker network create noctus-net          # one-time (start.sh also ensures it)
./start.sh                                  # the product fleet (separate project)
docker compose -f deploy/tunnel/compose.tunnel.yml up -d
docker logs -f noctus-tunnel                # confirm "Registered tunnel connection"
```

Verify: `curl -I https://noctusai.com/api/health` → 200 from `core`.

---

## Apply an ingress change (e.g. rename a slug)

The user WILL rename slugs. The flow is one edit + re-apply:

1. **Edit `ingress.yml`** — change the one line (hostname and/or service).
2. **Regenerate `config.yml`** `ingress:` to match (keep the `http_status:404`
   catch-all last).
3. **DNS:** add the new CNAME if the hostname changed —
   `cloudflared tunnel route dns <TUNNEL_NAME> <new-hostname>` (or dashboard/
   API per step 4). Old CNAMEs can be deleted from the dashboard if retired.
4. **Reload the tunnel** to pick up the new config:
   ```bash
   docker compose -f deploy/tunnel/compose.tunnel.yml up -d --force-recreate
   ```

No per-product file is touched — the map lives in exactly one place.

---

## Notes

- The product containers need **no change** for named-tunneling. The seed's
  same-origin SPA contract injects `window.location.origin` as the API base
  (KB § PATTERNS/containerization.md § same-origin), so each subdomain serves
  its SPA + API correctly with zero per-product config.
- The `legacy` container must be attached to `noctus-net`
  (`docker network connect noctus-net <legacy-container>` or a `networks:`
  entry in its compose) so cloudflared resolves `http://legacy:5000`.
- These artifacts are **for later** — nothing here goes live until the VPS
  setup runs the commands above.
