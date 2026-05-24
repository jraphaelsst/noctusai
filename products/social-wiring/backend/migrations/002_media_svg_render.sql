-- 002_media_svg_render.sql — additive forward migration for the SVG render mode.
--
-- Project: media-svg-render-mode (the media-creator absorption residual, 2026-05-24).
-- Adds the deterministic SVG render path alongside the existing raster
-- (Gemini image-gen) path in the media_creation module.
--
-- WHY a forward 002 (not an edit to the canonical 001): social-wiring 001 has
-- already been applied to the noctusai Supabase project (deployed 2026-05-22),
-- so an in-place edit to 001's CREATE TABLE would never re-apply. This file is
-- forward-only + idempotent (ADD COLUMN IF NOT EXISTS), applies cleanly to the
-- in-prod DB, and matches core's 030+ forward-migration convention.
--
-- NOTE: the offline local-db builder (scripts/bootstrap/build-init-local-db.sh)
-- consumes only each product's FIRST (001_*) migration, so these columns are
-- absent from the offline bootstrap DB — same as core's 030-035. Tests mock the
-- DB (MockSupabaseClient), so this does not affect the suite. Apply to the real
-- Supabase (social_wiring schema) at deploy time via the migration tooling.
--
-- All columns are NULLable + additive → zero impact on existing rows. RLS is
-- inherited from the existing mc_brand_kits / mc_post_slides table policies
-- (Postgres row policies cover new columns; no policy change required).

-- Structured design tokens (palette / typography / brand) a brand kit can
-- supply as DATA to drive deterministic SVG slides. NULL → the module falls
-- back to the generic premium/educational preset for the post's variant. A
-- specific brand (e.g. a client's exact palette) lives HERE, per-org, never in
-- platform code.
ALTER TABLE social_wiring.mc_brand_kits
    ADD COLUMN IF NOT EXISTS design_tokens JSONB;

-- The composed SVG markup for a slide (the editable, deterministic source).
-- Populated by the svg render mode; the rasterized PNG lands on the existing
-- image_url column with image_renderer = 'svg'.
ALTER TABLE social_wiring.mc_post_slides
    ADD COLUMN IF NOT EXISTS svg_markup TEXT;
