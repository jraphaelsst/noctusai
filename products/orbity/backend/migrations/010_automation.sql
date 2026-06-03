-- ============================================================================
-- Migration 010 — Orbity WhatsApp Automation Flow Engine
--
-- WHY:
--   Implements the config-driven automation flow engine that replaced the
--   legacy cadence cron workers (decommissioned by 20260523123000). The engine
--   is 100% runtime-authored; no seed rows.
--
--   Tables:
--     automation_flows           — named trigger → step-sequence definitions
--     automation_steps           — ordered steps within a flow
--     automation_executions      — one row per flow × lead run (state machine)
--     automation_pending_actions — per-minute cron queue for due send/wait steps
--
-- RLS: USING (org_id = public.current_org_id()) on all 4 verbs.
--      service_role bypass policy on each table.
--
-- IDEMPOTENT: CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS.
--
-- SEARCH PATH: session-pinned to orbity, public (consistent with 001).
--
-- EXECUTOR / SCHEDULER SEAMS:
--   - The Python engine (AutomationEngine.advance) drives executions.
--   - The scheduler (run_due_actions) processes automation_pending_actions
--     where scheduled_for <= now(); intended to be called by a pg_cron job
--     or a task-queue worker.
--     NOC-REMEDIATE[orbity-automation-scheduler] — attach real cron trigger
-- ============================================================================

SET search_path = orbity, public;


-- ============================================================================
-- 1. automation_flows — named flow definitions per org
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.automation_flows (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    name            TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 255),
    -- Trigger type vocabulary from Orbity FE builder (WhatsAppAutomationFlows.tsx)
    trigger_type    TEXT NOT NULL CHECK (trigger_type IN (
                        'lead_created', 'pipeline_stage_entered', 'lead_idle',
                        'whatsapp_message_received', 'keyword_received',
                        'tag_added', 'owner_changed', 'task_created',
                        'task_completed', 'meeting_created', 'proposal_sent',
                        'client_created', 'lead_status_changed', 'manual'
                    )),
    -- trigger_config: {"stage_id": "...", "keyword": "...", "tag": "..."} etc.
    trigger_config  JSONB NOT NULL DEFAULT '{}',
    active          BOOLEAN NOT NULL DEFAULT true,
    -- schedule_window: {"days": ["mon","tue","wed","thu","fri"],
    --                   "start": "08:00", "end": "17:00",
    --                   "tz": "America/Sao_Paulo",
    --                   "outside_window_behavior": "schedule_next_available"}
    -- Default: Mon-Fri 08:00-17:00 America/Sao_Paulo (from Orbity builder)
    schedule_window JSONB NOT NULL DEFAULT '{
        "days": ["mon","tue","wed","thu","fri"],
        "start": "08:00",
        "end": "17:00",
        "tz": "America/Sao_Paulo",
        "outside_window_behavior": "schedule_next_available"
    }'::jsonb,
    -- stop_rules baked in by construction (Orbity default)
    stop_rules      JSONB NOT NULL DEFAULT '{
        "stop_on_reply": true,
        "stop_on_final_status": true,
        "stop_on_manual_owner_change": false,
        "avoid_conflicts": true
    }'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS automation_flows_org_idx
    ON orbity.automation_flows (org_id);
CREATE INDEX IF NOT EXISTS automation_flows_org_active_idx
    ON orbity.automation_flows (org_id, active)
    WHERE active = true;

DROP TRIGGER IF EXISTS trg_automation_flows_updated_at ON orbity.automation_flows;
CREATE TRIGGER trg_automation_flows_updated_at
    BEFORE UPDATE ON orbity.automation_flows
    FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.automation_flows ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "automation_flows_select_own_org" ON orbity.automation_flows;
CREATE POLICY "automation_flows_select_own_org" ON orbity.automation_flows
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_flows_insert_own_org" ON orbity.automation_flows;
CREATE POLICY "automation_flows_insert_own_org" ON orbity.automation_flows
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_flows_update_own_org" ON orbity.automation_flows;
CREATE POLICY "automation_flows_update_own_org" ON orbity.automation_flows
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_flows_delete_own_org" ON orbity.automation_flows;
CREATE POLICY "automation_flows_delete_own_org" ON orbity.automation_flows
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_flows_service_role_all" ON orbity.automation_flows;
CREATE POLICY "automation_flows_service_role_all" ON orbity.automation_flows
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 2. automation_steps — ordered steps within a flow
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.automation_steps (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    flow_id     UUID NOT NULL REFERENCES orbity.automation_flows(id) ON DELETE CASCADE,
    ord         INT NOT NULL,               -- step sequence; 0-based ascending
    -- Step types from Orbity builder vocabulary
    step_type   TEXT NOT NULL CHECK (step_type IN (
                    'send_message', 'send_whatsapp_media', 'wait',
                    'condition', 'action', 'branch', 'end'
                )),
    -- config examples:
    --   send_message: {"template": "Olá {nome}! ...", "variables": ["nome"]}
    --   wait:         {"duration_minutes": 10}
    --   condition:    {"field": "source", "operator": "equals",
    --                  "value": "Meta Ads", "on_true": "next", "on_false": "stop"}
    --   branch:       {"field": "lead_replied", "operator": "is_true",
    --                  "on_true_step_ord": 3, "on_false_step_ord": 4}
    --   action:       {"action_type": "create_task", "title": "Follow-up comercial"}
    --   end:          {}
    config      JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (flow_id, ord)
);

CREATE INDEX IF NOT EXISTS automation_steps_flow_idx
    ON orbity.automation_steps (flow_id, ord);
CREATE INDEX IF NOT EXISTS automation_steps_org_idx
    ON orbity.automation_steps (org_id);

DROP TRIGGER IF EXISTS trg_automation_steps_updated_at ON orbity.automation_steps;
CREATE TRIGGER trg_automation_steps_updated_at
    BEFORE UPDATE ON orbity.automation_steps
    FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.automation_steps ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "automation_steps_select_own_org" ON orbity.automation_steps;
CREATE POLICY "automation_steps_select_own_org" ON orbity.automation_steps
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_steps_insert_own_org" ON orbity.automation_steps;
CREATE POLICY "automation_steps_insert_own_org" ON orbity.automation_steps
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_steps_update_own_org" ON orbity.automation_steps;
CREATE POLICY "automation_steps_update_own_org" ON orbity.automation_steps
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_steps_delete_own_org" ON orbity.automation_steps;
CREATE POLICY "automation_steps_delete_own_org" ON orbity.automation_steps
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_steps_service_role_all" ON orbity.automation_steps;
CREATE POLICY "automation_steps_service_role_all" ON orbity.automation_steps
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 3. automation_executions — one row per flow × lead run (state machine)
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.automation_executions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    flow_id             UUID NOT NULL REFERENCES orbity.automation_flows(id) ON DELETE CASCADE,
    lead_id             UUID NOT NULL REFERENCES orbity.leads(id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'running'
                            CHECK (status IN ('running', 'done', 'canceled', 'failed')),
    current_step_ord    INT NOT NULL DEFAULT 0,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- next_action_at: when the engine should next evaluate this execution
    next_action_at      TIMESTAMPTZ,
    -- context carries runtime state (e.g., {"lead_replied": true})
    context             JSONB NOT NULL DEFAULT '{}',
    error_detail        TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS automation_executions_org_idx
    ON orbity.automation_executions (org_id);
CREATE INDEX IF NOT EXISTS automation_executions_lead_idx
    ON orbity.automation_executions (org_id, lead_id);
CREATE INDEX IF NOT EXISTS automation_executions_running_idx
    ON orbity.automation_executions (org_id, status, next_action_at)
    WHERE status = 'running';

DROP TRIGGER IF EXISTS trg_automation_executions_updated_at ON orbity.automation_executions;
CREATE TRIGGER trg_automation_executions_updated_at
    BEFORE UPDATE ON orbity.automation_executions
    FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.automation_executions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "automation_executions_select_own_org" ON orbity.automation_executions;
CREATE POLICY "automation_executions_select_own_org" ON orbity.automation_executions
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_executions_insert_own_org" ON orbity.automation_executions;
CREATE POLICY "automation_executions_insert_own_org" ON orbity.automation_executions
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_executions_update_own_org" ON orbity.automation_executions;
CREATE POLICY "automation_executions_update_own_org" ON orbity.automation_executions
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_executions_delete_own_org" ON orbity.automation_executions;
CREATE POLICY "automation_executions_delete_own_org" ON orbity.automation_executions
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_executions_service_role_all" ON orbity.automation_executions;
CREATE POLICY "automation_executions_service_role_all" ON orbity.automation_executions
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 4. automation_pending_actions — per-minute cron queue for due steps
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.automation_pending_actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    execution_id    UUID NOT NULL
                        REFERENCES orbity.automation_executions(id) ON DELETE CASCADE,
    step_id         UUID NOT NULL REFERENCES orbity.automation_steps(id) ON DELETE CASCADE,
    scheduled_for   TIMESTAMPTZ NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'sent', 'skipped', 'failed')),
    -- payload: data produced at schedule time (rendered message, lead snapshot, etc.)
    payload         JSONB NOT NULL DEFAULT '{}',
    processed_at    TIMESTAMPTZ,
    error_detail    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Primary scheduler scan index: (org_id, status, scheduled_for)
-- Engine calls: WHERE org_id=? AND status='pending' AND scheduled_for <= now()
CREATE INDEX IF NOT EXISTS automation_pending_actions_due_idx
    ON orbity.automation_pending_actions (org_id, status, scheduled_for)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS automation_pending_actions_execution_idx
    ON orbity.automation_pending_actions (execution_id);

DROP TRIGGER IF EXISTS trg_automation_pending_actions_updated_at
    ON orbity.automation_pending_actions;
CREATE TRIGGER trg_automation_pending_actions_updated_at
    BEFORE UPDATE ON orbity.automation_pending_actions
    FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.automation_pending_actions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "automation_pending_actions_select_own_org"
    ON orbity.automation_pending_actions;
CREATE POLICY "automation_pending_actions_select_own_org"
    ON orbity.automation_pending_actions
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_pending_actions_insert_own_org"
    ON orbity.automation_pending_actions;
CREATE POLICY "automation_pending_actions_insert_own_org"
    ON orbity.automation_pending_actions
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_pending_actions_update_own_org"
    ON orbity.automation_pending_actions;
CREATE POLICY "automation_pending_actions_update_own_org"
    ON orbity.automation_pending_actions
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_pending_actions_delete_own_org"
    ON orbity.automation_pending_actions;
CREATE POLICY "automation_pending_actions_delete_own_org"
    ON orbity.automation_pending_actions
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "automation_pending_actions_service_role_all"
    ON orbity.automation_pending_actions;
CREATE POLICY "automation_pending_actions_service_role_all"
    ON orbity.automation_pending_actions
    FOR ALL TO service_role USING (true) WITH CHECK (true);
