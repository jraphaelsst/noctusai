-- ============================================================================
-- IgIg — SQLite mirror of `036_igig_contrato_encerramento.sql` (036 ↔ 036).
-- Parity-tested by tests/test_schema_parity.py.
-- ============================================================================

ALTER TABLE contrato ADD COLUMN data_encerramento TEXT;
ALTER TABLE contrato ADD COLUMN motivo_encerramento TEXT;
