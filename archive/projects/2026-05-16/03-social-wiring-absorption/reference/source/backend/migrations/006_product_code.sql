-- ============================================================================
-- YouTube Crawler — product_code
-- Associates upload jobs with real estate property codes (e.g. ONE5555).
-- Used by the CRM integration to auto-populate video title + description.
-- ============================================================================

SET search_path = youtube_crawler, public;

ALTER TABLE youtube_crawler.upload_jobs
    ADD COLUMN IF NOT EXISTS product_code TEXT;

CREATE INDEX IF NOT EXISTS idx_yt_upload_jobs_product_code
    ON youtube_crawler.upload_jobs(org_id, product_code);

-- Column-level additions inherit existing RLS policies — no policy
-- changes needed.
