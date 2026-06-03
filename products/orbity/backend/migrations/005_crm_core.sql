-- ============================================================================
-- Migration 005 — Orbity CRM Core: clients, lead_stages, leads,
--                 lead_activities, lead_scoring_rules, lead_scoring_results
--
-- WHY:
--   Implements the agency lead-management heart for the orbity product.
--   agency_id (Orbity native) → org_id (noc tenancy).
--   RLS on every table via public.current_org_id() (SECURITY DEFINER,
--   trusted-table-derived — defined in 001_orbity.sql, codified in
--   004_rls_current_org_id.sql). NEVER USING(true), NEVER JWT/user_metadata.
--
-- IDEMPOTENT: CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS.
--
-- SEARCH PATH: session-pinned to orbity, public (consistent with 001).
-- ============================================================================

SET search_path = orbity, public;


-- ============================================================================
-- 1. clients — the agency's customers (active contracts / recurring billing)
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.clients (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,   -- FK → noctus_users-derived org; enforced via RLS
    name            TEXT NOT NULL,
    email           TEXT,
    phone           TEXT,
    company         TEXT,
    monthly_value   NUMERIC(12, 2),
    due_date        INT CHECK (due_date BETWEEN 1 AND 31),  -- day-of-month for billing
    active          BOOLEAN NOT NULL DEFAULT true,
    default_billing_type        TEXT,
    billing_automation_enabled  BOOLEAN NOT NULL DEFAULT false,
    report_token    TEXT UNIQUE DEFAULT gen_random_uuid()::text,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS clients_org_id_idx  ON orbity.clients (org_id);
CREATE INDEX IF NOT EXISTS clients_active_idx  ON orbity.clients (org_id, active);

-- updated_at trigger
CREATE OR REPLACE FUNCTION orbity.set_updated_at()
  RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_clients_updated_at ON orbity.clients;
CREATE TRIGGER trg_clients_updated_at
  BEFORE UPDATE ON orbity.clients
  FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

-- RLS
ALTER TABLE orbity.clients ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "clients_select_own_org" ON orbity.clients;
CREATE POLICY "clients_select_own_org" ON orbity.clients
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "clients_insert_own_org" ON orbity.clients;
CREATE POLICY "clients_insert_own_org" ON orbity.clients
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "clients_update_own_org" ON orbity.clients;
CREATE POLICY "clients_update_own_org" ON orbity.clients
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "clients_delete_own_org" ON orbity.clients;
CREATE POLICY "clients_delete_own_org" ON orbity.clients
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

-- service_role bypass (seed contract)
DROP POLICY IF EXISTS "clients_service_role_all" ON orbity.clients;
CREATE POLICY "clients_service_role_all" ON orbity.clients
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 2. lead_stages — configurable funnel stages per org
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.lead_stages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    name        TEXT NOT NULL,
    position    INT  NOT NULL DEFAULT 0,
    color       TEXT NOT NULL DEFAULT '#6366f1',
    is_won      BOOLEAN NOT NULL DEFAULT false,
    is_lost     BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One org cannot have two stages at the same position
CREATE UNIQUE INDEX IF NOT EXISTS lead_stages_org_position_ux
  ON orbity.lead_stages (org_id, position);

CREATE INDEX IF NOT EXISTS lead_stages_org_idx ON orbity.lead_stages (org_id);

-- RLS
ALTER TABLE orbity.lead_stages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lead_stages_select_own_org" ON orbity.lead_stages;
CREATE POLICY "lead_stages_select_own_org" ON orbity.lead_stages
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_stages_insert_own_org" ON orbity.lead_stages;
CREATE POLICY "lead_stages_insert_own_org" ON orbity.lead_stages
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_stages_update_own_org" ON orbity.lead_stages;
CREATE POLICY "lead_stages_update_own_org" ON orbity.lead_stages
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_stages_delete_own_org" ON orbity.lead_stages;
CREATE POLICY "lead_stages_delete_own_org" ON orbity.lead_stages
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_stages_service_role_all" ON orbity.lead_stages;
CREATE POLICY "lead_stages_service_role_all" ON orbity.lead_stages
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Default pipeline seed function (called at org onboarding / first-use)
CREATE OR REPLACE FUNCTION orbity.seed_default_lead_stages(p_org_id UUID)
  RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  default_stages TEXT[][] := ARRAY[
    ARRAY['Novo',        '0', '#94a3b8', 'false', 'false'],
    ARRAY['Contato',     '1', '#60a5fa', 'false', 'false'],
    ARRAY['Qualificado', '2', '#34d399', 'false', 'false'],
    ARRAY['Proposta',    '3', '#fbbf24', 'false', 'false'],
    ARRAY['Negociação',  '4', '#f97316', 'false', 'false'],
    ARRAY['Fechado',     '5', '#22c55e', 'true',  'false'],
    ARRAY['Perdido',     '6', '#f43f5e', 'false', 'true' ]
  ];
  stage TEXT[];
BEGIN
  FOREACH stage SLICE 1 IN ARRAY default_stages LOOP
    INSERT INTO orbity.lead_stages (org_id, name, position, color, is_won, is_lost)
    VALUES (
      p_org_id,
      stage[1],
      stage[2]::INT,
      stage[3],
      stage[4]::BOOLEAN,
      stage[5]::BOOLEAN
    )
    ON CONFLICT (org_id, position) DO NOTHING;
  END LOOP;
END;
$$;


-- ============================================================================
-- 3. leads — the funnel cards
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.leads (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL,
    client_id            UUID REFERENCES orbity.clients(id) ON DELETE SET NULL,
    name                 TEXT NOT NULL,
    email                TEXT,
    phone                TEXT,
    company              TEXT,
    source               TEXT,
    stage_id             UUID REFERENCES orbity.lead_stages(id) ON DELETE SET NULL,
    temperature          TEXT CHECK (temperature IN ('cold', 'warm', 'hot')),
    qualification_score  INT,
    qualification_source TEXT,
    value                NUMERIC(12, 2),
    owner_id             UUID,   -- FK → auth.users — not enforced here (noc owner lookup)
    next_contact         TIMESTAMPTZ,
    custom_fields        JSONB NOT NULL DEFAULT '{}',
    tags                 TEXT[] NOT NULL DEFAULT '{}',
    won_at               TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS leads_org_id_idx    ON orbity.leads (org_id);
CREATE INDEX IF NOT EXISTS leads_stage_id_idx  ON orbity.leads (org_id, stage_id);
CREATE INDEX IF NOT EXISTS leads_owner_id_idx  ON orbity.leads (org_id, owner_id);

DROP TRIGGER IF EXISTS trg_leads_updated_at ON orbity.leads;
CREATE TRIGGER trg_leads_updated_at
  BEFORE UPDATE ON orbity.leads
  FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

-- RLS — protected routes only; public capture uses service_role
ALTER TABLE orbity.leads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "leads_select_own_org" ON orbity.leads;
CREATE POLICY "leads_select_own_org" ON orbity.leads
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "leads_insert_own_org" ON orbity.leads;
CREATE POLICY "leads_insert_own_org" ON orbity.leads
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "leads_update_own_org" ON orbity.leads;
CREATE POLICY "leads_update_own_org" ON orbity.leads
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "leads_delete_own_org" ON orbity.leads;
CREATE POLICY "leads_delete_own_org" ON orbity.leads
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

-- service_role: used by public capture endpoint (uses admin client)
DROP POLICY IF EXISTS "leads_service_role_all" ON orbity.leads;
CREATE POLICY "leads_service_role_all" ON orbity.leads
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 4. lead_activities — history log per lead
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.lead_activities (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    lead_id     UUID NOT NULL REFERENCES orbity.leads(id) ON DELETE CASCADE,
    type        TEXT NOT NULL,
    note        TEXT,
    created_by  UUID,   -- auth.users id — recorded, not enforced
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS lead_activities_lead_idx ON orbity.lead_activities (org_id, lead_id);

ALTER TABLE orbity.lead_activities ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lead_activities_select_own_org" ON orbity.lead_activities;
CREATE POLICY "lead_activities_select_own_org" ON orbity.lead_activities
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_activities_insert_own_org" ON orbity.lead_activities;
CREATE POLICY "lead_activities_insert_own_org" ON orbity.lead_activities
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_activities_service_role_all" ON orbity.lead_activities;
CREATE POLICY "lead_activities_service_role_all" ON orbity.lead_activities
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 5. lead_scoring_rules — per-org scoring config keyed by form
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.lead_scoring_rules (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    form_id     TEXT NOT NULL,   -- from Meta lead-ads form_id or custom form slug
    question    TEXT NOT NULL,   -- accent-normalized at insert for matching
    answer      TEXT NOT NULL,   -- accent-normalized at insert for matching
    score       INT NOT NULL CHECK (score BETWEEN -2 AND 2),
    is_blocker  BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS lead_scoring_rules_org_form_idx
  ON orbity.lead_scoring_rules (org_id, form_id);

ALTER TABLE orbity.lead_scoring_rules ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lead_scoring_rules_select_own_org" ON orbity.lead_scoring_rules;
CREATE POLICY "lead_scoring_rules_select_own_org" ON orbity.lead_scoring_rules
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_scoring_rules_insert_own_org" ON orbity.lead_scoring_rules;
CREATE POLICY "lead_scoring_rules_insert_own_org" ON orbity.lead_scoring_rules
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_scoring_rules_update_own_org" ON orbity.lead_scoring_rules;
CREATE POLICY "lead_scoring_rules_update_own_org" ON orbity.lead_scoring_rules
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_scoring_rules_delete_own_org" ON orbity.lead_scoring_rules;
CREATE POLICY "lead_scoring_rules_delete_own_org" ON orbity.lead_scoring_rules
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_scoring_rules_service_role_all" ON orbity.lead_scoring_rules;
CREATE POLICY "lead_scoring_rules_service_role_all" ON orbity.lead_scoring_rules
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 6. lead_scoring_results — one row per lead (upsert on re-score)
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.lead_scoring_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    lead_id         UUID NOT NULL UNIQUE REFERENCES orbity.leads(id) ON DELETE CASCADE,
    score_total     INT NOT NULL DEFAULT 0,
    qualification   TEXT CHECK (qualification IN ('hot', 'warm', 'cold')),
    answers_detail  JSONB NOT NULL DEFAULT '{}',
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS lead_scoring_results_org_idx
  ON orbity.lead_scoring_results (org_id);

ALTER TABLE orbity.lead_scoring_results ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lead_scoring_results_select_own_org" ON orbity.lead_scoring_results;
CREATE POLICY "lead_scoring_results_select_own_org" ON orbity.lead_scoring_results
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_scoring_results_insert_own_org" ON orbity.lead_scoring_results;
CREATE POLICY "lead_scoring_results_insert_own_org" ON orbity.lead_scoring_results
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_scoring_results_update_own_org" ON orbity.lead_scoring_results;
CREATE POLICY "lead_scoring_results_update_own_org" ON orbity.lead_scoring_results
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_scoring_results_service_role_all" ON orbity.lead_scoring_results;
CREATE POLICY "lead_scoring_results_service_role_all" ON orbity.lead_scoring_results
  FOR ALL TO service_role USING (true) WITH CHECK (true);
