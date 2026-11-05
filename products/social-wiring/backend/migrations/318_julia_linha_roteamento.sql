-- ============================================================================
-- Migration 318 -- social_wiring: ONE line, staff routing (CONTRACT julia-line §B / SW-A)
-- ============================================================================
-- WHY
-- ---
-- Owner decision 2026-11-04: the "One Chat" operator bot is RETIRED. Julia (leads) and the staff notifications share ONE WhatsApp
-- number. Routing on that number no longer depends on `whatsapp_connections.authorized_numbers`; it depends on WHO writes
-- (staff = active julia_staff rows + phones of the line-owning org's members) and on a durable ORIGIN stamped on every message.
--
-- WHAT
--   1. conversation_messages.origem  text NULL CHECK (lead|julia|humano|interno)
--        lead    -- an inbound from a lead
--        julia   -- an outbound Julia sent
--        humano  -- an outbound a person typed (phone or the Conversas UI)
--        interno -- staff-channel traffic: a system-sent notice (report / alert, pre-written by the sender keyed by
--                   provider_message_id so WAHA's `fromMe` echo dedups on UNIQUE(provider_message_id)) and a staff member's inbound
--      NULLABLE, NO BACKFILL: a historical outbound cannot be told apart (Julia vs a person) and a historical inbound cannot be
--      told apart from a staff message; a guessed value would be a lie the takeover rule then acts on. NULL = "before origin
--      stamping"; every rule reads only the explicit values.
--   2. whatsapp_chats.categoria  text NOT NULL DEFAULT 'lead' CHECK (lead|equipe)
--        equipe -- a staff conversation: stored and shown, NEVER routed to Julia, never eligible, never a takeover.
--      Existing rows become 'lead' (the DEFAULT), which is what they were treated as until now.
--   3. DROP CHECK whatsapp_connections_agente_exige_autorizados (migration 258): Julia no longer needs `authorized_numbers`
--      to be switched on. The columns authorized_numbers / auto_reply_enabled / bound_chats stay until SW-B (S12, after deploy).
--
-- FORWARD-ONLY, IDEMPOTENT. NO SECURITY DEFINER function. Apply with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.conversation_messages') IS NULL OR to_regclass('social_wiring.whatsapp_chats') IS NULL
     OR to_regclass('social_wiring.whatsapp_connections') IS NULL THEN
    RAISE EXCEPTION 'migration 318: conversation_messages / whatsapp_chats / whatsapp_connections missing -- apply 001/042/016 first';
  END IF;
END
$guard$;

-- -- 1. message origin -----------------------------------------------------------
ALTER TABLE social_wiring.conversation_messages
    ADD COLUMN IF NOT EXISTS origem text;

ALTER TABLE social_wiring.conversation_messages
    DROP CONSTRAINT IF EXISTS conversation_messages_origem_check;
ALTER TABLE social_wiring.conversation_messages
    ADD CONSTRAINT conversation_messages_origem_check
    CHECK (origem IS NULL OR origem IN ('lead', 'julia', 'humano', 'interno'));

COMMENT ON COLUMN social_wiring.conversation_messages.origem IS
    'Who produced the message: lead | julia | humano | interno (system-sent staff notice, pre-written by the sender so the WAHA '
    'fromMe echo dedups on provider_message_id). NULL = written before origin stamping (never backfilled).';

-- -- 2. chat category --------------------------------------------------------------
ALTER TABLE social_wiring.whatsapp_chats
    ADD COLUMN IF NOT EXISTS categoria text NOT NULL DEFAULT 'lead';

ALTER TABLE social_wiring.whatsapp_chats
    DROP CONSTRAINT IF EXISTS whatsapp_chats_categoria_check;
ALTER TABLE social_wiring.whatsapp_chats
    ADD CONSTRAINT whatsapp_chats_categoria_check
    CHECK (categoria IN ('lead', 'equipe'));

COMMENT ON COLUMN social_wiring.whatsapp_chats.categoria IS
    'lead (default) | equipe. A staff chat is stored and shown but never routed to Julia, never eligible, never a takeover.';

-- -- 3. Julia no longer requires authorized_numbers --------------------------------
ALTER TABLE social_wiring.whatsapp_connections
    DROP CONSTRAINT IF EXISTS whatsapp_connections_agente_exige_autorizados;
