-- ============================================================================
-- Migration 258 -- social_wiring: Julia (lead agent) routing on the WAHA path
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/julia-agent-contract.md
--   section 5   per-connection / per-chat routing fields
--   section 10.1 H3   `agente_leads_ativo => authorized_numbers non-empty`
--                     enforced by the DB on EVERY write (a CHECK spans both
--                     columns, so emptying the list while Julia is on is
--                     refused exactly like turning Julia on over an empty list)
--   section 11.1 chats that existed before the switch are never sent to Julia
--                     (snapshot table + `agente_leads_ativado_em`)
--   section 11.4 handoff notification target
--
-- FORWARD-ONLY, IDEMPOTENT. Do not apply by hand: the tech-lead applies it
-- with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

-- -- 1. connection: Julia switch + provenance + handoff target -----------------
ALTER TABLE social_wiring.whatsapp_connections
    ADD COLUMN IF NOT EXISTS agente_leads_ativo boolean NOT NULL DEFAULT false;
ALTER TABLE social_wiring.whatsapp_connections
    ADD COLUMN IF NOT EXISTS agente_leads_key text;
ALTER TABLE social_wiring.whatsapp_connections
    ADD COLUMN IF NOT EXISTS agente_leads_ativado_em timestamptz;
ALTER TABLE social_wiring.whatsapp_connections
    ADD COLUMN IF NOT EXISTS agente_handoff_notificar_user_id uuid;

COMMENT ON COLUMN social_wiring.whatsapp_connections.agente_leads_ativo IS
    'Julia answers contacts NOT in authorized_numbers on this line (contract 5). '
    'Requires non-empty authorized_numbers (CHECK below) and a snapshot (11.1).';
COMMENT ON COLUMN social_wiring.whatsapp_connections.agente_leads_ativado_em IS
    'When the switch was last turned on. A chat whose whatsapp_chats row is older '
    'than this is never eligible for Julia (contract 11.1 b).';
COMMENT ON COLUMN social_wiring.whatsapp_connections.agente_handoff_notificar_user_id IS
    'Who is notified on handoff. NULL = the connection owner (user_id). When set, '
    'must hold core org role owner/admin: checked by the API and re-checked at '
    'send time (contract 11.4).';

-- -- 2. chat: per-chat pause + the agents-side conversation id -----------------
ALTER TABLE social_wiring.whatsapp_chats
    ADD COLUMN IF NOT EXISTS agente_pausado boolean NOT NULL DEFAULT false;
ALTER TABLE social_wiring.whatsapp_chats
    ADD COLUMN IF NOT EXISTS agente_conversation_id uuid;

COMMENT ON COLUMN social_wiring.whatsapp_chats.agente_pausado IS
    'A human is handling this chat: Julia stays silent (handoff, manual toggle, '
    'or the owner typing from the phone; contract 5 / 10.1 L3).';
COMMENT ON COLUMN social_wiring.whatsapp_chats.agente_conversation_id IS
    'agents.conversations id once Julia owns the chat. Also the marker that the '
    'privacy disclosure bubble was already sent (contract 11.3).';

-- -- 3. snapshot of chats that existed when Julia was switched on (11.1) --------
CREATE TABLE IF NOT EXISTS social_wiring.lais_agente_chats_preexistentes (
    org_id         uuid NOT NULL,
    connection_id  uuid NOT NULL,
    chat_id        text NOT NULL,
    capturado_em   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (connection_id, chat_id)
);

COMMENT ON TABLE social_wiring.lais_agente_chats_preexistentes IS
    'Chats of the WAHA session that already existed when Julia was switched on '
    '(both the phone and the @lid form when WAHA exposes both). They are never '
    'sent to Julia (migration 258, contract 11.1).';

CREATE INDEX IF NOT EXISTS idx_lais_agente_preexistentes_org
    ON social_wiring.lais_agente_chats_preexistentes (org_id);

ALTER TABLE social_wiring.lais_agente_chats_preexistentes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_agente_preexistentes_select_own_org"
    ON social_wiring.lais_agente_chats_preexistentes;
CREATE POLICY "lais_agente_preexistentes_select_own_org"
    ON social_wiring.lais_agente_chats_preexistentes
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "lais_agente_preexistentes_service_role"
    ON social_wiring.lais_agente_chats_preexistentes;
CREATE POLICY "lais_agente_preexistentes_service_role"
    ON social_wiring.lais_agente_chats_preexistentes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- -- 4. the invariants the routing code relies on, enforced by the DB -----------
-- H3: `agente_leads_ativo => authorized_numbers non-empty`, on every write.
-- authorized_numbers is jsonb NOT NULL DEFAULT '[]' (migration 016).
ALTER TABLE social_wiring.whatsapp_connections
    DROP CONSTRAINT IF EXISTS whatsapp_connections_agente_exige_autorizados;
ALTER TABLE social_wiring.whatsapp_connections
    ADD CONSTRAINT whatsapp_connections_agente_exige_autorizados
    CHECK (
        NOT agente_leads_ativo
        OR (
            jsonb_typeof(authorized_numbers) = 'array'
            AND jsonb_array_length(authorized_numbers) > 0
        )
    );

ALTER TABLE social_wiring.whatsapp_connections
    DROP CONSTRAINT IF EXISTS whatsapp_connections_agente_exige_ativado_em;
ALTER TABLE social_wiring.whatsapp_connections
    ADD CONSTRAINT whatsapp_connections_agente_exige_ativado_em
    CHECK (
        NOT agente_leads_ativo
        OR (agente_leads_ativado_em IS NOT NULL AND agente_leads_key IS NOT NULL)
    );

