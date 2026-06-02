-- ============================================================================
-- Migration 0003 — Codify the live RLS fix: current_org_id() for dev_team schema
--
-- WHY THIS EXISTS
-- ---------------
-- Both dev_team migrations (0001 + 0002) created authenticated RLS policies
-- using the broken TOP-LEVEL JWT claim:
--
--     org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
--
-- This claim is ALWAYS NULL in Supabase. The fix was applied LIVE on 2026-06-02.
-- This migration codifies that state.
--
-- PREREQUISITE: public.current_org_id() must exist (defined in
--   products/core/backend/migrations/001_noctusai_core.sql, root-fixed 2026-06-02).
--
-- IDEMPOTENT: all policies use DROP POLICY IF EXISTS before CREATE POLICY.
--
-- SOURCE OF TRUTH: pg_policies on Supabase project nyplttplcoyiiqjrvtiw,
-- queried 2026-06-02.
-- ============================================================================

-- ----- dev_team.invitations -----
-- From 0001_init_telemetry_events.sql
DROP POLICY IF EXISTS "invitations_select_own_org" ON dev_team.invitations;
CREATE POLICY "invitations_select_own_org" ON dev_team.invitations
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

-- ----- dev_team.dev_team_telemetry_events -----
-- Note: the table name includes the schema prefix (dev_team.dev_team_telemetry_events).
-- From 0001_init_telemetry_events.sql
DROP POLICY IF EXISTS "telemetry_events_own_org" ON dev_team.dev_team_telemetry_events;
CREATE POLICY "telemetry_events_own_org" ON dev_team.dev_team_telemetry_events
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ----- dev_team.agent_config_overrides -----
-- From 0002_init_agent_config_overrides.sql
DROP POLICY IF EXISTS "agent_config_overrides_own_org" ON dev_team.agent_config_overrides;
CREATE POLICY "agent_config_overrides_own_org" ON dev_team.agent_config_overrides
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());
