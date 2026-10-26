-- ============================================================================
-- Migration 015 -- WhatsApp: connections (QR, WAHA lines) + inbox (chats, messages)
--
-- Monica's conversations. The three tables are the VERBATIM output of the seed's authoring-time DDL helpers
-- (`whatsapp_connections_table_ddl`, `whatsapp_chats_table_ddl`, `whatsapp_messages_table_ddl`, schema=monica),
-- with the policy helper pointed at the org-picker aware `public.current_org_id_for('monica')` (migration 007).
-- Browser roles may only READ their org's rows (SELECT policy); every write goes through the backend with the
-- service role (webhook ingest, send, mark-read, connection lifecycle).
--
-- LGPD: `whatsapp_messages.body` / `whatsapp_chats.*` hold health-adjacent personal data (psychoanalysis clinic).
-- Retention + erasure: LGPD-WARNINGS.md (monica entry) and KB PATTERNS/security/lgpd.md.
-- Prerequisites: `public.current_org_id_for(text)` (core 070 -- also required by 007).
-- Forward-only + idempotent (re-apply safe). NOT applied by the slice that authored it -- the tech-lead applies it (migrate_product).
-- ============================================================================

SET search_path = monica, public;

CREATE OR REPLACE FUNCTION monica.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = monica, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;
REVOKE ALL ON FUNCTION monica.set_updated_at() FROM PUBLIC, anon, authenticated;

CREATE TABLE IF NOT EXISTS monica.whatsapp_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    user_id UUID NOT NULL,
    label TEXT NOT NULL,
    base_url TEXT NOT NULL,
    session_name TEXT NOT NULL DEFAULT 'default',
    encrypted_api_key TEXT NOT NULL,
    webhook_url TEXT,
    webhook_token TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, label)
);

ALTER TABLE monica.whatsapp_connections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "whatsapp_connections_select_own_org" ON monica.whatsapp_connections;
CREATE POLICY "whatsapp_connections_select_own_org" ON monica.whatsapp_connections FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('monica')));

DROP POLICY IF EXISTS "service_role_bypass" ON monica.whatsapp_connections;
CREATE POLICY "service_role_bypass" ON monica.whatsapp_connections FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_monica_whatsapp_connections_org ON monica.whatsapp_connections(org_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_monica_whatsapp_connections_webhook_token ON monica.whatsapp_connections(webhook_token);
CREATE TABLE IF NOT EXISTS monica.whatsapp_chats (
    connection_id UUID NOT NULL REFERENCES monica.whatsapp_connections(id) ON DELETE CASCADE,
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

ALTER TABLE monica.whatsapp_chats ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "whatsapp_chats_select_own_org" ON monica.whatsapp_chats;
CREATE POLICY "whatsapp_chats_select_own_org" ON monica.whatsapp_chats FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('monica')));

DROP POLICY IF EXISTS "service_role_bypass" ON monica.whatsapp_chats;
CREATE POLICY "service_role_bypass" ON monica.whatsapp_chats FOR ALL TO service_role USING (true) WITH CHECK (true);

-- THE chat-list query: newest activity first, chat_id as the keyset tiebreak.
CREATE INDEX IF NOT EXISTS idx_monica_whatsapp_chats_list
    ON monica.whatsapp_chats (connection_id, last_message_at DESC, chat_id DESC);

CREATE OR REPLACE TRIGGER set_updated_at_whatsapp_chats
    BEFORE UPDATE ON monica.whatsapp_chats
    FOR EACH ROW EXECUTE FUNCTION monica.set_updated_at();
CREATE TABLE IF NOT EXISTS monica.whatsapp_messages (
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
        REFERENCES monica.whatsapp_chats(connection_id, chat_id) ON DELETE CASCADE,
    UNIQUE (connection_id, waha_message_id)
);

ALTER TABLE monica.whatsapp_messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "whatsapp_messages_select_own_org" ON monica.whatsapp_messages;
CREATE POLICY "whatsapp_messages_select_own_org" ON monica.whatsapp_messages FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('monica')));

DROP POLICY IF EXISTS "service_role_bypass" ON monica.whatsapp_messages;
CREATE POLICY "service_role_bypass" ON monica.whatsapp_messages FOR ALL TO service_role USING (true) WITH CHECK (true);

-- THE thread query (and the unread recount).
CREATE INDEX IF NOT EXISTS idx_monica_whatsapp_messages_thread
    ON monica.whatsapp_messages (connection_id, chat_id, timestamp DESC, waha_message_id DESC);
GRANT SELECT ON monica.whatsapp_connections, monica.whatsapp_chats, monica.whatsapp_messages TO authenticated;
GRANT ALL ON monica.whatsapp_connections, monica.whatsapp_chats, monica.whatsapp_messages TO service_role;
