-- ============================================================================
-- Migration 011 — Codify the live RLS fix: current_org_id() SECURITY DEFINER
--
-- WHY THIS EXISTS
-- ---------------
-- On 2026-06-02 a critical RLS bug was discovered and fixed LIVE on prod
-- Supabase (project nyplttplcoyiiqjrvtiw). Before this fix, all
-- social_wiring authenticated-read policies (and the underlying helper
-- functions) used the TOP-LEVEL JWT claim:
--
--     org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
--
-- This claim is ALWAYS NULL because Supabase places org_id under the
-- nested `user_metadata` object, NOT at the top level. The result:
-- RLS stripped all rows on every authenticated user read while
-- service_role writes succeeded — the "sync works, list empty" symptom.
--
-- THE WRONG NAIVE FIX would be to read `auth.jwt()->'user_metadata'->>'org_id'`,
-- which IS populated but is user-EDITABLE — a privilege escalation hole
-- that the Supabase advisor flags as rls_references_user_metadata (ERROR).
--
-- THE SECURE FIX: redefine current_org_id() in both public and erp schemas
-- as a SECURITY DEFINER function that reads from a trusted DB table:
--
--     SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid())
--
-- This is the only source of truth for the caller's org. The function was
-- applied live in the same session as the policy rewrites. This migration
-- codifies that live state so the repo and the DB are in sync.
--
-- SCOPE
-- -----
-- 1. CREATE OR REPLACE both current_org_id() functions (public + erp schema).
-- 2. DROP + CREATE the 49 social_wiring authenticated policies that were
--    already rewritten live to call public.current_org_id(). These are
--    idempotent but must be here so a fresh apply on a blank DB produces the
--    same final state as prod.
-- 3. Fix the 5 INSERT/ALL social_wiring policies that were NOT yet rewritten
--    live (they still carry the broken jwt() top-level claim).
--
-- IDEMPOTENT: all function definitions use CREATE OR REPLACE; all policies
-- use DROP POLICY IF EXISTS before CREATE POLICY. Re-running is safe.
--
-- POINTER: memory/feedback_rls_never_key_on_user_metadata.md
--          memory/feedback_fullstack_contract_first_api_db_rls.md
-- ============================================================================

-- ============================================================================
-- SECTION 1: current_org_id() — SECURITY DEFINER helper (both schemas)
-- ============================================================================

-- public schema — called by social_wiring and any cross-schema policies.
-- search_path locked to 'public' so noctus_users resolves correctly even
-- when the calling session has a different search_path.
CREATE OR REPLACE FUNCTION public.current_org_id()
  RETURNS uuid
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid());
$f$;

-- erp schema copy — erp policies may call erp.current_org_id() directly.
-- search_path includes both 'public' and 'erp' so noctus_users is reachable.
CREATE OR REPLACE FUNCTION erp.current_org_id()
  RETURNS uuid
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public', 'erp'
AS $f$
  SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid());
$f$;


-- ============================================================================
-- SECTION 2: social_wiring authenticated policies — codify the live rewrites
--            (49 policies already fixed live on 2026-06-02)
-- ============================================================================
-- All policies below call public.current_org_id() for the org predicate.
-- They are written as DROP + CREATE so this file is idempotent regardless
-- of which prior form is on the DB.

-- ---------------------------------------------------------------------------
-- api_tokens
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "api_tokens_select_own_org" ON social_wiring.api_tokens;
CREATE POLICY "api_tokens_select_own_org" ON social_wiring.api_tokens
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

DROP POLICY IF EXISTS "api_tokens_update_own_org_admin" ON social_wiring.api_tokens;
CREATE POLICY "api_tokens_update_own_org_admin" ON social_wiring.api_tokens
  FOR UPDATE TO authenticated
  USING (
    (org_id = current_org_id())
    AND (EXISTS (
      SELECT 1 FROM noctus_users nu
      WHERE nu.id = (SELECT auth.uid())
        AND nu.org_id = api_tokens.org_id
        AND nu.org_role = ANY (ARRAY['owner'::text, 'admin'::text])
    ))
  );

-- ---------------------------------------------------------------------------
-- automation_enrollments
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "em_enrollments_select_via_automation" ON social_wiring.automation_enrollments;
CREATE POLICY "em_enrollments_select_via_automation" ON social_wiring.automation_enrollments
  FOR SELECT TO authenticated
  USING (
    automation_id IN (
      SELECT automations.id FROM social_wiring.automations
      WHERE automations.org_id = current_org_id()
    )
  );

-- ---------------------------------------------------------------------------
-- automation_steps
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "em_steps_select_via_automation" ON social_wiring.automation_steps;
CREATE POLICY "em_steps_select_via_automation" ON social_wiring.automation_steps
  FOR SELECT TO authenticated
  USING (
    automation_id IN (
      SELECT automations.id FROM social_wiring.automations
      WHERE automations.org_id = current_org_id()
    )
  );

-- ---------------------------------------------------------------------------
-- automations
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "em_automations_select_own_org" ON social_wiring.automations;
CREATE POLICY "em_automations_select_own_org" ON social_wiring.automations
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- campaigns
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "em_campaigns_select_own_org" ON social_wiring.campaigns;
CREATE POLICY "em_campaigns_select_own_org" ON social_wiring.campaigns
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- clients
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "clients_delete_own_org" ON social_wiring.clients;
CREATE POLICY "clients_delete_own_org" ON social_wiring.clients
  FOR DELETE TO authenticated
  USING (org_id = current_org_id());

DROP POLICY IF EXISTS "clients_select_own_org" ON social_wiring.clients;
CREATE POLICY "clients_select_own_org" ON social_wiring.clients
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

DROP POLICY IF EXISTS "clients_update_own_org" ON social_wiring.clients;
CREATE POLICY "clients_update_own_org" ON social_wiring.clients
  FOR UPDATE TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- contact_list_members
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "em_list_members_select_via_list" ON social_wiring.contact_list_members;
CREATE POLICY "em_list_members_select_via_list" ON social_wiring.contact_list_members
  FOR SELECT TO authenticated
  USING (
    list_id IN (
      SELECT contact_lists.id FROM social_wiring.contact_lists
      WHERE contact_lists.org_id = current_org_id()
    )
  );

-- ---------------------------------------------------------------------------
-- contact_lists
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "em_lists_select_own_org" ON social_wiring.contact_lists;
CREATE POLICY "em_lists_select_own_org" ON social_wiring.contact_lists
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- contacts
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "em_contacts_select_own_org" ON social_wiring.contacts;
CREATE POLICY "em_contacts_select_own_org" ON social_wiring.contacts
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- conversation_messages
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "conversation_messages_select_own_org" ON social_wiring.conversation_messages;
CREATE POLICY "conversation_messages_select_own_org" ON social_wiring.conversation_messages
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- credentials
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "credentials_select_own_org" ON social_wiring.credentials;
CREATE POLICY "credentials_select_own_org" ON social_wiring.credentials
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- integration_accounts
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "integration_accounts_delete_own_org" ON social_wiring.integration_accounts;
CREATE POLICY "integration_accounts_delete_own_org" ON social_wiring.integration_accounts
  FOR DELETE TO authenticated
  USING (org_id = current_org_id());

DROP POLICY IF EXISTS "integration_accounts_select_own_org" ON social_wiring.integration_accounts;
CREATE POLICY "integration_accounts_select_own_org" ON social_wiring.integration_accounts
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

DROP POLICY IF EXISTS "integration_accounts_update_own_org" ON social_wiring.integration_accounts;
CREATE POLICY "integration_accounts_update_own_org" ON social_wiring.integration_accounts
  FOR UPDATE TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- invitations
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "invitations_select_own_org" ON social_wiring.invitations;
CREATE POLICY "invitations_select_own_org" ON social_wiring.invitations
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- link_clicks
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "em_clicks_select_via_send_log" ON social_wiring.link_clicks;
CREATE POLICY "em_clicks_select_via_send_log" ON social_wiring.link_clicks
  FOR SELECT TO authenticated
  USING (
    send_log_id IN (
      SELECT send_logs.id FROM social_wiring.send_logs
      WHERE send_logs.org_id = current_org_id()
    )
  );

-- ---------------------------------------------------------------------------
-- mc_brand_kits
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "mc_brand_kits_select_own_org" ON social_wiring.mc_brand_kits;
CREATE POLICY "mc_brand_kits_select_own_org" ON social_wiring.mc_brand_kits
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- mc_brand_references
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "mc_brand_references_select_own_org" ON social_wiring.mc_brand_references;
CREATE POLICY "mc_brand_references_select_own_org" ON social_wiring.mc_brand_references
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- mc_post_slides
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "mc_post_slides_select_own_org" ON social_wiring.mc_post_slides;
CREATE POLICY "mc_post_slides_select_own_org" ON social_wiring.mc_post_slides
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- mc_posts
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "mc_posts_select_own_org" ON social_wiring.mc_posts;
CREATE POLICY "mc_posts_select_own_org" ON social_wiring.mc_posts
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- notification_log
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "notification_log_select_own_org" ON social_wiring.notification_log;
CREATE POLICY "notification_log_select_own_org" ON social_wiring.notification_log
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- notification_recipients
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "notification_recipients_select_own_org" ON social_wiring.notification_recipients;
CREATE POLICY "notification_recipients_select_own_org" ON social_wiring.notification_recipients
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

DROP POLICY IF EXISTS "notification_recipients_write_own_org" ON social_wiring.notification_recipients;
CREATE POLICY "notification_recipients_write_own_org" ON social_wiring.notification_recipients
  FOR ALL TO authenticated
  USING (org_id = current_org_id())
  WITH CHECK (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- sched_appointment_request_services
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "sched_appt_req_svc_select_own_org" ON social_wiring.sched_appointment_request_services;
CREATE POLICY "sched_appt_req_svc_select_own_org" ON social_wiring.sched_appointment_request_services
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- sched_appointment_requests
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "sched_appt_requests_select_own_org" ON social_wiring.sched_appointment_requests;
CREATE POLICY "sched_appt_requests_select_own_org" ON social_wiring.sched_appointment_requests
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- sched_appointments
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "sched_appointments_select_own_org" ON social_wiring.sched_appointments;
CREATE POLICY "sched_appointments_select_own_org" ON social_wiring.sched_appointments
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- sched_condominiums
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "sched_condominiums_select_own_org" ON social_wiring.sched_condominiums;
CREATE POLICY "sched_condominiums_select_own_org" ON social_wiring.sched_condominiums
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- sched_crew_skills
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "sched_crew_skills_select_own_org" ON social_wiring.sched_crew_skills;
CREATE POLICY "sched_crew_skills_select_own_org" ON social_wiring.sched_crew_skills
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- sched_pending_chat_identities
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "sched_pending_chat_select_own_org" ON social_wiring.sched_pending_chat_identities;
CREATE POLICY "sched_pending_chat_select_own_org" ON social_wiring.sched_pending_chat_identities
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- sched_properties
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "sched_properties_select_own_org" ON social_wiring.sched_properties;
CREATE POLICY "sched_properties_select_own_org" ON social_wiring.sched_properties
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- sched_route_groups
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "sched_route_groups_select_own_org" ON social_wiring.sched_route_groups;
CREATE POLICY "sched_route_groups_select_own_org" ON social_wiring.sched_route_groups
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- sched_services
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "sched_services_select_own_org" ON social_wiring.sched_services;
CREATE POLICY "sched_services_select_own_org" ON social_wiring.sched_services
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- sched_tool_call_audits
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "sched_tool_call_audits_select_own_org" ON social_wiring.sched_tool_call_audits;
CREATE POLICY "sched_tool_call_audits_select_own_org" ON social_wiring.sched_tool_call_audits
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- sched_users
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "sched_users_select_own_org" ON social_wiring.sched_users;
CREATE POLICY "sched_users_select_own_org" ON social_wiring.sched_users
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- send_logs
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "em_send_logs_select_own_org" ON social_wiring.send_logs;
CREATE POLICY "em_send_logs_select_own_org" ON social_wiring.send_logs
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- sender_domains
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "em_domains_select_own_org" ON social_wiring.sender_domains;
CREATE POLICY "em_domains_select_own_org" ON social_wiring.sender_domains
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- templates
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "em_templates_select_own_org" ON social_wiring.templates;
CREATE POLICY "em_templates_select_own_org" ON social_wiring.templates
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- unsubscribes
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "em_unsubscribes_select_own_org" ON social_wiring.unsubscribes;
CREATE POLICY "em_unsubscribes_select_own_org" ON social_wiring.unsubscribes
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- upload_jobs
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "upload_jobs_select_own_org" ON social_wiring.upload_jobs;
CREATE POLICY "upload_jobs_select_own_org" ON social_wiring.upload_jobs
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

DROP POLICY IF EXISTS "upload_jobs_update_own_org" ON social_wiring.upload_jobs;
CREATE POLICY "upload_jobs_update_own_org" ON social_wiring.upload_jobs
  FOR UPDATE TO authenticated
  USING (org_id = current_org_id())
  WITH CHECK (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- video_cache
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "video_cache_select_own_org" ON social_wiring.video_cache;
CREATE POLICY "video_cache_select_own_org" ON social_wiring.video_cache
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- whatsapp_connections
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "whatsapp_connections_select_own" ON social_wiring.whatsapp_connections;
CREATE POLICY "whatsapp_connections_select_own" ON social_wiring.whatsapp_connections
  FOR SELECT TO authenticated
  USING (
    (org_id = current_org_id())
    AND (user_id = (SELECT auth.uid()))
  );

-- ---------------------------------------------------------------------------
-- youtube_channel_snapshots
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "youtube_channel_snapshots_select_own_org" ON social_wiring.youtube_channel_snapshots;
CREATE POLICY "youtube_channel_snapshots_select_own_org" ON social_wiring.youtube_channel_snapshots
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- youtube_shorts
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "youtube_shorts_select_own_org" ON social_wiring.youtube_shorts;
CREATE POLICY "youtube_shorts_select_own_org" ON social_wiring.youtube_shorts
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- youtube_video_snapshots
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "youtube_video_snapshots_select_own_org" ON social_wiring.youtube_video_snapshots;
CREATE POLICY "youtube_video_snapshots_select_own_org" ON social_wiring.youtube_video_snapshots
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- youtube_videos
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "youtube_videos_select_own_org" ON social_wiring.youtube_videos;
CREATE POLICY "youtube_videos_select_own_org" ON social_wiring.youtube_videos
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());


-- ============================================================================
-- SECTION 3: Fix the 5 INSERT/ALL social_wiring policies NOT yet rewritten
--            live (still used broken jwt() top-level claim)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- api_tokens — INSERT (admin-only gate)
-- Was: WITH CHECK (org_id = jwt()->>'org_id' AND EXISTS admin-role check)
-- Fix: use current_org_id() for the org_id predicate; keep admin-role gate.
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "api_tokens_insert_own_org_admin" ON social_wiring.api_tokens;
CREATE POLICY "api_tokens_insert_own_org_admin" ON social_wiring.api_tokens
  FOR INSERT TO authenticated
  WITH CHECK (
    (org_id = current_org_id())
    AND (EXISTS (
      SELECT 1 FROM noctus_users nu
      WHERE nu.id = (SELECT auth.uid())
        AND nu.org_id = api_tokens.org_id
        AND nu.org_role = ANY (ARRAY['owner'::text, 'admin'::text])
    ))
  );

-- ---------------------------------------------------------------------------
-- clients — INSERT
-- Was: WITH CHECK (org_id = jwt()->>'org_id')
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "clients_insert_own_org" ON social_wiring.clients;
CREATE POLICY "clients_insert_own_org" ON social_wiring.clients
  FOR INSERT TO authenticated
  WITH CHECK (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- integration_accounts — INSERT
-- Was: WITH CHECK (org_id = jwt()->>'org_id')
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "integration_accounts_insert_own_org" ON social_wiring.integration_accounts;
CREATE POLICY "integration_accounts_insert_own_org" ON social_wiring.integration_accounts
  FOR INSERT TO authenticated
  WITH CHECK (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- mc_brand_owners_legacy — ALL (public role — intentionally kept as-is,
-- but org predicate fixed)
-- Was: USING (org_id = jwt()->>'org_id') TO public
-- Fix: use current_org_id(). NOTE: this table is named "_legacy"; the
-- service_role_bypass policy below already exists.
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "mc_brand_owners_select_own_org" ON social_wiring.mc_brand_owners_legacy;
CREATE POLICY "mc_brand_owners_select_own_org" ON social_wiring.mc_brand_owners_legacy
  FOR ALL TO public
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- upload_jobs — INSERT
-- Was: WITH CHECK (org_id = jwt()->>'org_id')
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "upload_jobs_insert_own_org" ON social_wiring.upload_jobs;
CREATE POLICY "upload_jobs_insert_own_org" ON social_wiring.upload_jobs
  FOR INSERT TO authenticated
  WITH CHECK (org_id = current_org_id());
