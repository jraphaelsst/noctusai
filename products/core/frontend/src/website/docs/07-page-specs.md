# 07 · Page & section specs

The owner asked for every home section to be switchable ([01](01-brief-and-decisions.md#structure--content)), so every section below has a **settings key** in `website_settings.sections`. A hidden section is removed from the prerendered HTML, the nav/footer links and the sitemap. It is not hidden with CSS. The copy below is illustrative pt-BR; final copy is written in the admin copy editor.

## Home

| # | Section | Key | Default | Job |
|---|---|---|---|---|
| 0 | Header | — | on | Nav + one filled CTA ([05](05-information-architecture.md#navigation)) |
| 1 | **Hero** | — (always) | on | Say what NoctusAI is in 5 s; fork the two offers |
| 2 | Audience row | `audiences` | on | "Is this for me?" (P3) |
| 3 | **Products showcase** | `products` | on | Show each curated product as live UI (P10) |
| 4 | **IA sob medida** (custom builds) | `custom_builds` | on | Process + architecture + brief form |
| 5 | Why NoctusAI (true statements) | `trust` | on | Honest proof: LGPD, BR data, no training on your data (P7) |
| 6 | **Social proof** | `social_proof` | **off** | Logos/testimonials, only real and consented ones |
| 7 | **Pricing** | `pricing` | on | "A partir de R$…/mês" + plan cards (BR expectation) |
| 8 | Novidades / Blog | `news` | on, auto-hidden while < 3 items | Dated momentum (P7, P13) |
| 9 | FAQ | `faq` | on | Objections + FAQPage schema |
| 10 | Closing CTA band | — (always) | on | Final conversion |
| 11 | Footer | — | on | Mega-footer (P14) |

### 1 · Hero
- **Layout.** A full-viewport, always-dark band with the 3D scene behind ([06 §3D hero](06-design-system.md#3d-hero)). Text sits bottom-left: a mono eyebrow, then the H1, the subhead and the CTA pair. A small "latest update" card sits bottom-right (Sharplink), toggle key `hero_update_card`.
- **H1** (the only H1; carries the keyword and the hybrid offer, with in-H1 links, Anthropic style): *"IA que trabalha pela sua empresa — com **produtos prontos** ou **sob medida**."* One word takes the accent-gradient signature.
- **Subhead**, one sentence and concrete: *"Sistemas com IA para imobiliárias, clínicas e finanças — e projetos de IA construídos para o seu negócio."*
- **CTAs.**
  - Primary: **"Falar no WhatsApp"**, prefilled with *"Olá! Vim pelo site e quero saber mais sobre a NoctusAI."*
  - Secondary, following the admin switch: **"Criar conta grátis"** (sign-up enabled) or **"Entrar na lista de espera"**.
  - The header keeps its own single filled button (P8). In the hero, WhatsApp is primary because it converts BR SMB visitors best; this is **OPEN** to owner preference.
- **Below the fold line:** the HTML module list mirroring the 3D modules, one link per product. It gives keyboard access and SEO.

### 2 · Audience row
Four cards: **Pequenas empresas · Empresas · Desenvolvedores · Autônomos & solo founders**. Each has a one-line benefit and an audience-specific CTA ([05 §Audience paths](05-information-architecture.md#audience-paths)). A hairline grid, no imagery, mono labels.

### 3 · Products showcase
- The intro is an H2 plus a mono eyebrow "● PRODUTOS".
- Then one **chapter per curated product**, in admin order (Linear chapter template; Cerebrium sticky index on desktop):
  - left: H3 name, one-line job, 3–5 capability bullets, and a real capability metric if one exists;
  - right: a **faux-UI panel** in DOM/SVG or a real screenshot;
  - below: feature index links;
  - CTAs, per product state (Pipefy per-card routing):
    - `disponível`: "Criar conta" / "Falar no WhatsApp";
    - `lista de espera`: "Entrar na lista";
    - `em breve`: label only.
- **Mobile:** stack the chapter vertically. Never hide the panel (Linear's mobile gap).
- **Data:** `website_settings.products[]` = `{catalog_slug, order, state, copy.pt/en, panel_asset, cta_override}`. Name and slug come from the product catalog; copy is curated by the admin.

### 4 · IA sob medida (custom builds)
- H2 and a visionary line.
- A **numbered process**: 01 Diagnóstico → 02 Protótipo → 03 Produção → 04 Evolução (Blip journey pattern).
- A **layered architecture diagram** in SVG, themeable: LLMs → agentes → orquestração → integrações (WhatsApp, Google, Meta, ERPs). It's the credibility device (Pipefy).
- Capability chips.
- **Brief form** (≤ 5 fields: nome, WhatsApp, empresa, tipo de projeto, mensagem) with Turnstile. On submit it creates a lead, then offers "Continuar no WhatsApp" with the brief prefilled ([10](10-conversion-and-leads.md)).

### 5 · Why NoctusAI (true statements)
A 3–4 icon row: *Dados hospedados no Brasil · Conforme LGPD · Seus dados não treinam modelos · Integra com o que você já usa*. **Each statement ships only if it is verified true.** They are stored as admin-editable items with a `verified_by` + `verified_at` field ([11](11-admin-website-section.md#configurações)).

### 6 · Social proof (default OFF)
- Layouts: a logo strip (monochrome) and/or metric-first case cards (Blip).
- Every item requires the **consent reference**: who approved use of the logo or quote, and when.
- The admin UI refuses to enable the section with zero items.

### 7 · Pricing
- The heading carries **"a partir de R$ X/mês"**, with a Mensal/Anual toggle showing the discount chip.
- 3–4 plan cards with "Tudo do plano anterior, mais:" inheritance, one "Mais escolhido" anchor, and a first-person persona line per plan (RD Station).
- Per-tier CTA: low tiers → "Criar conta" (when enabled) or waitlist; high tiers → WhatsApp.
- A link to `/precos` for the full comparison `<table>`.
- **Data:** a public plans endpoint (the current `/api/plans` requires auth; [08 §7](08-technical-architecture.md#7-reuse--retire)).

### 8 · Novidades / Blog
The three latest items (posts + launches) in the shared post card: date, category, title, cover from the motif template. Links to "Ver tudo". Auto-hidden while fewer than 3 items exist.

### 9 · FAQ
6–10 questions: price, data/LGPD, how onboarding works, custom project timelines, WhatsApp support, cancellation ("sem fidelidade", only if true). Accordion; **FAQPage JSON-LD** is generated from the same data.

### 10 · Closing CTA band
Giant display line (Aspen type-as-hero), the CTA pair again, and a WhatsApp prefill tied to the band.

### v1.1 candidate: "Pergunte à IA" section (`assistant`, default off)
A Blip-style single input with intent chips ("Produtos prontos", "Projeto sob medida", "Preços", "Falar no WhatsApp"). Rendered statically; it activates only on focus, after consent, and hands off to prefilled WhatsApp. This is the **front door for the future lead-closing AI agent** ([10 §Agent-ready](10-conversion-and-leads.md#agent-ready-design)).

## Subpage templates

| Template | Structure |
|---|---|
| **Product page** `/produtos/:slug` | Sticky sub-nav (Visão geral · Recursos · Preços · FAQ, as Vercel does) → hero (H1 = "<Produto>: <job>", a large faux-UI panel, CTA by state) → capability chapters → integrations → product pricing → FAQ (schema) → related posts → closing CTA. JSON-LD: SoftwareApplication + Offer + BreadcrumbList + FAQPage |
| **Product index** `/produtos` | H1, product cards in admin order with state badges, "Não encontrou? → IA sob medida" |
| **Soluções** `/solucoes` | Home §4 expanded: process, architecture, sample use cases by vertical, brief form, FAQ |
| **Preços** `/precos` | Toggle + cards + full comparison `<table>` + FAQ (schema) + an optional cost calculator for custom builds (v1.1, Vercel) |
| **Blog index** `/blog` | H1, category tabs, search, post grid (shared card), pagination, RSS link |
| **Article** `/blog/:slug` | Long-read template (AI in Design): title, dek, author, date, reading time, sticky TOC (desktop), numbered sections, sourced charts, callouts, takeaways, related posts, CTA. JSON-LD Article + BreadcrumbList |
| **Novidades** `/novidades` | A dated list of launches and posts; mono date column |
| **Sobre** `/sobre` | Mission, "Como trabalhamos" principles list (Anthropic), legal entity, team (optional) |
| **Contato** `/contato` | WhatsApp primary, short form, e-mail. No booking |
| **Lista de espera** | Short form (nome, e-mail, WhatsApp +55 default, perfil) + explicit opt-in checkbox with purpose text (Blip) |
| **404** | Light on-brand scene or poster, search, popular links |

## Global states

- **Sign-up disabled:** every "Criar conta" becomes "Entrar na lista de espera". The backend rejects `/api/auth/signup` ([10](10-conversion-and-leads.md#sign-up-switch)).
- **Site disabled (kill switch):** the server serves the legacy `Landing.tsx` app shell ([08 §5](08-technical-architecture.md#5-serving-meta-injection--the-kill-switch)).
- **No JS:** every page is fully readable and every link works. Forms post server-side or fall back to WhatsApp links.
