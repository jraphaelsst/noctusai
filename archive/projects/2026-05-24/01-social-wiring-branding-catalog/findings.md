# findings.md — social-wiring-branding-catalog

## knowledge
- Follow-on to media-svg-render-mode. User now wants Wilson's brand IN noc as the first entry of a multi-brand branding system (reverses earlier "leave as data").
- Decisions: **agency model** (one org → many agents → many brandings) ⇒ `mc_brand_owners` layer; **repo catalog → seeds DB**.
- Existing model: `mc_brand_kits` (per-org, design_tokens JSONB) + `mc_brand_references` (per kit). SVG render mode reads design_tokens. A "branding" = a brand_kit row; "agent" = new owner layer.
- Wilson design_tokens (from DESIGN-SYSTEM.md): premium bg#2A2620/deep#1A1612/gold#C5A55E/gold-bright#E0C076/text#F5F1EA/muted#A89B85/divider#3D362B; educational lavender#E8E5F0/navy#3A4FB8/yellow#F0E63A; handle @wilson_one2022; pin GRANJA VIANA. Verified: these tokens render Wilson's exact look via the svg mode.

## decisions (triage)
- [A] `mc_brand_owners` + catalog/loader stay product-local (N=1 media-creation); seed-convergence noted if a 2nd product needs brand-owners.
- design_tokens = palette + serif/sans families + handle + pin (the per-brand VARIABLE part); full design system prose → `design_system` text (LLM pipeline) + design-system.md doc (human). The locked skeleton (canvas/roles/layout) lives in the svg builders, not per-brand.
- Catalog format = JSON (stdlib, no PyYAML dep). One `brand.json` per owner dir: owner + brandings[] + references[].
- Seed = idempotent upsert keyed by (org_id, owner.slug) + (owner, branding.slug); re-runnable. References replaced-per-kit on seed (mirrors slides replace pattern).
- Reference images (1.9MB) committed as repo brand assets under the catalog (preserve Wilson's source; pipeline reads reference METADATA not bytes).
- Inline (not dispatched): sequential dependency chain (schema→loader→catalog→api), full architect context, briefing cost > zero parallelism gain.

## slips / errors / mistakes / lessons
- Loader generates UUIDs explicitly (not reliant on insert-return) → same code path works on real Supabase + MockSupabaseClient. Lesson: don't depend on insert-return id shape across client impls.
- Migration 003 policies use DROP POLICY IF EXISTS + CREATE (PG has no CREATE POLICY IF NOT EXISTS) → idempotent.

## verification
- 9 branding tests (loader parse + seed idempotency + HTTP seed/list/get/404/re-seed) + 69 media_creation + 508 social-wiring suites GREEN.
- End-to-end: load Wilson from catalog → resolve_tokens → svg render = Wilson's exact look (gold #C5A55E, handle @wilson_one2022, 1080×1350, 361KB — matches the standalone render). `/tmp/svg_render_demo/wilson-from-catalog.png`.
- Wilson = 1 agent (owner) with 2 brandings (premium + educational) — proves "more than 1 branding per agent".
