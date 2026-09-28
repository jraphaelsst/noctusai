-- ============================================================================
-- IgIg — SQLite mirror of `032_igig_fatura_enviada_em.sql` (032 ↔ 032).
-- Parity-tested by tests/test_schema_parity.py.
-- ============================================================================

ALTER TABLE fatura ADD COLUMN enviada_em TEXT;
