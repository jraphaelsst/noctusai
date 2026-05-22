# Deploy personal-finance + therapy-platform to the VPS — Follow-up

> **Filed 2026-05-22** from the `deploy-hardening-and-dev-isolation` close-out. While asserting the fleet edge, an audit found that **`personal-finance` and `therapy-platform` are not deployed on the production VPS** — no container running, no Caddy vhost. The user chose to defer their deploy ("not now — file a follow-up") and **pre-decided the public slugs: `finance.noctusai.com` + `therapy.noctusai.com`**.

- **Status:** 📋 NOT STARTED (deferred by user 2026-05-22)
- **Owner:** Rapha (devops learner — teach-while-doing) · Claude
- **Slug:** `finance-therapy-vps-deploy` (root `projects/`)
- **Authority for the procedure:** `KB § GUIDES/production-deploy.md` (do NOT re-derive — follow §2/§2a/§4 + §6 lessons)

---

## 1. Context (zero-context reader)

The fleet is live on `noctusai.com` (Hostinger VPS `72.61.28.36`, **Caddy** interim edge, CF tunnel pre-staged). Deployed + serving today (verified 2026-05-22): apex→core · `core.` · `erp.` (erp-imobiliario) · `social.` (social-wiring) · `n8n.` · `waha.` · `legacy.`. The user uses **short public slugs** (core/erp/social), mapped in `projects/production-deploy-migration/deploy/caddy/Caddyfile` (the single source of truth for the Caddy edge). VPS tracks `origin/prod`; code reaches it via the §2a drill only.

**Gap:** `personal-finance` + `therapy-platform` exist in the repo as products but were never deployed to the VPS (no image built/run, no Caddyfile vhost, no DNS record). This is *incomplete rollout*, not a DNS bug.

## 2. Decision recorded
- **Public slugs:** `finance.noctusai.com` (personal-finance) · `therapy.noctusai.com` (therapy-platform). *(User-chosen 2026-05-22 over `pf.`/full-name options.)*
- **Deploy now?** No — deferred to this follow-up.

## 3. Procedure (per the GUIDE — each product)
1. **P5 gate FIRST:** `noctus.dev.predeploy_check <product>` → must be `ready` (framework-dep parity + `vite build` + `pytest` green). Block-fix before building. *(P5 interpreter resolution was fixed 2026-05-22; the gate is trustworthy.)*
2. **Confirm LLM provider** = OpenAI/Gemini, never Anthropic (`noctusai_lib.integrations.llm` ships openai/gemini/fake only; key via `OPENAI_API_KEY` Tier-3 env). GUIDE §6 lesson.
3. **Build the slim `--target runtime` image ON the VPS** (§2): `scripts/infra/build-base-images.sh dev` first; bake the public `VITE_*` (`VITE_CORE_URL`/`VITE_CORE_API_URL=https://core.noctusai.com`; the product's own API is same-origin via `window.location.origin`). Baking `localhost` = broken public app (boundary-contract B1).
4. **Run on `noctus-net`** (no host port publish; reachable by service name).
5. **Edge — A-record FIRST, then Caddy** (🔴 LE-negative-cache rule, GUIDE §6): create the grey-cloud A-record `finance`/`therapy` → `72.61.28.36` (Cloudflare; `mcp/cloudflare` connector has a token in `mcp/cloudflare/.env`), `dig` it against the CF nameservers until it resolves, THEN add the Caddyfile vhost (`finance.noctusai.com { reverse_proxy personal-finance:<port> }`), THEN `docker restart noctus-caddy` (single-file bind-mount → restart, NOT reload — stale-inode lesson).
6. **Verify:** `curl -I https://finance.noctusai.com/` → 200; same for therapy.

## 4. Prerequisites / blockers
- Internal ports for the two products (check each product's compose / `noctus.dev.available_ports`).
- Both products must pass `predeploy_check` — if either has build/test debt, fix before deploy (only-functional-code-online, P5).
- A Supabase/runtime `.env` on the VPS must carry these products' keys (deploy-local, never via git — GUIDE §1).

## 5. Done when
- `finance.noctusai.com` + `therapy.noctusai.com` both serve 200 over TLS; both containers `healthy` on `noctus-net`; Caddyfile vhosts committed (the vhost map is tracked; secrets/config are not).
