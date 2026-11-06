-- Migration: 325_org_id_default_acting_aware
-- Schema(s): social_wiring, mailing
--
-- Incident 2026-11-06 ("Extrator de Matriculas": new row violates row-level security policy
-- for table matricula_extracoes). 211 converted every policy to
-- (SELECT public.current_org_id_for('social_wiring')) -- the picker-aware org, i.e. the SELECTED
-- org while platform staff act -- but a column `org_id ... DEFAULT public.current_org_id()` (092)
-- stayed HOME-ONLY: an INSERT that omits org_id (the upload) stamped the staff member's HOME org
-- and the converted WITH CHECK refused it.
--
-- Fix: every org_id default in the product's schemas that still resolves HOME-ONLY now resolves
-- through the same helper the policies call. Data-driven (the live catalogue, not a hand list), so
-- a default added outside the chain is caught too. For every non-staff caller
-- current_org_id_for() returns exactly what current_org_id() returned (the HOME rule), so
-- nothing changes for customers; for staff it is the picker-selected org or NULL (deny), never
-- wider. Expand-safe: a column DEFAULT swap needs no rewrite; N-1 code keeps working.
--
-- DEPENDS ON core 070 (current_org_id_for). Idempotent.
-- KB § PATTERNS/backend/database-rls.md

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'migration 325 requires public.current_org_id_for(text) (core migration 070)';
  END IF;
END
$guard$;

DO $swap$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT c.table_schema, c.table_name
      FROM information_schema.columns c
      JOIN information_schema.tables t
        ON t.table_schema = c.table_schema AND t.table_name = c.table_name
       AND t.table_type = 'BASE TABLE'
     WHERE c.table_schema IN ('social_wiring', 'mailing')
       AND c.column_name = 'org_id'
       AND c.column_default ~ 'current_(user_)?org_id\(\)'
  LOOP
    EXECUTE format(
      'ALTER TABLE %I.%I ALTER COLUMN org_id SET DEFAULT public.current_org_id_for(%L)',
      r.table_schema, r.table_name, 'social_wiring');
    RAISE NOTICE 'org_id default now acting-aware: %.%', r.table_schema, r.table_name;
  END LOOP;
END
$swap$;
