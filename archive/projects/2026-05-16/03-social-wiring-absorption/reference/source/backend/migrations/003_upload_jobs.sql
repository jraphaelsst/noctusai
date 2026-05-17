-- ============================================================================
-- YouTube Crawler — upload_jobs
-- Tracks the lifecycle of a single video upload from "queued" through
-- "published" + "notified" (or "failed"). One row per upload attempt;
-- retries write a fresh row so progress is auditable.
--
-- Status flow:
--   queued → downloading? → uploading → processing → published → notified
--                                                            ↘ failed (terminal)
--
-- `downloading` only applies to gdrive-sourced jobs (browser uploads stream
-- straight from the request body). `processing` reflects YouTube's own
-- post-upload pipeline; the API call returns when the bytes are uploaded
-- but the video isn't watchable until processing finishes.
-- ============================================================================

SET search_path = youtube_crawler, public;

CREATE TABLE youtube_crawler.upload_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    youtube_video_id TEXT,                       -- populated once videos.insert returns
    title TEXT NOT NULL,
    description TEXT,
    tags TEXT[],
    privacy_status TEXT NOT NULL DEFAULT 'private'
        CHECK (privacy_status IN ('public', 'unlisted', 'private')),
    category_id TEXT NOT NULL DEFAULT '22',      -- "People & Blogs"
    source_type TEXT NOT NULL
        CHECK (source_type IN ('browser', 'gdrive')),
    source_url TEXT,                             -- Google Drive URL if source_type='gdrive'
    file_name TEXT NOT NULL,
    file_size_bytes BIGINT,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'downloading', 'uploading', 'processing', 'published', 'notified', 'failed')),
    progress_percent INTEGER NOT NULL DEFAULT 0
        CHECK (progress_percent BETWEEN 0 AND 100),
    error_message TEXT,
    notify_recipients UUID[] NOT NULL DEFAULT '{}',  -- empty = notify nobody for this job
    created_by UUID,                                  -- auth.users.id who started the job
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE youtube_crawler.upload_jobs ENABLE ROW LEVEL SECURITY;

-- Matches `rls_subquery_policy(youtube_crawler, "upload_jobs",
--   "upload_jobs_select_own_org", "SELECT",
--   using="org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid")` output.
CREATE POLICY "upload_jobs_select_own_org" ON youtube_crawler.upload_jobs
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

-- Authenticated users in the org can INSERT (queue a new upload), and UPDATE
-- their own org's rows (cancel-by-owner is Phase 4+; for now the backend
-- service-role updates progress, but the policy already permits org-scoped
-- self-edits so cancellation can ship without a migration).
CREATE POLICY "upload_jobs_insert_own_org" ON youtube_crawler.upload_jobs
    FOR INSERT TO authenticated
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "upload_jobs_update_own_org" ON youtube_crawler.upload_jobs
    FOR UPDATE TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid)
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

-- Service role does the heavy lifting from the upload pipeline (status
-- transitions, error capture). Separate policy so the role split is explicit.
CREATE POLICY "upload_jobs_service_role" ON youtube_crawler.upload_jobs
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE INDEX idx_yt_upload_jobs_org ON youtube_crawler.upload_jobs(org_id);
CREATE INDEX idx_yt_upload_jobs_status ON youtube_crawler.upload_jobs(org_id, status);
CREATE INDEX idx_yt_upload_jobs_created ON youtube_crawler.upload_jobs(org_id, created_at DESC);


-- The FK from notification_log.upload_job_id → upload_jobs.id lives in
-- migration 005 (which created notification_log) — it's been backfilled
-- there now that upload_jobs exists.

INSERT INTO youtube_crawler.status_pagina (nome_pagina, status) VALUES
    ('upload', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
