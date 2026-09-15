-- ============================================================================
-- 009_session_transcripts.sql — durable Julia session transcripts (contract
-- §E.11 "Durable transcripts", reserved in §F, slice B2)
--
-- Table: agents.session_transcript_entries — the Postgres-backed mirror of
-- the CLI's local JSONL transcript, written by
-- `app.runtime.transcript_mirror.ConversationTranscriptMirror` (the SDK's
-- `SessionStore.append`) and read back by `load_for_handoff()` so a slot can
-- resume a conversation after a container restart wipes its tmpfs (§E.11
-- "Resume after a restart now works").
--
-- SERVICE-ROLE ONLY — NO user-facing policy (unlike every table in 006/007,
-- which each carry an `<table>_select_own_org` SELECT policy for
-- `authenticated`). This table stores raw CLI transcript entries: tool
-- inputs/outputs, academia content and web-search results verbatim (§E.11
-- "LGPD: transcripts store tool outputs, academia content and web results").
-- No route ever needs to expose it to an org member directly — the chat UI
-- reads `messages`/`blocks` (contract §E.3), never this table. RLS is
-- therefore enabled with a SINGLE policy (`service_role_bypass`, the
-- keeper-audited literal name — see 006's header), and the table's default
-- schema-wide grant (001_agents.sql: `ALTER DEFAULT PRIVILEGES IN SCHEMA
-- agents GRANT ALL ON TABLES TO anon, authenticated, service_role`) is
-- explicitly REVOKEd for `anon`/`authenticated` below — the same
-- defense-in-depth posture 006 applies to its SECURITY DEFINER functions
-- (RLS-enabled-with-no-matching-policy already denies anon/authenticated
-- every operation; the REVOKE removes the grant itself so a future RLS
-- policy typo can never silently reopen access).
--
-- IDEMPOTENCY: `CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` /
-- drop-then-recreate the CHECK constraint and the RLS policy, matching the
-- rest of this product's migrations. NOT applied to any database by this
-- slice — the tech-lead applies it once every parallel slice lands.
-- ============================================================================

SET search_path = agents, public;

-- ────────────────────────────────────────────────────────────────────────
-- session_transcript_entries
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.session_transcript_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    conversation_id UUID NOT NULL REFERENCES agents.conversations(id) ON DELETE CASCADE,
    sdk_session_id  TEXT NOT NULL,
    seq             BIGINT NOT NULL,
    entry           JSONB NOT NULL,
    entry_uuid      TEXT NOT NULL,
    byte_size       INT NOT NULL CHECK (byte_size >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- entry_uuid is the SDK-supplied idempotency key (types.py
    -- `SessionStoreEntry`/`append` docstring: "adapters should treat [uuid]
    -- as an idempotency key"). Scoped per (conversation, sdk_session) so
    -- the same uuid in two different sessions/conversations never collides.
    UNIQUE (conversation_id, sdk_session_id, entry_uuid)
);

ALTER TABLE agents.session_transcript_entries ENABLE ROW LEVEL SECURITY;

-- No `<table>_select_own_org` policy on purpose — see header. Only the
-- literal, keeper-audited service-role-bypass policy exists.
CREATE POLICY "service_role_bypass" ON agents.session_transcript_entries
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Belt-and-suspenders on top of RLS-with-no-policy (see header):
-- 001_agents.sql's schema-wide `ALTER DEFAULT PRIVILEGES` grants `ALL` on
-- every new table in this schema to anon/authenticated at CREATE TABLE
-- time. Revoke it explicitly for this table so the deny is never implicit.
REVOKE ALL ON agents.session_transcript_entries FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS idx_agents_session_transcript_entries_org
    ON agents.session_transcript_entries(org_id);

-- The ordering index `load()`/`load_for_handoff()` read against — entries
-- for one (conversation, sdk_session) in `seq` order (contract §E.11
-- "TranscriptStore.load(...) -> list[entry] | None: ordered by seq").
CREATE INDEX IF NOT EXISTS idx_agents_session_transcript_entries_seq
    ON agents.session_transcript_entries(conversation_id, sdk_session_id, seq);


-- ────────────────────────────────────────────────────────────────────────
-- conversations.transcript_estado (contract §E.11 §E.1 data model addition)
-- ────────────────────────────────────────────────────────────────────────

ALTER TABLE agents.conversations
    ADD COLUMN IF NOT EXISTS transcript_estado TEXT NOT NULL DEFAULT 'ok';

ALTER TABLE agents.conversations
    DROP CONSTRAINT IF EXISTS conversations_transcript_estado_check;

ALTER TABLE agents.conversations
    ADD CONSTRAINT conversations_transcript_estado_check
        CHECK (transcript_estado IN ('ok', 'truncado', 'incompleto', 'invalido'));
