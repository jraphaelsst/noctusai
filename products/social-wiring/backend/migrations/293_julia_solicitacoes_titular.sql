-- ============================================================================
-- Migration 293 -- social_wiring: data-subject requests are RECORDED for a human (owner decision 2026-10-21)
-- ============================================================================
-- WHY
-- ---
-- Julia runs on a public number. A lead's WhatsApp message must never delete anything or trigger any other destructive
-- action. Owner (2026-10-21): "leads cant ask for their data deletion nor any other type of destructive actions."
-- No keyword creates anything either (it fired on transcribed audio / image text and on "nao vou apagar os dados"): JULIA
-- (the model) registers a data-subject request through her tool `registrar_solicitacao_titular`, which calls
-- POST /api/julia/ferramentas/solicitacao-titular. An org admin decides it; an erasure is the admin's act through the
-- existing operator "apagar-dados" flow, never automatic.
--
-- WHAT
--   1. julia_solicitacoes_titular: one row per request (LGPD art. 18 type, a <=500-char excerpt of what the lead said,
--      received_at, the legal deadline prazo_em = received_at + 15 days, status, who decided / when / why) + whether the
--      admins' in-app notice reached them (a failed notice is RECORDED, never swallowed). Backend-only (service role),
--      like every julia_* table (migration 289).
--   2. status_pagina: the "Opt-outs" page (julia_opt_outs), copying the status of julia_leads (as 252/259/273).
--
-- FORWARD-ONLY, IDEMPOTENT. NO SECURITY DEFINER function. The tech-lead applies it with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.julia_contatos') IS NULL OR to_regclass('social_wiring.status_pagina') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.julia_contatos + status_pagina -- apply the earlier migrations first';
  END IF;
END
$guard$;

CREATE TABLE IF NOT EXISTS social_wiring.julia_solicitacoes_titular (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             uuid        NOT NULL,
    connection_id      uuid,
    contato_id         uuid        NOT NULL,
    chat_id            text,
    tipo               text        NOT NULL
                       CHECK (tipo IN ('confirmacao', 'acesso', 'correcao', 'eliminacao', 'portabilidade',
                                       'revogacao_consentimento', 'oposicao', 'info_compartilhamento', 'outro')),
    trecho_lead        text        NOT NULL CHECK (char_length(trecho_lead) <= 500),
    recebida_em        timestamptz NOT NULL DEFAULT now(),
    prazo_em           timestamptz NOT NULL,
    status             text        NOT NULL DEFAULT 'aberta'
                       CHECK (status IN ('aberta', 'em_analise', 'atendida', 'negada', 'cancelada')),
    decidido_por       uuid,
    decidido_em        timestamptz,
    motivo_decisao     text,
    notificacao_status text        NOT NULL DEFAULT 'pendente'
                       CHECK (notificacao_status IN ('pendente', 'enviada', 'falhou')),
    notificacao_erro   text,
    notificado_em      timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS julia_solicitacoes_titular_org_idx
    ON social_wiring.julia_solicitacoes_titular (org_id, status, prazo_em);

COMMENT ON TABLE social_wiring.julia_solicitacoes_titular IS
    'Data-subject requests (LGPD) a lead made, registered by Julia through her tool and DECIDED by an org admin (migration 293). '
    'prazo_em = recebida_em + 15 days. Nothing is deleted because of a lead message. Backend-only.';

ALTER TABLE social_wiring.julia_solicitacoes_titular ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "julia_solicitacoes_titular_service_role" ON social_wiring.julia_solicitacoes_titular;
CREATE POLICY "julia_solicitacoes_titular_service_role" ON social_wiring.julia_solicitacoes_titular
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.julia_solicitacoes_titular FROM anon, authenticated;

-- status_pagina: Julia > Opt-outs (copies julia_leads, like 252/259/273)
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES ('julia_opt_outs', 'Julia — Opt-outs')) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'julia_leads'
ON CONFLICT (nome_pagina) DO NOTHING;
