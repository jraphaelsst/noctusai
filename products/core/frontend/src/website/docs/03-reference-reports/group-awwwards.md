# Awwwards SOTD group (Aug–Sep 2026): cross-site comparison
Sites: cerebrium · aspensearch · stateofaidesign · sharplink · lisa. Captured 2026-09-23. Perf figures are rough, and bytes are header sums, so treat them as orders of magnitude.

## Key dimensions
| Dimension | Cerebrium | Aspen Search | AI in Design 2026 | Sharplink | L.I.S.A. |
|---|---|---|---|---|---|
| Stack | Astro, Lenis, 1 WebGL canvas | Next.js, Sanity, Lenis, 5 shader canvases | Framer, video | SPA (noscript), Storyblok, Lenis, 3 canvases + 3 videos | Custom WebGL only |
| "Wow" device | WebGL magenta ribbon hero | 180px type + dither shader | AI-mutated flower art + ASCII video | Photoreal CGI video + HUD callouts | Full 3D character, click-to-start |
| Hero text in HTML? | Yes (H1 + sub + 2 CTAs) | Yes (brand-only H1) | Yes | Yes (but noscript H1 first) | **No**: prompt is in canvas, no H1 |
| H1 display metrics | Favorit 86/86 w300 −2.5% | Suisse 181/181 w450 −4% | Beausite 120/114 w500 −6% | Archivo ~88 (visual) | none (404: serif 70/77) |
| Palette | navy + hot pink, dark/light panels | ink + mint, grey cells | black/white + orange/lilac/sage | off-white/black + electric blue, blue gradients | B/W UI, colour only in render |
| Theme toggle / honours OS dark | No / No | **Yes** / No | No / No | No / No | No / No |
| Section theming | alternating dark↔light panels | cell-level | colour field per chapter | scroll-choreographed dark↔light | — |
| Primary CTA | Try it now / Sign up (+ Book demo) | Start a conversation (mailto) | Email for report markdown | Explore dashboard / Investor info | Let's talk |
| Proof type | logos, case studies, SOC2, status, benchmarks | stats, client list, testimonials, team | methodology stats, featured brands | Nasdaq, leadership, SEC filings | none |
| Pricing | per-second sheet + comparison table + FAQPage | — | — | — | — |
| Blog/hub | Engineering blog, filtered | — | Report = long-read hub | Thin news hub (1 post) | — |
| canonical / hreflang / lang | ✓ / ✗ / en | ✓ / ✗ / en | ✓ / ✗ / **empty** | **✗** / ✗ / **empty** | ✗ / ✗ (en+fr twins) / en |
| JSON-LD | Org, WebSite, SoftwareApp, FAQ, Breadcrumb | WebSite, WebPage | **none** | ItemList only | none |
| Heading hygiene | Subpage H1 = tiny eyebrow | 2× H1 (brand word) | 5–8 H1s per page | noscript H1 + dup H1 | 0 headings |
| Home load / req / DOM | 16.1s / 126 / 4.2k | 7.7s / 62 / 1.7k | 3.4s / 76 / 1.3k (~33MB media) | 3.1s / 109 / 1.8k (~15MB video) | 15.9s / 33 / 89 (~11MB 3D) |
| Static-render failure seen | none major | preloader blank mobile fold; counters "000+" | blank appear-on-scroll regions | ~3,000px empty pinned stage | preloader mid-scramble |

## Shared patterns (evidence-derived)
1. **The hero's heavy visual sits behind real HTML text.** 4 of 5 put the H1, subhead and CTAs in the DOM over the canvas or video (cerebrium, aspen, sharplink, aiid). Only the pure-experience site (lisa) renders the message in-canvas.
2. **Typography is the second hero.** Display headlines run 86–181px with aggressive negative tracking (−2.5% to −6%) and ≤1.0 line-height. Every site pairs a grotesk/display face with a **mono** for labels, eyebrows, buttons and data.
3. **Single-accent discipline.** Each site uses one saturated accent for action or emphasis (pink, mint, electric blue, orange) against near-monochrome neutrals. Cerebrium adds a gradient-highlighted word per headline.
4. **Theme as narrative, not preference.** Dark↔light alternates *by section or scroll* (cerebrium panels, sharplink gradient, aiid colour fields). Only aspen offers a user toggle, and none honours prefers-color-scheme.
5. **One art-direction metaphor, many renderings.** Cerebrium's ribbon (hero, subpages, blog thumbs), aiid's mutated flowers (photo + ASCII twin), sharplink's chrome CGI (+HUD), aspen's dither. The motif doubles as the blog/OG image system.
6. **Flat, zero-to-small radii, hairlines, no shadows.** Hairline grids and rules (aspen cells, sharplink dotted guides, aiid rules) replace cards-with-shadows.
7. **Proof without testimonials.** Compliance/status/benchmarks (cerebrium), methodology stats (aiid) and regulatory transparency (sharplink) all build credibility without customer quotes. That's directly usable by NoctusAI, which has none yet.
8. **Motion lives in scroll-reveal, pinned stages, counters and preloaders, and each one broke the static capture somewhere.** This is the main risk to prerendered SEO, Lighthouse and reduced-motion users.

## Divergences
- **Where the "wow" costs bytes:** a shader on flat images (aspen, ~0.6MB) vs. a WebGL scene (cerebrium, lisa) vs. documentary/CGI video (aiid ~33MB, sharplink ~15MB). Shaders are the cheapest wow per byte.
- **Funnel vs. stunt:** cerebrium runs a full self-serve + sales funnel with pricing. aspen and sharplink are relationship/IR sites. lisa is a pure brand stunt. aiid is a content lead-magnet.
- **SEO maturity:** cerebrium (Astro, rich schema) ≫ aspen ≈ aiid > sharplink > lisa. Framework choice correlated with SEO hygiene more than design ambition did.

## The WebGL-hero recipe that stays SEO-safe (for NoctusAI)
1. **HTML first:** prerender `<h1>` (one per page, keyword-bearing, pt-BR default with EN twin), subhead, and the CTA pair (WhatsApp prefilled + Cadastro/Waitlist per admin toggle) as normal DOM positioned over the hero area (cerebrium model). No message, label or CTA inside the canvas (lisa anti-pattern).
2. **Poster is the LCP:** ship a static AVIF/WebP render of the 3D scene (same camera as frame 0) as the hero background `<img fetchpriority="high">`, themed in light and dark variants. The canvas mounts *after* LCP/idle, crossfades over the poster, and never blocks first paint (no preloader: aspen and lisa blanked their folds).
3. **Gate the weight:** load the three.js/scene chunk via dynamic import on idle + IntersectionObserver on desktop. On mobile or `saveData` or low `deviceMemory`, keep the poster and offer an opt-in "Explorar em 3D" button (cerebrium's mobile play button; lisa's click-to-start, but optional). Budget: ≤~300KB JS + ≤~1.5MB compressed assets (Draco/KTX2) versus the 11–16MB seen here.
4. **Interactivity as an annotation layer:** if the 3D hero shows the product suite, render the labels as HTML (sharplink-style HUD callouts) projected from 3D positions. They're crawlable, translatable (pt-BR/EN), keyboard-focusable, and themeable via tokens.
5. **Reduced motion and no-JS parity:** `prefers-reduced-motion` means poster only (or a paused frame). All counters, scroll-reveals and pinned stages SSR their *final* state; animation is enhancement only (avoid aspen's "000+" and sharplink's 3,000px empty stage).
6. **Theme-aware scene:** read the same CSS custom properties (bg, accent) into the scene uniforms so the theme switch recolours the canvas without reload. Also honour prefers-color-scheme on first visit, then the user's toggle (aspen only did the toggle).
7. **Consent-clean:** no analytics or pixels inside the WebGL bundle. GA4/Meta Pixel load only after LGPD opt-in (sharplink's implied-consent bar is the anti-pattern).
8. **Schema + meta around it:** Organization, WebSite, SoftwareApplication per product, FAQPage on pricing, BreadcrumbList on subpages; canonical + hreflang pt-BR/en; per-page OG images generated from the same 3D render family (cerebrium reused one OG image, so do better).
