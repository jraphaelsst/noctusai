-- ============================================================================
-- Migration 033 — Codify the live RLS fix: current_org_id() for imobi_scheduling
--
-- WHY THIS EXISTS
-- ---------------
-- The imobi_scheduling schema was created directly on prod as part of the
-- imobi-scheduling feature (14-phase build). No repo migration file existed
-- for this schema before 2026-06-02. All 56 authenticated policies used:
--
--     org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
--
-- This is ALWAYS NULL in Supabase (see migration 032 header for root cause).
-- The fix was applied LIVE on 2026-06-02 using current_org_id().
-- This migration codifies both the schema RLS creation and the fix so that
-- a fresh DB build produces the correct secure state.
--
-- PLACEMENT DECISION: imobi_scheduling is owned by erp-imobiliario (the
-- imobi-scheduling product was built inside the erp-imobiliario container and
-- the media-scheduling product was absorbed into it in commit b91043fc).
--
-- PREREQUISITE: public.current_org_id() must exist (defined in
--   products/seed/backend/migrations/001_seed.sql).
--
-- IDEMPOTENT: all policies use DROP POLICY IF EXISTS before CREATE POLICY.
--
-- SOURCE OF TRUTH: pg_policies on Supabase project nyplttplcoyiiqjrvtiw,
-- queried 2026-06-02.
-- ============================================================================

-- ----- imobi_scheduling.appointment_request_services -----
DROP POLICY IF EXISTS "appt_req_services_delete_via_parent" ON imobi_scheduling.appointment_request_services;
CREATE POLICY "appt_req_services_delete_via_parent" ON imobi_scheduling.appointment_request_services
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "appt_req_services_insert_via_parent" ON imobi_scheduling.appointment_request_services;
CREATE POLICY "appt_req_services_insert_via_parent" ON imobi_scheduling.appointment_request_services
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "appt_req_services_select_via_parent" ON imobi_scheduling.appointment_request_services;
CREATE POLICY "appt_req_services_select_via_parent" ON imobi_scheduling.appointment_request_services
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.appointment_requests -----
DROP POLICY IF EXISTS "appointment_requests_delete_org" ON imobi_scheduling.appointment_requests;
CREATE POLICY "appointment_requests_delete_org" ON imobi_scheduling.appointment_requests
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "appointment_requests_insert_org" ON imobi_scheduling.appointment_requests;
CREATE POLICY "appointment_requests_insert_org" ON imobi_scheduling.appointment_requests
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "appointment_requests_select_org" ON imobi_scheduling.appointment_requests;
CREATE POLICY "appointment_requests_select_org" ON imobi_scheduling.appointment_requests
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "appointment_requests_update_org" ON imobi_scheduling.appointment_requests;
CREATE POLICY "appointment_requests_update_org" ON imobi_scheduling.appointment_requests
  FOR UPDATE TO authenticated
  USING ((org_id = public.current_org_id()))
  WITH CHECK ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.appointments -----
DROP POLICY IF EXISTS "appointments_delete_org" ON imobi_scheduling.appointments;
CREATE POLICY "appointments_delete_org" ON imobi_scheduling.appointments
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "appointments_insert_org" ON imobi_scheduling.appointments;
CREATE POLICY "appointments_insert_org" ON imobi_scheduling.appointments
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "appointments_select_org" ON imobi_scheduling.appointments;
CREATE POLICY "appointments_select_org" ON imobi_scheduling.appointments
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "appointments_update_org" ON imobi_scheduling.appointments;
CREATE POLICY "appointments_update_org" ON imobi_scheduling.appointments
  FOR UPDATE TO authenticated
  USING ((org_id = public.current_org_id()))
  WITH CHECK ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.condominiums -----
DROP POLICY IF EXISTS "condominiums_delete_org" ON imobi_scheduling.condominiums;
CREATE POLICY "condominiums_delete_org" ON imobi_scheduling.condominiums
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "condominiums_insert_org" ON imobi_scheduling.condominiums;
CREATE POLICY "condominiums_insert_org" ON imobi_scheduling.condominiums
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "condominiums_select_org" ON imobi_scheduling.condominiums;
CREATE POLICY "condominiums_select_org" ON imobi_scheduling.condominiums
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "condominiums_update_org" ON imobi_scheduling.condominiums;
CREATE POLICY "condominiums_update_org" ON imobi_scheduling.condominiums
  FOR UPDATE TO authenticated
  USING ((org_id = public.current_org_id()))
  WITH CHECK ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.conversation_messages -----
DROP POLICY IF EXISTS "conversation_messages_delete_org" ON imobi_scheduling.conversation_messages;
CREATE POLICY "conversation_messages_delete_org" ON imobi_scheduling.conversation_messages
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "conversation_messages_insert_org" ON imobi_scheduling.conversation_messages;
CREATE POLICY "conversation_messages_insert_org" ON imobi_scheduling.conversation_messages
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "conversation_messages_select_org" ON imobi_scheduling.conversation_messages;
CREATE POLICY "conversation_messages_select_org" ON imobi_scheduling.conversation_messages
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.conversation_summaries -----
DROP POLICY IF EXISTS "conversation_summaries_delete_org" ON imobi_scheduling.conversation_summaries;
CREATE POLICY "conversation_summaries_delete_org" ON imobi_scheduling.conversation_summaries
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "conversation_summaries_insert_org" ON imobi_scheduling.conversation_summaries;
CREATE POLICY "conversation_summaries_insert_org" ON imobi_scheduling.conversation_summaries
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "conversation_summaries_select_org" ON imobi_scheduling.conversation_summaries;
CREATE POLICY "conversation_summaries_select_org" ON imobi_scheduling.conversation_summaries
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.crew_skills -----
DROP POLICY IF EXISTS "crew_skills_delete_org" ON imobi_scheduling.crew_skills;
CREATE POLICY "crew_skills_delete_org" ON imobi_scheduling.crew_skills
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "crew_skills_insert_org" ON imobi_scheduling.crew_skills;
CREATE POLICY "crew_skills_insert_org" ON imobi_scheduling.crew_skills
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "crew_skills_select_org" ON imobi_scheduling.crew_skills;
CREATE POLICY "crew_skills_select_org" ON imobi_scheduling.crew_skills
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.invitations -----
DROP POLICY IF EXISTS "invitations_select_own_org" ON imobi_scheduling.invitations;
CREATE POLICY "invitations_select_own_org" ON imobi_scheduling.invitations
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.oauth_credentials -----
DROP POLICY IF EXISTS "oauth_credentials_delete_org" ON imobi_scheduling.oauth_credentials;
CREATE POLICY "oauth_credentials_delete_org" ON imobi_scheduling.oauth_credentials
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "oauth_credentials_insert_org" ON imobi_scheduling.oauth_credentials;
CREATE POLICY "oauth_credentials_insert_org" ON imobi_scheduling.oauth_credentials
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "oauth_credentials_select_org" ON imobi_scheduling.oauth_credentials;
CREATE POLICY "oauth_credentials_select_org" ON imobi_scheduling.oauth_credentials
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "oauth_credentials_update_org" ON imobi_scheduling.oauth_credentials;
CREATE POLICY "oauth_credentials_update_org" ON imobi_scheduling.oauth_credentials
  FOR UPDATE TO authenticated
  USING ((org_id = public.current_org_id()))
  WITH CHECK ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.pending_chat_identities -----
DROP POLICY IF EXISTS "pending_chat_identities_delete_org" ON imobi_scheduling.pending_chat_identities;
CREATE POLICY "pending_chat_identities_delete_org" ON imobi_scheduling.pending_chat_identities
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "pending_chat_identities_insert_org" ON imobi_scheduling.pending_chat_identities;
CREATE POLICY "pending_chat_identities_insert_org" ON imobi_scheduling.pending_chat_identities
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "pending_chat_identities_select_org" ON imobi_scheduling.pending_chat_identities;
CREATE POLICY "pending_chat_identities_select_org" ON imobi_scheduling.pending_chat_identities
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "pending_chat_identities_update_org" ON imobi_scheduling.pending_chat_identities;
CREATE POLICY "pending_chat_identities_update_org" ON imobi_scheduling.pending_chat_identities
  FOR UPDATE TO authenticated
  USING ((org_id = public.current_org_id()))
  WITH CHECK ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.properties -----
DROP POLICY IF EXISTS "properties_delete_org" ON imobi_scheduling.properties;
CREATE POLICY "properties_delete_org" ON imobi_scheduling.properties
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "properties_insert_org" ON imobi_scheduling.properties;
CREATE POLICY "properties_insert_org" ON imobi_scheduling.properties
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "properties_select_org" ON imobi_scheduling.properties;
CREATE POLICY "properties_select_org" ON imobi_scheduling.properties
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "properties_update_org" ON imobi_scheduling.properties;
CREATE POLICY "properties_update_org" ON imobi_scheduling.properties
  FOR UPDATE TO authenticated
  USING ((org_id = public.current_org_id()))
  WITH CHECK ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.route_groups -----
DROP POLICY IF EXISTS "route_groups_delete_org" ON imobi_scheduling.route_groups;
CREATE POLICY "route_groups_delete_org" ON imobi_scheduling.route_groups
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "route_groups_insert_org" ON imobi_scheduling.route_groups;
CREATE POLICY "route_groups_insert_org" ON imobi_scheduling.route_groups
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "route_groups_select_org" ON imobi_scheduling.route_groups;
CREATE POLICY "route_groups_select_org" ON imobi_scheduling.route_groups
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "route_groups_update_org" ON imobi_scheduling.route_groups;
CREATE POLICY "route_groups_update_org" ON imobi_scheduling.route_groups
  FOR UPDATE TO authenticated
  USING ((org_id = public.current_org_id()))
  WITH CHECK ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.routes -----
DROP POLICY IF EXISTS "routes_delete_org" ON imobi_scheduling.routes;
CREATE POLICY "routes_delete_org" ON imobi_scheduling.routes
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "routes_insert_org" ON imobi_scheduling.routes;
CREATE POLICY "routes_insert_org" ON imobi_scheduling.routes
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "routes_select_org" ON imobi_scheduling.routes;
CREATE POLICY "routes_select_org" ON imobi_scheduling.routes
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "routes_update_org" ON imobi_scheduling.routes;
CREATE POLICY "routes_update_org" ON imobi_scheduling.routes
  FOR UPDATE TO authenticated
  USING ((org_id = public.current_org_id()))
  WITH CHECK ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.services -----
DROP POLICY IF EXISTS "services_delete_org" ON imobi_scheduling.services;
CREATE POLICY "services_delete_org" ON imobi_scheduling.services
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "services_insert_org" ON imobi_scheduling.services;
CREATE POLICY "services_insert_org" ON imobi_scheduling.services
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "services_select_org" ON imobi_scheduling.services;
CREATE POLICY "services_select_org" ON imobi_scheduling.services
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "services_update_org" ON imobi_scheduling.services;
CREATE POLICY "services_update_org" ON imobi_scheduling.services
  FOR UPDATE TO authenticated
  USING ((org_id = public.current_org_id()))
  WITH CHECK ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.tool_call_audits -----
DROP POLICY IF EXISTS "tool_call_audits_delete_org" ON imobi_scheduling.tool_call_audits;
CREATE POLICY "tool_call_audits_delete_org" ON imobi_scheduling.tool_call_audits
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "tool_call_audits_insert_org" ON imobi_scheduling.tool_call_audits;
CREATE POLICY "tool_call_audits_insert_org" ON imobi_scheduling.tool_call_audits
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "tool_call_audits_select_org" ON imobi_scheduling.tool_call_audits;
CREATE POLICY "tool_call_audits_select_org" ON imobi_scheduling.tool_call_audits
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

-- ----- imobi_scheduling.users -----
DROP POLICY IF EXISTS "users_delete_org" ON imobi_scheduling.users;
CREATE POLICY "users_delete_org" ON imobi_scheduling.users
  FOR DELETE TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "users_insert_org" ON imobi_scheduling.users;
CREATE POLICY "users_insert_org" ON imobi_scheduling.users
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "users_select_org" ON imobi_scheduling.users;
CREATE POLICY "users_select_org" ON imobi_scheduling.users
  FOR SELECT TO authenticated
  USING ((org_id = public.current_org_id()));

DROP POLICY IF EXISTS "users_update_org" ON imobi_scheduling.users;
CREATE POLICY "users_update_org" ON imobi_scheduling.users
  FOR UPDATE TO authenticated
  USING ((org_id = public.current_org_id()))
  WITH CHECK ((org_id = public.current_org_id()));
