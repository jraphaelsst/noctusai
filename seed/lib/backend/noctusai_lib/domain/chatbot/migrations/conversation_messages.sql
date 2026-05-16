-- ============================================================================
-- chatbot seed — conversation_messages (schema-neutral template)
--
-- Reconciled 2026-05-16 from the live-validated
-- youtube-crawler/backend/migrations/007_conversation_messages.sql
-- (projects/social-wiring-absorption/ W1.E1, manifest `multimodal-stack`).
--
-- One row per inbound + outbound message, with a UNIQUE constraint on
-- `provider_message_id` driving idempotency: WAHA delivers `message` +
-- `message.any` for the same inbound carrying the same
-- provider_message_id; the duplicate INSERT trips the UNIQUE constraint
-- and the handler drops the second event by catching
-- `noctusai_lib.domain.chatbot.message_store.DuplicateMessage`. This is
-- the durable backstop for the restart-surviving dedup contract (the
-- Redis SETNX pre-filter is the fast, lossy-on-restart layer the
-- WhatsApp connector owns — see message_store.py seam contract).
--
-- TEMPLATE: this is NOT applied directly. Each consuming product copies
-- it into its own numbered migration and substitutes `{{SCHEMA}}` with
-- its product schema (the validated source hardcoded `youtube_crawler`;
-- the seed is schema-neutral per the full-reconcile rule). The
-- `SupabaseMessageStore` constructor takes the same schema name so the
-- runtime + the migration stay in lock-step.
-- ============================================================================

SET search_path = {{SCHEMA}}, public;

CREATE TABLE {{SCHEMA}}.conversation_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,

    -- Canonical conversation key. WhatsApp: phone-form when the
    -- LID-to-phone cache is known, else the raw LID. Platform chat:
    -- `web:<uuid>` issued by the frontend.
    session_id TEXT NOT NULL,

    -- Raw sender as the connector delivered it (`33613018058989@lid`
    -- or `5511974693365@c.us`). Verbatim for forensics; the canonical
    -- session_id is what recall keys on.
    raw_sender TEXT,

    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),

    -- Drives idempotency. NULL allowed (some outbound surfaces don't
    -- know the id at insert time); Postgres treats NULLs as distinct so
    -- the UNIQUE constraint is correctly relaxed for NULLs.
    provider_message_id TEXT,

    body TEXT NOT NULL,

    -- True when the sender passed the whitelist on inbound; always True
    -- for outbound (we initiated the message).
    authorized BOOLEAN NOT NULL DEFAULT false,

    -- Free-form bag: media descriptors, structured tool results, the
    -- chat-id used for the send, etc.
    structured_payload JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_conversation_messages_provider_message_id
        UNIQUE (provider_message_id)
);

ALTER TABLE {{SCHEMA}}.conversation_messages ENABLE ROW LEVEL SECURITY;

-- Operators read their own org's transcript via the platform UI.
CREATE POLICY "conversation_messages_select_own_org"
    ON {{SCHEMA}}.conversation_messages
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

-- Inbound + outbound writes come from the webhook + chatbot worker —
-- both run under the service role (no JWT context).
CREATE POLICY "conversation_messages_write_service_role"
    ON {{SCHEMA}}.conversation_messages
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE INDEX idx_conversation_messages_session
    ON {{SCHEMA}}.conversation_messages(session_id, created_at DESC);
CREATE INDEX idx_conversation_messages_org_session
    ON {{SCHEMA}}.conversation_messages(org_id, session_id, created_at DESC);
CREATE INDEX idx_conversation_messages_direction
    ON {{SCHEMA}}.conversation_messages(direction);
