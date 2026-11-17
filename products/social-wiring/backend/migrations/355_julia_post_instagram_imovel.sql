-- Migration 355: julia_post_instagram_imovel -- which listing an Instagram post/reel advertises.
-- WHY: a lead who pastes instagram.com/p/<code> or /reel/<code> means the listing the post shows. No table linked a post
-- to a listing (ig_media / cs_posts carry the permalink but no imovel), so Julia could only say "I don't have it". One dated
-- (shortcode shape is validated by the API, `julia_imovel_instagram.analisar`.) One dated row per (org, shortcode) is the link; Julia's `resolver_imovel` reads it. An admin sets it (API: /api/julia/post-instagram-imovel).
SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.julia_post_instagram_imovel (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    -- The post's shortcode (the segment after /p/ or /reel/); Instagram shortcodes are case-sensitive.
    shortcode text NOT NULL,
    codigo_imovel text NOT NULL,
    permalink text,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT julia_post_instagram_imovel_org_shortcode_uq UNIQUE (org_id, shortcode)
);

COMMENT ON TABLE social_wiring.julia_post_instagram_imovel IS 'tier:org';

ALTER TABLE social_wiring.julia_post_instagram_imovel ENABLE ROW LEVEL SECURITY;
-- Service role only (the backend reads/writes it org-scoped); no browser grant.
REVOKE ALL ON social_wiring.julia_post_instagram_imovel FROM anon, authenticated;
