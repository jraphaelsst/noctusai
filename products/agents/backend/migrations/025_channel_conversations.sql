-- ============================================================================
-- 025_channel_conversations.sql -- channel conversations + the product turn API
-- (Lais slice A2, contract products/social-wiring/projects/lais/specs/
-- julia-agent-contract.md section 3.3, 10.1 M2/M5).
--
-- 1. agents.conversations gains channel / channel_ref / contact. A channel
--    conversation (a lead on WhatsApp, driven by a PRODUCT token, not a user)
--    has no human owner: owner_user_id becomes nullable, and a CHECK keeps the
--    old invariant for every non-channel row (a user conversation MUST have an
--    owner). A partial unique index makes (org, agent, channel, channel_ref)
--    the conversation identity.
-- 2. agents.channel_inbound -- the idempotency ledger (M2): one row per
--    inbound provider message, UNIQUE (org_id, connection_id,
--    provider_message_id). Carries the sha256 of the text (a replay with a
--    different text is a 409, never a second turn) and, once the turn is done,
--    the stored reply (replaying an id returns it; no second turn). Cascades
--    with the conversation, so a deletion / the 180-day purge takes it too.
-- 3. agents.delete_channel_conversation / purge_channel_conversations -- ONE
--    transaction each (a PostgREST .rpc() is one transaction): messages,
--    approvals, the idempotency rows and the conversation (messages/approvals
--    FK the conversation without a cascade). Deletion on request + the
--    retention purge (M5, LGPD). service_role only.
--
-- Idempotent (IF NOT EXISTS / DROP CONSTRAINT IF EXISTS / OR REPLACE).
-- NOT applied to any database by this slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. conversations: channel identity ────────────────────────────────────

ALTER TABLE agents.conversations ADD COLUMN IF NOT EXISTS channel TEXT NULL;
ALTER TABLE agents.conversations ADD COLUMN IF NOT EXISTS channel_ref JSONB NULL;
ALTER TABLE agents.conversations ADD COLUMN IF NOT EXISTS contact JSONB NULL;

ALTER TABLE agents.conversations ALTER COLUMN owner_user_id DROP NOT NULL;

ALTER TABLE agents.conversations
    DROP CONSTRAINT IF EXISTS conversations_channel_owner_check;
ALTER TABLE agents.conversations
    ADD CONSTRAINT conversations_channel_owner_check
        CHECK (
            (channel IS NULL AND owner_user_id IS NOT NULL AND channel_ref IS NULL AND contact IS NULL)
            OR (channel IS NOT NULL AND channel <> '' AND channel_ref IS NOT NULL)
        );

CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_conversations_channel_ref
    ON agents.conversations (org_id, agent_id, channel, channel_ref)
    WHERE channel IS NOT NULL;

-- Retention purge scan (M5): channel rows by last activity.
CREATE INDEX IF NOT EXISTS idx_agents_conversations_channel_activity
    ON agents.conversations (COALESCE(last_message_at, created_at))
    WHERE channel IS NOT NULL;

-- Lead conversations hold third-party personal data (LGPD): a direct
-- (RLS-governed, `authenticated`) read must never reach a channel row. The
-- agents UI reads them through the admin-gated API route instead. 020's
-- org-picker predicate is kept, narrowed to non-channel rows.
ALTER POLICY conversations_select_own_org ON agents.conversations
    USING (
        channel IS NULL
        AND org_id = (SELECT public.current_org_id_for('agents'))
    );

ALTER POLICY messages_select_own_org ON agents.messages
    USING (
        org_id = (SELECT public.current_org_id_for('agents'))
        AND NOT EXISTS (
            SELECT 1 FROM agents.conversations c
            WHERE c.id = messages.conversation_id AND c.channel IS NOT NULL
        )
    );

-- ── 2. channel_inbound: the idempotency ledger ────────────────────────────

CREATE TABLE IF NOT EXISTS agents.channel_inbound (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    connection_id UUID NOT NULL,
    provider_message_id TEXT NOT NULL CHECK (provider_message_id <> ''),
    conversation_id UUID NOT NULL REFERENCES agents.conversations(id) ON DELETE CASCADE,
    texto_sha256 TEXT NOT NULL CHECK (char_length(texto_sha256) = 64),
    reply JSONB NULL,
    replied_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_agents_channel_inbound_msg UNIQUE (org_id, connection_id, provider_message_id)
);

ALTER TABLE agents.channel_inbound ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON agents.channel_inbound;
CREATE POLICY "service_role_bypass" ON agents.channel_inbound
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Lead text hash + the stored reply: service-role only, like every lead row's writer.
REVOKE ALL ON agents.channel_inbound FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS idx_agents_channel_inbound_conversation
    ON agents.channel_inbound (conversation_id);

-- ── 3. deletion on request + retention purge (one transaction each) ───────

CREATE OR REPLACE FUNCTION agents.delete_channel_conversation(
    p_org_id UUID,
    p_conversation_id UUID
) RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_found UUID;
BEGIN
    SELECT id INTO v_found FROM agents.conversations
    WHERE id = p_conversation_id AND org_id = p_org_id AND channel IS NOT NULL
    FOR UPDATE;
    IF v_found IS NULL THEN
        RETURN FALSE;
    END IF;
    DELETE FROM agents.messages WHERE conversation_id = v_found AND org_id = p_org_id;
    DELETE FROM agents.approvals WHERE conversation_id = v_found AND org_id = p_org_id;
    DELETE FROM agents.channel_inbound WHERE conversation_id = v_found AND org_id = p_org_id;
    DELETE FROM agents.conversations WHERE id = v_found AND org_id = p_org_id;
    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION agents.delete_channel_conversation(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.delete_channel_conversation(UUID, UUID) TO service_role;

CREATE OR REPLACE FUNCTION agents.purge_channel_conversations(
    p_cutoff TIMESTAMPTZ
) RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_ids UUID[];
BEGIN
    SELECT COALESCE(array_agg(id), ARRAY[]::UUID[]) INTO v_ids
    FROM agents.conversations
    WHERE channel IS NOT NULL
      AND COALESCE(last_message_at, created_at) < p_cutoff
      AND (turn_lock_until IS NULL OR turn_lock_until < now());
    IF array_length(v_ids, 1) IS NULL THEN
        RETURN 0;
    END IF;
    DELETE FROM agents.messages WHERE conversation_id = ANY (v_ids);
    DELETE FROM agents.approvals WHERE conversation_id = ANY (v_ids);
    DELETE FROM agents.channel_inbound WHERE conversation_id = ANY (v_ids);
    DELETE FROM agents.conversations WHERE id = ANY (v_ids);
    RETURN array_length(v_ids, 1);
END;
$$;

REVOKE ALL ON FUNCTION agents.purge_channel_conversations(TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.purge_channel_conversations(TIMESTAMPTZ) TO service_role;
