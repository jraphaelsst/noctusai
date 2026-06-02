-- 009_youtube_timeseries.sql — Phase-3 YouTube timeseries schema.
--
-- Project: social-wiring-yt-timeseries (2026-06-01). Adds:
--   • youtube_videos       — catalog, one row per video per account
--   • youtube_shorts       — catalog (extends video columns), shorts classification
--   • youtube_channel_snapshots — channel-level daily snapshots
--   • youtube_video_snapshots  — unified per-video timeseries (videos + shorts)
--   • snapshot_runs        — claim-row guard against double-spend of YouTube quota
--
-- RLS shape (copied from video_cache in 001):
--   SELECT TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid)
--   ALL    TO service_role   USING (true) WITH CHECK (true)
-- snapshot_runs has no org_id → service_role only (guard table, never read
-- directly by the client; access is through the snapshot-worker service role).
--
-- Forward-only + idempotent (CREATE TABLE IF NOT EXISTS, DO $$ guarded policies).
-- Apply to the noctusai Supabase (social_wiring schema) at deploy.

SET search_path = social_wiring, public;


-- ============================================================================
-- youtube_videos — catalog, one row per video per account
-- ============================================================================

CREATE TABLE IF NOT EXISTS social_wiring.youtube_videos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    account_id          UUID NOT NULL
        REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE,
    youtube_video_id    TEXT NOT NULL,
    title               TEXT,
    description         TEXT,
    thumbnail_url       TEXT,
    published_at        TIMESTAMPTZ,
    channel_id          TEXT,
    tags                TEXT[] NOT NULL DEFAULT '{}',
    category_id         TEXT,
    duration_iso        TEXT,
    duration_seconds    INTEGER,
    privacy_status      TEXT
        CHECK (privacy_status IS NULL
               OR privacy_status IN ('public', 'unlisted', 'private')),
    view_count          BIGINT NOT NULL DEFAULT 0,
    like_count          BIGINT NOT NULL DEFAULT 0,
    comment_count       BIGINT NOT NULL DEFAULT 0,
    favorite_count      BIGINT NOT NULL DEFAULT 0,
    uploaded_via_app    BOOLEAN NOT NULL DEFAULT false,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, youtube_video_id)
);

ALTER TABLE social_wiring.youtube_videos ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'social_wiring'
          AND tablename  = 'youtube_videos'
          AND policyname = 'youtube_videos_select_own_org'
    ) THEN
        CREATE POLICY "youtube_videos_select_own_org" ON social_wiring.youtube_videos
            FOR SELECT TO authenticated
            USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'social_wiring'
          AND tablename  = 'youtube_videos'
          AND policyname = 'youtube_videos_service_role'
    ) THEN
        CREATE POLICY "youtube_videos_service_role" ON social_wiring.youtube_videos
            FOR ALL TO service_role
            USING (true) WITH CHECK (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_sw_youtube_videos_org_published
    ON social_wiring.youtube_videos (org_id, published_at DESC);


-- ============================================================================
-- youtube_shorts — catalog with shorts-classification columns
-- ============================================================================

CREATE TABLE IF NOT EXISTS social_wiring.youtube_shorts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL,
    account_id              UUID NOT NULL
        REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE,
    youtube_video_id        TEXT NOT NULL,
    title                   TEXT,
    description             TEXT,
    thumbnail_url           TEXT,
    published_at            TIMESTAMPTZ,
    channel_id              TEXT,
    tags                    TEXT[] NOT NULL DEFAULT '{}',
    category_id             TEXT,
    duration_iso            TEXT,
    duration_seconds        INTEGER,
    privacy_status          TEXT
        CHECK (privacy_status IS NULL
               OR privacy_status IN ('public', 'unlisted', 'private')),
    view_count              BIGINT NOT NULL DEFAULT 0,
    like_count              BIGINT NOT NULL DEFAULT 0,
    comment_count           BIGINT NOT NULL DEFAULT 0,
    favorite_count          BIGINT NOT NULL DEFAULT 0,
    uploaded_via_app        BOOLEAN NOT NULL DEFAULT false,
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- shorts-specific classification
    detected_via            TEXT NOT NULL
        CHECK (detected_via IN ('probe', 'duration', 'hashtag', 'manual')),
    is_short_confidence     TEXT NOT NULL DEFAULT 'high'
        CHECK (is_short_confidence IN ('high', 'medium', 'low')),
    classified_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, youtube_video_id)
);

ALTER TABLE social_wiring.youtube_shorts ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'social_wiring'
          AND tablename  = 'youtube_shorts'
          AND policyname = 'youtube_shorts_select_own_org'
    ) THEN
        CREATE POLICY "youtube_shorts_select_own_org" ON social_wiring.youtube_shorts
            FOR SELECT TO authenticated
            USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'social_wiring'
          AND tablename  = 'youtube_shorts'
          AND policyname = 'youtube_shorts_service_role'
    ) THEN
        CREATE POLICY "youtube_shorts_service_role" ON social_wiring.youtube_shorts
            FOR ALL TO service_role
            USING (true) WITH CHECK (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_sw_youtube_shorts_org_published
    ON social_wiring.youtube_shorts (org_id, published_at DESC);


-- ============================================================================
-- youtube_channel_snapshots — channel-level daily timeseries
-- ============================================================================

CREATE TABLE IF NOT EXISTS social_wiring.youtube_channel_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    account_id          UUID NOT NULL
        REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE,
    snapshot_date       DATE NOT NULL,
    subscriber_count    BIGINT NOT NULL DEFAULT 0,
    view_count          BIGINT NOT NULL DEFAULT 0,
    video_count         BIGINT NOT NULL DEFAULT 0,
    captured_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, snapshot_date)
);

ALTER TABLE social_wiring.youtube_channel_snapshots ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'social_wiring'
          AND tablename  = 'youtube_channel_snapshots'
          AND policyname = 'youtube_channel_snapshots_select_own_org'
    ) THEN
        CREATE POLICY "youtube_channel_snapshots_select_own_org"
            ON social_wiring.youtube_channel_snapshots
            FOR SELECT TO authenticated
            USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'social_wiring'
          AND tablename  = 'youtube_channel_snapshots'
          AND policyname = 'youtube_channel_snapshots_service_role'
    ) THEN
        CREATE POLICY "youtube_channel_snapshots_service_role"
            ON social_wiring.youtube_channel_snapshots
            FOR ALL TO service_role
            USING (true) WITH CHECK (true);
    END IF;
END $$;


-- ============================================================================
-- youtube_video_snapshots — unified per-video timeseries (videos + shorts)
-- ============================================================================

CREATE TABLE IF NOT EXISTS social_wiring.youtube_video_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    account_id          UUID NOT NULL
        REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE,
    youtube_video_id    TEXT NOT NULL,
    kind                TEXT NOT NULL CHECK (kind IN ('video', 'short')),
    snapshot_date       DATE NOT NULL,
    view_count          BIGINT NOT NULL DEFAULT 0,
    like_count          BIGINT NOT NULL DEFAULT 0,
    comment_count       BIGINT NOT NULL DEFAULT 0,
    captured_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, youtube_video_id, snapshot_date)
);

ALTER TABLE social_wiring.youtube_video_snapshots ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'social_wiring'
          AND tablename  = 'youtube_video_snapshots'
          AND policyname = 'youtube_video_snapshots_select_own_org'
    ) THEN
        CREATE POLICY "youtube_video_snapshots_select_own_org"
            ON social_wiring.youtube_video_snapshots
            FOR SELECT TO authenticated
            USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'social_wiring'
          AND tablename  = 'youtube_video_snapshots'
          AND policyname = 'youtube_video_snapshots_service_role'
    ) THEN
        CREATE POLICY "youtube_video_snapshots_service_role"
            ON social_wiring.youtube_video_snapshots
            FOR ALL TO service_role
            USING (true) WITH CHECK (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_sw_youtube_video_snapshots_lookup
    ON social_wiring.youtube_video_snapshots
    (account_id, youtube_video_id, snapshot_date DESC);


-- ============================================================================
-- snapshot_runs — claim-row guard against duplicate YouTube quota spend.
-- No org_id — this is an internal scheduling-guard table, written and read
-- exclusively by the snapshot worker (service_role). No authenticated SELECT.
-- ============================================================================

CREATE TABLE IF NOT EXISTS social_wiring.snapshot_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL
        REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE,
    snapshot_date   DATE NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'done', 'error')),
    note            TEXT,
    UNIQUE (account_id, snapshot_date)
);

ALTER TABLE social_wiring.snapshot_runs ENABLE ROW LEVEL SECURITY;

-- No org_id: restrict to service_role only (internal guard table).
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'social_wiring'
          AND tablename  = 'snapshot_runs'
          AND policyname = 'snapshot_runs_service_role'
    ) THEN
        CREATE POLICY "snapshot_runs_service_role" ON social_wiring.snapshot_runs
            FOR ALL TO service_role
            USING (true) WITH CHECK (true);
    END IF;
END $$;
