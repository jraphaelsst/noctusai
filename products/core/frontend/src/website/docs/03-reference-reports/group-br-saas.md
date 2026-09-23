# BR SaaS group: RD Station · Conta Azul · Pipefy · Blip (captured 2026-09-23)

## Key dimensions
| Dimension | RD Station | Conta Azul | Pipefy | Blip |
|---|---|---|---|---|
| Target | SMB → mid (marketing/sales) | Micro/SMB owners + accountants | Mid/enterprise IT + ops | Enterprise CX (SMB via Blip Go) |
| Stack | Next.js + headless WP | Next.js (oklch tokens) + legacy WP | WordPress, heavy JS | WordPress + HubSpot + OneTrust |
| Hero | Promo headline, lime CTA, decorative art | Rotating-word headline, UI mockup | Carousel: AI Builder chat / Gartner slide | Full-bleed lifestyle photo |
| Primary CTA | Teste Grátis (lime) | Teste Grátis (yellow) | Teste grátis (header) / **Demo** (sticky right-edge tab + closing) | **Agende uma conversa** (sales) |
| WhatsApp | Product feature + plan support; no float | **Sticky bar (Vendas/Suporte) + header icon** | None seen | Product core; footer mention |
| AI assistant on site | No | Chat bubble (generic) | **Olívia video avatar, auto-open, voice** | **"Contato Inteligente" section + floating agent + quick-reply chips** |
| Price on site | Yes: 4 tiers, R$50→R$1.699/mês, "a partir de" | Yes: home + /planos, Anual/Trimestral toggle, strikethrough | Nav only (not shown) | No |
| Segment pages | Segmentos menu | 13 "Empresas" verticals + Contador/BPO | Industries × Departments × Studios | Segment tabs + journey stages |
| Dark mode / toggle | No / no | No / no | No / no | No / no (but alternating dark bands) |
| hreflang | None (region globe exists) | None | **pt-br / en-us / x-default** | pt / es / en / x-default |
| FAQPage schema | Tool page only | **Home, pricing, features, cases** | No | No |
| H1 hygiene | Hero ≠ H1 | Keyword H1 as 16px eyebrow | Mostly clean (p5 H2 before H1) | H1 after menu H2s; empty H1s on subpages |
| Consent banner | None detected | Custom (Personalizar/Aceitar first layer) | Custom, **equal Rejeitar/Aceitar** | OneTrust, **equal Rejeitar todos/Aceitar todos** |
| Home load (rough) | 3.4s / 151 req | 3.3s / 142 req | **12.0s / 257 req** | **17.6s / 319 req** |
| 3D/WebGL | None | None | None | None |

## Patterns shared by ≥3 sites
1. **Free trial as the default header CTA** ("Teste grátis", 3/4: RD, CA, Pipefy). It is a filled pill in one reserved accent color, with "Entrar" beside it as a ghost button.
2. **Segment/vertical routing in the primary nav**, via a mega-menu with a one-line benefit per item (4/4). BR buyers look for "is this for my kind of business?" before features.
3. **Enterprise and customer logo walls plus metric-headline proof** ("+50 mil empresas", "+1,9 mi notas/mês", "220% de ROI") near the fold (4/4).
4. **Content hub teased on home**: blog cards, glossário, materiais gratuitos, reports, academies (4/4). SEO content is part of the product surface, not an afterthought.
5. **Footer as a legal and trust anchor**: CNPJ, street address, phone with hours, privacy/cookie/ética links (4/4 show CNPJ or legal entity). This is expected by BR buyers and relevant for LGPD.
6. **FAQ accordion on key pages** (4/4: CA, Blip, the RD tool page, and Pipefy's "Entendendo a Era do BOAT" pillar FAQ, per scroll orquestracao-s08). Schema is only used consistently by Conta Azul. Pipefy and Blip ship visible FAQs without FAQPage markup.
7. **Light-only theme ignoring `prefers-color-scheme`** (4/4). No BR peer offers dark mode, so a theme toggle is a genuine differentiator for NoctusAI.
8. **Rounded, pill-heavy UI with a single blue-family brand color** and one contrasting action color (lime or yellow) or blue (4/4).

## Notable divergences
- **Sales motion:** self-serve price and trial (CA, RD low tiers) vs demo/conversation-only (Blip, Pipefy pillars). RD splits the motion **per plan tier**.
- **Channel of human contact:** WhatsApp-first (Conta Azul) vs AI-agent-first (Blip, Pipefy) vs form-and-phone (RD).
- **i18n:** Pipefy and Blip run proper hreflang. RD shows a region selector without hreflang. CA is pt-BR only.
- **AI-era SEO:** only Pipefy courts AI engines explicitly ("Peça a uma IA um resumo da Pipefy" footer links) and RD (the Radar GEO free tool). Blip and CA do not.
- **Performance:** the Next.js sites (RD, CA) load in about 3s. The WP-plus-third-party enterprise sites (Pipefy, Blip) take 12–18s. Pipefy's scroll-reveal left full-page captures blank, which is a fragility signal.
- **Voice:** colloquial ("a gente dá conta", CA) vs direct-commercial (RD) vs enterprise-visionary with anglicisms (Pipefy) vs outcome-premium (Blip).

## What BR SMB visitors expect (implications for noctusai.com)
- **A visible way to talk to a human on WhatsApp**, ideally prefilled and intent-specific. For SMB audiences it replaces "Book a demo".
- **A price or "a partir de R$…/mês"**, with an annual discount toggle. Hiding price reads as "enterprise, not for me".
- **"Teste grátis / sem cartão"** framing and "sem fidelidade" reassurance, which NoctusAI can offer as sign-up (when admin-enabled) or waitlist.
- **"Is this for my business?"** answered via segment pages or cards before features, which fits the NoctusAI vertical products.
- **Legal-entity transparency** (CNPJ, address) and an **LGPD consent banner with a real "Rejeitar"** (Blip/Pipefy model), with Reclame Aqui-style seals only once earned.
- **Free educational content** (glossário, guias, ferramentas gratuitas) as the entry point. It is the SEO-first engine NoctusAI's blog should seed.
- **Gap nobody fills:** none of the four offers dark mode, a 3D hero, or a fast AI-native assistant that is prerendered and consent-gated. NoctusAI can own "technical + visionary" without copying the heavy enterprise script load.
