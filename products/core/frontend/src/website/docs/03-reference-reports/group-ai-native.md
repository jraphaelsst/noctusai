# AI-native leaders: cross-site comparison (Linear · Vercel · Anthropic · Runway)
Captured 2026-09-23. Evidence is in the per-site reports. Perf numbers are rough (see caveats there).

## Key dimensions
| Dimension | Linear | Vercel | Anthropic | Runway |
|---|---|---|---|---|
| Stack | Next.js | Next.js + 1 canvas | Webflow+GSAP (home) / Next.js | Next.js + many `<video>` |
| Hero device | DOM product-UI mockup | Canvas-glow logo (triangle) | Serif mission text + brand-film video card | Full-bleed background video |
| H1 (size / weight / tracking) | 64/64 · 510 · −0.022em | 64/64 · 400 · −0.06em | 61/67 · 700 · normal | 40/46 · 400 · −0.5px |
| Font system | Inter + Berkeley Mono | Geist Sans + Geist Mono | Custom Sans + Custom Serif (+mono labels) | ABC Normal only |
| Base palette | Near-black, 1 indigo accent | Off-white/black mono, blue accent ~1× | Warm paper, clay accent | White/grey, blue-violet accent |
| prefers-color-scheme | No (dark-only) | **Yes (full inversion)** | No (light-only) | No (light-only) |
| On-page theme toggle | No | **Yes, 3-state system/light/dark, footer only** (scroll sandbox-s15) | No | No |
| i18n / hreflang | None | None (switcher detected) | None | **en/ja/ko/fr/pt-BR + x-default, locale toast** |
| Primary CTA | Sign up | Sign Up / Deploy now | Try Claude (split ▾) | Try Runway (for free) |
| Sales CTA | Contact sales | Get a Demo / Talk to sales | — | Enterprise Sales + 8-field form |
| Proof on home | Logos + 2 quotes + "40,000 teams" | Logos + customer metric per pillar (Notion/Zapier/Mintlify); quotes + metric row only on product pages | None (institutional trust) | Logo marquee + "60M+ creatives" |
| Pricing | 4 plans, per-card yearly toggle, long matrix | 3 plans, "Popular" anchor, grouped matrix | n/a | Segment tabs + yearly −20% + 2 anchors + outcome table |
| Content hub | "Now" (blog+changelog+press) | Blog w/ chip filters, text-first cards | Research/Engineering dated lists | News w/ tabs, grid/list, pagination |
| JSON-LD | WebPage (pricing only) | Org+Service+SoftwareApp; FAQPage | None | Org+SoftwareApp+WebSite; Offer×8+FAQ; Breadcrumb+ItemList |
| Weight (home) | 726 req / ~2.7MB | ~140 req / ~0.4MB | 22 req / ~1.6MB | 315 req / ~67MB (video) |

## Patterns shared by ≥3 sites
1. **Monochrome base + one accent hue** (all 4). Color is rationed; product UI, illustration or footage carries the color. NoctusAI: define 1 brand accent that works in both themes.
2. **Logo strip directly below the hero** (Linear, Vercel, Runway). The universal proof slot. NoctusAI: keep the slot behind the social-proof toggle, default off; never fill it with fabricated logos.
3. **Header = nav + one filled primary CTA + quieter secondary (login/sales)** (all 4). Exactly one filled button in the header. NoctusAI: primary "Falar no WhatsApp" or "Criar conta" (admin-switchable), with login as the quiet secondary.
4. **Dated momentum surfaces instead of (or alongside) testimonials** (Linear changelog, Vercel "Recently shipped", Anthropic "Latest releases", Runway "See the latest"). The best honest-proof pattern for a company with no customers to quote.
5. **Mega-footer with 5–12 labeled columns** (all 4). Doubles as a sitemap for SEO internal linking. Treatment varies: a dark contrasting band on Anthropic and Runway, the same background as the page on Vercel (light) and Linear (dark). Vercel also uses the footer as a utility bar (live status line + theme switcher + "New" pills).
6. **Tight negative tracking on large sans headlines, with mono as the "technical" accent font** (Linear, Vercel, Anthropic's spec labels). Reads as "technical + confident", the NoctusAI voice.
7. **Filterable content hub with category tabs + search (+RSS)** (Linear, Vercel, Runway; Anthropic uses team taxonomy). Blog layout baseline: tabs, search, date always visible.
8. **Self-canonical + summary_large_image OG on every page** (all 4), but **no hreflang on 3 of 4**. Only Runway does real i18n, and it is the model for pt-BR/EN.

## Notable divergences
- **Theme:** only Vercel honors `prefers-color-scheme`, and only Vercel has an on-page switch: a 3-state system/light/dark control tucked into the footer. None puts it in the header. NoctusAI should copy Vercel's 3-state control and its default of following the system setting, but in the header, which would be ahead of all four.
- **Pricing tools:** only Vercel puts an interactive cost calculator on a product page (slider → itemized breakdown → competitor bars, /sandbox). It is the strongest proof-free conversion device seen in this group.
- **3D/WebGL:** none of the four ships a WebGL hero. The heaviest motion is Runway's video and Vercel's canvas glow. NoctusAI's interactive 3D hero is a differentiator; the group evidence says keep it lazy with a static poster (Vercel's light/dark triangle is the fallback template).
- **Product vs brand hero:** Linear and Vercel sub-pages show the product (UI/code); Anthropic and Runway sell a vision (text/film). NoctusAI's hybrid wants both: a vision H1 plus product mockups immediately below.
- **Audience routing:** Runway routes explicitly per platform with CTA trios; Anthropic routes inside the H1 (underlined words); Linear/Vercel route via nav mega-menus. The Runway card trio plus Anthropic in-H1 links fit NoctusAI's 4 audiences best.
- **SEO rigor:** Runway (keyword titles, Offer/FAQ/Breadcrumb schema, hreflang) > Vercel (FAQ/Org schema) > Linear (dynamic OG, little schema) > Anthropic (duplicate metas, missing H1, no schema).
- **Performance vs richness:** Anthropic and Vercel stay light; Runway is 20–100× heavier. Linear is heavy in request count (script chunking) despite zero media.
