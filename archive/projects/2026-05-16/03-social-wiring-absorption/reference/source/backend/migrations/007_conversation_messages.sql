-- ============================================================================
-- YouTube Crawler — conversation_messages
--
-- One row per WhatsApp / platform-chat message (inbound + outbound), with a
-- UNIQUE constraint on `provider_message_id` driving WAHA idempotency
-- (whatsapp-scheduling's exact pattern: WAHA sends `message` + `message.any`
-- for the same inbound, both carrying the same provider_message_id, the
-- duplicate INSERT trips the UNIQUE constraint and the handler drops the
-- second event with an IntegrityError catch).
--
-- The Redis-backed memory list in `whatsapp:chatbot:{session_id}` stays the
-- runtime-fast recall layer the chatbot reads to build its OpenAI messages;
-- this table is the durable audit log + the dedup oracle.
-- ============================================================================

SET search_path = youtube_crawler, public;

CREATE TABLE youtube_crawler.conversation_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,

    -- Canonical conversation key. For WhatsApp this is the phone-form when
    -- the LID-to-phone cache is known; otherwise the raw LID. For platform
    -- chat: `web:<uuid>` issued by the frontend.
    session_id TEXT NOT NULL,

    -- Raw sender as WAHA delivered it (`33613018058989@lid` or
    -- `5511974693365@c.us`). Kept verbatim for forensics; the canonical
    -- session_id is what the chatbot keys recall on.
    raw_sender TEXT,

    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),

    -- Drives idempotency. NULL is allowed (some outbound surfaces don't
    -- know the id at insert time); Postgres treats NULLs as distinct so
    -- the UNIQUE constraint is correctly relaxed for NULLs.
    provider_message_id TEXT,

    body TEXT NOT NULL,

    -- True when the sender passed the whitelist on inbound; always True
    -- for outbound (we initiated the message).
    authorized BOOLEAN NOT NULL DEFAULT false,

    -- Free-form bag for downstream payload bits we want to keep around
    -- without growing columns: media descriptors, structured tool results,
    -- chat-id used for the WAHA send, etc.
    structured_payload JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_conversation_messages_provider_message_id
        UNIQUE (provider_message_id)
);

ALTER TABLE youtube_crawler.conversation_messages ENABLE ROW LEVEL SECURITY;

-- Operators can read their own org's transcript via the platform UI.
CREATE POLICY "conversation_messages_select_own_org"
    ON youtube_crawler.conversation_messages
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

-- Inbound + outbound writes come from the webhook + chatbot worker — both
-- run under the service role (no JWT context).
CREATE POLICY "conversation_messages_write_service_role"
    ON youtube_crawler.conversation_messages
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE INDEX idx_yt_conversation_messages_session
    ON youtube_crawler.conversation_messages(session_id, created_at DESC);
CREATE INDEX idx_yt_conversation_messages_org_session
    ON youtube_crawler.conversation_messages(org_id, session_id, created_at DESC);
CREATE INDEX idx_yt_conversation_messages_direction
    ON youtube_crawler.conversation_messages(direction);
