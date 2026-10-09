-- 039 -- audit every PostgREST write a platform staff member makes while acting in a customer org
--
-- Same as social-wiring 214: core 072's public.audit_acting_write() trigger (one audit_logs row,
-- ids + changed column names only, only when current_org_id_for('igig') <> current_org_id())
-- is attached to every org_id-bearing base table of the igig schema. Idempotent (re-run
-- re-creates). 040 flips org_picker_ready after this. The keeper check_org_picker_ready_policies
-- checks this call is present in the chain.
-- KB § PATTERNS/backend/tenancy-license-gate.md

DO $guard$
BEGIN
  IF to_regprocedure('public.attach_acting_audit_triggers(text, text)') IS NULL THEN
    RAISE EXCEPTION 'core 072 (public.attach_acting_audit_triggers) must be applied before igig 039';
  END IF;
END
$guard$;

SELECT public.attach_acting_audit_triggers('igig');
