-- ============================================================================
-- Migration 317 -- social_wiring: Vista-vs-ours divergence review (TRANSITIONAL; owner 2026-11-04)
-- ============================================================================
-- WHY
-- ---
-- "lets make our data count. the system recognizes divergencies from vista and warns us, so we human decide which data
-- is true. this is a mechanism we're implementing now on this transition phase and might get deleted anytime."
-- During every Vista refresh the sync compares Vista's value with OUR owned value (captação, imovel_dados manual
-- address / empreendimento, the owner's WhatsApp confirmation) and opens a PENDING `imovel_campo_conflitos` row
-- (origem_proposto = 'vista_sync') -- the EXISTING conflict machinery (154), no parallel store. Nothing is ever overwritten.
--
-- WHAT
--   1. imovel_campo_conflitos.notas JSONB : the drift note -- both values with WHEN each was set (Vista's DataAtualizacao,
--      our updated_at + who), Vista's código + links, and the ORIGIN of our value (a conversation: contato + sanitised
--      excerpt). NULL on every pre-existing row.
--   2. vista_divergencias_config : per-org switch `ativa` (the flag `divergencia_vista_ativa`) + `destino_user_id` (the org
--      USER who gets the WhatsApp digest; the phone is read from core at send time, never stored here). A missing row =
--      OFF; the One org is seeded ON.
--
-- REMOVAL (the whole mechanism): see KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md § 6c. This migration is the only DDL.
-- FORWARD-ONLY, IDEMPOTENT. NO SECURITY DEFINER function.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.imovel_campo_conflitos
    ADD COLUMN IF NOT EXISTS notas JSONB;

COMMENT ON COLUMN social_wiring.imovel_campo_conflitos.notas IS
    'Drift note of a Vista-vs-ours divergence (origem_proposto=''vista_sync'', migration 317): both values + when each was '
    'set, the Vista código and links, and the origin of our value (conversation excerpt, sanitised). NULL otherwise.';

CREATE TABLE IF NOT EXISTS social_wiring.vista_divergencias_config (
    org_id           uuid        PRIMARY KEY,
    ativa            boolean     NOT NULL DEFAULT false,
    destino_user_id  uuid,
    updated_by       uuid,
    updated_at       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.vista_divergencias_config IS
    'TRANSITIONAL (migration 317): per-org switch (divergencia_vista_ativa) + WhatsApp digest destination user of the '
    'Vista divergence review. A missing row means OFF. Delete with the mechanism. Backend-only.';

ALTER TABLE social_wiring.vista_divergencias_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS vista_divergencias_config_service_role ON social_wiring.vista_divergencias_config;
CREATE POLICY vista_divergencias_config_service_role ON social_wiring.vista_divergencias_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.vista_divergencias_config FROM PUBLIC, anon, authenticated;

-- The One org starts ON (owner 2026-11-04). Every other org stays OFF until an admin turns it on.
INSERT INTO social_wiring.vista_divergencias_config (org_id, ativa)
VALUES ('fd169d29-4d0a-4b04-9a5e-25e69407614d', true)
ON CONFLICT (org_id) DO NOTHING;
