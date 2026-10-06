-- Migration: termos_sinal_primeira_parcela
-- Schema: social_wiring

SET search_path = social_wiring, public;

-- ============================================================
-- "Sinal always as Parcela 01" — DEFAULT ON, adjustable per deal
-- (owner, 2026-10-05: "yes, by default, adjustable").
--
-- `contrato_gerador.derivacao.parcelas_ordenadas` hoists the first sinal run
-- to the front of the persisted `ordem` (all signed contracts print the sinal
-- as Parcela 01). With this flag FALSE the generator follows `ordem` exactly.
-- Additive + idempotent: existing rows take the default (TRUE) = today's
-- behaviour, so no contract changes until an operator turns it off.
-- ============================================================
ALTER TABLE social_wiring.atendimento_negociacao_termos
    ADD COLUMN IF NOT EXISTS sinal_primeira_parcela BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN social_wiring.atendimento_negociacao_termos.sinal_primeira_parcela IS
    'TRUE (default): the contract prints the sinal as Parcela 01 even when '
    'the operator ordered it later. FALSE: parcelas follow `ordem` exactly. '
    'Migration 206.';
