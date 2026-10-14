-- 264 -- imovel_dados: characteristics a price evaluation needs (NBR 14653 /
-- IBAPE-SP homogenization), authored by brokers on the imóvel.
--
-- WHY: Vista has no building-standard field and `area_terreno` is filled on
-- ~11 of 1982 imóveis (`frente` on none), so the evaluator's inputs must be
-- OURS. These are PHYSICAL attributes of the property (not legal/cartório
-- data) so they stay per-imóvel and do NOT follow the manual<->Vista
-- `legal_efetivo` link. `area_*_m2` are authored overrides — the Vista mirror
-- is never written.
--
-- padrao_construtivo   IBAPE-SP building standard scale.
-- estado_conservacao   Ross-Heidecke conservation scale used with IBAPE.
-- topografia/posicao_lote/testada_m/profundidade_m   lot factors (optional).
--
-- Forward-only + idempotent; every column nullable (no value known = NULL).

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS padrao_construtivo TEXT,
    ADD COLUMN IF NOT EXISTS estado_conservacao TEXT,
    ADD COLUMN IF NOT EXISTS area_terreno_m2 NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS area_construida_m2 NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS testada_m NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS profundidade_m NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS topografia TEXT,
    ADD COLUMN IF NOT EXISTS posicao_lote TEXT,
    ADD COLUMN IF NOT EXISTS avaliacao_campos_atualizado_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS avaliacao_campos_atualizado_por UUID;

DO $chk$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
      WHERE conname = 'imovel_dados_padrao_construtivo_check'
        AND conrelid = 'social_wiring.imovel_dados'::regclass) THEN
    ALTER TABLE social_wiring.imovel_dados
      ADD CONSTRAINT imovel_dados_padrao_construtivo_check
      CHECK (padrao_construtivo IS NULL OR padrao_construtivo IN (
        'simples', 'medio', 'superior', 'fino', 'luxo'));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint
      WHERE conname = 'imovel_dados_estado_conservacao_check'
        AND conrelid = 'social_wiring.imovel_dados'::regclass) THEN
    ALTER TABLE social_wiring.imovel_dados
      ADD CONSTRAINT imovel_dados_estado_conservacao_check
      CHECK (estado_conservacao IS NULL OR estado_conservacao IN (
        'novo', 'entre_novo_e_regular', 'regular', 'reparos_simples',
        'reparos_importantes', 'sem_valor'));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint
      WHERE conname = 'imovel_dados_topografia_check'
        AND conrelid = 'social_wiring.imovel_dados'::regclass) THEN
    ALTER TABLE social_wiring.imovel_dados
      ADD CONSTRAINT imovel_dados_topografia_check
      CHECK (topografia IS NULL OR topografia IN (
        'plano', 'aclive_leve', 'aclive_acentuado', 'declive_leve',
        'declive_acentuado', 'irregular'));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint
      WHERE conname = 'imovel_dados_posicao_lote_check'
        AND conrelid = 'social_wiring.imovel_dados'::regclass) THEN
    ALTER TABLE social_wiring.imovel_dados
      ADD CONSTRAINT imovel_dados_posicao_lote_check
      CHECK (posicao_lote IS NULL OR posicao_lote IN (
        'meio_quadra', 'esquina', 'multiplas_frentes'));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint
      WHERE conname = 'imovel_dados_avaliacao_medidas_check'
        AND conrelid = 'social_wiring.imovel_dados'::regclass) THEN
    ALTER TABLE social_wiring.imovel_dados
      ADD CONSTRAINT imovel_dados_avaliacao_medidas_check
      CHECK ((area_terreno_m2 IS NULL OR area_terreno_m2 > 0)
         AND (area_construida_m2 IS NULL OR area_construida_m2 > 0)
         AND (testada_m IS NULL OR testada_m > 0)
         AND (profundidade_m IS NULL OR profundidade_m > 0));
  END IF;
END
$chk$;

COMMENT ON COLUMN social_wiring.imovel_dados.padrao_construtivo IS
    'IBAPE-SP building standard: simples|medio|superior|fino|luxo.';
COMMENT ON COLUMN social_wiring.imovel_dados.estado_conservacao IS
    'Ross-Heidecke conservation state (IBAPE): novo..sem_valor.';
-- RLS: inherited from imovel_dados (075) — org-scoped SELECT, service_role writes.
