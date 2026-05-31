-- 006_enable_rls_tool_call_audits — defense-in-depth RLS on social_wiring.tool_call_audits
--
-- WHY: 001_social-wiring.sql:637 creates social_wiring.tool_call_audits without
-- RLS (the seed template ships RLS-enable as opt-in — see
-- noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template). Because the
-- social_wiring schema GRANTs USAGE + ALL to anon/authenticated (001:28-31), an
-- RLS-OFF table in that exposed schema is reachable by those roles → flagged by
-- the Supabase rls_disabled_in_public advisor. The sibling
-- social_wiring.sched_tool_call_audits (001:912) already enables RLS; this table
-- was the lone miss.
--
-- SHAPE: ENABLE RLS with NO policy. tool_call_audits is a service_role-written
-- audit trail with no end-user read path — RLS-on + zero policies = deny
-- anon/authenticated, allow service_role (which bypasses RLS). This matches the
-- state hand-applied to production 2026-05-31 (orphan-schema RLS sweep) and the
-- "service_role + admin-only callers" default the core copy documents.
-- Idempotent: ENABLE ROW LEVEL SECURITY is a no-op if already enabled.

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.tool_call_audits ENABLE ROW LEVEL SECURITY;
