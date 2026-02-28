-- =====================================================================
-- 006 — Lead Scoring columns on erp.clientes
-- Adds AI lead-score persistence (score, justificativa, timestamp).
-- =====================================================================

ALTER TABLE erp.clientes
  ADD COLUMN IF NOT EXISTS lead_score INTEGER CHECK (lead_score >= 0 AND lead_score <= 100),
  ADD COLUMN IF NOT EXISTS lead_score_justificativa TEXT,
  ADD COLUMN IF NOT EXISTS lead_score_updated_at TIMESTAMPTZ;
