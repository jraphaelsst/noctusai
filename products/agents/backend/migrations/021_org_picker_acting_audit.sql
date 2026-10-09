-- Migration: 021_org_picker_acting_audit
-- Schema(s): agents
--
-- ORG PICKER -- acting audit. Attaches the acting-audit triggers (core migration 072)
-- to every table of the agents schema, so a write made while a platform-staff member
-- acts in another org records who acted and for which org.
--
-- DEPENDS ON core migration 072 (public.attach_acting_audit_triggers). Fails loudly
-- if absent. Idempotent (the helper is). KB § PATTERNS/backend/database-rls.md

DO $guard$
BEGIN
  IF to_regprocedure('public.attach_acting_audit_triggers(text, text)') IS NULL THEN
    RAISE EXCEPTION
      'migration 021 requires public.attach_acting_audit_triggers(text, text) (core migration 072) -- apply core first';
  END IF;
END
$guard$;

SELECT public.attach_acting_audit_triggers('agents');
