-- ============================================================================
-- Migration 022 -- Assistant: the owner's CONVERSATIONS (seed inbox tables) + the "Conversas" nav page
--
-- Owner decision 2026-11-12: the personal line's conversations are kept (both directions, 1:1) so the owner can read
-- and answer them in the app AND so the assistant can be evaluated over time. This REVERSES, for the owner's own line,
-- the migration-015 stance of "no chat log": 015's intake queue (HMAC'd chat_ref, no raw phone, 90-day body retention)
-- is UNTOUCHED and keeps feeding the classifier; these two tables are a separate consumer of the same webhook event.
--
-- `whatsapp_chats` / `whatsapp_messages` are the seed's authoring-time DDL (`whatsapp_chats_table_ddl`,
-- `whatsapp_messages_table_ddl`, schema=assistant) with ONE deliberate change: NO browser SELECT policy and NO browser
-- grant. The seed ships an org-member read policy; here the rows are third-party personal messages of the owner's
-- private line, so the only reader is the backend (service role), and every route that reads them is admin-gated.
--
-- LGPD: `body`, `name`, `phone`, `sender_*` are personal data of third parties. Retention: kept for as long as the
-- connection exists (evaluation over time); deleting the connection cascades (FK ON DELETE CASCADE). See
-- LGPD-WARNINGS.md (assistant entry).
-- Forward-only + idempotent (re-apply safe). NOT applied by the slice that authored it -- the tech-lead applies it.
-- ============================================================================

SET search_path = assistant, public;

CREATE TABLE IF NOT EXISTS assistant.whatsapp_chats (
    connection_id UUID NOT NULL REFERENCES assistant.whatsapp_connections(id) ON DELETE CASCADE,
    chat_id TEXT NOT NULL,
    org_id UUID NOT NULL,
    name TEXT,
    phone TEXT,
    is_group BOOLEAN NOT NULL DEFAULT false,
    origin TEXT NOT NULL DEFAULT 'inbound'
        CHECK (origin IN ('inbound', 'outbound', 'backfill')),
    new_chat_notified_at TIMESTAMPTZ,
    last_message_at TIMESTAMPTZ,
    last_message_preview TEXT NOT NULL DEFAULT '',
    last_message_from_me BOOLEAN,
    unread_count INTEGER NOT NULL DEFAULT 0,
    last_read_at TIMESTAMPTZ,
    synced_through TIMESTAMPTZ,
    -- per-chat agent pause (seed whatsapp_chats_table_ddl(with_agent_pause=True)): the live agent stops answering this chat
    agent_paused BOOLEAN NOT NULL DEFAULT false,
    agent_paused_at TIMESTAMPTZ,
    agent_paused_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (connection_id, chat_id)
);

ALTER TABLE assistant.whatsapp_chats ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.whatsapp_chats;
CREATE POLICY "service_role_bypass" ON assistant.whatsapp_chats FOR ALL TO service_role USING (true) WITH CHECK (true);

-- THE chat-list query: newest activity first, chat_id as the keyset tiebreak.
CREATE INDEX IF NOT EXISTS idx_assistant_whatsapp_chats_list
    ON assistant.whatsapp_chats (connection_id, last_message_at DESC, chat_id DESC);

CREATE OR REPLACE TRIGGER set_updated_at_whatsapp_chats
    BEFORE UPDATE ON assistant.whatsapp_chats
    FOR EACH ROW EXECUTE FUNCTION assistant.set_updated_at();

COMMENT ON TABLE assistant.whatsapp_chats IS 'tier:org';
REVOKE ALL ON assistant.whatsapp_chats FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.whatsapp_chats TO service_role;

CREATE TABLE IF NOT EXISTS assistant.whatsapp_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    connection_id UUID NOT NULL,
    chat_id TEXT NOT NULL,
    waha_message_id TEXT NOT NULL,
    from_me BOOLEAN NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT 'chat',
    media_url TEXT,
    media_mimetype TEXT,
    ack SMALLINT,
    acked_at TIMESTAMPTZ,
    sender_name TEXT,
    sender_phone TEXT,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (connection_id, chat_id)
        REFERENCES assistant.whatsapp_chats(connection_id, chat_id) ON DELETE CASCADE,
    UNIQUE (connection_id, waha_message_id)
);

ALTER TABLE assistant.whatsapp_messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.whatsapp_messages;
CREATE POLICY "service_role_bypass" ON assistant.whatsapp_messages FOR ALL TO service_role USING (true) WITH CHECK (true);

-- THE thread query (and the unread recount).
CREATE INDEX IF NOT EXISTS idx_assistant_whatsapp_messages_thread
    ON assistant.whatsapp_messages (connection_id, chat_id, timestamp DESC, waha_message_id DESC);

COMMENT ON TABLE assistant.whatsapp_messages IS 'tier:org';
REVOKE ALL ON assistant.whatsapp_messages FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.whatsapp_messages TO service_role;

-- status_pagina -- the "Conversas" nav page (`/conversas`). Every nav-listed route needs a matching row, or
-- `filterNavByPageStatus` hides it from EVERYONE (KB § PATTERNS/frontend/status-pagina-dev-visibility.md).
INSERT INTO assistant.status_pagina (nome_pagina, status) VALUES
    ('conversas', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;

-- ----- Per-chat LGPD erasure of the assistant's OWN derived data (the chat + its messages are erased by the seed organ) -----
-- A contact's chat is identified in the intake by its keyed HMAC (`chat_ref`, computed server-side). One transaction
-- removes every row derived from that chat's intake rows: the reply events, the intake events (append-only tables:
-- the single `assistant.retention_purge` carve-out is set LOCAL to this transaction), the classifier verdicts
-- (ai_outputs), its jobs, then the intake rows. ai_feedback_events (the owner's labels: ids + a label, no chat data) is
-- append-only with no carve-out and keeps only opaque ids. Returns the number of intake rows erased.
CREATE OR REPLACE FUNCTION assistant.apagar_dados_conversa(p_org_id uuid, p_connection_id uuid, p_chat_ref text)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$
DECLARE
    v_ids uuid[];
    v_n integer;
BEGIN
    SELECT coalesce(array_agg(id), '{}') INTO v_ids FROM assistant.intake_messages
     WHERE org_id = p_org_id AND connection_id = p_connection_id AND chat_ref = p_chat_ref;
    IF coalesce(array_length(v_ids, 1), 0) = 0 THEN
        RETURN 0;
    END IF;
    PERFORM set_config('assistant.retention_purge', 'on', true);
    DELETE FROM assistant.respostas_eventos WHERE intake_id = ANY (v_ids);
    DELETE FROM assistant.intake_messages_eventos WHERE entidade_id = ANY (v_ids);
    DELETE FROM assistant.ai_outputs WHERE ref_type = 'intake_message' AND ref_id = ANY (v_ids);
    DELETE FROM assistant.jobs WHERE (payload ->> 'intake_id')::text = ANY (SELECT unnest(v_ids)::text);
    DELETE FROM assistant.intake_messages WHERE id = ANY (v_ids);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    PERFORM set_config('assistant.retention_purge', 'off', true);
    RETURN v_n;
END;
$$;
REVOKE ALL ON FUNCTION assistant.apagar_dados_conversa(uuid, uuid, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.apagar_dados_conversa(uuid, uuid, text) TO service_role;
