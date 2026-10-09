-- Migration: 015_org_picker_policies
-- Schema(s): academia_de_reciclagem
--
-- ORG PICKER (projects/org-picker/CONTRACT.md) -- rollout from the social-wiring pilot (211).
--
-- Every academia_de_reciclagem RLS policy that resolved the caller's org through public.current_org_id()
-- now calls (SELECT public.current_org_id_for('academia_de_reciclagem')): the home org for everyone,
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
-- Does NOT flip products.org_picker_ready (see 017_org_picker_ready).
--
-- KB § PATTERNS/backend/database-rls.md

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION
      'migration 015 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

ALTER POLICY api_token_audit_select_own_org ON academia_de_reciclagem.api_token_audit
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY api_tokens_insert_own_org_admin ON academia_de_reciclagem.api_tokens
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))) AND (EXISTS ( SELECT 1
   FROM public.noctus_users nu
  WHERE ((nu.id = ( SELECT auth.uid() AS uid)) AND (nu.org_id = api_tokens.org_id) AND (nu.org_role = ANY (ARRAY['owner'::text, 'admin'::text])))))));

ALTER POLICY api_tokens_select_own_org ON academia_de_reciclagem.api_tokens
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY api_tokens_update_own_org_admin ON academia_de_reciclagem.api_tokens
  USING (((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))) AND (EXISTS ( SELECT 1
   FROM public.noctus_users nu
  WHERE ((nu.id = ( SELECT auth.uid() AS uid)) AND (nu.org_id = api_tokens.org_id) AND (nu.org_role = ANY (ARRAY['owner'::text, 'admin'::text])))))));

ALTER POLICY approval_consumptions_select_own_org ON academia_de_reciclagem.approval_consumptions
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY code_counters_select_own_org ON academia_de_reciclagem.code_counters
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY content_drafts_select_own_org ON academia_de_reciclagem.content_drafts
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY decisions_select_own_org ON academia_de_reciclagem.decisions
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY examples_delete_own_org ON academia_de_reciclagem.examples
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY examples_insert_own_org ON academia_de_reciclagem.examples
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY examples_select_own_org ON academia_de_reciclagem.examples
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY examples_update_own_org ON academia_de_reciclagem.examples
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY invitations_select_own_org ON academia_de_reciclagem.invitations
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY kb_entries_select_own_org ON academia_de_reciclagem.kb_entries
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY kb_revisions_select_own_org ON academia_de_reciclagem.kb_revisions
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY open_questions_select_own_org ON academia_de_reciclagem.open_questions
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY research_sources_select_own_org ON academia_de_reciclagem.research_sources
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY roadmap_phases_select_own_org ON academia_de_reciclagem.roadmap_phases
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY tasks_select_own_org ON academia_de_reciclagem.tasks
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));

ALTER POLICY timeline_events_select_own_org ON academia_de_reciclagem.timeline_events
  USING ((org_id = (SELECT public.current_org_id_for('academia_de_reciclagem'))));
