<<<<<<<< HEAD:products/social-wiring/backend/migrations/044_whatsapp_inbox_realtime_schema.sql
-- 044_whatsapp_inbox_realtime_schema.sql — Postgres as the read source of
========
-- 042_whatsapp_inbox_realtime_schema.sql — Postgres as the read source of
>>>>>>>> origin/dev:products/social-wiring/backend/migrations/042_whatsapp_inbox_realtime_schema.sql
-- truth for the WhatsApp chat inbox.
--
-- Project: whatsapp-realtime-inbox (2026-08-03), Slice 3.
--
-- Context: today the chat list is derived by a Python GROUP BY over
-- social_wiring.conversation_messages on every request, then merged with a
-- live WAHA call that takes ~13s on the NOWEB engine. There is no chats
-- table, no read cursor, and `unread` is hardcoded 0 for WAHA-sourced chats.
-- This migration adds:
--
--   1. social_wiring.whatsapp_chats — one row per (connection_id, chat_id)
--      conversation, carrying the denormalized "list view" fields (last
--      message preview/direction/time, unread_count, read cursor,
--      archived/pinned) so GET /chats becomes a single indexed SELECT
--      instead of a GROUP BY + a live WAHA round-trip.
--
--   2. conversation_messages.ack / .acked_at / .chat_id — WAHA delivery-ack
--      tracking + an explicit chat_id column (mirrors whatsapp_chats.chat_id)
--      so the thread query (GET /chats/:chatId/messages) is a direct index
--      scan instead of a raw_sender-based re-derivation.
--
-- Design decisions (preserve this intent — do not re-derive):
--
--   whatsapp_chats.connection_id is NOT NULL but carries NO FOREIGN KEY to
--   whatsapp_connections, matching the precedent set in
--   014_whatsapp_chat_per_connection.sql (lines 11-15, 30): connections can
--   be deleted, and orphaned chat history is an accepted trade-off — a chat
--   row surviving its connection's deletion is not a bug. Enforcing the FK
--   here would only reintroduce the coupling 014 deliberately avoided.
--
--   conversation_messages.chat_id is added NULLABLE and is NOT backfilled.
--   Pre-existing rows keep chat_id = NULL and simply do not participate in
--   the new indexed thread query — exactly the same reasoning
--   014_whatsapp_chat_per_connection.sql already applied to connection_id
--   (see its lines 11-15): historical rows lack the context to backfill
--   correctly (chat_id here would have to be reconstructed from raw_sender,
--   which is lossy for group chats / @lid-style ids), so we leave them NULL
--   rather than write a guess. New rows are stamped with chat_id going
--   forward by the ingestion path (out of this migration's territory).
--
--   whatsapp_chats.synced_through is a backfill watermark (the timestamp
--   through which WAHA history has been synced into Postgres for that chat)
--   — NULL means "never synced," letting the backfill job resume instead of
--   re-walking from the beginning on every run.
--
-- RLS: org-scoped via public.current_org_id() (defined in
-- 011_rls_current_org_id.sql — PREREQUISITE), mirroring
-- 011_rls_current_org_id.sql:448-453 / 038_n8n_folders.sql exactly:
-- authenticated gets SELECT only (org_id = current_org_id(), no further
-- predicate — see KB § PATTERNS/frontend/status-pagina-dev-visibility.md: a
-- read-policy that filters a category makes every downstream FE branch on
-- it dead, so archived/unread rows are NOT filtered out here — the FE owns
-- the archived-tab / unread-badge branching, not RLS); service_role gets
-- ALL (the backend writes via the service-role/admin client).
--
-- Forward-only + idempotent (IF NOT EXISTS / DROP+CREATE POLICY / guarded
-- ALTER — running this file twice must not error). Apply to the noctusai
-- Supabase (social_wiring schema) AFTER 014 and 011 are applied.

SET search_path = social_wiring, public;

-- ── 1. whatsapp_chats — one row per conversation ────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.whatsapp_chats (
    connection_id         UUID NOT NULL,
    -- No FK to whatsapp_connections — see header note above (mirrors 014).
    chat_id               TEXT NOT NULL,
    org_id                UUID NOT NULL,
    title                 TEXT,
    last_message_at       TIMESTAMPTZ,
    last_message_preview  TEXT,
    last_direction        TEXT
        CHECK (last_direction IN ('inbound', 'outbound')),
    unread_count          INTEGER NOT NULL DEFAULT 0,
    last_read_at          TIMESTAMPTZ,
    last_read_message_id  TEXT,
    archived              BOOLEAN NOT NULL DEFAULT false,
    pinned                BOOLEAN NOT NULL DEFAULT false,
    synced_through        TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (connection_id, chat_id)
);

ALTER TABLE social_wiring.whatsapp_chats ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "whatsapp_chats_select_own_org" ON social_wiring.whatsapp_chats;
CREATE POLICY "whatsapp_chats_select_own_org" ON social_wiring.whatsapp_chats
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

DROP POLICY IF EXISTS "whatsapp_chats_service_role" ON social_wiring.whatsapp_chats;
CREATE POLICY "whatsapp_chats_service_role" ON social_wiring.whatsapp_chats
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- THE chat-list query: "chats for this connection, non-archived first,
-- newest activity first." This index IS GET /chats — do not drop/reorder
-- the columns without re-checking that query's ORDER BY / WHERE shape.
CREATE INDEX IF NOT EXISTS idx_sw_whatsapp_chats_list
    ON social_wiring.whatsapp_chats (connection_id, archived, last_message_at DESC);

CREATE OR REPLACE FUNCTION social_wiring.set_updated_at_whatsapp_chats()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = social_wiring, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

DROP TRIGGER IF EXISTS set_updated_at_whatsapp_chats ON social_wiring.whatsapp_chats;
CREATE TRIGGER set_updated_at_whatsapp_chats
    BEFORE UPDATE ON social_wiring.whatsapp_chats
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_whatsapp_chats();


-- ── 2. conversation_messages — ack tracking + explicit chat_id ─────────────
-- WAHA ack levels: -1 error, 0 pending, 1 server, 2 device, 3 read, 4 played.
ALTER TABLE social_wiring.conversation_messages
    ADD COLUMN IF NOT EXISTS ack SMALLINT;
ALTER TABLE social_wiring.conversation_messages
    ADD COLUMN IF NOT EXISTS acked_at TIMESTAMPTZ;
ALTER TABLE social_wiring.conversation_messages
    ADD COLUMN IF NOT EXISTS chat_id TEXT;
-- chat_id is NOT backfilled — see header note above. Existing rows stay
-- NULL by design; do not backfill.

-- THE thread query: "messages for this chat on this connection, oldest to
-- newest" (or newest-first for the initial page load — DESC on the index
-- serves both directions well for the common recent-page access pattern).
-- This index IS GET /chats/:chatId/messages.
CREATE INDEX IF NOT EXISTS idx_sw_conv_msgs_connection_chat_id
    ON social_wiring.conversation_messages (connection_id, chat_id, created_at DESC);
