-- ============================================================================
-- Migration 278 -- social_wiring: Lais wave 8 "Captacao" (potential property captures)
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md section 10 (wave 8).
--   lais_captacoes  one row per "A Julia identificou uma potencial captacao de imovel": the owner of
--                   a property talked to the agent. `status`: nova -> registrada (a manual imovel was
--                   created through the existing `imovel_captacao` flow, migration 226; `imovel_id`
--                   holds its canonical codigo, `imovel_codigo` the display codigo the SW imovel page /imoveis/:codigo routes by) | descartada. A registrada row ALWAYS names its imovel.
--   status_pagina   `lais_captacao` (copies whatsapp_chat, like 259/270).
--
-- RLS: select_own_org + service_role (writes through the backend only), pattern 267/270.
-- NO SECURITY DEFINER function in this file. FORWARD-ONLY, IDEMPOTENT.
-- PREREQUISITES: core 070, 014 (status_pagina), 267 (lais_contatos). Applied by the tech-lead with
-- noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regclass('social_wiring.lais_contatos') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.lais_contatos (migration 267) -- apply 267 first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'whatsapp_chat') THEN
    RAISE EXCEPTION 'this migration requires the whatsapp_chat status row (migration 014) -- apply 014 first';
  END IF;
END
$guard$;

CREATE TABLE IF NOT EXISTS social_wiring.lais_captacoes (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid        NOT NULL,
    contato_id uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    descricao  text,
    endereco   text,
    operacao   text,
    status     text        NOT NULL DEFAULT 'nova',
    imovel_id  text,
    imovel_codigo text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_captacoes_status_valido CHECK (status IN ('nova', 'registrada', 'descartada')),
    CONSTRAINT lais_captacoes_operacao_valida CHECK (operacao IS NULL OR operacao IN ('venda', 'aluguel')),
    CONSTRAINT lais_captacoes_registrada_exige_imovel CHECK (status <> 'registrada' OR imovel_id IS NOT NULL)
);

COMMENT ON TABLE social_wiring.lais_captacoes IS
    'Lais > Captacao feed (migration 278, contract 10): one potential property capture per row; '
    'registrada rows carry the codigo of the imovel_captacao imovel they produced.';

CREATE INDEX IF NOT EXISTS idx_lais_captacoes_feed
    ON social_wiring.lais_captacoes (org_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lais_captacoes_contato
    ON social_wiring.lais_captacoes (contato_id);

ALTER TABLE social_wiring.lais_captacoes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_captacoes_select_own_org" ON social_wiring.lais_captacoes;
CREATE POLICY "lais_captacoes_select_own_org" ON social_wiring.lais_captacoes
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_captacoes_service_role" ON social_wiring.lais_captacoes;
CREATE POLICY "lais_captacoes_service_role" ON social_wiring.lais_captacoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT 'lais_captacao', origem.status, 'Lais — Captação'
  FROM social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
