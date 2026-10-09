-- Migration: 212_org_picker_mailing_policies
-- Schema(s): mailing (owned by the social-wiring chain)
--
-- ORG PICKER (projects/org-picker/CONTRACT.md) -- the email-marketing engine's own
-- `mailing` schema. Same conversion as 211, same literal: the picker selection is
-- keyed by the social-wiring PRODUCT, and `mailing` is a social-wiring-owned schema,
-- so every org-scoped policy resolves through
-- (SELECT public.current_org_id_for('social_wiring')) -- home org for everyone, the
-- staff member's selected org while acting in social-wiring.
--
-- ALTER POLICY only (name, command, roles unchanged); bodies generated from the LIVE
-- pg_policies of prod (schemaname = 'mailing', 32 policies, 15 org-scoped; the rest are
-- service_role `true`). Must land before 213 flips org_picker_ready.
--
-- DEPENDS ON core migration 070 (public.current_org_id_for). Fails loudly if absent.
--
-- KB § PATTERNS/backend/database-rls.md

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION
      'migration 212 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

ALTER POLICY ai_feedback_own_org ON mailing.ai_feedback
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND (user_id = ( SELECT auth.uid() AS uid))));

ALTER POLICY ai_outputs_own_org ON mailing.ai_outputs
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY enrollments_via_automation ON mailing.automation_enrollments
  USING ((automation_id IN ( SELECT automations.id
   FROM mailing.automations
  WHERE (automations.org_id = (SELECT public.current_org_id_for('social_wiring'))))));

ALTER POLICY steps_via_automation ON mailing.automation_steps
  USING ((automation_id IN ( SELECT automations.id
   FROM mailing.automations
  WHERE (automations.org_id = (SELECT public.current_org_id_for('social_wiring'))))));

ALTER POLICY automations_own_org ON mailing.automations
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY campaigns_own_org ON mailing.campaigns
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY list_members_via_list ON mailing.contact_list_members
  USING ((list_id IN ( SELECT contact_lists.id
   FROM mailing.contact_lists
  WHERE (contact_lists.org_id = (SELECT public.current_org_id_for('social_wiring'))))));

ALTER POLICY lists_own_org ON mailing.contact_lists
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY contacts_own_org ON mailing.contacts
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY invitations_select_own_org ON mailing.invitations
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY clicks_via_send_log ON mailing.link_clicks
  USING ((send_log_id IN ( SELECT send_logs.id
   FROM mailing.send_logs
  WHERE (send_logs.org_id = (SELECT public.current_org_id_for('social_wiring'))))));

ALTER POLICY send_logs_own_org ON mailing.send_logs
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY domains_own_org ON mailing.sender_domains
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY templates_own_org ON mailing.templates
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY unsubscribes_own_org ON mailing.unsubscribes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));
