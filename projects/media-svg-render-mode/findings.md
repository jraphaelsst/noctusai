# findings.md — media-svg-render-mode

> 5 categories: slips · errors · mistakes · lessons · knowledge. Append in-the-moment; synthesize at close.

## knowledge
- **media-creator was already ~95% absorbed** into `social-wiring/media_creation` (Wave 2.4, ~2026-05-20). Pipeline (storyboard→image_prompts→copy), brand-kit/persona/design-system structure, references framework, image_gen (seed), AND the golden example (→ eval case `post1_3_condominios_cotia.json`) all already in noc. Provenance docstrings throughout. The user's "absorb the product" framing ⊥ tree reality → Gate-3 interrogation surfaced it; user chose audit-first.
- **The ONE genuine delta**: SVG-composited slide rendering. media-creator renders each slide as deterministic SVG (locked palette/typography/4-role-layout, photo as embedded/placeholder) → rasterize via `@resvg/resvg-js`. noc `render_post` is RASTER-ONLY (Gemini generates the whole image). User decision: absorb as a 2nd render mode.
- **Rasterizer de-risk (Phase 0, proven not asserted)**: `resvg-py` (PyPI 0.3.2) — `svg_to_bytes(svg_string, font_files=[...], skip_system_fonts=True, width, height)` returns valid PNG bytes. cp311 manylinux2014_x86_64 wheel downloads cleanly ⇒ slim-container-compatible, NO system libs (vs cairosvg needing libcairo). Cormorant+Inter variable fonts (Google OFL) render (with-font 19131B vs without 5742B → text drew). Bundle fonts as package assets + `skip_system_fonts=True` ⇒ deterministic, dev↔prod-parity-safe.
- **Brand-token tension**: noc stores `mc_brand_kits.design_system` as PROSE; deterministic SVG needs STRUCTURED tokens (palette hex, type scale, role). Resolution: add `mc_brand_kits.design_tokens JSONB NULL` (brand supplies tokens as DATA — honors "Wilson brand = user's data") + ship generic premium/educational presets (structure only, NOT Wilson's colors).

## lessons
- (Phase 0) De-risk the load-bearing external dep BEFORE planning locks to it — verified resvg-py installs + rasterizes + has a linux wheel + renders bundled variable fonts, all before writing a line of the primitive.

## decisions (triage)
- [F] SVG→PNG rasterization → SEED primitive `noctusai_lib.integrations.svg_render` (Protocol+Fake+Real+factory, lazy resvg import, bundled fonts) — mirrors `image_gen`/`media`. Rationale: outbound render is a reusable IO primitive; `media` is inbound-only.
- [F] resvg-py added to SEED deps (lazy-imported) — matches PyMuPDF/google-genai precedent (heavy media deps in seed-required, Fake path works without).
- [A→F] SVG slide template engine stays in `social-wiring/media_creation` at N=1 (only media-creation consumer); seed-convergence destination noted if N=2 surfaces.

## slips / errors / mistakes
- (Phase 0) First Cormorant fetch saved a 404 HTML page as `.ttf` (wrong Google-fonts path) — caught by HTTP-404 + size-mismatch; corrected via the GitHub contents API (real path `CormorantGaramond[wght].ttf`). Lesson: verify downloaded asset is the asset (curl `-w "HTTP %{http_code}"` + `file`), don't trust exit 0.

## fix-on-contact (bumped-into pre-existing)
- Eval README `tests/.../evals/README.md` points at `projects/media-creator-evals-cases/PROJECT.md` which no longer exists → durable-doc→transient-`projects/`-path violation. Fix in Phase 3.
- 19 stale agent worktrees = 3.3 GB in `.claude/worktrees/`. Tangential disk debt — surface to user, offer cleanup (destructive → confirm).
