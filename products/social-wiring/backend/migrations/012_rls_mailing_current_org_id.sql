-- ============================================================================
-- Migration 012 — Codify the live RLS fix: current_org_id() for mailing schema
--
-- WHY THIS EXISTS
-- ---------------
-- The mailing schema is a legacy product that was absorbed into social-wiring
-- (001_social-wiring.sql notes "email_marketing tables absorbed from `mailing`").
-- The mailing schema still exists on prod with 15 authenticated RLS policies
-- that used the broken TOP-LEVEL JWT claim:
--
--     org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
--
-- This is ALWAYS NULL in Supabase (see 011_rls_current_org_id.sql for the root
-- cause). The fix was applied LIVE on 2026-06-02 using public.current_org_id().
-- This migration codifies that live state.
--
-- PLACEMENT: social-wiring owns the mailing schema (it was absorbed into the
-- social-wiring product). The mailing schema's policies are managed here.
--
-- PREREQUISITE: public.current_org_id() must exist (defined in Section 1
-- of migration 011_rls_current_org_id.sql).
--
-- IDEMPOTENT: all policies use DROP POLICY IF EXISTS before CREATE POLICY.
--
-- SOURCE OF TRUTH: pg_policies on Supabase project nyplttplcoyiiqjrvtiw,
-- queried 2026-06-02.
-- ============================================================================

-- ----- mailing.ai_feedback -----
DROP POLICY IF EXISTS "ai_feedback_own_org" ON mailing.ai_feedback;
CREATE POLICY "ai_feedback_own_org" ON mailing.ai_feedback
  FOR ALL TO authenticated
  USING ((org_id = public.current_org_id()))
  WITH CHECK (((org_id = public.current_org_id()) AND (user_id = ( SELECT auth.uid() AS uid))));

-- ----- mailing.ai_outputs -----
DROP POLICY IF EXISTS "ai_outputs_own_org" ON mailing.ai_outputs;
CREATE POLICY "ai_outputs_own_org" ON mailing.ai_outputs
  FOR ALL TO authenticated
  USING ((org_id = public.current_org_id()))
  WITH CHECK ((org_id = public.current_org_id()));

-- ----- mailing.automation_enrollments -----
DROP POLICY IF EXISTS "enrollments_via_automation" ON mailing.automation_enrollments;
CREATE POLICY "enrollments_via_automation" ON mailing.automation_enrollments
  FOR ALL TO authenticated
  USING ((automation_id IN ( SELECT automations.id
   FROM mailing.automations
  WHERE (automations.org_id = public.current_org_id()))));

-- ----- mailing.automation_steps -----
DROP POLICY IF EXISTS "steps_via_automation" ON mailing.automation_steps;
CREATE POLICY "steps_via_automation" ON mailing.automation_steps
  FOR ALL TO authenticated
  USING ((automation_id IN ( SELECT automations.id
   FROM mailing.automations
  WHERE (automations.org_id = public.current_org_id()))));

-- ----- mailing.automations -----
DROP POLICY IF EXISTS "automations_own_org" ON mailing.automations;
CREATE POLICY "automations_own_org" ON mailing.automations
  FOR ALL TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- mailing.campaigns -----
DROP POLICY IF EXISTS "campaigns_own_org" ON mailing.campaigns;
CREATE POLICY "campaigns_own_org" ON mailing.campaigns
  FOR ALL TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- mailing.contact_list_members -----
DROP POLICY IF EXISTS "list_members_via_list" ON mailing.contact_list_members;
CREATE POLICY "list_members_via_list" ON mailing.contact_list_members
  FOR ALL TO authenticated
  USING ((list_id IN ( SELECT contact_lists.id
   FROM mailing.contact_lists
  WHERE (contact_lists.org_id = public.current_org_id()))));

-- ----- mailing.contact_lists -----
DROP POLICY IF EXISTS "lists_own_org" ON mailing.contact_lists;
CREATE POLICY "lists_own_org" ON mailing.contact_lists
  FOR ALL TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- mailing.contacts -----
DROP POLICY IF EXISTS "contacts_own_org" ON mailing.contacts;
CREATE POLICY "contacts_own_org" ON mailing.contacts
  FOR ALL TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- mailing.invitations -----
DROP POLICY IF EXISTS "invitations_select_own_org" ON mailing.invitations;
CREATE POLICY "invitations_select_own_org" ON mailing.invitations
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- mailing.link_clicks -----
DROP POLICY IF EXISTS "clicks_via_send_log" ON mailing.link_clicks;
CREATE POLICY "clicks_via_send_log" ON mailing.link_clicks
  FOR ALL TO authenticated
  USING ((send_log_id IN ( SELECT send_logs.id
   FROM mailing.send_logs
  WHERE (send_logs.org_id = public.current_org_id()))));

-- ----- mailing.send_logs -----
DROP POLICY IF EXISTS "send_logs_own_org" ON mailing.send_logs;
CREATE POLICY "send_logs_own_org" ON mailing.send_logs
  FOR ALL TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- mailing.sender_domains -----
DROP POLICY IF EXISTS "domains_own_org" ON mailing.sender_domains;
CREATE POLICY "domains_own_org" ON mailing.sender_domains
  FOR ALL TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- mailing.templates -----
DROP POLICY IF EXISTS "templates_own_org" ON mailing.templates;
CREATE POLICY "templates_own_org" ON mailing.templates
  FOR ALL TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- mailing.unsubscribes -----
DROP POLICY IF EXISTS "unsubscribes_own_org" ON mailing.unsubscribes;
CREATE POLICY "unsubscribes_own_org" ON mailing.unsubscribes
  FOR ALL TO authenticated
  USING ((org_id = public.current_org_id()));
