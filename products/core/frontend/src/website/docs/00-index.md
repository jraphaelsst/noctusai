# Website noctusai.com — Documentação

> **Status: v1 BUILT, on `dev` @ 8462ff912, CI green; awaiting owner ship approval → core deploy (2026-09-23).** The owner authorized the full build and prod deploy ("go all the way to prod"). Open decisions were taken for v1 as recorded in [15 · Build contract §0](15-api-contract.md#0--decisions-taken-for-v1-owner-delegated-go-all-the-way); anything still marked **OPEN** in 01–14 is resolved there or deferred to v1.1.

This is the design and technical guide for the public website at **noctusai.com**. It is the source of truth for anyone, human or agent, who designs, builds, writes copy for or operates the website. It sits in the logged app under **Website → Documentação**, and its files live in `products/core/frontend/src/website/docs/`.

## 🔴 Rules every agent must know before touching the website

1. **Higgsfield MCP is permission-only.** Never call a Higgsfield tool without the owner's explicit approval *for that specific use*. In this codebase Higgsfield is used **only** for the noctusai.com website (rebrand exploration + product imagery). If the Higgsfield MCP is **not connected**, do not do Higgsfield-dependent design work and do not substitute another generator. Stop and ask. → [Tooling & MCP policy](13-tooling-and-mcp-policy.md)
2. **The website lives inside `products/core`**, not in a seed product (owner decision). → [Technical architecture](08-technical-architecture.md)
3. **Never fabricate proof.** No invented logos, testimonials, metrics or certifications. The social-proof section stays hidden (admin toggle) until real, consented proof exists. → [Pattern synthesis §P7](04-pattern-synthesis.md#p7-honest-proof-before-social-proof)
4. **SEO-first.** Every public page ships prerendered HTML with one H1, unique meta, hreflang, and content visible without JavaScript. Motion is enhancement only. → [SEO, performance & a11y](09-seo-performance-a11y.md)
5. **Rebrand is website-scoped.** The website's tokens must not leak into the logged app; the app adopts the brand later, in a separate project. → [Design system](06-design-system.md)

## Reading order

| # | Document | What it answers |
|---|---|---|
| 01 | [Brief & decisions](01-brief-and-decisions.md) | What the owner decided in the 2026-09-22 interview, and why |
| 02 | [Research method](02-research-method.md) | Which sites were studied, how, and known capture gaps |
| 03 | [Reference reports](03-reference-reports/README.md) | 13 site-by-site technical reports + 3 group comparisons |
| 04 | [Pattern synthesis](04-pattern-synthesis.md) | The principles derived from the research that the website follows |
| 05 | [Information architecture](05-information-architecture.md) | Sitemap, navigation, URL + i18n scheme, page inventory |
| 06 | [Design system](06-design-system.md) | Rebrand brief, token architecture, type, color, theming, motion, 3D hero |
| 07 | [Page & section specs](07-page-specs.md) | Home section by section, plus every subpage template |
| 08 | [Technical architecture](08-technical-architecture.md) | How the site is built inside core: routing, prerender, serving, kill switch |
| 09 | [SEO, performance & a11y](09-seo-performance-a11y.md) | Budgets, metadata, schema, i18n, accessibility gates |
| 10 | [Conversion & leads](10-conversion-and-leads.md) | CTAs, WhatsApp, sign-up, waitlist, the lead model and follow-up pipeline |
| 11 | [Admin: Website section](11-admin-website-section.md) | The logged-app surfaces: Documentação, Configurações, Blog, Leads, roles |
| 12 | [Privacy, LGPD & tracking](12-privacy-lgpd-tracking.md) | Consent, analytics, pixels, first-party events, policy changes |
| 13 | [Tooling & MCP policy](13-tooling-and-mcp-policy.md) | Higgsfield rules, Context7 / Chrome DevTools / shadcn MCPs, capture tooling |
| 14 | [Build plan](14-build-plan.md) | Waves, slices, gates, rollout, and open decisions |
| 16 | [v1 status & follow-ups](16-v1-status.md) | What shipped, how to operate it, known gaps, next steps |
| 15 | [Build contract v1](15-api-contract.md) | **v1 decisions taken** (host split, no seed changes), DB, settings shape, API, build output, serving, acceptance |

## Change log

| Date | Version | Change |
|---|---|---|
| 2026-09-23 | 0.1 | First draft: interview, reference research (13 sites), synthesis, specs, Phase-0 architecture audit. |
| 2026-09-23 | 0.2 | Build contract v1 (15) + v1 decisions: host split instead of `/app` move, no seed changes, prerender + FastAPI post-processing, blog deferred. |
| 2026-09-23 | 1.0 | v1 built: backend (migration 052 applied to prod, public/admin API, signup gate, host-split middleware), public site (22 prerendered pages pt-BR/EN, 3D hero, consent, lead forms), admin (Configurações, Leads, marketing role). Real-browser integration caught and fixed a blank-page crash (`plans.features` shape) and hero/mobile layout defects. See [16 · v1 status](16-v1-status.md). |
