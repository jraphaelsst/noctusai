# 16 · v1 status & follow-ups

## Status (2026-09-23)

The build and ship are owner-authorized. The website is **built and on `dev` at `8462ff912`, with CI green** and `predeploy_check core` ready. **Migration `052_website.sql` is applied to prod.** The core **prod deploy** waits on the owner's per-project ship approval (`noctus.dev.ship_consent`, project `noctus-website`). The noctusai-1b session runs that deploy.

## What v1 ships

| Area | Delivered |
|---|---|
| **Serving** | Host split: on `noctusai.com` the website owns `/` (22 prerendered pages, pt-BR + EN). App paths 301 to `core.noctusai.com`. `core.noctusai.com` is unchanged. `sitemap.xml` / `robots.txt` / `llms.txt` generated. Kill switch |
| **Public site** | Home (hero with a lazy three.js constellation over a static poster, audiences, products, custom builds, pricing from real plans, FAQ, closing CTA), Produtos + one page per curated product, Soluções (brief form), Preços, Contato, Lista de espera, Sobre, 404. Theme switch (Sistema/Claro/Escuro), PT/EN, LGPD consent bar (equal Rejeitar/Aceitar), consent-gated analytics loaders (no IDs set ⇒ nothing loads) |
| **Products shown** | Social Wiring (`disponível`), Orbity and Igig (`lista de espera`). Chosen from the live catalog (`deploy_scope`); no invented metrics, customers or certifications |
| **Leads** | `POST /api/website/leads` (waitlist/brief/contact) → core DB, dedupe, activity timeline. Optional fan-out: e-mail (Resend), WAHA alert, n8n webhook (each env-gated; a failure is recorded as a `fanout_failed` activity) |
| **Admin (logged app)** | Sidebar **Website**: Documentação · Configurações (site/signup switches, WhatsApp, per-section toggles, product curation, trust, social proof, FAQ, tracking IDs, version history + rollback) · Leads (stats, filters, detail, stage, notes, WhatsApp, CSV export). New **marketing** role sees only the Website group |
| **Sign-up switch** | `signup_enabled` off ⇒ `/api/auth/signup` → 403 `signup_closed`, and the site swaps sign-up CTAs for the waitlist. `/login?mode=signup` opens sign-up mode |

## Operating it

- **Turn the site off/on:** Website → Configurações → Geral → `site_enabled` (admin). Off ⇒ the apex serves the old app landing again.
- **WhatsApp CTAs:** set the number in Configurações. Until then, CTAs fall back to sign-up/waitlist.
- **Hide a section:** the switch removes it from the HTML immediately. **Showing a section that was off at build time** (social proof, news, update card) reaches JS visitors immediately, but crawlers only see it after the next deploy (prerender limitation, contract §0 D5).
- **Optional env** (prod `.env`): `WEBSITE_LEADS_NOTIFY_EMAIL`, `WEBSITE_SALES_WHATSAPP`, `WEBSITE_LEADS_WEBHOOK_URL` / `_SECRET`, `WEBSITE_TURNSTILE_SECRET`, build arg `VITE_TURNSTILE_SITE_KEY`.

## Known gaps → next steps

| # | Gap | Next step |
|---|---|---|
| 1 | Bootstrap identity, not the rebrand | Higgsfield exploration (**owner permission per session**) → identity approval → token/asset swap ([06](06-design-system.md)) |
| 2 | `www.noctusai.com` not in tunnel ingress | Add the ingress route + DNS; the middleware already 301s `www` → apex |
| 3 | Blog / Novidades deferred | v1.1: CMS in admin + `/blog` routes + meta injection |
| 4 | Copy editor (hero/section text) | v1.1: copy stored in settings; today, copy lives in `src/website/i18n` + `content/` |
| 5 | Privacy text says "strictly necessary cookies only" | Update the seed consent content with compliance-reviewer **before** setting GA4/Pixel IDs ([12](12-privacy-lgpd-tracking.md)) |
| 6 | Legal-entity footer (CNPJ, address) omitted | Owner provides the data → `content/legal.ts` |
| 7 | Seed promotion of i18n / consent / analytics / Turnstile widget (`NOC-REMEDIATE[seed-promotion]`) | Promote at the next consumer (Turnstile widget is already N=2 with community) |
| 8 | App-path allowlist hand-maintained in `website_html.py` (`NOC-REMEDIATE[website-app-path-derivation]`) | Derive from a build-time route export |
| 9 | Mobile theme button uses an emoji icon | Swap for a lucide icon |
| 10 | Seed e-mail organ is SMTP-only; core used its Resend service | Add a Resend Real adapter to `integrations/email` |
| 11 | Future AI sales agent | Pipeline is agent-ready ([10 §Agent-ready](10-conversion-and-leads.md#agent-ready-design)) |
