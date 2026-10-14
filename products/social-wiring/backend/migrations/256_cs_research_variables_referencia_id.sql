-- ============================================================================
-- Migration 256 · social_wiring: cs_research_variables.corestudio_id -> referencia_id
-- ============================================================================
-- WHY
-- ---
-- Owner decision 2026-10-14 ("no leftovers from Core"): the column holding each
-- research variable's id in the reference app no longer names that app. Pure
-- rename -- same type, same values, no data touched.
--
-- Safe while the previous image runs: no runtime code selects this column
-- (pesquisa_service lists slug,label,grupo,description,classifiable,sort_order);
-- only migration 217's seed upsert names it, and 217 is applied + immutable.
--
-- FORWARD-ONLY, IDEMPOTENT (renames only while the old name exists). No CHECK /
-- UNIQUE / trigger added, so no GuardProbe.
-- ============================================================================

SET search_path = social_wiring, public;

DO $rename$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
     WHERE table_schema = 'social_wiring' AND table_name = 'cs_research_variables'
       AND column_name = 'corestudio_id'
  ) THEN
    ALTER TABLE social_wiring.cs_research_variables RENAME COLUMN corestudio_id TO referencia_id;
  END IF;
END
$rename$;

COMMENT ON COLUMN social_wiring.cs_research_variables.referencia_id IS
  'Id of the variable in the reference app it was mapped from (NULL = our own variable).';
