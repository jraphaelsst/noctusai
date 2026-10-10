-- ============================================================================
-- Migration 237 — anon loses every privilege in `mailing` except SELECT on
-- status_pagina: the fleet posture (SW 140, seed 010/011, SW 235) applied to the
-- legacy schema it had skipped.
--
-- WHY: prod 2026-10-10 — anon held ALL (incl. TRUNCATE) on all 16 mailing
-- tables plus anon default privileges on future tables and sequences. mailing is
-- in PostgREST's exposed schemas; RLS (no anon write policy) still refused anon
-- writes, so defence in depth, not an open hole. Idempotent.
-- GuardProbe: verify_db_guards `mailing.anon_only_reads_status_pagina`.
-- ============================================================================

DO $lock$
BEGIN
  IF to_regnamespace('mailing') IS NULL THEN
    RAISE NOTICE 'no mailing schema — nothing to lock';
    RETURN;
  END IF;
  REVOKE ALL ON ALL TABLES IN SCHEMA mailing FROM anon;
  REVOKE ALL ON ALL SEQUENCES IN SCHEMA mailing FROM anon;
  ALTER DEFAULT PRIVILEGES IN SCHEMA mailing REVOKE ALL ON TABLES FROM anon;
  ALTER DEFAULT PRIVILEGES IN SCHEMA mailing REVOKE ALL ON SEQUENCES FROM anon;
  GRANT SELECT ON mailing.status_pagina TO anon;
END
$lock$;
