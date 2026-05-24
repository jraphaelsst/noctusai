# PROJECT — media-svg-render-mode

**Status:** ⏳ in-flight · **Branch:** `media-svg-render-mode` (off `dev`) · **Started:** 2026-05-24

## §1 Context
Final residual of the media-creator absorption. Audit (see `findings.md`) proved media-creator's functional core already lives in `social-wiring/media_creation` (Wave 2.4). The ONE genuine delta = **SVG-composited slide rendering** (deterministic typography/layout/brand via SVG; AI for photos only). noc is raster-only today. User chose: absorb it as a 2nd render mode. Demo-brand: no (user's data). Retire workspace: yes (Gate-9 sign-off).

## §2 Goal
Add an `svg` render mode to `social-wiring/media_creation` alongside the existing `raster` mode: deterministic brand-locked SVG slides → rasterized PNG, via a new seed SVG→PNG primitive.

## §3a Seed-first analysis
- **SVG→PNG rasterization** = cross-product-reusable outbound IO primitive ⇒ SEED (`noctusai_lib.integrations.svg_render`, Protocol+Fake+Real+factory). Per-product count = 0.
- **SVG slide template engine** (4 role builders + design-token model) — only consumer = media-creation (N=1) ⇒ stays in `social-wiring/media_creation`; [A] accept-at-N=1 with seed-convergence destination if N=2. Generic premium/educational presets (structure only) ship with it; Wilson's specific tokens = per-org DB data.
- **Fonts** bundled in the seed primitive package (one home) — not per-product.

## §4 Phases
- **P1 (seed)** — `integrations/svg_render`: types + Fake + Resvg(Real) + factory + bundled OFL fonts (Cormorant+Inter) + tests + `resvg-py` dep. File-disjoint (no consumers). [de-risked Phase 0 ✅]
- **P2 (social-wiring)** — `DesignTokens` model + premium/educational presets + 4 Jinja2 SVG role templates (Cover/Develop/Insight/CTA, ported from media-creator slides) + `render_post(mode=...)` wiring + migration (`mc_post_slides.svg_markup TEXT` + `mc_brand_kits.design_tokens JSONB`) + tests. Consumes P1.
- **P3 (integrate)** — container/propagate (dep + font package-data reach slim image) · pytest + vite build (end-of-session gate) · fix eval-README dangling pointer · KB pattern doc + CLAUDE.md pointer + memory (3-way sync) · Gate-9 sign-off · merge→dev.

## §5 Gates
- Wave: P2 gated on P1 contract green. P3 gated on P1∧P2 green.
- Dev↔prod parity: resvg-py linux wheel + bundled fonts verified to reach the slim `runtime` target.
- No push to `dev`/`main` without explicit user go.

## §11 Learnings
→ `findings.md` (curated at close).
