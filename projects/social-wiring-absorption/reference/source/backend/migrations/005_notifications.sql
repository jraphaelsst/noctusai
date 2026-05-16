-- ============================================================================
-- YouTube Crawler — notifications
-- Recipient list (Settings page CRUD) + per-dispatch delivery log.
-- The recipients table is needed in Phase 1 (Settings page); the log table
-- is exercised in Phase 4 (Notifications dispatch from upload pipeline).
-- ============================================================================

SET search_path = youtube_crawler, public;

CREATE TABLE youtube_crawler.notification_recipients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    name TEXT NOT NULL,
    email TEXT,                                  -- NULL = no email channel
    whatsapp_number TEXT,                        -- E.164 format: +5511999999999
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- A recipient with neither channel is a degenerate row that would never
    -- get notified. Block at the DB level so the API surface is honest.
    CONSTRAINT recipient_has_at_least_one_channel
        CHECK (email IS NOT NULL OR whatsapp_number IS NOT NULL)
);

ALTER TABLE youtube_crawler.notification_recipients ENABLE ROW LEVEL SECURITY;

CREATE POLICY "notification_recipients_select_own_org"
    ON youtube_crawler.notification_recipients
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "notification_recipients_write_own_org"
    ON youtube_crawler.notification_recipients
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid)
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_yt_notification_recipients_org
    ON youtube_crawler.notification_recipients(org_id);
CREATE INDEX idx_yt_notification_recipients_active
    ON youtube_crawler.notification_recipients(org_id, is_active)
    WHERE is_active = true;


-- ============================================================================
-- Notification log
-- One row per (upload_job, recipient, channel) dispatch attempt. Captures
-- transient failures + retries. References upload_jobs (Phase 2 migration);
-- the FK is a CASCADE so log entries don't outlive their source job.
-- ============================================================================

CREATE TABLE youtube_crawler.notification_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    upload_job_id UUID REFERENCES youtube_crawler.upload_jobs(id) ON DELETE CASCADE,
    recipient_id UUID REFERENCES youtube_crawler.notification_recipients(id) ON DELETE SET NULL,
    channel TEXT NOT NULL CHECK (channel IN ('email', 'whatsapp')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'failed')),
    error_message TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE youtube_crawler.notification_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "notification_log_select_own_org"
    ON youtube_crawler.notification_log
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "notification_log_write_service_role"
    ON youtube_crawler.notification_log
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE INDEX idx_yt_notification_log_org
    ON youtube_crawler.notification_log(org_id);
CREATE INDEX idx_yt_notification_log_job
    ON youtube_crawler.notification_log(upload_job_id);
CREATE INDEX idx_yt_notification_log_recipient
    ON youtube_crawler.notification_log(recipient_id);
