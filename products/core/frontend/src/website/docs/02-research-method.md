# 02 · Research method

## Reference set (13 sites, captured 2026-09-23)

| Group | Sites | Why |
|---|---|---|
| **AI-native leaders** | [Linear](03-reference-reports/linear.md) · [Vercel](03-reference-reports/vercel.md) · [Anthropic](03-reference-reports/anthropic.md) · [Runway](03-reference-reports/runway.md) | The "technical + confident" register; SaaS conversion; content hubs |
| **Brazilian SaaS** | [RD Station](03-reference-reports/rdstation.md) · [Conta Azul](03-reference-reports/contaazul.md) · [Pipefy](03-reference-reports/pipefy.md) · [Blip](03-reference-reports/blip.md) | What BR SMB buyers expect: WhatsApp, "a partir de R$", segments, LGPD |
| **Awwwards Sites of the Day (Aug–Sep 2026)** | [Cerebrium](03-reference-reports/cerebrium.md) · [Aspen Search](03-reference-reports/aspensearch.md) · [AI in Design 2026](03-reference-reports/stateofaidesign.md) · [Sharplink](03-reference-reports/sharplink.md) · [L.I.S.A.](03-reference-reports/lisa.md) | Craft tier: WebGL/3D heroes, typography as hero, art direction |

**Excluded: openai.com.** Cloudflare's human-verification challenge blocked every page, including the home page. Bot checks are never bypassed, so the site was dropped.

## How the capture worked

The owner first asked for the Chrome browser MCP. The extension would not connect (`list_connected_browsers` returned none), so the owner chose **headless Playwright Chromium** instead.

1. **Pages per site:** home plus up to 6 subpages, taken from header navigation or an explicit list (pricing, product, segment, blog, about, contact).
2. **Screenshots per page:** above the fold at 1440×900 and the full page. The home page was also captured at 390px mobile and with `prefers-color-scheme: dark`, to test whether the site follows the OS theme.
3. **Scroll first:** each page was scrolled slowly before capture so lazy content rendered. Cookie banners were rejected, never accepted, where a reject button existed.
4. **Scroll-revealed sites (Vercel, Pipefy):** full-page captures came back blank, so these were recaptured as viewport-by-viewport frames while scrolling.
5. **Data extracted per page:** title, meta, OG, canonical, hreflang, JSON-LD types, H1 plus its computed font metrics, font families, dominant computed colours, heading outline, nav labels, filled-button CTAs, forms, detected libraries (three.js, WebGL canvas, GSAP, Lenis, Lottie, video, framework), theme and language toggles, DOM size, word count, and a rough request/byte count.
6. **Analysis:** three analyst agents (one per group) viewed every screenshot and wrote a 12-section technical report per site from one template, plus a comparison per group.

## Known caveats

- **Byte counts are rough.** They sum `content-length` headers, which streamed video inflates and missing headers deflate. Treat them as orders of magnitude.
- **Headless capture misses hover and scroll-scrubbed motion.** Where motion is inferred rather than observed, the reports say so.
- **Tile citations** in the reports (`home t03`, `scroll home-s05`) point to the full capture archive, which is **not in the repo** (see below). Tile numbering was non-linear on some sites, so the analysts took section order from the full-page thumbnails.
- **Detector misses.** For example, the cookie banners on Conta Azul and Sharplink weren't detected. The screenshots are the ground truth.

## Artefacts

- **In the repo:** 27 curated fold screenshots (WebP, ~780 KB) in [`assets/refs/`](03-reference-reports/README.md#screenshots). They show the home above the fold, desktop and mobile, for every site, plus Vercel's dark variant.
- **Outside the repo:** the full capture archive. It holds about 450 full-page tiles, scroll frames and `extract.json` per site, roughly 58 MB, which is too heavy for git. The durable home is **OPEN**: a private storage bucket served by signed URL, per the zero-public-bucket rule. See [Build plan](14-build-plan.md#open-decisions).
- **Capture tooling:** an ad-hoc Playwright script. Turning it into a reusable `noctus.dev.*` MCP tool is a follow-up ([13](13-tooling-and-mcp-policy.md#reference-capture-tooling)).
