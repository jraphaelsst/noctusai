# 05 · Information architecture

## URL & language scheme

- **pt-BR is the default at the root, and English lives under `/en/`.** URL slugs are localised (`/produtos` ↔ `/en/products`). Every page declares its twin with `hreflang="pt-BR"`, `hreflang="en"` and `hreflang="x-default"` (pointing at pt-BR).
- **No forced redirect by browser language** (a redirect would hurt SEO). A dismissible **locale-suggestion bar** offers the other language, as Runway does ("This page is available in English · Switch"). It appears only after the consent bar is dismissed ([P12](04-pattern-synthesis.md#p12-one-overlay-at-a-time)).
- **The language switch** sits in the header and the footer. It keeps the visitor on the equivalent page.
- **Canonical host: OPEN.** `noctusai.com` and `core.noctusai.com` both reach core. The website must be canonical on the apex, and `core.*` must 301 or `noindex` public pages. See [Build plan · Open decisions](14-build-plan.md#open-decisions).

## Sitemap

| pt-BR | EN | Template | Admin-hideable | Notes |
|---|---|---|---|---|
| `/` | `/en` | Home | per section | [07 §Home](07-page-specs.md#home) |
| `/produtos` | `/en/products` | Product index | — | Curated list, in admin order |
| `/produtos/:slug` | `/en/products/:slug` | Product page | per product | One per curated vertical (ERP Imobiliário, Terapia, Finanças Pessoais, Social Wiring…) |
| `/solucoes` | `/en/solutions` | Custom builds | yes | "IA sob medida": process, capabilities, brief form |
| `/precos` | `/en/pricing` | Pricing | yes | Public plans endpoint needed ([08](08-technical-architecture.md#7-reuse--retire)) |
| `/desenvolvedores` | `/en/developers` | Developers | yes (default **off** until the API story is real) | API keys, MCP, docs links; only states what exists |
| `/blog` | `/en/blog` | Content hub | yes (off until ≥ 3 posts) | Tabs by category, search, RSS |
| `/blog/:slug` | `/en/blog/:slug` | Article / long-read | — | DB-backed; server-side meta injection |
| `/novidades` | `/en/changelog` | Dated feed | yes | Launches + posts tagged "novidade" (P7) |
| `/sobre` | `/en/about` | About | — | Mission, how we work, legal entity |
| `/contato` | `/en/contact` | Contact | — | WhatsApp + short form; no booking |
| `/lista-de-espera` | `/en/waitlist` | Waitlist | auto | Live only while sign-up is disabled (or per-product waitlists) |
| `/privacidade`, `/termos`, `/cookies` | `/en/privacy`, … | Legal | — | Seed consent-content update ([12](12-privacy-lgpd-tracking.md)) |
| `/404` | — | Not found | — | Light on-brand 404 with search + popular links (L.I.S.A. idea, without the weight) |

**Existing routes that must not move:**
- `/login`, the sign-up mode of `Login.tsx`, `/invite/:token`, the `/api/sso/*` routes and the seed-mounted **consent routes** all stay where they are.
- The logged app moves to **`/app/*`**. Legacy app paths get server 301s ([08 §3](08-technical-architecture.md#3-moving-the-dashboard-to-app)).
- Machine files served by the website router: `/sitemap.xml` (+ per-language sitemaps), `/robots.txt`, `/rss.xml` (+ `/en/rss.xml`), `/llms.txt`.

## Navigation

**Header, desktop, left to right:**
1. Logo, linking to `/`.
2. **Produtos ▾**, a mega-menu with one line per curated product plus "Ver todos".
3. **Soluções** (IA sob medida).
4. **Preços**.
5. **Recursos ▾**: Blog · Novidades · Desenvolvedores.
6. **Sobre**.
7. *(right side)* WhatsApp icon · language switch (PT/EN) · theme switch (Sistema/Claro/Escuro) · **Entrar** (ghost) · **one filled primary**, either "Criar conta grátis" or "Entrar na lista de espera", depending on the admin switch ([P8](04-pattern-synthesis.md#p8-one-filled-button-in-the-header)).

**Header, mobile:** logo, the filled primary (compact) and a menu button. The drawer holds all nav plus the language and theme switches. The floating WhatsApp button shows after the consent decision.

**Rules.** Hidden sections and pages disappear from the nav and footer automatically, driven by the same `website_settings`. Nav labels are links, not headings (P11).

**Footer, mega-footer (P14):**
- Produtos
- Soluções
- Recursos: Blog, Novidades, Desenvolvedores
- Empresa: Sobre, Contato, Lista de espera
- Legal: Privacidade, Termos, Cookies, "Preferências de cookies"
- Then a legal-entity block (razão social, CNPJ, address), the language and theme switches, social links, and © year.

## Audience paths

| Audience | Entry points | Primary CTA | Secondary |
|---|---|---|---|
| **SMB owner (BR)** | Home audience card → product page | WhatsApp, prefilled with the product | Criar conta / Lista de espera |
| **Mid/enterprise** | Home "IA sob medida" → `/solucoes` | Brief form → WhatsApp | Sobre / architecture |
| **Developers** | Recursos → Desenvolvedores | Criar conta (API keys) | Docs / blog engineering |
| **Freelancers & solo founders** | Home audience card → pricing | Criar conta grátis / Lista de espera | WhatsApp |

## Page inventory by phase

- **Launch (v1):** Home, Produtos index + each curated product, Soluções, Preços, Contato, Sobre, Legal, 404, Waitlist, Blog (hidden until ≥ 3 posts), `/en` twins of all of them.
- **v1.1:** Novidades, Desenvolvedores (once real), pillar long-reads per vertical, per-vertical landing variants for SEO ("IA para imobiliárias").
