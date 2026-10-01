-- ============================================================================
-- IgIg — contrato encerramento (CRUD de contratos)
--
-- `contrato.status` already allows 'encerrado' (CHECK on migration 006) and
-- the code already reads it, but nothing could set it and nothing recorded
-- WHEN or WHY. Contratos are never deleted — they are ENCERRADOS: this adds
-- the two columns `POST /api/contratos/{id}/encerrar` writes. Billing stops
-- counting an encerrado contrato from the month after `data_encerramento`.
-- Expand-only, nullable, idempotent: an image that does not know these
-- columns keeps working.
--
-- SQLite mirror: migrations/sqlite/036_contrato_encerramento.sql (parity-tested).
-- ============================================================================
SET search_path = igig, public;

ALTER TABLE igig.contrato ADD COLUMN IF NOT EXISTS data_encerramento DATE;
ALTER TABLE igig.contrato ADD COLUMN IF NOT EXISTS motivo_encerramento TEXT;
