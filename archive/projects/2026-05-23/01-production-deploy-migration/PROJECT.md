# Production deploy & domain cutover — Project Document

> **Living document.** Migrating `noctusai.com` from the current Replit-hosted single app to the self-hosted NoctusAI fleet, moving the current app to `legacy.noctusai.com`, with Cloudflare as the consolidation point. Updated as we learn.

- **Created:** 2026-05-21
- **Last updated:** 2026-05-21
- **Status:** Discovery ✅ → architecture confirming (tunnel justification under discussion) → execution not started
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com) · Claude (architect)
- **Related docs:** `KB § CONTEXT/05-INFRASTRUCTURE.md` (stale for apex — see findings) · `KB § PATTERNS/containerization.md` (tunnel seam) · `KB § GUIDES/deploy-workspace-online.md` (local drill, NOT prod) · archived prod runbook `archive/projects/2026-05-16/03-social-wiring-absorption/reference/scripts/deploy/DEPLOY.md`
- **Project slug:** `production-deploy-migration` @ `projects/production-deploy-migration/` (platform-infra)
- **Findings log:** `projects/production-deploy-migration/findings.md`

---

## 1. Context & Purpose

`noctusai.com` currently serves a single Replit-hosted app — *"Sistema de Permutas Imobiliárias"*. The goal is to make `noctusai.com` serve the **NoctusAI multi-product fleet** (this repo) instead, while preserving the current app at **`legacy.noctusai.com`** (instant rollback + continuity). The user wants infrastructure consolidated into **Cloudflare** as much as possible. This is a live-domain cutover, so it is outward-facing and must be zero-downtime + reversible.

---

## 2. Confirmed constraints

- **CF approach** — Cloudflare **Named Tunnel** to the VPS fleet (user-selected; justification in progress). *(Maximizes "everything in Cloudflare"; matches the platform's built-in cloudflared seam.)*
- **Apex routing** — `noctusai.com` = `core` control-plane; each product at `<slug>.noctusai.com`. *(Multi-product fleet.)*
- **Deploy in WAVES — Wave 1 = `core` + `erp-imobiliario` + `social-wiring`** (user 2026-05-21; core added — it's the apex). Prove + **document** the process on these three, then Wave 2 (the other 5) from the documented runbook — **Wave 2 is PARKED, do not plan now**. Apex (`noctusai.com`) → `core` IS in Wave 1. *(Pilot-products-first cadence — `KB § PATTERNS/project-execution.md §2.12`. The `deploy/` artifacts cover all products; a wave just builds/brings-up + routes a subset.)*
- **Slug remap must be EASY** — the user will NOT keep today's slugs; the public-hostname↔product mapping must be changeable from a single source with one edit + one re-apply. *(Drives the single-declarative-ingress design in §5/§3a — never hardcode per-product.)*
- **Automation mode** — MIX. User manually assists on the credentialed/console parts (Replit domain UI, name.com/Cloudflare nameservers, Hostinger, Coolify); Claude scripts the safe/local parts and presents exact commands for outward-facing steps with go/no-go.
- **Document the transition** — explicit ask: capture what we did, what went wrong, and new learnings, so it can be **automated by evidence** later (→ a reusable deploy runbook/tool). *(This PROJECT.md + findings.md are that surface; codification target in Phase 7.)*
- **Teach-while-doing** — user is not a devops specialist and wants to *learn and master* this. Explain each concept/command + the *why* BEFORE executing it; favor narration over silent action. *(Shapes execution style for the whole project.)*
- **Full Cloudflare for the domain** — user wants the domain itself in Cloudflare (CF **Registrar** + CF DNS), not just delegated nameservers, and prefers to stop managing it in Replit. *(Path: NS→CF first (Phase 2, fast/reversible) then registrar transfer (Phase 8, optional, decoupled). Registrar of record is name.com — that's where unlock/NS/EPP happen.)*
- **Legacy → containerize `one-permutas` on the VPS; decommission Replit** (user decision 2026-05-21). Legacy app = the **pre-absorption matching system** at `github.com/jraphaelsst/one-permutas` (separate repo — **Django + Celery + Redis + Supabase**, single-port :5000; NOT the FastAPI fleet). Brought in as a gitignored read-only reference at `projects/production-deploy-migration/reference/one-permutas/`. Redeploy as a standalone container at `legacy.noctusai.com`.
- **Compute reality — edge vs compute** — "migrate ALL to Cloudflare" is achievable for the **edge** (registrar+DNS+TLS+tunnel+WAF = 100% CF) but NOT the **compute**: the fleet is a docker-compose Python stack (FastAPI + Redis + WAHA + Supabase). CF *Containers* is GA but is a Worker/DO-fronted, scale-to-zero model with no managed Redis/WAHA — adopting it = a re-architecture, not a migration. ⇒ compute needs ONE server (Hostinger or any VPS) behind the CF tunnel; CF Containers parked as a future option (§7). Real consolidation = CF (all edge) + ONE box (all compute), dropping Replit + name.com.
- **Use the CF MCP where it helps** — the managed *Developer-Platform* MCP can READ the account + search CF docs only. The DNS/zone/Tunnel actions now go through our **own `mcp/cloudflare` connector** (built 2026-05-21; needs a scoped token in `mcp/cloudflare/.env` + `.mcp.json` registration), or the dashboard/API.
- **DROP Coolify ENTIRELY — full decommission** (user, emphasized 10× on 2026-05-21; corrected from my earlier wrong "leave it idle"). **✅ DONE 2026-05-21** — all Coolify removed; n8n/waha/postgres migrated to raw compose (volumes preserved, n8n workflows + WhatsApp session intact); Traefik replaced by Caddy (interim, → CF tunnel when the domain moves to CF). End state = Cloudflare + Hostinger only, ZERO Coolify. Coolify currently ALSO runs the reverse proxy (Traefik+LE) serving `n8n`/`waha`.noctusai.com AND manages n8n/waha/postgres/redis (data in named volumes `r8co..._{n8n-data,pgdata,redis-data,waha-sessions,waha-media}` — survive container removal). **Safe decommission sequence** (Coolify removed as the FINAL step = "migrating out"): (1) author raw `docker compose` for n8n+waha+postgres+redis reusing those EXISTING volumes (preserves workflows + WhatsApp session) + the 3 products + legacy, all on `noctus-net`; (2) CF named tunnel takes over routing for n8n+waha+products (needs DNS-on-CF = the domain step); (3) swap Coolify-managed → raw containers (reuse volumes); (4) `docker rm` Coolify + control-plane + uninstall. **Build ON the VPS** (no GHCR for Wave 1); secrets from root `.env` (29 vars). SSH for Claude: ✅ working. **Dependency:** Coolify's *final* removal is coupled to the tunnel taking over n8n/waha routing (domain/DNS) — prep now, remove at the tunnel cutover (or now if n8n/waha public downtime is acceptable).
- **Code delivery = git, NOT rsync** (user 2026-05-21). The VPS gets the platform code via `git clone`/`git pull` from `github.com/jraphaelsst/noctusai` using a **read-only deploy key** generated on the VPS + added to the repo — never an rsync file-copy. Implications: (a) `origin/main` must be current — local `main` is presently **6 commits ahead** (incl. social-wiring auth/vista/fanout), so those **push first** (confirm-gated, FF) or the VPS builds **stale social-wiring**; (b) the root `.env` (29 vars, gitignored) does NOT travel via git → delivered **out-of-band** (one-time `scp` of the secret file — that's secret delivery, not a code-sync); (c) build ON the VPS from the checkout (no GHCR for Wave 1); (d) future redeploys = `git pull` + rebuild (the runbook step). *(Why git: code stays version-pinned + auditable on the box; redeploy = `git pull`, never a stateful rsync diff.)*
- **n8n/waha move ONTO the tunnel (scope change from §4 "out of scope").** Dropping Coolify removes Traefik, which currently serves `n8n.noctusai.com` + `waha.noctusai.com` — so these are no longer optional-to-migrate; the CF named tunnel MUST serve them. Their hostnames stay identical (so `WEBHOOK_URL`/`WHATSAPP_HOOK_URL` need no change). Raw compose: `deploy/services/`.

### Verified current state (2026-05-21, evidence in findings.md)

| Thing | Reality | Evidence |
|---|---|---|
| **Registrar of record** | **Name.com, Inc.** (NOT Replit — Replit UI fronts it) | WHOIS `Registrar: Name.com`; created `2026-01-09`; expiry `2027-01-09`; status `clientTransferProhibited` (LOCKED) |
| DNS authority for `noctusai.com` | **name.com** (NOT Cloudflare yet) | `dig NS` → `ns{1cny,2ckr,3jkl,4hny}.name.com` |
| `noctusai.com` apex (Permutas) | **Replit Deployment** (GCP-backed) | `dig TXT` → `replit-verify=bee5257b…`; headers `server: Google Frontend`, `GAESA` cookie; A `34.111.179.208` |
| `n8n.noctusai.com` / `waha.noctusai.com` | Hostinger VPS `72.61.28.36` | `dig A` → `72.61.28.36` |
| VPS reverse proxy | **Coolify + Traefik** (confirmed) | probe `:8000→302` (Coolify login), `:80→404` / `:443→503` (Traefik default Host) |
| `legacy.noctusai.com` | does not exist | `dig` empty / `ECONNREFUSED` |
| `www.noctusai.com` | not configured | `dig` empty |

---

## 3. Design principles

1. **Reversible, zero-downtime cutover** — stand up `legacy` + verify the new fleet on a temp hostname BEFORE flipping the apex; keep legacy as instant rollback; lower DNS TTL ahead of the flip.
2. **Single source of truth for hostname→service** — one declarative ingress map (git-tracked), derived from / aligned with the product registry; remapping a slug = one edit + one apply (satisfies the "easy changing" constraint).
3. **Cloudflare as the consolidation point** — DNS + edge TLS + tunnel (+ optional Access/WAF) in Cloudflare; compute stays on the Hostinger VPS (a Docker/Python fleet can't run on Workers/Pages).
4. **Confirm before every outward-facing step** — NS change, DNS records, the apex flip are presented with exact commands for explicit go/no-go.
5. **Evidence-logged** — every step + every surprise lands in findings.md in-the-moment, not at retro.

---

## 3a. Seed-first analysis

This is platform-infra, not product code, but the seed-first lens still applies to the **deploy tooling**:

1. **Contract identical for every product?** YES — every product is a single container behind one tunnel hostname.
2. **Data source product-specific?** NO — the hostname→service map is uniform fleet data, **derivable from the product registry** (`BEGIN/END_PRODUCTS_REGISTRY` in `start.sh`).
3. **Placement product-specific?** NO — one tunnel config + one DNS-sync routine for the whole fleet.
4. **Visibility/permission rule the same?** YES — public hostnames, uniform.
5. **Seam already in seed?** PARTIAL — the per-product **quick** (ephemeral) tunnel ships in compose; a **named/persistent** fleet tunnel + ingress-sync does NOT yet exist. Gap → build at platform level (scripts/MCP + KB guide), never per-product.
6. **Default-on or opt-in?** N/A (infra).

**Litmus — per-product code for this concern: 0 lines.** The tunnel ingress + DNS sync is a single fleet-level artifact derived from the registry. *If any phase walks product-by-product editing per-product deploy config, the design is wrong.* The reusable output belongs in `scripts/` (or a `noctus.dev.deploy` MCP tool) + a `KB § GUIDES/production-deploy.md`, NOT in `products/<slug>/`.

---

## 4. Scope

**In scope:**
- Verify current hosting (Replit app + Coolify/VPS) with user-side console confirmation.
- Move the `noctusai.com` zone to Cloudflare (NS change).
- Stand up `legacy.noctusai.com` → current Replit app; verify.
- Deploy the noc fleet to the Hostinger VPS (Cloudflare **named** tunnel) — **Wave 1 = `core` + `erp-imobiliario` + `social-wiring`** (incl. apex→core); remaining 5 products = Wave 2, parked.
- Cut `noctusai.com` (+ `<slug>.noctusai.com`) over to the fleet; verify; keep legacy as rollback.
- Build the single-source hostname→service ingress + DNS-sync (the "easy remap" mechanism).
- Document the whole transition + codify into a reusable runbook/tool.

**Out of scope (for now):**
- Migrating `n8n`/`waha` off direct VPS records onto the tunnel — leave as-is to limit blast radius (later phase if desired).
- Re-architecting the Permutas app — it stays on Replit, just remapped to `legacy`.
- Cloudflare Access/WAF hardening — optional follow-up after cutover is stable.

---

## 5. Architecture / topology

**Current**
```
name.com DNS ─┬─ noctusai.com (A 34.111.179.208) ─→ Replit Deployment (Permutas, on GCP)
              ├─ n8n.noctusai.com  (A 72.61.28.36) ─→ Hostinger VPS (Docker)
              └─ waha.noctusai.com (A 72.61.28.36) ─→ Hostinger VPS (Docker)
```

**Target**
```
Cloudflare DNS ─┬─ noctusai.com         (CNAME → tunnel, proxied) ─┐
                ├─ <slug>.noctusai.com  (CNAME → tunnel, proxied) ─┤   cloudflared (named tunnel)
                │                                                   ├─→ on Hostinger VPS ─→ fleet containers
                ├─ legacy.noctusai.com  (→ Replit, DNS-only)        │      ingress: hostname → container:port
                ├─ n8n.noctusai.com     (A 72.61.28.36, unchanged)  │      (single source of truth, git-tracked)
                └─ waha.noctusai.com     (A 72.61.28.36, unchanged) ─┘
```

**Single-source ingress (the "easy remap" mechanism).** One git-tracked file (e.g. `deploy/tunnel-ingress.yml` or generated from the product registry) lists `hostname → service:port`. Changing a slug's public name = edit one line → run the sync (writes cloudflared `config.yml` + `cloudflared tunnel route dns` for the CNAME). To be designed in the deploy phase; candidate to graduate into a `noctus.dev.deploy` MCP tool (Phase 7).

**Deploy artifacts (drafted 2026-05-21, on disk untracked under `deploy/`):**
- `deploy/fleet/` — `docker-compose.prod.yml` (8 products, GHCR `image:` pulls, slim `runtime`, expose-only on `noctus-net`) · `compose.infra.prod.yml` (Redis + WAHA-profile) · `build-and-push.sh` (seed bases + 8 images `--target runtime` + GHCR push, VITE build-args) · `README.md`.
- `deploy/tunnel/` — `ingress.yml` (single source of truth) · `config.yml` (named tunnel, `protocol: http2`, 404 catch-all) · `compose.tunnel.yml` (cloudflared on `noctus-net`) · `README.md`.
- `deploy/legacy/` — `Dockerfile` (multi-stage, gunicorn :5000, non-root) · `compose.legacy.yml` (legacy + legacy-celery) · `.env.example` · `README.md`.
- `fleet-readiness-audit.md` — roster / ports / gaps audit.

---

## 6. Implementation phases

### Phase 0 — Discovery ✅ (2026-05-21)
- [x] DNS/HTTP recon → current topology verified (see §2 table + findings)
- [x] Identify Replit as the apex host (TXT proof)
- [x] Confirm CF Developer-Platform MCP cannot do DNS/Tunnel (read-only/docs only)
- **Improvements:** Discovery must live-probe infra (`dig`/`whois`/`curl -I`) before trusting the KB or the user's stated stack — the apex was Replit-on-GCP, not the assumed Hostinger/Coolify, and `KB § CONTEXT/05-INFRASTRUCTURE.md` was stale. Captured as findings.md lessons; fold the "verify infra against live DNS" step into the Phase-7 production-deploy runbook.

### Phase 1 — Confirm & decide 🅿️ (blocked on user)
- [x] Replit Deployment ownership confirmed (user owns noctusai.com / Permutas)
- [x] Coolify presence on VPS confirmed (probe `:8000→302` login redirect); user to confirm login access
- [x] Registrar of record identified = **name.com** (WHOIS), not Replit
- [ ] Confirm registrar control: direct name.com login vs Replit-only access (gates where unlock/NS/EPP happen)
- [ ] Decide legacy-app fate (keep on Replit vs move to VPS) — §7
- [ ] Lock tunnel-vs-Coolify-proxy decision (justification provided; user to confirm)
- [ ] Decide automation split: scoped CF API token (Claude scripts) vs dashboard-driven

### Phase 2 — Move DNS to Cloudflare (nameserver change — the cutover prerequisite)
> Fast (mins–hours), free, reversible. This is ALL the cutover needs. Decoupled from the registrar transfer (Phase 8).
- [ ] Add `noctusai.com` as a site in Cloudflare (free plan); let CF import existing records (apex, n8n, waha)
- [ ] Lower TTLs ahead of cutover
- [ ] At **name.com**: change nameservers → Cloudflare's two NS; confirm `dig NS` shows Cloudflare

### Phase 3 — Stand up legacy = `one-permutas` on the VPS (no apex change yet)
> Legacy = Django + Celery + Redis + Supabase, single-port :5000 (`run.sh`). Different stack from the fleet ⇒ standalone container, NOT absorbed. Reference (gitignored): `reference/one-permutas/`. Artifacts drafted: `deploy/legacy/`.
- [x] Dockerfile + compose + `.env.example` + README drafted (`deploy/legacy/`)
- [x] **`settings.py` made env-driven** — authored `deploy/legacy/settings_prod.py` shim (imports read-only base + overrides SECRET_KEY/DEBUG/ALLOWED_HOSTS/CSRF + SECURE_PROXY_SSL_HEADER from env); Dockerfile sets `DJANGO_SETTINGS_MODULE=backend.settings_prod` + passes a throwaway build-only key to `collectstatic`. `ast.parse` ✓
- [x] **SECRET_KEY rotation wired** — `.env.example` now REQUIRES a fresh `SECRET_KEY` (dev literal never used); a fresh key generated for the VPS `.env` (handed to user, not committed). README documents the VPS clone-public-repo → cp-shim → build → migrate steps + the A-record-before-Caddy caution.
- [x] **DEPLOYED 2026-05-21** — user provided the secrets + `legacy` A-record. `one-permutas` cloned (public repo) → prod shim → built (with the Pillow + @supabase fixes) → raw compose on `noctus-net` → Caddy route. **`https://legacy.noctusai.com` serves the Permutas SPA** (HTTP 200, LE TLS, Supabase DB + Celery/Redis connected). Build/deploy gotchas captured in findings + KB GUIDE §6 (dep-gap N=2, shim-path, bind-mount-stale, ALLOWED_HOSTS-healthcheck). **Surfaced (not fixed):** `proprietario` has un-migrated model changes (app dev debt; would alter live schema → user decision). **NOT yet done:** retire the Replit deployment — only after the apex→core cutover (so Permutas stays reachable at the apex until then).

### Phase 4 — Wave 1 deploy: `core` + `erp-imobiliario` + `social-wiring`
> Scope (user 2026-05-21): Wave 1 = these THREE only (core = apex). Learn + **document** the process, then Wave 2 (the other 5) — PARKED, do not plan now. The `deploy/fleet/` artifacts already define all products; Wave 1 just builds/brings-up this subset. **Note: build + run on the VPS does NOT need the domain** — only VPS access + GHCR; public routing (Phase 5) is what waits on DNS-on-Cloudflare.
- [x] Confirm fleet deploy-readiness → `fleet-readiness-audit.md`
- [x] VPS prep: Docker 29 + external `noctus-net` ✅; code delivered via **git clone** (read-only deploy key), NOT GHCR/rsync; root `.env` scp'd (out-of-band secret delivery)
- [x] Build **core** + **erp-imobiliario** + **social-wiring** `runtime` images **ON the VPS** (per-product VITE build-args; `VITE_CORE_URL/API_URL` corrected dev→`https://noctusai.com` in-place) — no GHCR for Wave 1 (built 2026-05-21, ~7 min: seed bases + 3 products)
- [x] Bring up the 3 + Redis (`compose.infra.prod.yml`, `noctus-redis` on `noctus-net`); verify `/api/health` → **all 3 healthy** (core 1.0.0 · erp 0.2.0 · social-wiring 0.1.0), internal `docker exec` probe
- [ ] **Draft the runbook live as we go** — `KB § GUIDES/production-deploy.md` = the "learned process" for Wave 2 (Phase 7)
- **Improvements:** (1) `build-and-push.sh` builds all 8 — add a slug-subset arg for wave-based builds (needed for the runbook + Wave 2). (2) box `.env` shipped dev `VITE_CORE_URL/API_URL` (`localhost`) — Wave-1 build corrected them in-place; the seed/template `.env.example` should ship a prod-shaped placeholder so future boxes don't inherit localhost. (3) pip dependency-resolver conflict warnings during image build (non-fatal, exit 0) — capture + pin to silence. (4) ~~ANTHROPIC absent → LLM on Fake fallbacks~~ **CORRECTED 2026-05-21:** the product LLM layer (`noctusai_lib.integrations.llm`) ships **openai/gemini/fake only — no Anthropic provider**; default = `openai`/`gpt-4o-mini`, and `OPENAI_API_KEY` (`sk-proj…`) WAS set + resolves via `resolve_credential` Tier-3 env fallback → **social-wiring LLM/chatbot is live on OpenAI** (verified: runtime key matches `.env`, no "not configured" fallback in logs). ANTHROPIC_API_KEY only matters for `dev-team` (agno), not Wave-1. WAHA_* now extracted.

### Phase 5 — Wave 1 go-live: tunnel + subdomains + apex→core cutover
> Apex IS in Wave 1 (core included). Needs DNS-on-Cloudflare (Phase 2).
- [x] Create the named tunnel + run cloudflared (ingress already in `deploy/tunnel/ingress.yml`) — `noctusai-prod` id `6e9ccdc5-…`, **4 connections to CF edge, idle until DNS routes** (2026-05-21)
- [ ] Create proxied CNAMEs for **core** + **erp-imobiliario** + **social-wiring** subdomains (+ `legacy.noctusai.com`)
- [ ] Verify all three over the tunnel (TLS, health, app loads) BEFORE the apex flip
- [x] **Flip `noctusai.com` apex → `core` — DONE 2026-05-21** (Caddy interim): `@` A-record → VPS `72.61.28.36` + apex Caddy vhost (`84214391`) → LE cert; `https://noctusai.com` 200 serving core same-origin (no rebuild/CORS). Replit app + `legacy` remain as instant rollback. *(tunnel cutover still pending → this phase not fully ✅)*

### Phase 5b — Wave 2: remaining products (PARKED — do not plan now, user 2026-05-21)
> Built later from the documented Wave-1 runbook. Remaining: personal-finance, therapy-platform, daily-life, adconnect, dev-team.
- [ ] (later) per product: build/push image → add to compose up → add tunnel route + CNAME → verify

### Phase 6 — Post-cutover verification
- [ ] Health, TLS, all product subdomains, OAuth redirect URIs (Google/Meta), WhatsApp re-pair
- [ ] Soak; confirm no regressions; document rollback drill

### Phase 7 — Codify the learning
- [x] Write `KB § GUIDES/production-deploy.md` (fleet-grade, replacing the single-product archived runbook) — shipped 2026-05-21 + three-way-synced (INDEX/CLAUDE.md/OPENAI.md/memory)
- [ ] Fix the stale `KB § CONTEXT/05-INFRASTRUCTURE.md` apex claim — defer until the CF cutover stabilizes the infra (it's interim now); tracked in findings drift-list
- [ ] Evaluate a `noctus.dev.deploy` / tunnel-ingress-sync MCP tool (the "automate by evidence" output)

### Phase 8 — (Optional) Transfer registrar to Cloudflare = "full CF"
> Decoupled from the cutover — do anytime after Phase 2 is active on CF. ~5 days; does NOT affect the live site. ICANN: eligible (created 2026-01-09 > 60d) but currently LOCKED (`clientTransferProhibited`).
- [ ] At name.com: unlock the domain + request the EPP/auth code
- [ ] In Cloudflare → Transfer Domains: enter code, pay (~at-cost for `.com`, adds 1 yr), approve
- [ ] Confirm registrar = Cloudflare (DNS must remain on Cloudflare — required by CF Registrar)

### Phase 9 — (Optional) Domain email via Cloudflare Email Routing
> User wants an `@noctusai.com` address. Requires DNS on Cloudflare (Phase 2) first.
- [ ] Enable Cloudflare **Email Routing** (free) — auto-adds MX + SPF/DMARC TXT; forwards e.g. `you@noctusai.com` → personal inbox (receive-only)
- [ ] To SEND as `@noctusai.com`: add the alias in Gmail "Send mail as" (SMTP), OR provision a real mailbox (Zoho Mail free / Google Workspace ~$6/mo) — decide by need

---

## 7. Open questions

1. **Domain custody / how to move it (BLOCKER)** — domain is Replit-managed via name.com (reseller). To migrate to CF you need the **unlock + transfer (EPP) code** from the current custodian — that lives in **Replit's domain settings** (or name.com if direct access). NO CF/MCP bypass exists (anti-hijacking). User dislikes touching Replit; reframe = this one EPP retrieval IS the exit action, after which Replit is gone. Alt: contact name.com support directly with proof of ownership. RESOLUTION NEEDED before Phase 2 / user. *(User has no @domain email yet — see Phase 9.)*
2. **Legacy env + secrets** — which Supabase project does the live `one-permutas` use, and where are its prod secrets (Django `SECRET_KEY`, Supabase keys, Redis URL)? Needed to redeploy legacy (Phase 3). — from the Replit deployment / user.
3. **Final apex↔core + per-product subdomain list** — which products go live now vs later (Phase 5).

**Resolved:** compute home → ONE VPS (Hostinger) behind CF tunnel ✅ · tunnel-vs-Coolify → tunnel (Coolify optional inside the box) ✅ · legacy source → `one-permutas` repo (separate Django app) ✅.

---

## 8. Dependencies & blockers

- **VPS confirmed (Hostinger API)** — KVM 2: **2 vCPU / 8 GB RAM / 100 GB disk**, Ubuntu 24.04 + Coolify, `72.61.28.36`. RAM/disk ✅; **CPU (2 vCPU) is below the rec 4** — deployable, monitor; upgrade to KVM 4 if real-WAHA/heavy load. (Claude now has read access via the Hostinger API token in `mcp/hostinger/.env`.)
- **User console access** — Replit dashboard (domain transfer/EPP), name.com/registrar (if direct), Cloudflare (zone+tunnel), Coolify on the VPS (fleet host). Claude has the Hostinger API (VPS) but none of the others.
- **Scoped CF API token** (optional) — if Claude is to script DNS/tunnel: `Account:Cloudflare Tunnel:Edit` + `Zone:DNS:Edit` + `Zone:Zone Settings:Read` on `noctusai.com`.
- **Production secrets** — Supabase, LLM keys, OAuth client IDs, encryption key, WAHA, etc. (per archived `DEPLOY.md` checklist).

---

## 9. Success criteria

- `https://noctusai.com` serves the NoctusAI fleet (`core`), each product reachable at its subdomain, all over Cloudflare-edge TLS.
- `https://legacy.noctusai.com` serves the original Permutas app; usable as instant rollback.
- DNS authority is Cloudflare; hostname→product remap is a one-edit-one-apply operation.
- Zero unплanned downtime during cutover; a documented, tested rollback exists.
- The transition is fully documented (this project + findings) and a reusable runbook/tool is filed.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-21 | Initial draft after recon + 4-question interrogation; current-state verified (Replit apex via TXT proof); architecture leaning CF named tunnel | Claude |
| 2026-05-21 | WHOIS: registrar = name.com (not Replit), transfer-eligible but LOCKED (`clientTransferProhibited`); Coolify confirmed on VPS (`:8000`); user wants full-CF (registrar+DNS); split DNS-move (Phase 2) from optional registrar-transfer (Phase 8); taught DNS/TLS | Claude |
| 2026-05-21 | Clarified CF compute ceiling (edge=100% CF; compute needs a server — CF Containers GA but a re-arch); Permutas grep-confirmed = `erp-imobiliario` lineage (source in-repo); legacy decision = move off Replit into the fleet env; opened compute-home + permutas-source questions | Claude |
| 2026-05-21 | Compute LOCKED = one VPS behind CF tunnel; legacy = `one-permutas` (separate PUBLIC GitHub repo: Django+Celery+Redis+Supabase, single-port :5000) cloned in as gitignored read-only reference; flagged repo is PUBLIC w/ committed `db.sqlite3` (LGPD → surfaced to user); Phase 3 rewritten for containerizing one-permutas | Claude |
| 2026-05-21 | secrets.txt not pushed (repo last push 2026-03-17 → not leaked); env-var names to be derived from code; clarified domain is Replit-managed-via-name.com (EPP code from custodian = unavoidable exit step, no CF bypass); added Phase 9 (CF Email Routing for @noctusai.com); dispatched 3 parallel agents (fleet audit / legacy Dockerfile / tunnel ingress) | Claude |
| 2026-05-21 | Fleet audit complete → `fleet-readiness-audit.md` (9 products, core=apex:8000, seed excluded; deploy 8+legacy; gaps = named-tunnel + prod-compose-building-`runtime`-not-`runtime-watch`; rec 4 vCPU/8GB/80GB). Dispatched Engineer D for the missing prod fleet compose + build/push (`deploy/fleet/`). 3 agents still running (legacy/tunnel/fleet) | Claude |
| 2026-05-21 | All 4 deploy-prep agents landed → `deploy/{fleet,tunnel,legacy}/` (12 files, on disk, untracked). Cleanup: dropped `seed` from tunnel ingress. Surfaced: legacy `settings.py` hardcodes SECRET_KEY/DEBUG (needs env-override + key rotation — public repo); product Dockerfiles pin `FROM seed-base:dev` (param-tag follow-up); VITE build-args differ per product; dev-team image-baked in prod | Claude |
| 2026-05-21 | Hostinger API key provided → pulled live VPS specs (KVM 2: 2 vCPU/8 GB/100 GB, Ubuntu 24.04+Coolify): RAM/disk ✅, CPU below rec (monitor/upgrade-to-KVM4). Mapped the Hostinger API; dispatched Engineer E to build `mcp/hostinger` connector v1 (VPS + diagnostics, waha/n8n pattern). Temp token stored gitignored in `mcp/hostinger/.env` (rotate later) | Claude |
| 2026-05-21 | `mcp/hostinger` SHIPPED (8 tools, 18 tests green, live read-only-validated). Dispatched Engineer F → `mcp/cloudflare` connector (zones/DNS/tunnel/diagnostics, CF API v4) — needs user-created scoped token in `mcp/cloudflare/.env`. Filed DRY N=4 follow-up `projects/kit-connector-boilerplate-consolidation/`. PENDING: three-way sync (CLAUDE.md+memory) for both connectors + `.mcp.json` registration (user-gated) | Claude |
| 2026-05-21 | **Scope → WAVES** (user): Wave 1 = `erp-imobiliario` + `social-wiring` only (pilot-products-first); rest + `core`/apex in later waves via a runbook documented live during Wave 1. Restructured Phases 4/5/5b. Apex stays on Replit until `core` deploys (default, confirm pending). Insight: Phase 4 build/deploy is domain-independent (needs only VPS+GHCR); only public routing waits on DNS | Claude |
| 2026-05-21 | Scope refined (user): **Wave 1 = `core` + `erp-imobiliario` + `social-wiring`** (core added = apex; apex→core IS in-wave). Wave 2 (other 5) PARKED. `mcp/cloudflare` SHIPPED (15 tools, 25 tests green); both connectors three-way-synced (CLAUDE.md §2/§3 + MEMORY.md + memory files). Exec approach (user): build ON the VPS, use root `.env` keys, **SSH** (key generated, awaiting pubkey install), **NO Coolify** → raw `docker compose` + CF tunnel | Claude |
| 2026-05-21 | **Code delivery decided = git, not rsync** (user). VPS clones from GitHub via a read-only deploy key; `origin/main` is **6 commits behind** local `main` (incl. social-wiring) → push-first required; root `.env` delivered out-of-band (scp, gitignored). SSH confirmed working (`/opt/noctus` empty, git+docker present, `noctus-net` up, 81 GB free). Read-only recon of the 4 Coolify services → volumes + Traefik hostnames (`n8n`/`waha`.noctusai.com) + pg `default/default` captured; **n8n uses SQLite** (no `DB_POSTGRESDB_*`) ⇒ postgres role to verify before final teardown. Authored `deploy/services/` raw compose (n8n+waha+pg+redis) reusing the existing `r8co0…` volumes. n8n/waha promoted INTO tunnel scope (Traefik is going away). | Claude |
| 2026-05-21 | **Phase 4 compute DONE** — pushed 2 own-work commits to `origin/main` (`a12a8213`; connectors + project); read-only deploy key wired on the VPS; full repo cloned to `/opt/noctus/noctusai`; root `.env` scp'd. Built seed bases + `core`/`erp-imobiliario`/`social-wiring` `runtime` images ON the VPS (~7 min) with VITE bake corrected to `https://noctusai.com`. **All 3 healthy** over internal `/api/health` (core 1.0.0 · erp 0.2.0 · social-wiring 0.1.0) + `noctus-redis` healthy on `noctus-net`. **Domain unblocked:** WHOIS proved `noctusai.com` never lost (name.com, until 2027, in Replit's reseller account — user's personal name.com = empty); user recovered it in Replit (Verified, Manage available); CF zone already exists `pending` (id `068b91fa…`), CF NS to set = `clyde`/`lina.ns.cloudflare.com`. CF API token valid+active, saved gitignored. Remaining gate to public = the NS flip (Phase 2/5). | Claude |
| 2026-05-21 | **✅ LEGACY DEPLOYED — `legacy.noctusai.com` serves Permutas.** User gave the one-permutas secrets + `legacy` A-record + the Replit project join-link (for the NS ticket). Cloned one-permutas → prod shim → built (fixed: Pillow missing from requirements.txt = Django ImageField/`fields.E210`; @supabase root-hoist = `TS2307`; shim must be in the `backend/backend/` config package) → raw compose on `noctus-net` (Supabase DB + Redis Cloud + Celery worker) → Caddy route. **HTTP 200 + LE TLS, Permutas SPA loads.** Bind-mount-stale gotcha (caddy `reload` read the old inode after git pull → `docker restart` fixed) + Host-aware healthcheck. Methodology enriched: KB GUIDE §6 (+3 lessons), findings, memory. Surfaced: `proprietario` un-migrated models (app debt, user decision). OpenAI NS ticket replied with NS + join-link. | Claude |
| 2026-05-21 | **Session wrap-up (A: deploy runbook + doc sync · B: legacy deploy-ready).** **A:** authored `KB § GUIDES/production-deploy.md` (reusable external-server deploy runbook — the Phase-7 runbook sub-task; other Phase-7 items still open) + three-way-synced (INDEX tree+table, CLAUDE.md §2/§3, OPENAI.md, `reference_production_deploy_runbook` memory); marked the cloudflare MCP connector live-validated. **B:** legacy `one-permutas` made env-driven via `deploy/legacy/settings_prod.py` shim (no editing the read-only reference) + Dockerfile wired to it + `.env.example`/README updated (VPS clone-public-repo → cp-shim → build steps + A-record-before-Caddy caution) + fresh SECRET_KEY generated. Legacy DEPLOY gated on user secrets + `legacy` A-record (non-urgent — Permutas still on Replit). | Claude |
| 2026-05-21 | **OpenAI confirmed as social-wiring's LLM (Wave-1 functionally COMPLETE).** Product LLM layer = openai/gemini/fake (NO Anthropic provider); default `openai`/`gpt-4o-mini`; `OPENAI_API_KEY` (sk-proj) set + resolves via `resolve_credential` Tier-3 env fallback; runtime key == `.env`, no "not configured" fallback in logs → chatbot/LLM live on OpenAI. Corrected the earlier wrong "ANTHROPIC fallback" note. **Wave-1 done:** 5 subdomains live+TLS, Coolify gone, LLM on OpenAI. Remaining (user-gated): legacy `one-permutas` secrets (Phase 3), Replit NS ticket (full CF / Phase 2), apex→core after legacy. Wave 2 skipped per user. | Claude |
| 2026-05-21 | **✅ INTERIM GO-LIVE COMPLETE — all 5 subdomains live + LE TLS.** User added short-slug A-records (`core`/`erp`/`social` → VPS); Caddyfile updated to match (containers unchanged). All certs issued: `core`/`erp`/`social`/`n8n`/`waha`.noctusai.com serve SPA+API HTTP 200 over Let's Encrypt TLS; WhatsApp WORKING. Slip: Caddy attempted product certs in Phase 2 before the A-records existed → poisoned LE's DNS negative-cache (NXDOMAIN, SOA neg-TTL 3600s); recovered by polling public resolvers (cleared ~15min) + `docker restart noctus-caddy`. End state: Cloudflare(token+idle tunnel) + Hostinger + Caddy(interim). Coolify fully gone. Remaining = (later) NS→CF via Replit support → swap Caddy→tunnel (zero URL change). | Claude |
| 2026-05-21 | **COOLIFY DECOMMISSIONED + interim go-live on real subdomains via Caddy.** Replit can't delegate NS (Manage = records+disconnect only) → CF tunnel blocked on a support ticket; pivoted to Caddy + REAL `<svc>.noctusai.com` subdomains (final URLs; only routing swaps to the tunnel later). Migrated n8n/waha/postgres to raw compose (`deploy/services/`, reused r8co0… volumes) — **n8n 135M workflows intact, WAHA session resumed WORKING (no QR)**. Replaced Traefik with Caddy (`deploy/caddy/`, 80/443, per-subdomain LE): n8n.noctusai.com 200+cert, waha.noctusai.com 401(protected). Removed ALL Coolify (6 control-plane + 4 services + /data/coolify + network + images). Rebuilt 3 products w/ `core.noctusai.com` baked, all healthy. **Pending:** user adds 3 product A-records → product TLS; dead `coolify` SSH key flagged. | Claude |
| 2026-05-21 | **Tunnel PRE-STAGED + WAHA extracted; DOMAIN BLOCKER pinned.** CF named tunnel `noctusai-prod` (`6e9ccdc5-…`) created via API + cloudflared running on `noctus-net` (4 edge connections, http2, idle until DNS). WAHA creds extracted from the live container into VPS `.env` (`WAHA_BASE_URL` empty till services swap); env-gap audit = nothing real missing (ANTHROPIC skip + 3 stale `.env.example` aliases). **Replit Manage panel = DNS-records + Disconnect ONLY — no NS/transfer/EPP in UI** ⇒ freeing the domain for CF needs a **Replit support ticket** (set CF NS, or unlock+EPP). Interim option = direct A-records→VPS + Caddy TLS (throwaway, opens ports, baked-URL caveat). Decision pending (user). | Claude |
| 2026-05-21 | **✅ APEX CUTOVER DONE — `https://noctusai.com` → `core`** (Caddy interim). User repointed the `@` A-record → VPS `72.61.28.36`; added the apex Caddy vhost (commit `84214391`; deployed via surgical `git fetch && git checkout origin/main -- Caddyfile` — no full pull) → LE cert (`CN=noctusai.com`, E7) in ~15s; apex 200 serving core same-origin (no rebuild, no CORS); `core.noctusai.com` unregressed; Replit/`legacy` remain as rollback. **Two access blockers fixed in-flight:** (a) my VPS login key had been dropped from `authorized_keys` (PaaS-teardown rewrite) → user re-added via Hostinger console; (b) `git pull` on the VPS failed `publickey` though the deploy key authenticated — pinned it durably (`git config core.sshCommand 'ssh -i /root/.ssh/github_noctus_deploy -o IdentitiesOnly=yes'`). **Replit replied = EPP transfer code, not NS flip** → the real ask is the NS repoint to `clyde`/`lina` (CF zone `pending`); transfer is the optional follow-up. Lessons → findings + GUIDE §6 (+3 rows) + runbook memory. | Claude |
