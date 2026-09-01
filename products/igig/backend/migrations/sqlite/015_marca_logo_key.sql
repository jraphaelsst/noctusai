-- ============================================================================
-- SQLite mirror of 015_igig_marca_logo_key.sql (parity-tested by
-- tests/test_schema_parity.py — every `0NN_igig_*.sql` needs a counterpart).
--
-- Column only. The Postgres file's backfill is a data repair for the live
-- database and has no meaning here: the SQLite path is tests-only and starts
-- empty every run, so there is never a legacy signed URL to recover.
-- ============================================================================
ALTER TABLE marca ADD COLUMN logo_key TEXT;
