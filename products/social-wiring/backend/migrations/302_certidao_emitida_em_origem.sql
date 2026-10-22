-- ============================================================================
-- Migration 302 -- social_wiring: certidao_resultados.emitida_em_origem
--
-- A CENPROT / Serasa "consulta" saved as a text PDF can carry the protocolo
-- and the result but NO date anywhere in its text; the PDF metadata
-- CreationDate is the moment the consulta was printed. The reader falls back
-- to it (same plausibility window the CENPROT reader already uses) and
-- records WHERE the date came from, so an inferred date is never silently
-- equal to a printed one:
--   NULL            -> printed on the document / registry / typed by a human
--   'metadados_pdf' -> inferred from the PDF CreationDate
-- No CHECK on the vocabulary (the reader owns it; room for more origins).
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================
SET search_path = social_wiring, public;

ALTER TABLE social_wiring.certidao_resultados
    ADD COLUMN IF NOT EXISTS emitida_em_origem TEXT;
