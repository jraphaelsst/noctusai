-- ============================================================================
-- Migration 018 — Orbity automations go LIVE
--
-- WHY (owner decision 2026-10-15: integrations first, then promote):
--   The flow engine (010) could not run for real. Three schema gaps:
--     1. no WhatsApp connection table -> nothing to send WITH;
--     2. no per-occurrence key on executions -> the same event could start the
--        same flow twice, and every execution needed a lead -> task/client/
--        meeting triggers had no subject to run on;
--     3. no claim state on pending actions -> two drains (or two replicas)
--        could pick up and double-send the same row.
--
-- 1. whatsapp_connections — VERBATIM output of
--    noctusai_lib.integrations.whatsapp.whatsapp_connections_table_ddl("orbity")
--    (made idempotent: IF NOT EXISTS / DROP POLICY IF EXISTS). Backs
--    noctusai_seed.whatsapp_connections_router (Conexoes WhatsApp). No
--    anon/authenticated write policy: every mutation goes through the
--    service-role client in the router (the seed contract).
--
-- 2. automation_executions
--      lead_id      -> nullable (a task/client/meeting run has no lead)
--      subject_type -> 'lead' (default, = lead_id) | 'client' | 'task' | 'meeting'
--      subject_id   -> the non-lead subject's id (NULL when subject_type='lead')
--      trigger_key  -> per-OCCURRENCE key (e.g. 'lead_created:<lead_id>',
--                      'stage:<lead_id>:<stage_id>:<ts>'); UNIQUE per flow, so
--                      a re-delivered event can never start the flow twice.
--    Shape chosen over a polymorphic lead_id because the FK to leads (with
--    ON DELETE CASCADE) stays intact for the dominant lead case, and a CHECK
--    guarantees every row has exactly one resolvable subject.
--
-- 3. automation_pending_actions
--      status 'processing' + claimed_at -> compare-and-set claim; a drain that
--      dies mid-send leaves a 'processing' row the next drain marks FAILED
--      (never re-sends: at-most-once beats a duplicate message to a client).
--
-- IDEMPOTENT (runs twice on a real Postgres): IF NOT EXISTS / DROP ... IF EXISTS.
-- ============================================================================

SET search_path = orbity, public;


-- ============================================================================
-- 1. whatsapp_connections — org-scoped, multi-session WAHA connection lines
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.whatsapp_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    user_id UUID NOT NULL,
    label TEXT NOT NULL,
    base_url TEXT NOT NULL,
    session_name TEXT NOT NULL DEFAULT 'default',
    encrypted_api_key TEXT NOT NULL,
    webhook_url TEXT,
    webhook_token TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, label)
);

ALTER TABLE orbity.whatsapp_connections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "whatsapp_connections_select_own_org" ON orbity.whatsapp_connections;
CREATE POLICY "whatsapp_connections_select_own_org" ON orbity.whatsapp_connections
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "whatsapp_connections_service_role_bypass" ON orbity.whatsapp_connections;
CREATE POLICY "whatsapp_connections_service_role_bypass" ON orbity.whatsapp_connections
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_orbity_whatsapp_connections_org
    ON orbity.whatsapp_connections (org_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orbity_whatsapp_connections_webhook_token
    ON orbity.whatsapp_connections (webhook_token);


-- ============================================================================
-- 2. automation_executions — idempotency key + non-lead subjects
-- ============================================================================

ALTER TABLE orbity.automation_executions
    ALTER COLUMN lead_id DROP NOT NULL;

ALTER TABLE orbity.automation_executions
    ADD COLUMN IF NOT EXISTS subject_type TEXT NOT NULL DEFAULT 'lead';
ALTER TABLE orbity.automation_executions
    ADD COLUMN IF NOT EXISTS subject_id UUID;
ALTER TABLE orbity.automation_executions
    ADD COLUMN IF NOT EXISTS trigger_key TEXT;

ALTER TABLE orbity.automation_executions
    DROP CONSTRAINT IF EXISTS automation_executions_subject_type_check;
ALTER TABLE orbity.automation_executions
    ADD CONSTRAINT automation_executions_subject_type_check
    CHECK (subject_type IN ('lead', 'client', 'task', 'meeting'));

-- Exactly one resolvable subject: a lead run carries lead_id; every other
-- subject carries subject_id.
ALTER TABLE orbity.automation_executions
    DROP CONSTRAINT IF EXISTS automation_executions_subject_check;
ALTER TABLE orbity.automation_executions
    ADD CONSTRAINT automation_executions_subject_check
    CHECK (
        (subject_type = 'lead' AND lead_id IS NOT NULL)
        OR (subject_type <> 'lead' AND subject_id IS NOT NULL)
    );

-- One run per flow per occurrence. Partial: manual/legacy rows have no key.
CREATE UNIQUE INDEX IF NOT EXISTS automation_executions_flow_trigger_key_ux
    ON orbity.automation_executions (flow_id, trigger_key)
    WHERE trigger_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS automation_executions_subject_idx
    ON orbity.automation_executions (org_id, subject_type, subject_id)
    WHERE subject_id IS NOT NULL;


-- ============================================================================
-- 3. automation_pending_actions — claim support
-- ============================================================================

ALTER TABLE orbity.automation_pending_actions
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;

ALTER TABLE orbity.automation_pending_actions
    DROP CONSTRAINT IF EXISTS automation_pending_actions_status_check;
ALTER TABLE orbity.automation_pending_actions
    ADD CONSTRAINT automation_pending_actions_status_check
    CHECK (status IN ('pending', 'processing', 'sent', 'skipped', 'failed'));

-- Stale-claim sweep scans only the (few) in-flight rows.
CREATE INDEX IF NOT EXISTS automation_pending_actions_processing_idx
    ON orbity.automation_pending_actions (org_id, claimed_at)
    WHERE status = 'processing';

-- ============================================================================
-- Nav: the WhatsApp connections page (/whatsapp). A route with NO
-- orbity.status_pagina row is silently hidden by the seed nav filter (see 013).
-- ============================================================================

INSERT INTO orbity.status_pagina (nome_pagina, status) VALUES
    ('whatsapp', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
