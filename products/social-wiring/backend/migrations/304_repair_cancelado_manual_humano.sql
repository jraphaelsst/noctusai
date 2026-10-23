-- ============================================================================
-- Migration 304 -- social_wiring: repair human-filled manual resultados that
-- `cancelar_processamento` flipped to erro / "Cancelado manualmente"
--
-- Before the fix, cancelling a manual consulta reset EVERY pendente resultado
-- to `erro`, including cells a human had filled (resultado marked by hand,
-- numero/emitida_em typed, a confirmado_por, an uploaded file). Their pre-cancel
-- status was `pendente` (nothing ever moves a hand-filled cell). This restores
-- exactly those rows and nothing else:
--   * the consulta is manual and not soft-deleted,
--   * the resultado is not soft-deleted, status='erro' AND erro_mensagem is the
--     exact cancel text,
--   * the resultado carries human/read evidence (an EMPTY cancelled placeholder
--     is left alone -- readers already skip it and garantir_celula revives it).
-- Nothing is recomputed (consulta status/concluidas untouched).
-- FORWARD-ONLY, IDEMPOTENT: after the first run no row matches the WHERE.
-- ============================================================================
SET search_path = social_wiring, public;

UPDATE social_wiring.certidao_resultados r
SET status = 'pendente',
    erro_mensagem = NULL
FROM social_wiring.certidao_consultas c
WHERE c.id = r.consulta_id
  AND c.origem = 'manual'
  AND c.excluida_em IS NULL
  AND r.excluida_em IS NULL
  AND r.status = 'erro'
  AND r.erro_mensagem = 'Cancelado manualmente pelo usuário.'
  AND (
        r.arquivo_url IS NOT NULL
     OR r.numero IS NOT NULL
     OR r.resultado IS NOT NULL
     OR r.confirmado_por IS NOT NULL
     OR r.resultado_origem IS NOT NULL
     OR r.emitida_em IS NOT NULL
  );
