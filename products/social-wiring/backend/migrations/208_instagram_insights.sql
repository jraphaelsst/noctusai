-- 208_instagram_insights.sql — Instagram (Instagram Business Login) per-post
-- catalog + daily per-post and per-account snapshots.
--
-- Owner decision 2026-10-06: Instagram authenticates via Instagram Business
-- Login (integration_accounts.provider = 'instagram'); track EVERY post EVERY
-- day with all available metrics. Mirrors the YouTube timeseries model
-- (009_youtube_timeseries.sql: catalog + daily snapshots + snapshot_runs
-- claim guard). The daily job reuses social_wiring.snapshot_runs as its
-- claim-row guard — keyed (account_id, snapshot_date), and an IG account is
-- its own integration_accounts row, so it never collides with a YouTube run.
--
-- Tables:
--   • ig_media              — catalog, one row per media per account
--   • ig_media_snapshots    — per-media daily metrics (typed common columns
--                              + extra_metrics jsonb for the rest)
--   • ig_profile_snapshots  — per-ACCOUNT daily profile + account insights
--
-- Why a NEW ig_profile_snapshots instead of extending ig_metric_snapshots
-- (020): that table is keyed (org_id, ig_user_id) with one row per CAPTURE
-- (no per-day uniqueness, no account FK) and is written by the Facebook-Login
-- "Capturar agora" path. The daily job needs an idempotent (account_id,
-- snapshot_date) upsert with an ON DELETE CASCADE to the connection row —
-- retrofitting a unique day key onto 020 would break its multi-capture
-- semantics for the existing consumer.
--
-- Metric nullability: every metric column is NULLABLE with no default. A
-- metric Meta did not return / rejected for the media type is NULL and named
-- in `unsupported_metrics` — never 0 (no-silent-errors).
--
-- RLS (post-011 shape, see 020/204): authenticated SELECT via
-- public.current_org_id(); service_role ALL (the sync job + API read through
-- the admin client with explicit org/account filters).
--
-- PREREQUISITE: public.current_org_id() (011), social_wiring.integration_accounts
-- (008), social_wiring.snapshot_runs (009).
-- Forward-only + idempotent (IF NOT EXISTS / DROP POLICY IF EXISTS + CREATE).
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.

SET search_path = social_wiring, public;


-- ============================================================================
-- ig_media — catalog
-- ============================================================================

CREATE TABLE IF NOT EXISTS social_wiring.ig_media (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL,
    account_id            UUID NOT NULL
        REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE,
    ig_media_id           TEXT NOT NULL,
    caption               TEXT,
    media_type            TEXT,
    media_product_type    TEXT,
    permalink             TEXT,
    thumbnail_url         TEXT,
    media_url             TEXT,
    -- Graph `timestamp`. NOT NULL: it is the grid's keyset-pagination key;
    -- the sync skips (and logs + counts) an item Graph returned without one.
    published_at          TIMESTAMPTZ NOT NULL,
    like_count            BIGINT,
    comments_count        BIGINT,
    is_shared_to_feed     BOOLEAN,
    latest_metrics        JSONB,
    latest_snapshot_date  DATE,
    first_seen_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    synced_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, ig_media_id)
);

ALTER TABLE social_wiring.ig_media ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ig_media_select_own_org" ON social_wiring.ig_media;
CREATE POLICY "ig_media_select_own_org" ON social_wiring.ig_media
    FOR SELECT TO authenticated USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "ig_media_service_role" ON social_wiring.ig_media;
CREATE POLICY "ig_media_service_role" ON social_wiring.ig_media
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Serves the grid: WHERE account_id = ? ORDER BY published_at DESC, ig_media_id DESC
CREATE INDEX IF NOT EXISTS idx_sw_ig_media_account_published
    ON social_wiring.ig_media (account_id, published_at DESC, ig_media_id DESC);


-- ============================================================================
-- ig_media_snapshots — per-media daily metrics
-- ============================================================================

CREATE TABLE IF NOT EXISTS social_wiring.ig_media_snapshots (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                          UUID NOT NULL,
    account_id                      UUID NOT NULL
        REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE,
    ig_media_id                     TEXT NOT NULL,
    media_product_type              TEXT,
    snapshot_date                   DATE NOT NULL,
    views                           BIGINT,
    reach                           BIGINT,
    likes                           BIGINT,
    comments                        BIGINT,
    shares                          BIGINT,
    saved                           BIGINT,
    total_interactions              BIGINT,
    follows                         BIGINT,
    profile_visits                  BIGINT,
    ig_reels_avg_watch_time         BIGINT,   -- milliseconds
    ig_reels_video_view_total_time  BIGINT,   -- milliseconds
    extra_metrics                   JSONB NOT NULL DEFAULT '{}'::jsonb,
    unsupported_metrics             TEXT[] NOT NULL DEFAULT '{}',
    captured_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, ig_media_id, snapshot_date)
);

ALTER TABLE social_wiring.ig_media_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ig_media_snapshots_select_own_org" ON social_wiring.ig_media_snapshots;
CREATE POLICY "ig_media_snapshots_select_own_org" ON social_wiring.ig_media_snapshots
    FOR SELECT TO authenticated USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "ig_media_snapshots_service_role" ON social_wiring.ig_media_snapshots;
CREATE POLICY "ig_media_snapshots_service_role" ON social_wiring.ig_media_snapshots
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_ig_media_snapshots_lookup
    ON social_wiring.ig_media_snapshots (account_id, ig_media_id, snapshot_date DESC);


-- ============================================================================
-- ig_profile_snapshots — per-account daily profile + account insights
-- ============================================================================

CREATE TABLE IF NOT EXISTS social_wiring.ig_profile_snapshots (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL,
    account_id              UUID NOT NULL
        REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE,
    snapshot_date           DATE NOT NULL,
    ig_user_id              TEXT,
    username                TEXT,
    followers_count         BIGINT,
    follows_count           BIGINT,
    media_count             BIGINT,
    reach                   BIGINT,
    views                   BIGINT,
    accounts_engaged        BIGINT,
    total_interactions      BIGINT,
    likes                   BIGINT,
    comments                BIGINT,
    shares                  BIGINT,
    saves                   BIGINT,
    extra_metrics           JSONB NOT NULL DEFAULT '{}'::jsonb,
    unsupported_metrics     TEXT[] NOT NULL DEFAULT '{}',
    window_since            TIMESTAMPTZ,
    window_until            TIMESTAMPTZ,
    captured_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, snapshot_date)
);

ALTER TABLE social_wiring.ig_profile_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ig_profile_snapshots_select_own_org" ON social_wiring.ig_profile_snapshots;
CREATE POLICY "ig_profile_snapshots_select_own_org" ON social_wiring.ig_profile_snapshots
    FOR SELECT TO authenticated USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "ig_profile_snapshots_service_role" ON social_wiring.ig_profile_snapshots;
CREATE POLICY "ig_profile_snapshots_service_role" ON social_wiring.ig_profile_snapshots
    FOR ALL TO service_role USING (true) WITH CHECK (true);
