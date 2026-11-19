-- ============================================================================
-- Migration 364 · social_wiring: CoreStudio criação pipeline, M-C -- cs_post_eventos admits the criação event names
-- ============================================================================
-- WHY: criacao-pipeline-contract.md section 2.2. The post event ledger (342, widened by 353) gains the intent-named events
-- of the roteiro loop (opcoes_geradas, opcoes_selecionadas, contraparte_gerada, refinamento_pedido, headline_aprovada,
-- roteiro_aprovado, publicacao_gerada), the criação steps (criacao_enfileirada, passo_iniciado, passo_concluido,
-- passo_falhou, criacao_concluida), the final approval (midia_aprovada, midia_reprovada), the opt-in transcription check
-- (verificacao_transcricao_pedida / _concluida -- never gates a move), the system mover (card_movido_automaticamente) and
-- the quota (cota_alterada, cota_excedida). EVERY existing name stays (353's list is the base).
-- WIDENING a CHECK only: every existing row still satisfies it, so the previous image keeps working. The table stays
-- append-only (342's guard is untouched). cota_alterada is also written, org-level, by 366's own ledger (an org-level
-- event has no post_id); it is admitted here so the vocabulary is one list. FORWARD-ONLY, IDEMPOTENT. Requires 353.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.cs_post_eventos DROP CONSTRAINT IF EXISTS cs_post_eventos_tipo_check;
ALTER TABLE social_wiring.cs_post_eventos ADD CONSTRAINT cs_post_eventos_tipo_check CHECK (tipo IN (
    -- 342 / 353 (unchanged)
    'midia_versao_criada', 'midia_status_alterado', 'insumos_apagados',
    'publicacao_agendada', 'publicacao_reagendada', 'publicado', 'publicacao_falhou', 'publicacao_cancelada',
    -- roteiro loop
    'opcoes_geradas', 'opcoes_selecionadas', 'contraparte_gerada', 'refinamento_pedido',
    'headline_aprovada', 'roteiro_aprovado', 'publicacao_gerada',
    -- criação
    'criacao_enfileirada', 'passo_iniciado', 'passo_concluido', 'passo_falhou', 'criacao_concluida',
    -- final approval
    'midia_aprovada', 'midia_reprovada',
    -- opt-in only
    'verificacao_transcricao_pedida', 'verificacao_transcricao_concluida',
    -- system moves + quota
    'card_movido_automaticamente', 'cota_alterada', 'cota_excedida')) NOT VALID;
ALTER TABLE social_wiring.cs_post_eventos VALIDATE CONSTRAINT cs_post_eventos_tipo_check;
