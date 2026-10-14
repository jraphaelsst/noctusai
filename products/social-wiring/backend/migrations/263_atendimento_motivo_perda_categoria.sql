-- 263 -- atendimentos.motivo_perda_categoria (fixed lost-deal reason list).
--
-- WHY: a deal marked lost is a data signal for the price evaluator (a deal
-- lost for "preco_acima_mercado" is evidence an asking price sits above
-- market). Free text cannot be aggregated, so the reason is a closed set; the
-- free-text `motivo_perda` stays as the operator's note (required in the API
-- only when the category is 'outro').
--
-- Independent of 262's release order: `motivo_perda` is (re)declared here with
-- IF NOT EXISTS so this file applies cleanly whether or not 262 ran first.
-- Forward-only + idempotent. Legacy lost rows keep NULL (no category known).

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.atendimentos
    ADD COLUMN IF NOT EXISTS motivo_perda TEXT;

ALTER TABLE social_wiring.atendimentos
    ADD COLUMN IF NOT EXISTS motivo_perda_categoria TEXT;

DO $chk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'atendimentos_motivo_perda_categoria_check'
       AND conrelid = 'social_wiring.atendimentos'::regclass
  ) THEN
    ALTER TABLE social_wiring.atendimentos
      ADD CONSTRAINT atendimentos_motivo_perda_categoria_check
      CHECK (motivo_perda_categoria IS NULL OR motivo_perda_categoria IN (
        'preco_acima_mercado',
        'cliente_desistiu',
        'comprou_outro_imovel',
        'comprou_com_concorrente',
        'financiamento_negado',
        'documentacao_imovel',
        'proprietario_desistiu',
        'imovel_vendido_outro',
        'sem_retorno',
        'outro'
      ));
  END IF;
END
$chk$;

COMMENT ON COLUMN social_wiring.atendimentos.motivo_perda_categoria IS
    'Closed-set reason the atendimento was marked perdida '
    '(POST /atendimentos-venda/{id}/perder). NULL for open/won deals and for '
    'rows lost before this column existed.';
