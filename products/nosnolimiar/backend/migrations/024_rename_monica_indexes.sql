-- ============================================================================
-- 024 -- rename the `idx_monica_*` indexes to `idx_nosnolimiar_*` (product rename, 2026-11-14)
-- ============================================================================
-- `monica` was absorbed by `nosnolimiar`; 023 moved the schema but left the eight index names that the frozen
-- migrations 001/003/015 declare (idx_monica_examples_*, idx_monica_invitations_*, idx_monica_whatsapp_*). The owner
-- asked for the rename to leave nothing named after the old product, so this file renames them in place.
-- An index rename changes metadata only: no rebuild, no data touched, and no behaviour changes (the unique
-- webhook-token index refuses duplicates under either name; its probe in verify_db_guards now names the new one).
-- Derived from the live catalog (pg_class in schema `nosnolimiar`), never a hand-copied list.
-- IDEMPOTENT: once converged no `idx_monica_*` index is left, so a re-run renames nothing.
-- ORDER (prod): after 023 (the indexes live in `nosnolimiar` only once the schema is renamed).
-- ROLLBACK: projects/rename-2026-11/rollback-024.sql (the same block with the prefixes swapped).
-- ============================================================================

DO $mig$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT c.relname
      FROM pg_class c
     WHERE c.relnamespace = to_regnamespace('nosnolimiar')
       AND c.relkind = 'i'
       AND c.relname LIKE 'idx\_monica\_%'
  LOOP
    EXECUTE format('ALTER INDEX nosnolimiar.%I RENAME TO %I',
                   r.relname, 'idx_nosnolimiar_' || substr(r.relname, length('idx_monica_') + 1));
  END LOOP;

  IF EXISTS (SELECT 1 FROM pg_class c
              WHERE c.relnamespace = to_regnamespace('nosnolimiar') AND c.relkind = 'i'
                AND c.relname LIKE 'idx\_monica\_%') THEN
    RAISE EXCEPTION '024: an idx_monica_* index survived the rename';
  END IF;
END
$mig$;
