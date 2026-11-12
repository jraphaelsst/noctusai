-- ============================================================================
-- Migration 021 -- Assistant: the live-reply attempt log (append-only, one event per inbound message)
--
-- The Assistant now ANSWERS an admitted inbound 1:1 text through the owner's agent hosted in `agents`. Every reply
-- attempt lands as ONE immutable, intent-named event; the event type IS the outcome (a closed CHECK enum):
--   enviada | enviada_parcial | recusada_lista | agente_desligado | controle_indisponivel | sem_atendimento |
--   erro_turno | erro_envio | mensagem_antiga
-- `UNIQUE (intake_id)`: one attempt per intake row, so a replayed webhook / a second worker can never answer twice
-- (the writer answers NO row on a repeat = "already attempted").
--
-- LGPD: the contact is the intake row (its `chat_ref` is a keyed HMAC); this table stores NO phone number, NO message
-- text and NO reply text -- `motivo` is a reason code, `dados` holds counts / status words only.
-- Access: service role only (tier:service); no browser grant, no browser policy; INSERT-only (guard trigger refuses
-- UPDATE/DELETE, with the single `assistant.retention_purge` carve-out the intake events already have).
-- Forward-only + idempotent (re-apply safe).
-- ============================================================================
SET search_path = assistant, public;

CREATE TABLE IF NOT EXISTS assistant.respostas_eventos (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL,
    connection_id uuid NOT NULL REFERENCES assistant.whatsapp_connections(id) ON DELETE RESTRICT,
    intake_id     uuid NOT NULL REFERENCES assistant.intake_messages(id) ON DELETE RESTRICT,
    event_type    text NOT NULL CHECK (event_type IN (
        'enviada', 'enviada_parcial', 'recusada_lista', 'agente_desligado', 'controle_indisponivel',
        'sem_atendimento', 'erro_turno', 'erro_envio', 'mensagem_antiga'
    )),
    motivo        text,                                   -- reason code (agents status word / exception class), never text
    dados         jsonb NOT NULL DEFAULT '{}'::jsonb,     -- counts only (bubbles, parts), never a phone / a body
    actor_kind    text NOT NULL DEFAULT 'agent' CHECK (actor_kind IN ('user', 'agent', 'system', 'integration')),
    occurred_at   timestamptz NOT NULL DEFAULT now(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (intake_id)
);
CREATE INDEX IF NOT EXISTS idx_assistant_respostas_eventos_conn ON assistant.respostas_eventos (connection_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_assistant_respostas_eventos_tipo ON assistant.respostas_eventos (event_type, occurred_at DESC);

ALTER TABLE assistant.respostas_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS service_role_select ON assistant.respostas_eventos;
CREATE POLICY service_role_select ON assistant.respostas_eventos FOR SELECT TO service_role USING (true);
DROP POLICY IF EXISTS service_role_insert ON assistant.respostas_eventos;
CREATE POLICY service_role_insert ON assistant.respostas_eventos FOR INSERT TO service_role WITH CHECK (true);
REVOKE ALL ON assistant.respostas_eventos FROM PUBLIC, anon, authenticated;
REVOKE UPDATE, DELETE, TRUNCATE ON assistant.respostas_eventos FROM service_role;
GRANT SELECT, INSERT ON assistant.respostas_eventos TO service_role;
COMMENT ON TABLE assistant.respostas_eventos IS 'tier:service';

-- ----- GUC carve-out guard: assistant.respostas_eventos (flag assistant.retention_purge) -----
-- guc-carveout-guard: rendered by noctusai_lib.domain.sql_templates.guc_carveout_guard_sql
CREATE OR REPLACE FUNCTION assistant.guard_respostas_eventos_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('assistant.retention_purge', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'append_only' USING ERRCODE = 'P0001';
END;
$$;

REVOKE ALL ON FUNCTION assistant.guard_respostas_eventos_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.guard_respostas_eventos_append_only() TO service_role;

DROP TRIGGER IF EXISTS guard_respostas_eventos_append_only ON assistant.respostas_eventos;
CREATE TRIGGER guard_respostas_eventos_append_only
    BEFORE UPDATE OR DELETE ON assistant.respostas_eventos
    FOR EACH ROW EXECUTE FUNCTION assistant.guard_respostas_eventos_append_only();

-- registrar_resposta: the ONLY writer. Resolves the intake row by (connection, WAHA message id) and appends the
-- attempt's event; a repeat answers no row (already attempted). `p_event_type` outside the enum is the CHECK's error.
CREATE OR REPLACE FUNCTION assistant.registrar_resposta(
    p_org_id uuid, p_connection_id uuid, p_waha_message_id text, p_event_type text, p_motivo text, p_dados jsonb
) RETURNS TABLE (id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$
DECLARE
    v_intake uuid;
    v_id uuid;
BEGIN
    SELECT m.id INTO v_intake FROM assistant.intake_messages m
     WHERE m.connection_id = p_connection_id AND m.org_id = p_org_id AND m.waha_message_id = p_waha_message_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown intake row' USING ERRCODE = 'P0002';
    END IF;

    INSERT INTO assistant.respostas_eventos (org_id, connection_id, intake_id, event_type, motivo, dados)
    VALUES (p_org_id, p_connection_id, v_intake, p_event_type, p_motivo, coalesce(p_dados, '{}'::jsonb))
    ON CONFLICT (intake_id) DO NOTHING
    RETURNING respostas_eventos.id INTO v_id;

    IF v_id IS NULL THEN
        RETURN;  -- already attempted: nothing written
    END IF;
    id := v_id;
    RETURN NEXT;
END;
$$;
REVOKE ALL ON FUNCTION assistant.registrar_resposta(uuid, uuid, text, text, text, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.registrar_resposta(uuid, uuid, text, text, text, jsonb) TO service_role;
