-- 031_media_creation_methodology_roles.sql — relax the media_creation CHECK
-- constraints for the Método Audience wiring.
--
-- Project: media-creation-methodology (2026-07-26). The storyboard generator now
-- builds posts on the Método Audience role skeleton
-- (capa/identificacao/virada/nome/prova/valor/cta) and supports a `reels` format.
-- The original 001 CHECK constraints only allowed the legacy role set
-- (cover/develop/insight/cta) and formats (carousel/single/video), so inserts of
-- the new values would fail. This forward migration widens both constraints.
--
-- WHY a forward migration (not an edit to 001): social-wiring 001 is already
-- applied to the noctusai Supabase project — an in-place edit to 001's CREATE
-- TABLE would never re-apply. Forward-only + idempotent, matching the 002+
-- convention. The legacy role/format values are KEPT so existing rows stay
-- valid and the legacy SVG layouts still dispatch.
--
-- Idempotent: DROP CONSTRAINT IF EXISTS + re-ADD. Zero data migration.

-- Posts: allow the `reels` format alongside the existing set.
ALTER TABLE social_wiring.mc_posts
    DROP CONSTRAINT IF EXISTS mc_posts_format_check;
ALTER TABLE social_wiring.mc_posts
    ADD CONSTRAINT mc_posts_format_check
    CHECK (format IN ('carousel', 'single', 'reels', 'video'));

-- Slides: allow the Método Audience role skeleton alongside the legacy roles.
ALTER TABLE social_wiring.mc_post_slides
    DROP CONSTRAINT IF EXISTS mc_post_slides_role_check;
ALTER TABLE social_wiring.mc_post_slides
    ADD CONSTRAINT mc_post_slides_role_check
    CHECK (role IN (
        -- Método Audience roles
        'capa', 'identificacao', 'virada', 'nome', 'prova', 'valor', 'cta',
        -- legacy roles (back-compat with existing rows + the legacy SVG layouts)
        'cover', 'develop', 'insight'
    ));
