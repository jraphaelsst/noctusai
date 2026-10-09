-- Migration: 020_org_picker_policies
-- Schema(s): agents
--
-- ORG PICKER (projects/org-picker/CONTRACT.md) -- rollout from the social-wiring pilot (211).
--
-- Every agents RLS policy that resolved the caller's org through public.current_org_id()
-- now calls (SELECT public.current_org_id_for('agents')): the home org for everyone,
-- and the platform-staff member's SELECTED org while they act in this product
-- (core migration 070). The schema literal is in the policy, never a request header.
--
-- Same command, roles, USING / WITH CHECK shape as the live policy: ALTER POLICY (no
-- drop/create gap), bodies generated from the LIVE pg_policies of prod (2026-10-09).
--
-- NOT converted, on purpose:
--   * policies that only test status / true / current_org_role() (status_pagina,
--     service_role_bypass) -- they carry no org identity.
--   * the api_tokens *_admin policies keep their `nu.org_id = api_tokens.org_id` +
--     owner/admin EXISTS on the caller's own noctus_users row: the org predicate is
--     converted, the role check stays home-keyed (the backend writes api_tokens
--     through the service role; a JWT-direct write while acting is refused).
--   * no SECURITY DEFINER helper in this schema embeds the home-only org lookup;
--     there is no storage.objects policy for this product.
--
-- DEPENDS ON core migration 070 (public.current_org_id_for). Fails loudly if absent.
-- Does NOT flip products.org_picker_ready (see 022_org_picker_ready).
--
-- KB § PATTERNS/backend/database-rls.md

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION
      'migration 020 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

ALTER POLICY agent_audit_log_select_own_org ON agents.agent_audit_log
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY agent_client_entries_select_own_org ON agents.agent_client_entries
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY agent_clients_select_own_org ON agents.agent_clients
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY agent_learnings_select_own_org ON agents.agent_learnings
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY agent_package_trees_select_own_org ON agents.agent_package_trees
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY agent_personas_select_own_org ON agents.agent_personas
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY agent_project_sources_select_own_org ON agents.agent_project_sources
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY agent_prompt_sections_select_own_org ON agents.agent_prompt_sections
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY agent_skill_files_select_own_org ON agents.agent_skill_files
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY agent_skills_select_own_org ON agents.agent_skills
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY agent_versions_select_own_org ON agents.agent_versions
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY agents_select_own_org ON agents.agents
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY api_token_audit_select_own_org ON agents.api_token_audit
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY api_tokens_insert_own_org_admin ON agents.api_tokens
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('agents'))) AND (EXISTS ( SELECT 1
   FROM public.noctus_users nu
  WHERE ((nu.id = ( SELECT auth.uid() AS uid)) AND (nu.org_id = api_tokens.org_id) AND (nu.org_role = ANY (ARRAY['owner'::text, 'admin'::text])))))));

ALTER POLICY api_tokens_select_own_org ON agents.api_tokens
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY api_tokens_update_own_org_admin ON agents.api_tokens
  USING (((org_id = (SELECT public.current_org_id_for('agents'))) AND (EXISTS ( SELECT 1
   FROM public.noctus_users nu
  WHERE ((nu.id = ( SELECT auth.uid() AS uid)) AND (nu.org_id = api_tokens.org_id) AND (nu.org_role = ANY (ARRAY['owner'::text, 'admin'::text])))))));

ALTER POLICY approvals_select_own_org ON agents.approvals
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY compiled_prompts_select_own_org ON agents.compiled_prompts
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY conversations_select_own_org ON agents.conversations
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY eval_cases_select_own_org ON agents.eval_cases
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY eval_results_select_own_org ON agents.eval_results
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY eval_runs_select_own_org ON agents.eval_runs
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY examples_delete_own_org ON agents.examples
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY examples_insert_own_org ON agents.examples
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY examples_select_own_org ON agents.examples
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY examples_update_own_org ON agents.examples
  USING ((org_id = (SELECT public.current_org_id_for('agents'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY invitations_select_own_org ON agents.invitations
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY knowledge_collections_select_own_org ON agents.knowledge_collections
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY knowledge_documents_select_own_org ON agents.knowledge_documents
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY knowledge_revisions_select_own_org ON agents.knowledge_revisions
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));

ALTER POLICY messages_select_own_org ON agents.messages
  USING ((org_id = (SELECT public.current_org_id_for('agents'))));
