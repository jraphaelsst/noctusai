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
