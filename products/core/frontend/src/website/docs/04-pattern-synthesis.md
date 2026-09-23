# 04 · Pattern synthesis — the principles noctusai.com follows

These principles come from the 13 reference reports. Each one has four parts:
- **Evidence**: how many sites showed it, and which.
- **Principle**: the rule we adopt.
- **For NoctusAI**: how it applies under the owner's decisions.
- **Guards**: what must never happen.

Later docs cite these as `P1`–`P14`.

---

## P1. Text is HTML; the spectacle sits behind it
**Evidence.** 4 of 5 Awwwards sites (Cerebrium, Aspen, AI in Design, Sharplink) layer a real HTML H1, subhead and CTAs over the canvas or video. L.I.S.A. puts its message *inside* the canvas and ends up with no H1 and ~3 crawlable words.
**Principle.** Every word a visitor must read, and every control they must use, is DOM. The 3D scene is decorative or explorable, never the carrier of the message.
**For NoctusAI.** The interactive 3D hero renders *behind* a prerendered H1, subhead and CTA pair. If the scene labels things (e.g. product "modules"), the labels are HTML overlays projected from 3D positions, in the Sharplink HUD style. That keeps them crawlable, translatable (pt-BR/EN), focusable and themeable.
**Guards.** No copy, CTA or label drawn in WebGL. No click-to-start gate before content.

## P2. The poster is the LCP; WebGL is a late guest
**Evidence.** The heavy heroes cost 11–16 MB and 15–16 s loads (L.I.S.A., Cerebrium). Preloaders blanked the fold on Aspen and L.I.S.A. Vercel degrades gracefully to a themed static logo glow.
**Principle.** Ship a static render of the scene's first frame, with light and dark variants, as the hero image (`fetchpriority="high"`). Mount the canvas after LCP, on idle, and cross-fade it in. On mobile, `saveData`, low memory or `prefers-reduced-motion`, keep the poster and offer an opt-in "Explorar em 3D".
**For NoctusAI.** Budget: ≤ ~300 KB JS for the scene chunk and ≤ ~1.5 MB compressed assets (Draco/KTX2). Details in [06 §3D hero](06-design-system.md#3d-hero) and [09](09-seo-performance-a11y.md#budgets).
**Guards.** No blocking preloader. three.js is never imported by the logged app ([08 §6](08-technical-architecture.md#6-bundle-isolation)).

## P3. Route by audience early
**Evidence.** 4 of 4 BR sites route by segment or vertical in the main nav. Runway uses per-audience CTA trios. Anthropic puts dual-audience links inside the H1.
**Principle.** Answer "is this for me?" before listing features.
**For NoctusAI.** The hero H1 carries the hybrid positioning: "produtos prontos" + "IA sob medida" are in-H1 links, Anthropic style. Right under the hero, an **audience row** of four cards (Pequenas empresas · Empresas · Desenvolvedores · Autônomos & solo founders) gives each audience a tailored CTA. The main nav has a **Produtos** mega-menu (one line per vertical) and a **Soluções** entry for custom builds.
**Guards.** Don't build separate sites per audience. Audience routing changes emphasis and CTA, not the whole design.

## P4. Monochrome base, one accent, one action colour
**Evidence.** All 4 AI-native sites, all 5 Awwwards sites and all 4 BR sites ration colour: neutrals plus one brand accent, and often a separate reserved action colour (RD's lime, Conta Azul's yellow, Cerebrium's pink).
**Principle.** Neutrals carry the layout. **One brand accent** is used for emphasis, including one highlighted word per headline (Cerebrium). **One `--action` token** is used only for the primary CTA. Both must hold WCAG AA in light *and* dark.
**For NoctusAI.** Product verticals may each own a secondary **chapter colour** (AI in Design) used only inside that product's own section and page.
**Guards.** No rainbow gradients. The action colour never appears on non-actions.

## P5. Typography is the second hero
**Evidence.** Awwwards display headlines run 86–181 px with −2.5% to −6% tracking and line-height ≤ 1.0. AI-native H1s are 61–64 px with tight tracking. Every craft site pairs a grotesk with a **mono** for labels, eyebrows, buttons and data.
**Principle.** A two-family system: a display/text sans plus a mono. Huge, tightly tracked display type is a first-class visual device, and it costs almost nothing.
**For NoctusAI.** The mono carries the "technical" voice: eyebrows ("● PRODUTOS"), spec rows, pricing numbers, code. A weight-contrast or gradient word inside the headline is the brand signature. The final faces come from the rebrand exploration ([06](06-design-system.md#typography)).
**Guards.** Fonts properly licensed (Cerebrium ships a *Trial* font in production). Self-hosted and subset, with `font-display: swap` and size-adjusted fallbacks so layout doesn't shift.

## P6. Theme: follow the OS, let the user switch, never flash
**Evidence.** Only Vercel follows `prefers-color-scheme`, with a 3-state switcher in its footer. Aspen has a header toggle but ignores the OS. None of the 13 has both. Cerebrium, Sharplink and AI in Design alternate dark and light *sections* as a narrative device.
**Principle.** First visit follows the OS. A **3-state switch (Sistema / Claro / Escuro) sits in the header**. The choice persists, and an inline `<head>` script applies it before first paint, so the page never flashes the wrong theme.
**For NoctusAI.** Both themes are designed, not inverted. One **"always-dark" band** (the hero and one AI band) is allowed as a narrative device and still reads correctly in light mode. The WebGL scene reads the same CSS variables, so switching the theme recolours it without a reload ([06](06-design-system.md#theming)).
**Guards.** No theme-dependent content. Contrast AA in both themes, including dimmed "inactive" copy.

## P7. Honest proof before social proof
**Evidence.** 3 of 4 AI-native sites put a logo strip under the hero, and all 4 BR sites show metric headlines. The honest substitutes appear everywhere too: dated "what's new" surfaces (Linear changelog, Vercel "Recently shipped", Anthropic "Latest releases", Runway "See the latest"), security/compliance rows (Cerebrium, Vercel), methodology stats (AI in Design) and transparency (Sharplink). Pipefy shows the risk: its proof numbers disagree between pages (260% vs 220% ROI).
**Principle.** Credibility comes from **what is verifiably true today**. That means:
- live products you can open;
- a dated "Novidades" feed of launches and blog posts;
- architecture transparency (a layered diagram, as Pipefy does);
- trust statements that are true ("Dados hospedados no Brasil", "Conforme LGPD", "Seus dados não treinam modelos"), *only if true*;
- capability metrics measured in our own products ("gera um contrato em 30 s"), sourced from one canonical data file.
**For NoctusAI.** The **social-proof section exists but ships hidden** (admin toggle off) until real, consented logos or testimonials exist.
**Guards.** 🔴 Never fabricate logos, testimonials, counts or certifications. No placeholder proof. Every number lives in one versioned source.

## P8. One filled button in the header
**Evidence.** All 4 AI-native sites have exactly one filled primary CTA plus a quieter login/sales link. On BR sites, "Teste grátis" is the filled pill and "Entrar" is a ghost button.
**Principle.** The header has one filled CTA, one ghost "Entrar", the theme switch and the language switch. Nothing else competes.
**For NoctusAI.** The header primary follows the admin switch: **"Criar conta grátis"** when sign-up is enabled, **"Entrar na lista de espera"** when it isn't. WhatsApp is always reachable from the header icon and one floating button (P9).
**Guards.** Never more than one floating or sticky overlay at a time ([P12](#p12-one-overlay-at-a-time)).

## P9. WhatsApp is the BR "talk to us", with intent built in
**Evidence.** Conta Azul keeps WhatsApp persistent and split by intent (Vendas / Suporte). BR buyers expect a human channel. Blip and Pipefy put AI assistants on the page, with quick-reply chips.
**Principle.** One persistent WhatsApp affordance. Its **prefilled message depends on context**: which product page, custom-build page, pricing plan or blog post the visitor is on. Every click creates a lead event (after consent for analytics; the lead record itself is first-party).
**For NoctusAI.** It replaces "Book a demo" entirely. The custom-build section's short brief form (≤ 5 fields, Runway/Blip style) submits into the lead pipeline, then offers to continue on WhatsApp with the brief prefilled ([10](10-conversion-and-leads.md)).
**Guards.** No demo scheduling. Don't stack a chat bubble, a WhatsApp bar and a header icon (Conta Azul's clutter).

## P10. Show the product, in DOM
**Evidence.** Linear's hero is the product UI built in DOM. Cerebrium uses faux-UI widgets and RD Station a product bento. Vercel pairs a capability list with a mockup and one-line proof.
**Principle.** Each vertical product is shown with a **live-looking UI panel built in HTML/SVG** or real screenshots: not stock imagery, not abstract art. One repeated **chapter template**: H2 and copy on the left, product panel on the right, a feature index below.
**For NoctusAI.** The chapter template renders each curated product. The admin controls order and visibility. Product imagery can be produced with Higgsfield (owner-approved) for hero-grade visuals ([13](13-tooling-and-mcp-policy.md)).
**Guards.** Don't hide product visuals on mobile (Linear's blank mobile block). Mobile-first BR traffic needs them most.

## P11. SEO is structural, not a plugin
**Evidence.** SEO maturity tracked the framework, not the design ambition. Runway, Cerebrium and Conta Azul got it right: keyword titles, hreflang, and Organization, SoftwareApplication, Offer, FAQPage and BreadcrumbList schema. Common failures: missing, duplicate or eyebrow H1s (Anthropic, Blip, Cerebrium subpages, AI in Design); one shared OG image (RD Station, Cerebrium); no hreflang (3 of 4 AI-native); content revealed only on scroll that renders blank without JavaScript (Vercel, Pipefy, Aspen, Sharplink).
**Principle.** Every template ships:
- one keyword-bearing H1;
- a unique title and meta description;
- a self-canonical URL;
- hreflang pt-BR/en plus x-default;
- a per-page OG image;
- the right JSON-LD;
- **all content visible in the prerendered HTML**.
Animation only enhances what is already there. Counters and reveals render their final state.
**For NoctusAI.** Full spec in [09](09-seo-performance-a11y.md). Add `llms.txt` and a clean text structure for AI engines, as Pipefy and RD Station do.
**Guards.** Nav and footer labels are not headings. No noscript H1. No text inside canvas.

## P12. One overlay at a time
**Evidence.** Pipefy stacks four overlays (sticky header, demo tab, auto-open avatar, cookie modal), covering about 30% of the viewport. Runway stacks a promo bar, locale toast and cookie bar on mobile. Conta Azul stacks three contact surfaces.
**Principle.** At most one transient overlay at a time. The consent bar comes first, then the locale suggestion. The floating WhatsApp button appears only after the consent decision and never covers CTAs.
**Guards.** No auto-opening chat or assistant. Consent is a **bottom bar**, not a modal over the content.

## P13. Content hub as the SEO engine
**Evidence.** All 4 BR sites tease content (blog, glossário, free materials) on the home page. 3 AI-native sites run filterable hubs (tabs, search, dates, RSS). AI in Design's long-read template (numbered findings, sourced charts, takeaways, reading time) is the flagship format.
**Principle.** The blog launches with pillar content per vertical ("IA para imobiliárias", "IA para clínicas de terapia"), a long-read template and a filterable index (category tabs, search, dates, RSS). Posts are edited in the admin CMS, with pt-BR and EN fields.
**For NoctusAI.** The "Novidades" feed (P7) and the blog share one card component, as Vercel does. Each product's page links its own pillar posts.
**Guards.** Don't ship a hub with one post (Sharplink). Keep the section hidden until there are at least 3 posts.

## P14. Mega-footer as sitemap and legal anchor
**Evidence.** All 4 AI-native sites use 5–12 column mega-footers. All 4 BR sites show CNPJ, address and policy links. Vercel's footer doubles as a utility bar (status + theme).
**Principle.** Footer columns: Produtos, Soluções, Recursos (Blog, Novidades, Docs), Empresa, Legal. It also carries the legal-entity block (razão social, CNPJ, address), a "Preferências de cookies" link, the language switch and social links.
**Guards.** Show a status line only if it's backed by a real status endpoint.

---

## Differentiation — where NoctusAI leads

No site in the 13 has **all** of:
- a header theme switch that also follows the OS;
- an interactive 3D hero that stays SEO-safe;
- real pt-BR/EN hreflang;
- WhatsApp-native conversion;
- a fast, consent-gated build.

The BR market has **no** dark mode and **no** 3D (0 of 4). That combination is the positioning gap noctusai.com occupies.
