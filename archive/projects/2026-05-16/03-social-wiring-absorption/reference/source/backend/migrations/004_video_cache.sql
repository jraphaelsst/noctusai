-- ============================================================================
-- YouTube Crawler — video_cache
-- Local mirror of the connected channel's video catalog. The cache lets the
-- Videos page render instantly + the Dashboard aggregate over the org's
-- entire channel without paying YouTube quota on every page load.
--
-- Sync model: explicit refresh only (POST /api/videos/sync). The cache is
-- staleness-tolerant — view counts age, but the Settings UI surfaces
-- last-synced-at so the operator knows when the numbers were captured.
--
-- The `uploaded_via_app` flag distinguishes cache rows that originated from
-- this product's upload pipeline (cross-referenced via upload_jobs.youtube_video_id)
-- vs videos uploaded externally (YouTube Studio, mobile app, etc.). Drives the
-- Dashboard's "Recent uploads via app" panel + the Videos page's app-badge.
-- ============================================================================

SET search_path = youtube_crawler, public;

CREATE TABLE youtube_crawler.video_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    youtube_video_id TEXT NOT NULL,
    title TEXT,
    description TEXT,
    thumbnail_url TEXT,
    published_at TIMESTAMPTZ,
    duration TEXT,                               -- ISO-8601 (PT1M30S)
    privacy_status TEXT
        CHECK (privacy_status IS NULL OR privacy_status IN ('public', 'unlisted', 'private')),
    view_count BIGINT NOT NULL DEFAULT 0,
    like_count BIGINT NOT NULL DEFAULT 0,
    comment_count BIGINT NOT NULL DEFAULT 0,
    favorite_count BIGINT NOT NULL DEFAULT 0,
    tags TEXT[] NOT NULL DEFAULT '{}',
    category_id TEXT,
    uploaded_via_app BOOLEAN NOT NULL DEFAULT false,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, youtube_video_id)
);

ALTER TABLE youtube_crawler.video_cache ENABLE ROW LEVEL SECURITY;

-- Matches `rls_subquery_policy(youtube_crawler, "video_cache",
--   "video_cache_select_own_org", "SELECT",
--   using="org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid")` output.
CREATE POLICY "video_cache_select_own_org" ON youtube_crawler.video_cache
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

-- Writes go through the backend's service-role client (the sync pipeline
-- batches upserts); user-side direct writes are not a use case today.
CREATE POLICY "video_cache_service_role" ON youtube_crawler.video_cache
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE INDEX idx_yt_video_cache_org ON youtube_crawler.video_cache(org_id);
CREATE INDEX idx_yt_video_cache_published
    ON youtube_crawler.video_cache(org_id, published_at DESC);
CREATE INDEX idx_yt_video_cache_uploaded_via_app
    ON youtube_crawler.video_cache(org_id, uploaded_via_app)
    WHERE uploaded_via_app = true;
CREATE INDEX idx_yt_video_cache_synced
    ON youtube_crawler.video_cache(org_id, synced_at DESC);

INSERT INTO youtube_crawler.status_pagina (nome_pagina, status) VALUES
    ('videos', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
