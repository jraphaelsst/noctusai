# Fleet single-VPS deploy-readiness audit (2026-05-21)

> Produced by the read-only fleet-audit agent. Ground truth for Phases 4–5.

## 1. Product roster
Registry source: `start.sh` `BEGIN/END_PRODUCTS_REGISTRY`. Single container per product; uvicorn serves API + baked SPA on the **backend port**. Dockerfile at `products/<slug>/backend/Dockerfile`.

| Product | Container | Internal port | Build target (compose) | Apex (`core`)? |
|---|---|---|---|---|
| core | noctus-core | 8000 | runtime-watch | **YES — apex** |
| erp-imobiliario | noctus-erp-imobiliario | 8001 | runtime-watch | no |
| personal-finance | noctus-personal-finance | 8002 | runtime-watch | no |
| therapy-platform | noctus-therapy-platform | 8003 | runtime-watch | no |
| seed | noctus-seed | 8004 | runtime-watch | no (template — **exclude from deploy**) |
| daily-life | noctus-daily-life | 8005 | runtime-watch | no |
| adconnect | noctus-adconnect | 8007 | runtime-watch | no |
| dev-team | noctus-dev-team | 8009 | runtime-watch | no (adds `/opt/dev_team`, needs `ANTHROPIC_API_KEY`) |
| social-wiring | noctus-social-wiring | 8011 | runtime-watch | no |

Every Dockerfile = 4-stage: `frontend-build` → `runtime` (slim, baked dist, **the shippable artifact**) → `runtime-watch` (adds node + bind-mount live-rebuild). Image tag: `ghcr.io/jraphaelsst/noctus-<slug>:${NOCTUS_IMAGE_TAG:-dev}`.

## 2. Base images
Two shared seed bases (`scripts/infra/build-base-images.sh`), built **before** any product image:
1. `noctus-seed-backend-base` ← `seed/docker/Dockerfile.backend-base`.
2. `noctus-seed-frontend-base` ← `seed/docker/Dockerfile.frontend-base`.
Each product `FROM noctus-seed-{backend,frontend}-base:dev` (the inherit seam). Order: bases first (cached once) → product layers.

## 3. Env vars
Root `.env` consumed by every compose via `env_file: ../../.env` (no per-product `.env`). Union (from `.env.example`): `SUPABASE_URL`, `SUPABASE_KEY`🔑, `SUPABASE_SERVICE_ROLE_KEY`🔑, `JWT_SECRET`🔑, `ANTHROPIC_API_KEY`🔑, `OPENAI_API_KEY`🔑, `WAHA_BASE_URL`, `WAHA_API_KEY`🔑, `WAHA_SESSION`, `WAHA_DASHBOARD_USERNAME`, `WAHA_DASHBOARD_PASSWORD`🔑, `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_KEY`. Optional/CI: `GHCR_TOKEN`🔑, `GHCR_USERNAME`, `NOCTUS_IMAGE_TAG`. **`VITE_*` are build-time baked** (Vite inlines them; empty → blank-page) ⇒ must be set when building images, not just at run.

## 4. Production-readiness gaps
- **Tunnels are EPHEMERAL quick-tunnels only.** Every `<slug>-tunnel` runs `cloudflared tunnel --url …` → random `*.trycloudflare.com`. KB `containerization.md §5b` marks named-tunnel promotion as "a future option" — **not built**. No `TUNNEL_TOKEN`, no ingress map, no persistent cloudflared service. **Primary gap.** (→ Engineer C: tunnel ingress.)
- **Compose builds `target: runtime-watch`** (node + bind-mounts + `vite build --watch`) — the dev shape. Deploy must build/run the slim `runtime` artifact via `image:` pulls. **No prod compose overlay exists** (deliberately deferred per KB §11b). (→ Engineer D: prod fleet compose.)
- **All 9 products container-ready** (Dockerfile + single-service compose + `/api/health`). `seed` = template → exclude. Deploy 8 products + 1 legacy extra.
- **Infra on the VPS** (`docker-compose.infra.yml`, project `noctusai-infra`): **Redis** needed (chatbot buffer/worker: core, erp-imobiliario, therapy-platform, social-wiring); **WAHA** only if real WhatsApp (else `FakeWahaClient`). **Postgres NOT needed** (remote Supabase). `noctus-net` is **external**.
- **Cold-boot CPU contention** disappears on the `runtime` image (dist baked, no in-container vite build) — another reason to deploy `runtime`, not `runtime-watch`.

## 5. Recommended single-VPS topology + resources
- **Topology:** ONE persistent named cloudflared (own container, `TUNNEL_TOKEN`, replacing per-product quick-tunnels) with ingress `noctusai.com → http://core:8000`, `<slug>.noctusai.com → http://<slug>:<port>` for the 8, all on `noctus-net`. Deploy slim `runtime` images (CI build → GHCR → `docker pull` on VPS via a **prod compose** with `image:` + `env_file` + no bind-mounts). Run `noctusai-infra` (Redis always; WAHA if live) on the same box. `restart: unless-stopped`.
- **Resources:** 8 products ≈ 200–400 MB RAM each (~2–4 GB total light load); Redis ~100–300 MB; WAHA (Chromium) ~0.7–1.5 GB; cloudflared ~50 MB; +1 legacy ~0.3–0.5 GB.
  - **Recommended: 4 vCPU / 8 GB RAM / 80 GB SSD.** Minimum 2 vCPU / 4 GB if WAHA stays Fake + low traffic.
  - Disk: ~600–900 MB per `runtime` image, deduped via shared bases → ~3–5 GB images + volumes/logs ⇒ 80 GB comfortable.

**Single biggest deliverable:** the missing **production compose + named-tunnel ingress** (build `runtime`, GHCR `image:` pulls, persistent `TUNNEL_TOKEN` cloudflared with apex+subdomain ingress). Everything else ships; this layer was deliberately deferred until a real deploy target existed → this migration.
