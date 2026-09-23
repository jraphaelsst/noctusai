# 09 · SEO, performance & accessibility

These are gates, not goals: a page that fails them doesn't ship. Verify with Chrome DevTools MCP (Lighthouse and performance traces) plus CI checks ([13](13-tooling-and-mcp-policy.md), [14](14-build-plan.md#gates)).

## Per-page SEO contract

| Item | Rule |
|---|---|
| HTML | Server-rendered; **all content visible without JS**; `lang="pt-BR"` or `lang="en"` |
| H1 | Exactly one, keyword-bearing, equal to the page's positioning line; never an eyebrow; nav/footer labels are not headings |
| Title | `<Keyword phrase> \| NoctusAI`, ≤ 60 chars, unique per page and language (keyword-first, as Runway does) |
| Meta description | Unique, 140–160 chars, pt-BR and EN |
| Canonical | Self-canonical on the canonical host ([08 §3](08-technical-architecture.md#3-moving-the-dashboard-to-app)) |
| hreflang | `pt-BR`, `en`, `x-default` (→ pt-BR) on every page, reciprocal |
| OG / Twitter | Per-page image generated at build or publish time from the motif template, per language; `summary_large_image` |
| JSON-LD | Home: Organization + WebSite (+ SearchAction for the blog). Product: SoftwareApplication + Offer + BreadcrumbList (+ FAQPage). Pricing: Offer + FAQPage. Article: Article + BreadcrumbList. Every visible FAQ gets FAQPage; Vercel's /sandbox shows what happens when it doesn't |
| Links | Descriptive anchors; internal links from the footer mega-menu (P14); no orphan pages |
| Machine files | `sitemap.xml` (index → per-language sitemaps with `xhtml:link` alternates), `robots.txt`, `rss.xml`, and `llms.txt`: a plain-text map for AI engines (Pipefy and RD Station court AI search) |
| Hidden sections/pages | Removed from HTML, the sitemap and internal links; formerly public URLs 301 to their parent |

## Budgets

| Metric | Budget (mobile, 4G, mid-tier device) |
|---|---|
| Lighthouse Performance / SEO / Best Practices / Accessibility | **≥ 90 / 100 / ≥ 95 / ≥ 95** |
| LCP | ≤ 2.0 s (the hero **poster** is the LCP element) |
| CLS | ≤ 0.05 (metric-matched font fallbacks, reserved media boxes) |
| INP | ≤ 200 ms |
| Initial JS (website entry, gzipped) | ≤ 90 KB before hydration of below-the-fold islands |
| 3D scene chunk | ≤ 300 KB JS gzipped + ≤ 1.5 MB compressed assets; **never loaded on mobile unless opted in** |
| Total home weight (first view, no 3D) | ≤ 1.2 MB |
| Third-party scripts before consent | **0** |
| Fonts | ≤ 2 families, ≤ 4 files, subset, preloaded |

The research numbers that set these budgets:
- Runway: 67 MB home.
- Pipefy: 12 s load.
- Blip: 17.6 s load and 88 scripts.
- L.I.S.A.: 11 MB before interaction.
- Vercel: about 0.4 MB.

## Motion & rendering rules (static-render safety)

- Nothing starts hidden in SSR output: no `opacity:0` waiting on IntersectionObserver.
- Counters render final values. Pinned or scroll-scrubbed stages are banned, as are preloaders.
- The hero canvas mounts after LCP, pauses when off-screen, and respects `prefers-reduced-motion` and `saveData`.

## Accessibility (WCAG 2.2 AA)

- **Contrast** AA in **both themes**, including muted text, the dimmed "inactive" list items and text over the hero scrim.
- **Keyboard:** everything reachable with a visible `--focus-ring`; a skip link; the 3D modules mirrored by an HTML link list; the mega-menu operable with the keyboard; the theme and language switches are real buttons with labels.
- **Canvas** is `aria-hidden` and decorative. Everything meaningful exists in DOM (P1).
- **Forms:** labels, error text, `autocomplete`, and a `tel` input with a +55 default. Turnstile must be accessible (the managed mode).
- **Images:** alt text in both languages; decorative images use `alt=""`.
- **Reduced motion** is honoured globally.
- **Language:** `lang` attributes on mixed-language snippets.

## i18n rules

- Copy lives in the DB (admin editor) with `pt` and `en` fields. Static UI strings live in `i18n/*.json`.
- A **missing EN translation never falls back silently.** Either the EN page doesn't render (its hreflang is omitted and the language switch shows "EN indisponível"), or the admin sees a "tradução pendente" badge. No mixed-language pages.
- Formats: pt-BR uses `R$ 1.299,00`, `23/09/2026`. EN uses BRL prices shown as `R$ 1,299.00`, dates as `Sep 23, 2026`. Prices stay in BRL (**OPEN**: USD for EN?).
