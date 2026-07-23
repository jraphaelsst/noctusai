-- 030_meta_ads.sql — Meta Ads console (roadmap
-- `meta-ads-console-2026-07`): four tables backing a read-only console
-- over the operator's own Meta ad account (campaign -> ad set -> ad
-- hierarchy, daily insight-snapshot history, an intra-day-accurate
-- activity change log).
--
-- RLS shape mirrors 020_instagram_metric_snapshots.sql exactly:
-- authenticated reads via `public.current_org_id()` (SECURITY DEFINER,
-- resolves the caller's org from `public.noctus_users` — NEVER from
-- `auth.jwt()` top-level OR `user_metadata`, both of which are either
-- always-null or user-editable, per
-- `memory/feedback_rls_never_key_on_user_metadata.md`); service_role
-- ALL (backend sync writes go through the admin client, same as
-- `ig_metric_snapshots` / the YouTube snapshot tables).
--
-- PREREQUISITE: public.current_org_id() defined in
-- 011_rls_current_org_id.sql.
-- Forward-only + idempotent (CREATE TABLE IF NOT EXISTS / DROP POLICY IF
-- EXISTS + CREATE POLICY).
--
-- Money convention: every `*_cents` column is an INTEGER CENTS value
-- (BIGINT to be safe against large lifetime spend totals) — see
-- `app/modules/meta_ads/services/money.py` for the two DISTINCT
-- Marketing-API unit conventions this schema normalizes away
-- (AdAccount/AdSet fields arrive already minor-unit; Insights
-- spend/cpc/cpm arrive major-unit and are `* 100`'d before landing
-- here). `date` on `ads_insight_snapshots` is the *Meta* day (the
-- account's timezone — America/Sao_Paulo for the pilot account), NOT
-- the day the sync job happened to run.
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply
-- via noctus.dev.migrate_product with explicit tech-lead consent.

SET search_path = social_wiring, public;

-- ─── ads_accounts ───────────────────────────────────────────────────────
-- `list_ad_accounts()` — one row per (org, ad account). A single-account
-- deployment (roadmap v1: "One ad account — the operator's own") still
-- gets the full discovery shape so Phase 4 (multi-org ad accounts) is
-- additive, not a schema change.
CREATE TABLE IF NOT EXISTS social_wiring.ads_accounts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    act_id              TEXT NOT NULL,
    name                TEXT,
    currency            TEXT,
    timezone_name       TEXT,
    amount_spent_cents  BIGINT,
    balance_cents       BIGINT,
    spend_cap_cents     BIGINT,
    account_status      INTEGER,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw                 JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, act_id)
);

ALTER TABLE social_wiring.ads_accounts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ads_accounts_select_own_org" ON social_wiring.ads_accounts;
CREATE POLICY "ads_accounts_select_own_org" ON social_wiring.ads_accounts
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "ads_accounts_service_role" ON social_wiring.ads_accounts;
CREATE POLICY "ads_accounts_service_role" ON social_wiring.ads_accounts
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ─── ads_objects ─────────────────────────────────────────────────────────
-- Unified campaign/ad-set/ad hierarchy — ONE table, not three: the tree
-- is homogeneous and the UI drills generically (roadmap schema sketch).
-- `parent_id` is NULL for a campaign row, the campaign's `object_id` for
-- an ad-set row, and the ad-set's `object_id` for an ad row.
CREATE TABLE IF NOT EXISTS social_wiring.ads_objects (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL,
    object_id               TEXT NOT NULL,
    level                   TEXT NOT NULL CHECK (level IN ('campaign', 'adset', 'ad')),
    parent_id               TEXT,
    act_id                  TEXT,
    name                    TEXT,
    objective               TEXT,
    status                  TEXT,
    effective_status        TEXT,
    daily_budget_cents      BIGINT,
    lifetime_budget_cents   BIGINT,
    optimization_goal       TEXT,
    creative_id             TEXT,
    creative_thumbnail_url  TEXT,
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw                     JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, object_id)
);

ALTER TABLE social_wiring.ads_objects ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ads_objects_select_own_org" ON social_wiring.ads_objects;
CREATE POLICY "ads_objects_select_own_org" ON social_wiring.ads_objects
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "ads_objects_service_role" ON social_wiring.ads_objects;
CREATE POLICY "ads_objects_service_role" ON social_wiring.ads_objects
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_ads_objects_org_level_parent
    ON social_wiring.ads_objects (org_id, level, parent_id);


-- ─── ads_insight_snapshots ───────────────────────────────────────────────
-- Daily per-object insight snapshot — campaign-level is backfilled 12
-- months (W2.3); ad-set/ad-level rows (if ever written, e.g. a future
-- backfill decision) share the same shape.
--
-- 🔴 NULL-breakdown UNIQUE footgun (memory
-- `feedback_sql_unique_null_sibling`): a plain
-- `UNIQUE(org_id, object_id, date, breakdown_key)` would NOT dedupe two
-- unbroken-total rows (`breakdown_key IS NULL` on both) — Postgres
-- treats every NULL as distinct for uniqueness purposes, so a re-sync
-- would insert a SECOND unbroken-total row for the same day instead of
-- upserting the first. Solved explicitly via a generated,
-- NOT-NULL-by-construction `breakdown_key_norm` column
-- (`COALESCE(breakdown_key, '')`) and putting THAT — not the raw
-- nullable `breakdown_key` — in the UNIQUE constraint. The app layer's
-- `on_conflict` target for every upsert is
-- `org_id,object_id,date,breakdown_key_norm` (see
-- `app/modules/meta_ads/services/ads_sync_service.py`).
CREATE TABLE IF NOT EXISTS social_wiring.ads_insight_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    object_id           TEXT NOT NULL,
    level               TEXT NOT NULL CHECK (level IN ('campaign', 'adset', 'ad')),
    date                DATE NOT NULL,
    breakdown_key       TEXT,
    breakdown_key_norm  TEXT GENERATED ALWAYS AS (COALESCE(breakdown_key, '')) STORED,
    spend_cents         BIGINT,
    impressions         BIGINT,
    reach               BIGINT,
    frequency           NUMERIC,
    clicks              BIGINT,
    cpc_cents           BIGINT,
    cpm_cents           BIGINT,
    ctr                 NUMERIC,
    actions             JSONB NOT NULL DEFAULT '{}'::jsonb,
    action_values       JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw                 JSONB,
    captured_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, object_id, date, breakdown_key_norm)
);

ALTER TABLE social_wiring.ads_insight_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ads_insight_snapshots_select_own_org" ON social_wiring.ads_insight_snapshots;
CREATE POLICY "ads_insight_snapshots_select_own_org" ON social_wiring.ads_insight_snapshots
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "ads_insight_snapshots_service_role" ON social_wiring.ads_insight_snapshots;
CREATE POLICY "ads_insight_snapshots_service_role" ON social_wiring.ads_insight_snapshots
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_ads_insight_snapshots_org_object_date
    ON social_wiring.ads_insight_snapshots (org_id, object_id, date);


-- ─── ads_activity_events ─────────────────────────────────────────────────
-- Append-only change log fed from `act_{id}/activities` — daily
-- snapshots cannot capture an activate -> pause -> reactivate sequence
-- within one calendar day; this table carries the intra-day fidelity
-- (`occurred_at` is Meta's own `event_time`, not the ingest time).
-- `event_key` is the seed's LOCALLY SYNTHESIZED composite id
-- (`{object_id}:{event_time}:{event_type}` — see `AdActivity`'s
-- docstring in `noctusai_lib.integrations.meta.types`; Graph's
-- Activities edge is an audit log, not a first-class Graph node, so it
-- carries no stable per-row id of its own).
CREATE TABLE IF NOT EXISTS social_wiring.ads_activity_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    event_key       TEXT NOT NULL,
    object_id       TEXT,
    object_level    TEXT,
    event_type      TEXT,
    occurred_at     TIMESTAMPTZ NOT NULL,
    actor_name      TEXT,
    actor_id        TEXT,
    old_value       TEXT,
    new_value       TEXT,
    raw             JSONB,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, event_key)
);

ALTER TABLE social_wiring.ads_activity_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ads_activity_events_select_own_org" ON social_wiring.ads_activity_events;
CREATE POLICY "ads_activity_events_select_own_org" ON social_wiring.ads_activity_events
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "ads_activity_events_service_role" ON social_wiring.ads_activity_events;
CREATE POLICY "ads_activity_events_service_role" ON social_wiring.ads_activity_events
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_ads_activity_events_org_object_time
    ON social_wiring.ads_activity_events (org_id, object_id, occurred_at);
