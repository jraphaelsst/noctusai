# SVG render mode — deterministic brand-locked slides

> Two layers: the **seed SVG→PNG primitive** (`noctusai_lib.integrations.svg_render`)
> and its first consumer, the **`svg` render mode** in `social-wiring/media_creation`.
> Born 2026-05-24 as the final residual of the media-creator absorption: the
> media-creator prototype rendered carousel slides as deterministic SVG (locked
> palette / typography / layout; AI only for photography) → rasterized via
> `@resvg/resvg-js`. This is the noc-native, Python, seed-first equivalent.

---

## 1 · The seed primitive — `noctusai_lib.integrations.svg_render`

Protocol+Fake+Real+factory, mirroring `image_gen` / `media`
(`KB § PATTERNS/seed-fake-real-adapter.md`). **Outbound** rasterization
(markup → pixels) — sibling to `integrations/media` (inbound media → text).

`__all__`: `SvgRenderInput` · `RenderedImage` · `SvgRenderAdapter` (Protocol) ·
`FakeSvgRenderAdapter` · `ResvgRenderAdapter` · `get_svg_render_adapter` ·
`bundled_font_files` · `resvg_available`.

- **Real** = `ResvgRenderAdapter` → `resvg-py` (self-contained Rust `resvg`
  binding; ships manylinux2014 + macOS cp3x wheels, **NO system libs** ⇒ works
  unchanged in the slim prod `runtime` image, unlike cairosvg which needs
  libcairo). Lazy-imported — the seed stays importable without it; the **Fake**
  path is the dev/test default.
- **Fonts are bundled** (`svg_render/fonts/*.ttf`: Cormorant Garamond + Inter,
  OFL) and passed with `skip_system_fonts=True` ⇒ deterministic text without a
  system-font install. This is the dev↔prod-parity choice — the slim image has
  no system fonts ([[feedback_dev_prod_parity_verify_in_prod_shape]]). Family
  names referenced in SVG MUST match the bundled faces; **no Google-fonts
  `@import`** (won't resolve server-side). NO emoji font ⇒ no emoji glyphs in
  markup (they rasterize as tofu) — draw glyphs as `<path>`.

```python
from noctusai_lib.integrations.svg_render import SvgRenderInput, get_svg_render_adapter
adapter = get_svg_render_adapter(real=True)                 # prod
result = adapter.render(SvgRenderInput(svg_markup=svg, width=1080, height=1350))
storage.put(path, result.png_bytes)                         # or pass upload_url_resolver
```

`upload_url_resolver=(png_bytes, SvgRenderInput) -> url` persists the PNG to
durable storage (e.g. Supabase Storage) and lands the URL on
`RenderedImage.image_url`; omit it and the caller persists `png_bytes`. Tests
inject `FakeSvgRenderAdapter` (or `real=False`) — never monkeypatch the real
adapter ([[di-test-seam]]).

**Dev↔prod parity — proven, not asserted:** `resvg-py` installs in
`python:3.11-slim` (the exact base) with zero system libs and rasterizes a
valid PNG (2026-05-24 slim smoke). Base-image rebuild auto-picks-up the dep +
fonts via `pip install -e ./seed/lib/backend` (editable reads copied source).

## 2 · The consumer — `svg` render mode in `social-wiring/media_creation`

`GenerationService.render_post(post, *, mode="raster"|"svg", variant=None)`:

- `mode="raster"` (default) — unchanged: one AI image per slide via `image_gen`.
- `mode="svg"` — per slide: resolve `DesignTokens` → build the role SVG →
  rasterize via the seed primitive → persist `svg_markup` + `image_renderer='svg'`
  (+ PNG as a `data:` URL when no storage resolver is wired — the image_gen dev
  fallback shape; prod wires an `upload_url_resolver`).

HTTP: `POST /api/media-creation/posts/{id}/render` body `{mode, renderer, variant}`.

### Design tokens (`design/tokens.py`)
`DesignTokens` (palette / type scale / canvas / brand handle+pin) + **generic**
`premium` / `educational` presets (structural idioms only — neutral dark+gold /
light+navy). `resolve_tokens(brand_kit, variant)` = preset overridden by the
brand kit's `mc_brand_kits.design_tokens` JSONB. **A specific brand's exact
palette is per-org DATA in that column, never baked into platform code.**

### Slide builders (`design/svg_slides.py`)
Token-driven Python builders, one per role — `cover` / `develop` / `insight` /
`cta` (the locked DESIGN-SYSTEM skeleton: canvas 1080×1350, safe-area margins,
gold accent rules, brand handle). All caller text is XML-escaped (`_esc` — the
slide engine is an injection boundary). v1 photo = gradient placeholder
(faithful to media-creator's validated first pass); AI-photo-embed (data-URI
into `<image>`) is a fast-follow.

### Migration
`002_media_svg_render.sql` — forward, idempotent `ADD COLUMN IF NOT EXISTS`
(`design_tokens` JSONB on `mc_brand_kits`; `svg_markup` TEXT on
`mc_post_slides`). Forward-only because `001` is already in prod (deployed
2026-05-22); matches core's 030+ convention. The offline local-db builder takes
only each product's `001_*`, so these cols are absent there (same as core 030+);
tests mock the DB. Apply to the real Supabase at deploy.

## 3 · Provenance / triage
- `svg_render` primitive = [F] formalize-to-seed (outbound render is reusable).
- SVG slide engine = [A] accept at N=1 (only `media_creation` consumes it);
  seed-convergence destination if N=2 surfaces.
- Built by `projects/media-svg-render-mode` (the media-creator absorption residual).
  media-creator's functional core was already ported into `media_creation`
  (Wave 2.4); this closed the one remaining capability gap.
