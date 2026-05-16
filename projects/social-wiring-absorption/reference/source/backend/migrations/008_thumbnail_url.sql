-- ============================================================================
-- YouTube Crawler — thumbnail_url
-- Carries an optional thumbnail-source URL through the upload pipeline.
-- ``run_upload_job`` downloads + pushes it as a custom YT thumbnail after
-- the video is uploaded (best-effort; thumbnail failure does NOT fail the
-- video itself).
-- ============================================================================

SET search_path = youtube_crawler, public;

ALTER TABLE youtube_crawler.upload_jobs
    ADD COLUMN IF NOT EXISTS thumbnail_url TEXT;

-- No index — thumbnail_url is read-only metadata + isn't a query filter
-- anywhere in the dashboard.

-- Column-level additions inherit existing RLS policies — no policy
-- changes needed.
