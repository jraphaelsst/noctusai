-- ============================================================================
-- Migration 348 · social_wiring: admit the Esteira stage role `agendado`
-- ============================================================================
-- WHY: CoreStudio S3 (CORESTUDIO-STRUCTURE.md 2.3 board mapping) declares the role `agendado` in esteira_config.py
-- (PIPELINE_ESTEIRA.stage_roles). The role set is mirrored by the pipeline_stages_papel_check CHECK (migration 241), so the
-- CHECK must admit it or an org assigning it would hit a 500. No stage is created here (S4 owns the stage and the move).
-- WIDENING a CHECK: every existing row still satisfies it, so the previous image keeps working. IDEMPOTENT.
-- ============================================================================
SET search_path = social_wiring, public;

ALTER TABLE social_wiring.pipeline_stages DROP CONSTRAINT IF EXISTS pipeline_stages_papel_check;
ALTER TABLE social_wiring.pipeline_stages ADD  CONSTRAINT pipeline_stages_papel_check
  CHECK (papel IN ('proposta_aceite', 'final', 'gravacao', 'agendado', 'postado', 'cancelado'));
