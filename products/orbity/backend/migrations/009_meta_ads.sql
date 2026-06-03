-- ============================================================================
-- Migration 009 — Orbity Meta Ads organ:
--                 ad_accounts, campaigns, campaign_metrics
--
-- WHY:
--   Implements the agency traffic/paid-ads management core for the orbity
--   product. agency_id (Orbity native) → org_id (noc tenancy).
--   RLS on every table via public.current_org_id() (SECURITY DEFINER,
--   trusted-table-derived — defined in 001_orbity.sql, codified in
--   004_rls_current_org_id.sql). NEVER USING(true), NEVER JWT/user_metadata.
--
--   Token storage: access_token_ref is a CREDENTIAL REFERENCE (opaque TEXT
--   key into the vault adapter, not the raw token). The real vault is wired
--   at the service layer. This migration stores the reference only.
--   NOC-REMEDIATE[orbity-meta-ads-live]: when the vault adapter is wired,
--   ensure the reference column is kept encrypted at rest (bytea+pgcrypto or
--   the noc credential store convention). See KB § PATTERNS/backend/seed-fake-real-adapter.md.
--
-- IDEMPOTENT: CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS.
--
-- SEARCH PATH: session-pinned to orbity, public (consistent with 001–008).
-- ============================================================================

SET search_path = orbity, public;


-- ============================================================================
-- 1. ad_accounts — connected Meta ad accounts per client
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.ad_accounts (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL,
    client_id             UUID REFERENCES orbity.clients(id) ON DELETE SET NULL,
    external_account_id   TEXT NOT NULL,
    name                  TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'paused', 'disconnected', 'error')),
    -- Credential REFERENCE into the vault adapter. NOT the raw token.
    -- NOC-REMEDIATE[orbity-meta-ads-live]: wire the real vault / credential store here.
    access_token_ref      TEXT,
    connected_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One ad account per (org, external_account_id) — prevents duplicate connections
CREATE UNIQUE INDEX IF NOT EXISTS ad_accounts_org_external_ux
  ON orbity.ad_accounts (org_id, external_account_id);

CREATE INDEX IF NOT EXISTS ad_accounts_org_idx        ON orbity.ad_accounts (org_id);
CREATE INDEX IF NOT EXISTS ad_accounts_org_client_idx ON orbity.ad_accounts (org_id, client_id);

DROP TRIGGER IF EXISTS trg_ad_accounts_updated_at ON orbity.ad_accounts;
CREATE TRIGGER trg_ad_accounts_updated_at
  BEFORE UPDATE ON orbity.ad_accounts
  FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

-- RLS
ALTER TABLE orbity.ad_accounts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ad_accounts_select_own_org" ON orbity.ad_accounts;
CREATE POLICY "ad_accounts_select_own_org" ON orbity.ad_accounts
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "ad_accounts_insert_own_org" ON orbity.ad_accounts;
CREATE POLICY "ad_accounts_insert_own_org" ON orbity.ad_accounts
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "ad_accounts_update_own_org" ON orbity.ad_accounts;
CREATE POLICY "ad_accounts_update_own_org" ON orbity.ad_accounts
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "ad_accounts_delete_own_org" ON orbity.ad_accounts;
CREATE POLICY "ad_accounts_delete_own_org" ON orbity.ad_accounts
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "ad_accounts_service_role_all" ON orbity.ad_accounts;
CREATE POLICY "ad_accounts_service_role_all" ON orbity.ad_accounts
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 2. campaigns — Meta campaign records per ad account
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.campaigns (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL,
    client_id             UUID REFERENCES orbity.clients(id) ON DELETE SET NULL,
    ad_account_id         UUID NOT NULL REFERENCES orbity.ad_accounts(id) ON DELETE CASCADE,
    external_campaign_id  TEXT NOT NULL,
    name                  TEXT NOT NULL,
    objective             TEXT,
    status                TEXT NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'paused', 'archived', 'deleted')),
    daily_budget          NUMERIC(12, 2) CHECK (daily_budget IS NULL OR daily_budget >= 0),
    -- result_metric: the KPI label the gestor tracks (e.g. 'leads', 'purchases', 'clicks')
    result_metric         TEXT,
    -- situation: the gestor's health signal for this campaign
    situation             TEXT NOT NULL DEFAULT 'on-track'
                              CHECK (situation IN ('on-track', 'attention', 'off')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One campaign record per (org, external_campaign_id) — upsert-safe on sync
CREATE UNIQUE INDEX IF NOT EXISTS campaigns_org_external_ux
  ON orbity.campaigns (org_id, external_campaign_id);

CREATE INDEX IF NOT EXISTS campaigns_org_idx           ON orbity.campaigns (org_id);
CREATE INDEX IF NOT EXISTS campaigns_org_account_idx   ON orbity.campaigns (org_id, ad_account_id);
CREATE INDEX IF NOT EXISTS campaigns_org_client_idx    ON orbity.campaigns (org_id, client_id);
CREATE INDEX IF NOT EXISTS campaigns_org_situation_idx ON orbity.campaigns (org_id, situation);

DROP TRIGGER IF EXISTS trg_campaigns_updated_at ON orbity.campaigns;
CREATE TRIGGER trg_campaigns_updated_at
  BEFORE UPDATE ON orbity.campaigns
  FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

-- RLS
ALTER TABLE orbity.campaigns ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "campaigns_select_own_org" ON orbity.campaigns;
CREATE POLICY "campaigns_select_own_org" ON orbity.campaigns
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "campaigns_insert_own_org" ON orbity.campaigns;
CREATE POLICY "campaigns_insert_own_org" ON orbity.campaigns
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "campaigns_update_own_org" ON orbity.campaigns;
CREATE POLICY "campaigns_update_own_org" ON orbity.campaigns
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "campaigns_delete_own_org" ON orbity.campaigns;
CREATE POLICY "campaigns_delete_own_org" ON orbity.campaigns
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "campaigns_service_role_all" ON orbity.campaigns;
CREATE POLICY "campaigns_service_role_all" ON orbity.campaigns
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 3. campaign_metrics — daily snapshot time-series (the sync target)
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.campaign_metrics (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    campaign_id   UUID NOT NULL REFERENCES orbity.campaigns(id) ON DELETE CASCADE,
    date          DATE NOT NULL,
    spend         NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (spend >= 0),
    impressions   BIGINT NOT NULL DEFAULT 0 CHECK (impressions >= 0),
    leads         INT NOT NULL DEFAULT 0 CHECK (leads >= 0),
    -- cpl: cost per lead (spend / leads); NULL when leads = 0 to avoid /0
    cpl           NUMERIC(12, 4),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Upsert-on-resync idempotency: one metrics row per (campaign, date)
CREATE UNIQUE INDEX IF NOT EXISTS campaign_metrics_campaign_date_ux
  ON orbity.campaign_metrics (campaign_id, date);

CREATE INDEX IF NOT EXISTS campaign_metrics_org_idx          ON orbity.campaign_metrics (org_id);
CREATE INDEX IF NOT EXISTS campaign_metrics_campaign_idx     ON orbity.campaign_metrics (org_id, campaign_id);
CREATE INDEX IF NOT EXISTS campaign_metrics_date_idx         ON orbity.campaign_metrics (org_id, date DESC);

DROP TRIGGER IF EXISTS trg_campaign_metrics_updated_at ON orbity.campaign_metrics;
CREATE TRIGGER trg_campaign_metrics_updated_at
  BEFORE UPDATE ON orbity.campaign_metrics
  FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

-- RLS
ALTER TABLE orbity.campaign_metrics ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "campaign_metrics_select_own_org" ON orbity.campaign_metrics;
CREATE POLICY "campaign_metrics_select_own_org" ON orbity.campaign_metrics
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "campaign_metrics_insert_own_org" ON orbity.campaign_metrics;
CREATE POLICY "campaign_metrics_insert_own_org" ON orbity.campaign_metrics
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "campaign_metrics_update_own_org" ON orbity.campaign_metrics;
CREATE POLICY "campaign_metrics_update_own_org" ON orbity.campaign_metrics
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "campaign_metrics_delete_own_org" ON orbity.campaign_metrics;
CREATE POLICY "campaign_metrics_delete_own_org" ON orbity.campaign_metrics
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "campaign_metrics_service_role_all" ON orbity.campaign_metrics;
CREATE POLICY "campaign_metrics_service_role_all" ON orbity.campaign_metrics
  FOR ALL TO service_role USING (true) WITH CHECK (true);
