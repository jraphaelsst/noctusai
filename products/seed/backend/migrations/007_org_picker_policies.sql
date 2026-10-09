-- Migration: 007_org_picker_policies
-- Schema(s): seed
--
-- ORG PICKER (projects/org-picker/CONTRACT.md) -- rollout from the social-wiring pilot (211).
--
-- Every seed RLS policy that resolved the caller's org through public.current_org_id()
-- now calls (SELECT public.current_org_id_for('seed')): the home org for everyone,
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
-- Does NOT flip products.org_picker_ready (see 009_org_picker_ready).
--
-- KB § PATTERNS/backend/database-rls.md

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION
      'migration 007 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

ALTER POLICY examples_delete_own_org ON seed.examples
  USING ((org_id = (SELECT public.current_org_id_for('seed'))));

ALTER POLICY examples_insert_own_org ON seed.examples
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('seed'))));

ALTER POLICY examples_select_own_org ON seed.examples
  USING ((org_id = (SELECT public.current_org_id_for('seed'))));

ALTER POLICY examples_update_own_org ON seed.examples
  USING ((org_id = (SELECT public.current_org_id_for('seed'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('seed'))));

ALTER POLICY invitations_select_own_org ON seed.invitations
  USING ((org_id = (SELECT public.current_org_id_for('seed'))));
