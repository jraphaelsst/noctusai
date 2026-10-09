-- ============================================================================
-- Migration 220 · social_wiring: chat<->card link + WhatsApp document intake
-- ============================================================================
-- sw-lead-to-contract CONTRACT §2 (S2).
--
--  1. whatsapp_chats.cliente_id -- the card the conversation belongs to,
--     resolved from the chat's phone against clientes.chave_canonica (same rule
--     the inbox already uses to NAME a chat). ON DELETE SET NULL: deleting a
--     cliente never deletes the conversation.
--  2. cliente_documentos.origem_entrada ('upload' | 'whatsapp') and the
--     classifier's verdict (classificacao_*), so the operator can see how a
--     document arrived and why it sits in the triage list.
--  3. The catalogue type 'a_classificar': a document that arrived by WhatsApp
--     and could not be typed with confidence. Media is never dropped; it waits
--     here until the operator picks the real type (extraction then runs).
--     'identidade' LGPD category = the strictest class a stranger's scan can be.
--
-- No new table => no attach_acting_audit_triggers re-run needed.
-- FORWARD-ONLY, IDEMPOTENT. NOT APPLIED by the author.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.whatsapp_chats
    ADD COLUMN IF NOT EXISTS cliente_id UUID
        REFERENCES social_wiring.clientes(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_sw_whatsapp_chats_cliente
    ON social_wiring.whatsapp_chats (cliente_id)
    WHERE cliente_id IS NOT NULL;

ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS origem_entrada TEXT NOT NULL DEFAULT 'upload'
        CHECK (origem_entrada IN ('upload', 'whatsapp')),
    ADD COLUMN IF NOT EXISTS classificacao_tipo_provavel TEXT,
    ADD COLUMN IF NOT EXISTS classificacao_confianca TEXT
        CHECK (classificacao_confianca IS NULL OR classificacao_confianca IN ('alta', 'baixa', 'nenhuma')),
    ADD COLUMN IF NOT EXISTS classificado_em TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_sw_cliente_documentos_a_classificar
    ON social_wiring.cliente_documentos (cliente_id, created_at DESC)
    WHERE deleted_at IS NULL AND tipo_documento = 'a_classificar';

INSERT INTO social_wiring.cliente_documento_tipos
    (tipo_documento, categoria_lgpd, identidade, ativo, descricao)
VALUES
    ('a_classificar', 'identidade', false, true,
     'Recebido por WhatsApp, tipo ainda não identificado -- aguardando triagem')
ON CONFLICT (tipo_documento) DO NOTHING;

-- Retention policy (079) is per (superficie, tipo): inherit rg's platform row so
-- the sweep never meets a type with no policy.
INSERT INTO social_wiring.documento_retencao_politicas
    (org_id, superficie, tipo_documento, retencao_dias, motivo)
SELECT NULL, p.superficie, 'a_classificar', p.retencao_dias,
       'Herdado de rg (220): triagem de documento recebido por WhatsApp.'
FROM social_wiring.documento_retencao_politicas p
WHERE p.org_id IS NULL AND p.superficie = 'cliente' AND p.tipo_documento = 'rg'
ON CONFLICT DO NOTHING;
