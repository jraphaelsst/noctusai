-- 020_instagram_metric_snapshots.sql — Instagram insights v1: metric
-- history table.
--
-- Stores one row per capture (manual "Capturar agora" click, or the
-- daily automation job) of an org's Instagram Business/Creator account
-- numbers: follower/follows/media counts (from
-- ``adapter.list_instagram_accounts()``) + reach/profile_views (summed
-- from ``adapter.get_instagram_account_insights()``). ``raw`` keeps the
-- full insight payload for future metric additions without a schema
-- change.
--
-- RLS shape mirrors the POST-011 org-derivation pattern (see
-- 011_rls_current_org_id.sql + 013_mailchimp_connections.sql, the
-- newest CREATE-TABLE-with-RLS migration at authoring time):
-- authenticated reads via ``public.current_org_id()`` (SECURITY DEFINER,
-- resolves the caller's org from ``public.noctus_users`` — NEVER from
-- ``auth.jwt()`` top-level OR ``user_metadata``, both of which are
-- either always-null or user-editable, per
-- ``memory/feedback_rls_never_key_on_user_metadata.md``);
-- service_role ALL (backend snapshot writes go through the admin client,
-- same as ``credential_vault`` / the YouTube snapshot tables).
--
-- PREREQUISITE: public.current_org_id() defined in 011_rls_current_org_id.sql.
-- Forward-only + idempotent (CREATE TABLE IF NOT EXISTS / DROP POLICY IF
-- EXISTS + CREATE POLICY).
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply
-- via noctus.dev.migrate_product with explicit tech-lead consent.

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.ig_metric_snapshots (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL,
    ig_user_id        TEXT NOT NULL,
    username          TEXT,
    captured_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    followers_count   INTEGER,
    follows_count     INTEGER,
    media_count       INTEGER,
    reach             INTEGER,
    profile_views     INTEGER,
    raw               JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.ig_metric_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ig_metric_snapshots_select_own_org" ON social_wiring.ig_metric_snapshots;
CREATE POLICY "ig_metric_snapshots_select_own_org" ON social_wiring.ig_metric_snapshots
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "ig_metric_snapshots_service_role" ON social_wiring.ig_metric_snapshots;
CREATE POLICY "ig_metric_snapshots_service_role" ON social_wiring.ig_metric_snapshots
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_ig_metric_snapshots_org_ig_captured
    ON social_wiring.ig_metric_snapshots (org_id, ig_user_id, captured_at DESC);
