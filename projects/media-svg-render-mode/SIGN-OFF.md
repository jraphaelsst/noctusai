# Gate-9 sign-off — media-creator workspace safe to retire

**Date:** 2026-05-24 · **Project:** media-svg-render-mode · **Verdict:** ✅ SAFE TO DELETE — with one data caveat (§B).

The media-creator workspace (`/Users/rapha/Documents/repository/NoctusAI/media-creator`, not a git repo) was a single-tenant, file-based creative-director prototype. Its functional substance is now in noc. **You delete the workspace manually — noc never deletes it.**

## A · Every artifact → its noc home (nothing useful lost)

| media-creator artifact | Where it lives in noc now |
|---|---|
| Pipeline (idea → storyboard → image-prompts → copy) | `social-wiring/media_creation/services/generation_service.py` (4 stages) |
| `skills/carousel-storyboard`, `image-prompt-generator`, `instagram-copywriting` | `media_creation/prompts/{storyboard,image_prompts,copy}.py` (provenance-documented `# Ported from media-creator/skills/...`) |
| `skills/brand-voice`, `visual-style-guide`, `DESIGN-SYSTEM.md` *structure* | `mc_brand_kits` (persona / design_system / **design_tokens** JSONB) + the `DesignTokens` premium/educational presets (generic structure) |
| `PERSONA.md`, `CLAUDE.md` creative methodology | Embedded in the prompt constants (source of truth) + `KB § PATTERNS/svg-render-mode.md` provenance |
| Renderers nano_banana / galilai / midjourney | Seed `noctusai_lib.integrations.image_gen` (renderer flavors) |
| **SVG slide rendering + `scripts/svg-to-png.mjs`** | **NEW this project:** seed `noctusai_lib.integrations.svg_render` (SVG→PNG, resvg + bundled fonts) + `media_creation` `render_post(mode="svg")` (4 role builders) |
| `output/carousels/post1-3-condominios-cotia/` (the validated example) | Already a regression eval fixture: `media_creation/tests/.../evals/cases/post1_3_condominios_cotia.json` |
| `.mcp.json` (mcp-image Gemini), `.env` GEMINI_API_KEY | Superseded by seed `image_gen` + `svg_render`; key via root `.env` `GEMINI_API_KEY` |
| `templates/carousel-myth-vs-truth`, `evals/cases` (empty), `workflows/` (empty) | "Myth vs Truth" is an arc pattern in `storyboard.py`; eval harness + cases live in noc; nothing unique to port |

## B · ⚠ One data caveat — the Wilson / Granja-Viana brand is NOT in noc (by your choice)

You chose "leave the brand as my data" (not seed a demo). So these **brand-specific files exist ONLY in the workspace**:
- `DESIGN-SYSTEM.md` — the full Wilson palette / typography / layout (the exact hexes `#2A2620` / `#C5A55E`, Cormorant/Inter scale). noc has only a **condensed** version in the eval fixture + **generic** presets.
- `references/models/post1`, `post2`, `references/CHAT-GPT.md`, palettes/typography — Wilson reference assets.

**In noc's model these are per-org DATA**: you re-enter them once as a `mc_brand_kits` row with the `design_tokens` JSONB (the SVG mode then renders the exact Wilson look — proven 2026-05-24). They are **not** lost capability, but if you want to keep the source files, **copy `DESIGN-SYSTEM.md` + `references/` somewhere before deleting** the workspace. (Verified: feeding the Wilson tokens as `design_tokens` reproduces the prototype look pixel-faithfully.)

## C · Deploy steps to make the new SVG mode live (NOT done — landed on `dev`)
1. Rebuild the seed base image: `bash scripts/infra/build-base-images.sh` (auto-installs `resvg-py` + bundled fonts via the editable seed install). Slim-image smoke already verified.
2. Apply `products/social-wiring/backend/migrations/002_media_svg_render.sql` to the noctusai Supabase (`social_wiring` schema) — additive nullable cols, zero-risk.
3. (prod polish) Wire a Supabase-Storage `upload_url_resolver` into the svg adapter so rasterized PNGs are URLs, not inline `data:`.

## D · Verification evidence
- 18 svg tests + 60 media_creation + 499 social-wiring backend suites green; seed-lib 1844 pass (the 1 fail = pre-existing unrelated KE CORS sentinel, see PROJECT.md/findings).
- All 4 roles render to valid 1080×1350 PNGs; cover + cta visually confirmed.
- Slim-image smoke: `resvg-py` installs + rasterizes in `python:3.11-slim` (prod base), zero system libs.
