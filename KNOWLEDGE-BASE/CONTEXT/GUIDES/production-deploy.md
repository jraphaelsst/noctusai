# GUIDE — Production deploy of the noc fleet to a VPS

> **What this is.** The fleet-grade, evidence-tested runbook for putting noc products **live on a real domain on a single VPS**. Distilled from the 2026-05-21 `noctusai.com` migration (Replit/Coolify → Cloudflare/Hostinger). Self-contained: the durable procedure + lessons live here, not in the (archivable) project folder.
>
> **NOT** the local "put X online" drill (`KB § GUIDES/deploy-workspace-online.md` = `./start.sh` + quick-tunnel on your machine). This is the *external server* deploy.

---

## 0 · Topology (the end state)

```
Cloudflare (DNS + edge TLS + named tunnel) ──┐
                                              ├─→ ONE VPS (Hostinger/any)
your registrar (NS → Cloudflare)             │      docker, external `noctus-net`
                                              │      ├─ product containers (one each, runtime image)
                                              │      ├─ infra: redis (+ optional waha)
                                              │      └─ cloudflared (named tunnel)  ← edge option B
```

- **Compute = ONE box.** The fleet is a docker-compose Python stack — it cannot run on Workers/Pages. CF owns the *edge* (DNS/TLS/tunnel/WAF); the VPS owns the *compute*. (`KB § PATTERNS/containerization.md`.)
- **`noctus-net`** is the external shared bridge every layer joins (products + infra + edge), so containers reach each other by service name with **no published host ports**.
- **Two edge options** (pick by what the registrar lets you do — see §4):
  - **A · Caddy on real subdomains** — works with only DNS-*record* editing (no nameserver control). Auto-TLS via Let's Encrypt. Interim/standalone.
  - **B · Cloudflare named tunnel** — needs the **zone on Cloudflare** (nameservers delegated). No open ports, CF edge in front. The target end state.

---

## 1 · Code delivery = git (never rsync)

The VPS gets code by **cloning from GitHub via a read-only deploy key** — not file-copy. Redeploy = `git pull` + rebuild.

```bash
# ON THE VPS — generate a deploy key
ssh-keygen -t ed25519 -f /root/.ssh/github_deploy -N "" -C "vps-deploy-readonly"
cat /root/.ssh/github_deploy.pub        # → add as a READ-ONLY Deploy Key on the repo
ssh-keyscan -t ed25519 github.com >> /root/.ssh/known_hosts
# clone
GIT_SSH_COMMAND="ssh -i /root/.ssh/github_deploy" git clone git@github.com:<org>/<repo>.git /opt/noctus/<repo>
```

- **Push local `main` first** — `origin/main` must be current (a clone gets `origin`, not your local unpushed commits). Verify `git log origin/main..HEAD` is empty before relying on the clone.
- **Secrets do NOT travel via git.** The root `.env` is gitignored → deliver out-of-band (one-time `scp` of the file). `.env.services`/connector `.env`s likewise.

## 2 · Build ON the VPS (no GHCR needed for a small fleet)

Product images are the slim `--target runtime` shape (baked dist, node-absent). `deploy/fleet/build-and-push.sh --no-push` builds them locally; for a subset, build by hand:

```bash
cd /opt/noctus/<repo>
bash scripts/infra/build-base-images.sh dev          # seed bases — product Dockerfiles FROM :dev (hardcoded)
set -a; source .env; set +a                           # VITE_SUPABASE_* from .env
docker build --target runtime -f products/<slug>/backend/Dockerfile \
  -t ghcr.io/<org>/noctus-<slug>:latest \
  --build-arg VITE_SUPABASE_URL="$VITE_SUPABASE_URL" \
  --build-arg VITE_SUPABASE_PUBLISHABLE_KEY="$VITE_SUPABASE_PUBLISHABLE_KEY" \
  --build-arg VITE_CORE_URL="https://core.<domain>" \
  --build-arg VITE_CORE_API_URL="https://core.<domain>" .
```

> ⚠️ **`VITE_*` are BAKED at build time** (Vite inlines `import.meta.env.VITE_*`). `VITE_CORE_URL`/`VITE_CORE_API_URL` MUST be the **public** URL where `core` is served — `core`'s own FE reads `VITE_CORE_API_URL` for its API (`products/core/frontend/src/lib/api.ts`); other products' own API is same-origin (`VITE_BACKEND_API_URL` define-injected to `window.location.origin`). Bake `localhost` → broken public app; rebuild to fix. (`KB § PATTERNS/boundary-contract-tests.md` B1.)

## 3 · Bring up (infra + products on `noctus-net`)

```bash
docker network create noctus-net 2>/dev/null || true     # one-time
docker compose -f deploy/fleet/compose.infra.prod.yml up -d        # redis (+ --profile waha if WhatsApp)
docker compose -f deploy/fleet/docker-compose.prod.yml up -d core <slug>...   # subset = a wave
# verify (ports are internal — exec curl, no host publish)
docker exec noctus-<slug> curl -fsS http://localhost:<port>/api/health
```

Products use **remote Supabase** (not local postgres) + `redis://noctus-redis:6379` over `noctus-net`. `restart: unless-stopped` survives reboots.

## 4 · Edge — pick A or B by what your registrar allows

**First check what you can do at the registrar.** Many platform-resold domains (Replit/Wix/…) only expose **DNS-record editing**, not nameserver delegation — see `KB § INTEGRATIONS/` and the domain-reseller note in memory. `whois <domain>` finds the real registrar; the platform UI ≠ the registrar.

### Option A — Caddy on real subdomains (DNS-records-only path)

Add `A <slug> → <VPS-IP>` records at the registrar. Caddy reverse-proxies + auto-issues per-host LE certs (HTTP-01). Needs ports 80/443 free (displace any prior proxy first — see §5).

```caddyfile
{ email you@domain }
core.<domain>   { reverse_proxy core:8000 }
<slug>.<domain> { reverse_proxy <service>:<port> }
```
```bash
docker compose -f deploy/caddy/compose.caddy.yml up -d   # joins noctus-net, publishes :80/:443
```

### Option B — Cloudflare named tunnel (zone-on-CF path; the target)

Needs the zone active on Cloudflare (nameservers → CF). Then:
```bash
# create the tunnel (CF API or `cloudflared tunnel create`); config_src=local for config.yml ingress
# creds JSON on the VPS, chown 65532:65532 chmod 600 (cloudflared runs nonroot)
docker compose -f deploy/tunnel/compose.tunnel.yml up -d   # cloudflared --protocol http2
# DNS routes: cloudflared tunnel route dns <name> <hostname>  (or proxied CNAME → <id>.cfargotunnel.com)
```
Ingress is a single source of truth (`deploy/tunnel/ingress.yml`) → remap a slug = 1 edit + re-apply. `--protocol http2` is pinned (QUIC dropped by NATs).

### Migrating A → B later (zero URL change)

Real subdomains chosen in A are the **final URLs**. When the domain reaches Cloudflare: bring up the tunnel (B), create the CNAMEs, verify, then stop Caddy. The `<slug>.<domain>` URLs never change — only the plumbing.

## 5 · Decommissioning a prior PaaS (e.g. Coolify) — preserve stateful data

If the box ran a PaaS managing stateful services (n8n/waha/postgres/redis), migrate them to **raw compose reusing the EXISTING named volumes** before removing the PaaS:

```yaml
# deploy/services/compose.services.yml — external volumes = the PaaS's data, untouched
volumes:
  n8n-data:      { external: true, name: <paas-prefix>_n8n-data }
  waha-sessions: { external: true, name: <paas-prefix>_waha-sessions }
  # ...
```
```bash
docker stop <paas>-n8n <paas>-waha <paas>-postgres        # brief downtime starts
docker compose --env-file .env.services -f deploy/services/compose.services.yml up -d postgres n8n waha
# VERIFY data survived (volume mounts + sizes) BEFORE touching the proxy → rollback = restart the PaaS containers
docker stop <paas>-proxy && docker compose -f deploy/caddy/compose.caddy.yml up -d   # proxy swap
# only after all green: docker rm the PaaS containers + control-plane; rm its host data dir; keep DATA volumes
```
- **WAHA resumes without QR:** auth persists in the sessions volume but WAHA doesn't auto-start saved sessions → `POST /api/sessions/<name>/start`.
- Keep PaaS containers **stopped, not deleted**, until verified green (rollback net).

## 6 · Lessons (evidence-tested 2026-05-21 — heed these)

| Gotcha | Rule |
|---|---|
| **LE DNS negative-cache** | NEVER add a host to Caddy/LE before its A-record exists — a failed ACME poisons LE's NXDOMAIN cache (SOA neg-TTL, ~1h). Sequence: A-record → then Caddy. Recover: poll `dig @1.1.1.1/@8.8.8.8/@9.9.9.9` until it resolves → `docker restart` the proxy (clears ACME backoff). |
| **compose `${VAR:?}`** | `docker compose` interpolates required vars on EVERY subcommand (`ps`/`exec`, not just `up`) → pass `--env-file` everywhere. |
| **`depends_on` over-starts** | `up -d a b c` also starts their `depends_on` services → can collide on a shared network alias. Name only what you need + drop needless deps. |
| **cloudflared nonroot (uid 65532)** | root-owned `0600` creds = unreadable → `chown 65532:65532`, keep `0600` (not world-readable). |
| **local resolver lies** | your machine's negative-cache outlives the world's → verify externally with `curl --resolve <host>:443:<ip>`, not the bare hostname. |
| **single-file bind-mount goes stale on `git pull`** | A container bind-mounting a SINGLE config file (`./Caddyfile:/etc/caddy/Caddyfile`, `./config.yml:…`) keeps the **original inode**. `git pull`/editors replace files via rename → a NEW inode → the container still sees the OLD content, so `caddy reload` (or `cloudflared` re-read) applies a **stale config silently** (e.g. a just-added vhost is missing, no cert issued). **Verify** `docker exec <c> grep <new-thing> /etc/.../file` (it'll be absent) → **`docker restart <container>`** (re-establishes the mount against the current inode), not just `reload`. Proper fix: bind-mount the **directory**, not the file. Bit the `legacy.noctusai.com` Caddy route. |
| **Django `ALLOWED_HOSTS` + healthcheck** | a strict `ALLOWED_HOSTS` (e.g. `legacy.noctusai.com`) makes a bare `curl localhost` 400 (`DisallowedHost`) → the compose healthcheck must send the real Host: `curl -fsS -H "Host: <domain>" http://localhost:<port>/`. |
| **product LLM = OpenAI/Gemini** | `noctusai_lib.integrations.llm` ships openai/gemini/fake — **no Anthropic provider**; default `openai`/`gpt-4o-mini`; key via `resolve_credential` Tier-3 env fallback (`OPENAI_API_KEY`). ANTHROPIC only for `dev-team` (agno). |
| **platform-auto-installed deps missing from the manifest (external/absorbed app)** | A Replit/PaaS packager auto-installs deps **without writing them to the committed manifest** → a clean reproducible `docker build` misses them. Hit **twice** in the legacy `one-permutas` build: ① **npm root-hoist** — `@supabase/supabase-js` lived in the MONOREPO ROOT `package.json` (resolved via hoisted parent `node_modules`), invisible to an isolated `frontend/` `npm ci` → `TS2307: Cannot find module`; ② **pip framework-implicit** — `Pillow` (Django `ImageField` requires it) wasn't in `requirements.txt` at all → `fields.E210` at the `manage.py` system check. **Fix:** diff actual imports (+ framework-implicit deps like Pillow) against the manifest the Dockerfile installs; add the missing ones to the Dockerfile (`npm install --no-save <pkg>` / `pip install … <pkg>`), pinned. **Surface them at BUILD time** — run the frontend `build` + `manage.py collectstatic`/`check` in the Dockerfile so a missing dep fails the build, not prod. (Bonus Django gotcha: a prod-settings *shim* must sit in the **config package** `backend/backend/` next to `settings.py` for `DJANGO_SETTINGS_MODULE=backend.settings_prod` to import.) |
| **VPS git deploy key must be pinned** | A read-only GitHub deploy key that *authenticates* (`ssh -i <key> -T git@github.com` → "successfully authenticated") still fails `git fetch`/`git pull` with `git@github.com: Permission denied (publickey)` from a fresh SSH session — git uses the **default** identity, not the deploy key, unless told to. The clone often worked via an inline `GIT_SSH_COMMAND=` or a loaded `ssh-agent` that **doesn't persist**. **Durable fix:** pin it on the repo — `git config core.sshCommand 'ssh -i ~/.ssh/<deploy_key> -o IdentitiesOnly=yes'` (or a `~/.ssh/config` `Host github.com` block). Without it the "redeploy = `git pull`" pipeline silently breaks on the next session. To push a single file without a full pull: `git fetch && git checkout origin/main -- <path>`. |
| **lost SSH → recover via the host console (box stays up)** | If your VPS login key stops being accepted (`Permission denied (publickey)`) — e.g. a PaaS teardown rewrote `/root/.ssh/authorized_keys` — the box is usually fine (sites still serve); you only lost the shell. Re-add your pubkey from the provider's **browser/VNC console** (Hostinger hPanel → VPS → Browser terminal): `echo '<pubkey>' >> /root/.ssh/authorized_keys`. (Gotcha: a deploy key distributed as a *folder* `~/.ssh/<name>/id_ed25519` — point `ssh -i` at the inner file; the dir needs `700`, not `600`.) |
| **apex = same-origin, no rebuild** | Serving a noc product at the bare apex (`noctusai.com` → `core:8000`) needs **no rebuild and no CORS change** — the seed FE calls its backend at `window.location.origin` (`VITE_BACKEND_API_URL` define-injection), so it just works at whatever host Caddy routes. `VITE_CORE_API_URL` is only for *other* products calling core. Add the Caddy vhost, `docker restart` the proxy, done. |

## 7 · Artifacts + graduation

The composes/Caddyfile/scripts referenced live under a project's `deploy/{fleet,services,tunnel,caddy,legacy}/` while a migration is active. **They should graduate to a durable home** (`scripts/infra/` or a `deploy/` template set, or a `noctus.dev.deploy` MCP tool) once the shape stabilizes — that is the "automate by evidence" follow-up. Until then, copy from the most recent deploy project and adapt the placeholders.

> **MCP tools that operate the deploy:** `mcp/hostinger` (VPS power/metrics), `mcp/cloudflare` (zones/DNS/tunnel — used to create the named tunnel here), `mcp/waha` (session ops), `mcp/n8n` (workflow ops). See `KB § MCP-SERVERS/`.
