---
slug: production-deploy-tooling
origin:
  - scripts/deploy/01-provision-vps.sh
  - scripts/deploy/02-deploy-stack.sh
  - scripts/deploy/03-setup-tunnel.sh
  - scripts/deploy/DEPLOY.md
intended_noc_destination: templates/seed-workspace-docker/scripts/deploy/
layer_rationale: |
  Operator-facing deploy automation. Every Docker-Compose-based noc
  product needs the same three steps (provision Linux host, deploy
  stack, wire Cloudflare Tunnel for a stable HTTPS URL) — scaffolding
  this once in the seed template lets every new product inherit a
  production path from day one instead of inventing it ad-hoc when
  the dev workflow stops being enough.
seed_first_analysis: |
  Q1 — Cross-product candidate? YES. The path from "dev on macOS"
  to "production on a Linux VPS with stable URL" is identical for
  every noc product that talks to external OAuth providers. The
  scripts are generic over product name (only DEPLOY.md mentions
  specific env vars).
  Q2 — Variance? Per-product variance lives in the .env values +
  the list of required env vars (each product has its own set).
  Mechanic is the same.
  Q3 — Existing seed coverage? None. `start.sh` / `stop.sh` /
  `refresh_cf_tunnel.sh` cover the dev loop; nothing covers the
  one-time-to-prod transition.
  Q4 — Fake+Real? N/A (shell + cloudflared CLI).
  Q5 — Migration cost? Low. Copy 4 files; replace product-specific
  env var list in 02-deploy-stack.sh + DEPLOY.md (or factor it out
  to a `<product>-env-template.txt` per product).
  Q6 — Premature lift risk? Low. The Cloudflare Tunnel + VPS
  pattern is mature and stable; the scripts are thin wrappers over
  documented Cloudflare APIs.
dependencies_on_other_additions:
  - recreate-script   # 02-deploy-stack.sh references the same recreate
                      # pattern; future versions could call scripts/recreate.sh
promoted_on: not-yet
---

## Why this addition exists

User requested a permanent production deployment so they can stop
hitting:
- Docker Desktop on macOS networking issues (large TLS bodies fail)
- Ephemeral Cloudflare Quick Tunnel URLs that rotate on every restart
- The "OAuth provider dashboard re-registration tax" each time the URL
  changes

Real production needs a stable URL on their own domain. Three-script
shape lets them:
1. Provision a fresh Linux box (or re-provision after disaster)
2. Deploy the app stack with current env values
3. Wire the Cloudflare Tunnel for stable HTTPS

Each script is idempotent — safe to re-run after any change.

## What ships

### `01-provision-vps.sh`
Bootstraps a fresh Ubuntu 24.04 VPS:
- apt installs: docker, docker-compose plugin, git, ufw, cloudflared, jq
- Creates `noctus` deploy user (docker group, SSH key copied from root)
- UFW firewall: deny inbound except SSH (Cloudflare Tunnel handles
  inbound HTTPS, so we never need 80/443 publicly open — better
  security posture than a typical "open 443" deploy)
- App dir: `/opt/noctus`
- Idempotent

### `02-deploy-stack.sh`
Runs as the deploy user. Clones the workspace + noc repos, sets up
the same symlink shape as the local-dev workspace, writes `.env` from
the env vars the operator exports before running, brings the docker-
compose stack up, health-polls.

The `.env` template inside the script is product-specific (the env var
list reflects what this product reads). When promoting to noc, swap
the template generation step for `cat $PRODUCT_DIR/.env.production.template`
or similar.

### `03-setup-tunnel.sh`
Runs as root. Creates the Cloudflare Named Tunnel via API (or reuses
existing), rotates secret, writes credentials + ingress config, creates
or updates the DNS CNAME (proxied), installs cloudflared as a systemd
service, starts it.

Tunnel→stack routing: tunnel ingress goes to `http://localhost:8090`
(the nginx proxy container, which already path-routes to backend /
frontend / WAHA). This means a single subdomain serves the whole stack.

### `DEPLOY.md`
Operator runbook. Pre-reqs checklist, step-by-step walkthrough,
maintenance ops, troubleshooting table, disaster recovery procedure.
Written in present tense as a runbook, not as marketing — operators
read this when something's broken at 2 AM.

## Integration notes for noc-side

When promoting:

1. **Move `scripts/deploy/` → `templates/seed-workspace-docker/scripts/deploy/`.**
   Scaffolded into every new product.

2. **Factor out the `.env` generation** from `02-deploy-stack.sh` into
   `<product>/.env.production.template` so each product owns its
   env-var list. The script just does
   `envsubst < .env.production.template > .env`.

3. **Parameterize Tunnel ingress** in `03-setup-tunnel.sh`. Currently
   hardcodes a single ingress rule pointing at the proxy. For products
   that want multi-subdomain (api.x.com + waha.x.com + frontend.x.com),
   the script needs a config-table input.

4. **Document the architecture** in
   `KB § PATTERNS/production-deployment.md` covering the
   VPS-plus-Cloudflare-Tunnel pattern as the seed's recommended
   production posture. Pair with `KB § PATTERNS/containerization.md`.

5. **Cloudflare Account ID discovery** — the current script requires
   the operator to paste it; could fetch it via the token if the
   token has the right scope. Minor UX improvement.

## Future work (NOT in this promotion)

- **TLS-secured local-only mode** — for operators who want a real
  HTTPS test setup without a domain. Use mkcert or self-signed.
- **Multi-environment support** — staging vs production. Today
  scripts assume single env per VPS.
- **Backup automation** — periodic dump of Supabase credentials +
  WAHA session volume to S3-compatible storage. Currently manual.
- **Monitoring stack** — sidecar Prometheus + Grafana for
  per-service metrics. Today: `docker compose logs`.
