-- ============================================================================
-- Migration 234 — erp.current_org_id() excludes customer roles, like
-- public.current_org_id() has since 173_customer_role_isolation.
--
-- WHY: the 2026-09-28 fleet customer-role isolation re-declared
-- public.current_org_id() to return NULL for a customer (`org_role = 'membro'`),
-- but the `erp` copy — declared by THIS product's 011 (social-wiring owns that
-- leg while erp-imobiliario is asleep) — was never touched. Prod 2026-10-10:
-- erp is in PostgREST's exposed schemas, 183 erp policies call
-- erp.current_org_id(), and the function still returns a customer's org — so a
-- 'membro' user reads that org's erp rows (2769 live). Found by the ledger
-- checksum audit's catalog check.
--
-- Guarded with to_regnamespace('erp'): a fresh chain (migration_replay, a new
-- environment) has no erp schema while erp-imobiliario is asleep — then this is
-- a NOTICE, never an error. Idempotent (CREATE OR REPLACE). No REVOKE EXECUTE:
-- it is an RLS helper called from pg_policy (the secdef keeper's allowlist), the
-- same posture as public.current_org_id() in 173.
-- GuardProbe: verify_db_guards `erp.current_org_id_excludes_customer`.
-- ============================================================================

DO $erp$
BEGIN
  IF to_regnamespace('erp') IS NULL THEN
    RAISE NOTICE 'no erp schema — erp.current_org_id() not re-declared';
    RETURN;
  END IF;
  EXECUTE $fn$
    -- secdef-execute-ok: rls-helper called by 183 erp RLS policies (pg_policy); same posture as public.current_org_id()
    CREATE OR REPLACE FUNCTION erp.current_org_id()
      RETURNS uuid
      LANGUAGE sql
      STABLE SECURITY DEFINER
      SET search_path TO 'public', 'erp'
    AS $f$
      SELECT org_id FROM public.noctus_users
       WHERE id = (SELECT auth.uid())
         AND COALESCE(org_role, '') <> ALL (ARRAY['membro']);
    $f$
  $fn$;
END
$erp$;
