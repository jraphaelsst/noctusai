# 01 · Brief & decisions

Source: owner interview, 2026-09-22 (five rounds). Each decision is final unless the owner reopens it. Items the research or audit later marked as risks are listed in [Build plan · Open decisions](14-build-plan.md#open-decisions).

## Intent

| Topic | Decision | Consequence for the build |
|---|---|---|
| What NoctusAI is (5-second test) | **Hybrid**: a suite of ready-made AI vertical products **and** custom AI builds | The hero states both; the page forks early into "Produtos prontos" and "IA sob medida" ([P3](04-pattern-synthesis.md#p3-route-by-audience-early)) |
| Audiences | BR SMB owners · mid/enterprise · developers · freelancers & solo founders | Four audience paths; segment routing in nav + an audience card row on home |
| Languages | **pt-BR primary + EN toggle** | i18n from day one; `/` = pt-BR, `/en/…` = English; hreflang pairs |
| Conversion | **WhatsApp** (prefilled) · **sign-up** (admin can enable/disable) · **waitlist**. **No demo booking.** | Sign-up and waitlist swap by an admin switch; WhatsApp is always available |

## Brand & visuals

| Topic | Decision | Consequence |
|---|---|---|
| Theme | Theme-aware **light + dark**, with an **on-page theme switch** | 3-state switch (system / light / dark) in the header; first visit follows the OS |
| Motion | **Interactive 3D/WebGL hero** + **minimal motion elsewhere** | One lazy WebGL scene over a static poster; everything else is static or micro-interaction |
| Brand | **Full rebrand**, website-only for now | New identity scoped to the website's tokens; the app adopts it in a later project |
| Voice | **Confident & technical** + **visionary** | Short, concrete claims; one big-idea line per section; no hype adjectives |

## Structure & content

| Topic | Decision | Consequence |
|---|---|---|
| Site shape | Landing + subpages + **blog/content hub** | Blog is part of the SEO engine from launch |
| Home sections | Products showcase · Custom builds · Social proof · Pricing, **each switchable** in Website → Configurações | Every section is a self-contained block that can disappear without breaking the layout |
| Product showcase source | **Curated by admin** (which products, order, copy) | `website_settings` holds the curated list; not the raw catalog |
| Social proof | **None exists yet** | Section ships **hidden**; never filled with placeholders |
| Content ops | Blog posts + site copy edited in an **admin UI inside core** (DB-backed, pt-BR/EN fields) | Blog CMS + copy editor under Website in the sidebar |

## Build & operations

| Topic | Decision | Consequence |
|---|---|---|
| Where it lives | **Inside `products/core`**, not a seed product ("the seed is probably gonna break things") | Website code isolated under `src/website/`; safety measures in [08](08-technical-architecture.md) |
| Root route | **Website owns `/`**; the dashboard moves to **`/app`** | Blast-radius audit + redirects required ([08 §3](08-technical-architecture.md#3-moving-the-dashboard-to-app)) |
| Priority | **SEO first** | Prerendered HTML, Lighthouse ≥ 90, WebGL lazy with a poster |
| Leads | Core DB + admin list · WAHA WhatsApp · email notify · n8n workflow, plus a **follow-up management UI**. A future AI agent will talk to leads and close deals | Lead pipeline model designed agent-ready ([10](10-conversion-and-leads.md)) |
| Access | **Admins + a new "marketing" role** | New role + role-aware shell for the Website group |
| Tracking | LGPD cookie consent · privacy-first analytics · GA4 + Meta Pixel (after opt-in) · first-party events | Consent-gated loaders; privacy policy update ([12](12-privacy-lgpd-tracking.md)) |
| Sidebar | All sidebar groups **collapsed by default**; new group **Website** with **Documentação** | Collapse already shipped (seed `Sidebar`, commit `e3ebde374`); the group holding the active page auto-opens |

## Tooling

| Topic | Decision |
|---|---|
| Higgsfield MCP | Used **only** for this website: **rebrand exploration** and **product imagery**. **Explicit owner permission per use.** Not connected ⇒ don't do that work. |
| Frontend MCPs | Enable **Context7**, **Chrome DevTools MCP**, **shadcn MCP**, scoped to website work (not always-on). Figma, Playwright MCP, Filesystem, GitHub and Magic Patterns MCPs were considered and declined. |
| Sequence | Research → docs → **owner approval** → build |
