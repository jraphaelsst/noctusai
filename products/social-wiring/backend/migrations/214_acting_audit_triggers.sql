-- 214 -- audit every PostgREST write a platform staff member makes while acting in a customer org
--
-- Closes NOC-REMEDIATE[org-picker-postgrest-audit] for social-wiring: core 072's
-- public.audit_acting_write() trigger (one audit_logs row, ids + changed column names only,
-- only when current_org_id_for('social_wiring') <> current_org_id()) is attached to every
-- org_id-bearing base table of the product's two schemas. Idempotent (re-run re-creates).
-- 213 flipped org_picker_ready first; the keeper check_org_picker_ready_policies checks this
-- call is present anywhere in the chain. KB § PATTERNS/backend/tenancy-license-gate.md

DO $guard$
BEGIN
  IF to_regprocedure('public.attach_acting_audit_triggers(text, text)') IS NULL THEN
    RAISE EXCEPTION 'core 072 (public.attach_acting_audit_triggers) must be applied before social-wiring 214';
  END IF;
END
$guard$;

-- The selection is keyed by the PRODUCT schema; 'mailing' belongs to social-wiring's chain, so its
-- triggers pass 'social_wiring' as the product schema (second argument).
SELECT public.attach_acting_audit_triggers('social_wiring');
SELECT public.attach_acting_audit_triggers('mailing', 'social_wiring');
