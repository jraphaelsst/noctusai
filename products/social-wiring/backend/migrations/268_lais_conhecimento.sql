-- ============================================================================
-- Migration 268 -- social_wiring: Lais "Conhecimento" (Meu negocio, perfil, IPTU, recesso)
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md section 3 (wave 1).
-- One row per (org, secao): `dados` is the section's JSON (validated per section by pydantic in
-- the service, extra=forbid), `versao` is the optimistic-lock counter. The rendered knowledge is
-- the `conhecimento` contexto provider; saving changes the next turn's `contexto.hash`.
--
-- RLS: ENABLE + `select_own_org` + `service_role` (pattern 255 / 258 / 267); writes go through the
-- backend service client only. status_pagina row `lais_conhecimento` copies `whatsapp_chat`
-- (pattern 259).
--
-- FORWARD-ONLY, IDEMPOTENT. PREREQUISITES: 014 (status_pagina), core 070 (current_org_id_for).
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'whatsapp_chat') THEN
    RAISE EXCEPTION 'Migration 268 requires the whatsapp_chat status row (migration 014) -- apply 014 first';
  END IF;
END
$guard$;

CREATE TABLE IF NOT EXISTS social_wiring.lais_conhecimento_secoes (
    org_id      uuid        NOT NULL,
    secao       text        NOT NULL,
    dados       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    versao      integer     NOT NULL DEFAULT 1,
    updated_by  uuid,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, secao),
    CONSTRAINT lais_conhecimento_secao_valida CHECK (secao IN (
        'politicas', 'telefones', 'exibir_atendente', 'recesso', 'venda_info', 'venda_documentos',
        'venda_financiamento', 'locacao_info', 'locacao_documentos', 'locacao_processo',
        'locacao_garantias', 'perfil_whatsapp', 'endereco_iptu'))
);

COMMENT ON TABLE social_wiring.lais_conhecimento_secoes IS
    'Lais knowledge sections per org (migration 268, contract section 3). dados = per-section JSON '
    '(pydantic extra=forbid in lais_conhecimento_service); versao = optimistic lock.';

ALTER TABLE social_wiring.lais_conhecimento_secoes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_conhecimento_secoes_select_own_org" ON social_wiring.lais_conhecimento_secoes;
CREATE POLICY "lais_conhecimento_secoes_select_own_org" ON social_wiring.lais_conhecimento_secoes
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "lais_conhecimento_secoes_service_role" ON social_wiring.lais_conhecimento_secoes;
CREATE POLICY "lais_conhecimento_secoes_service_role" ON social_wiring.lais_conhecimento_secoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES
          ('lais_conhecimento', 'Lais — Conhecimento')
       ) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
