-- ============================================================================
-- Migration 022 -- WhatsApp inbox: per-chat agent pause columns
--
-- monica.whatsapp_chats.agent_paused / agent_paused_at / agent_paused_by -- the seed inbox organ's per-chat
-- "the product's agent is paused here" record (flag, when, by whom = the actor's user id, never a name). Output of
-- the seed helper `chat_agent_pause_alter_ddl("monica")`. Monica has NO agent answering on its inbox, so the pause
-- route is not mounted and nothing writes the columns yet; they exist so the chat DTO (`agent_paused`) is
-- complete and a later agent needs no schema change.
-- Forward-only + idempotent (re-apply safe). NOT applied by the slice that authored it -- the tech-lead applies it (migrate_product).
-- ============================================================================

SET search_path = monica, public;

ALTER TABLE monica.whatsapp_chats
    ADD COLUMN IF NOT EXISTS agent_paused BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS agent_paused_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS agent_paused_by TEXT;
