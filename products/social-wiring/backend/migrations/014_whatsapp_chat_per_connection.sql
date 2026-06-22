-- 014_whatsapp_chat_per_connection.sql — per-connection chat inbox
--
-- Project: sw-wa-chat (2026-06-22). Enables the per-connection WhatsApp
-- inbox UI: every message can be tagged with the connection it arrived on
-- (conversation_messages.connection_id), messages are queryable per-chat
-- (raw_sender grouping within a connection), and a per-connection
-- auto_reply_enabled toggle controls whether the existing chatbot fires.
--
-- Design decisions:
--
--   connection_id is NULLABLE on conversation_messages — pre-existing
--   historical rows have no connection context and stay NULL by design.
--   They do NOT surface in per-connection chat queries (the chat inbox
--   filters WHERE connection_id = :id AND org_id = current). This is
--   acceptable and is documented here so future engineers don't backfill.
--
--   auto_reply_enabled defaults to FALSE (locked-off product decision)
--   so existing connections don't accidentally trigger the chatbot during
--   manual operator testing of the new chat UI.
--
-- Forward-only + idempotent (IF NOT EXISTS / ON CONFLICT DO NOTHING /
-- guarded ALTER). Apply to the noctusai Supabase (social_wiring schema)
-- AFTER 013 is applied.

SET search_path = social_wiring, public;

-- ── 1. conversation_messages: add connection_id ──────────────────────────────
ALTER TABLE social_wiring.conversation_messages
    ADD COLUMN IF NOT EXISTS connection_id UUID;
-- No FK: connections can be deleted; orphaned chat history is acceptable.
-- connection_id = NULL means "untagged / pre-2026-06-22 message."

-- Index: the two query shapes this feature drives:
--   (a) GET /chats — SELECT max(created_at), last body per raw_sender, grouped by raw_sender
--       ORDER BY max(created_at) DESC → connection_id + raw_sender + created_at
--   (b) GET /chats/:chatId/messages — SELECT * WHERE connection_id=? AND raw_sender=?
--       ORDER BY created_at ASC → same compound
-- DESC prefix on created_at matches the ORDER BY of the grouping query;
-- ASC message thread scans do a sort on the small result set.
CREATE INDEX IF NOT EXISTS idx_sw_conv_msgs_connection_chat
    ON social_wiring.conversation_messages(connection_id, raw_sender, created_at DESC);

-- ── 2. whatsapp_connections: add auto_reply_enabled ──────────────────────────
ALTER TABLE social_wiring.whatsapp_connections
    ADD COLUMN IF NOT EXISTS auto_reply_enabled BOOLEAN NOT NULL DEFAULT false;

-- ── 3. status_pagina: register the whatsapp_chat nav route ───────────────────
-- The nav gates items by status_pagina (unlisted route ⇒ hidden).
-- This row makes the WhatsApp chat inbox page visible once the FE ships it.
-- ON CONFLICT DO NOTHING keeps the migration idempotent on re-apply.
INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('whatsapp_chat', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
