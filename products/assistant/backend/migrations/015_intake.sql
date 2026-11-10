-- ============================================================================
-- Migration 015 -- Assistant: the WhatsApp line (QR connection) + the INTAKE queue + its append-only events
--
-- The Assistant is a READ-ONLY shadow of one personal WhatsApp line (D46). Nothing here stores a chat: the seed inbox
-- tables (`whatsapp_chats` / `whatsapp_messages`) are deliberately NOT created -- they would keep raw third-party phone
-- numbers + a message log the Assistant never reads back. What the Assistant keeps is one INTAKE row per inbound 1:1
-- text message, written by `assistant.append_intake(...)` (the only writer), and one append-only EVENT per state change.
--
-- * `whatsapp_connections` -- the seed connection store's table (verbatim `whatsapp_connections_table_ddl`) + `paired_at`
--   (stamped when WAHA reports the session WORKING; cleared when it asks for a QR again). Forward-only: a message
--   older than `paired_at`, or any message while `paired_at` is NULL, is recorded as `skipped` with NO body.
-- * `intake_messages` -- dated, outcome is a CHECK-enum (`pending|classified|failed|skipped_budget|skipped_excluded|
--   skipped`; S3's worker moves `pending` forward through `assistant.set_intake_outcome`). LGPD minimisation: the third
--   party is an HMAC'd identifier (`chat_ref`, keyed server-side -- never a phone), the body is kept ONLY while
--   `outcome = 'pending'|'classified'|'failed'` and until `retain_until` (90 days; the S5 retention spec enforces it).
-- * `intake_messages_eventos` -- one row per outcome change, written in the SAME transaction as the change (both SQL
--   functions are single statements-blocks: PostgREST gives one RPC = one transaction). Append-only, guard trigger with
--   the single `assistant.retention_purge` carve-out for the retention job.
--
-- Access: service role only (no browser grant, no browser policy); every route is admin-gated in the backend.
-- Forward-only + idempotent (re-apply safe). NOT applied by the slice that authored it -- the tech-lead applies it.
-- ============================================================================

SET search_path = assistant, public;

-- ----- Connections (seed shape) -----
CREATE TABLE IF NOT EXISTS assistant.whatsapp_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    user_id UUID NOT NULL,
    label TEXT NOT NULL,
    base_url TEXT NOT NULL,
    session_name TEXT NOT NULL DEFAULT 'default',
    encrypted_api_key TEXT NOT NULL,
    webhook_url TEXT,
    webhook_token TEXT NOT NULL,
    app_enabled BOOLEAN NOT NULL DEFAULT true,
    session_role TEXT NOT NULL DEFAULT 'owner' CHECK (session_role IN ('owner', 'borrower')),
    paired_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, label)
);
ALTER TABLE assistant.whatsapp_connections ADD COLUMN IF NOT EXISTS paired_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_assistant_whatsapp_connections_org ON assistant.whatsapp_connections(org_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_assistant_whatsapp_connections_webhook_token ON assistant.whatsapp_connections(webhook_token);

CREATE OR REPLACE FUNCTION assistant.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;
REVOKE ALL ON FUNCTION assistant.set_updated_at() FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE TRIGGER set_updated_at_whatsapp_connections
    BEFORE UPDATE ON assistant.whatsapp_connections
    FOR EACH ROW EXECUTE FUNCTION assistant.set_updated_at();

ALTER TABLE assistant.whatsapp_connections ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.whatsapp_connections;
CREATE POLICY "service_role_bypass" ON assistant.whatsapp_connections FOR ALL TO service_role USING (true) WITH CHECK (true);
COMMENT ON TABLE assistant.whatsapp_connections IS 'tier:org';
REVOKE ALL ON assistant.whatsapp_connections FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.whatsapp_connections TO service_role;

-- ----- Intake queue -----
CREATE TABLE IF NOT EXISTS assistant.intake_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL,
    connection_id uuid NOT NULL REFERENCES assistant.whatsapp_connections(id) ON DELETE CASCADE,
    waha_message_id text NOT NULL,                 -- the dedup key (one row per WAHA message id per line)
    chat_ref text NOT NULL,                        -- HMAC'd conversation identifier, never a phone / JID
    msg_type text NOT NULL DEFAULT 'chat',
    has_text boolean NOT NULL DEFAULT false,
    body text,                                     -- NULL for skipped rows; cleared at retain_until by the retention job
    outcome text NOT NULL DEFAULT 'pending'
        CHECK (outcome IN ('pending', 'classified', 'failed', 'skipped_budget', 'skipped_excluded', 'skipped')),
    outcome_reason text,
    received_at timestamptz NOT NULL,              -- the WhatsApp message timestamp
    outcome_at timestamptz NOT NULL DEFAULT now(),
    retain_until timestamptz NOT NULL DEFAULT (now() + interval '90 days'),  -- LGPD: message content retention
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (connection_id, waha_message_id)
);

CREATE INDEX IF NOT EXISTS idx_assistant_intake_pending ON assistant.intake_messages (connection_id, received_at) WHERE outcome = 'pending';
CREATE INDEX IF NOT EXISTS idx_assistant_intake_retention ON assistant.intake_messages (retain_until);

CREATE OR REPLACE TRIGGER set_updated_at_intake_messages
    BEFORE UPDATE ON assistant.intake_messages
    FOR EACH ROW EXECUTE FUNCTION assistant.set_updated_at();

ALTER TABLE assistant.intake_messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.intake_messages;
CREATE POLICY "service_role_bypass" ON assistant.intake_messages FOR ALL TO service_role USING (true) WITH CHECK (true);
COMMENT ON TABLE assistant.intake_messages IS 'tier:org';
REVOKE ALL ON assistant.intake_messages FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.intake_messages TO service_role;

-- ----- Events (append-only): who / when / from -> to, same transaction as the change -----
CREATE TABLE IF NOT EXISTS assistant.intake_messages_eventos (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entidade_id uuid NOT NULL REFERENCES assistant.intake_messages(id) ON DELETE RESTRICT,
    event_type  text NOT NULL CHECK (event_type IN ('recebida', 'desfecho_alterado')),
    de          text,           -- previous outcome; NULL on creation
    para        text NOT NULL,  -- new outcome
    dados       jsonb NOT NULL DEFAULT '{}'::jsonb,  -- reason code only; never message content, never a phone
    actor_id    uuid,
    actor_kind  text NOT NULL DEFAULT 'system' CHECK (actor_kind IN ('user', 'agent', 'system', 'integration')),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_intake_messages_eventos_entidade ON assistant.intake_messages_eventos (entidade_id, occurred_at DESC);

ALTER TABLE assistant.intake_messages_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.intake_messages_eventos;
CREATE POLICY "service_role_bypass" ON assistant.intake_messages_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
COMMENT ON TABLE assistant.intake_messages_eventos IS 'tier:org';
REVOKE ALL ON assistant.intake_messages_eventos FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.intake_messages_eventos TO service_role;

-- ----- GUC carve-out guard: assistant.intake_messages_eventos (flag assistant.retention_purge) -----
-- guc-carveout-guard: rendered by noctusai_lib.domain.sql_templates.guc_carveout_guard_sql
CREATE OR REPLACE FUNCTION assistant.guard_intake_messages_eventos_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('assistant.retention_purge', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'append_only' USING ERRCODE = 'P0001';
END;
$$;

REVOKE ALL ON FUNCTION assistant.guard_intake_messages_eventos_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.guard_intake_messages_eventos_append_only() TO service_role;

DROP TRIGGER IF EXISTS guard_intake_messages_eventos_append_only ON assistant.intake_messages_eventos;
CREATE TRIGGER guard_intake_messages_eventos_append_only
    BEFORE UPDATE OR DELETE ON assistant.intake_messages_eventos
    FOR EACH ROW EXECUTE FUNCTION assistant.guard_intake_messages_eventos_append_only();

-- ----- The two writers: the change and its event are ONE transaction (one RPC) -----

-- append_intake: dedup on (connection, WAHA message id); forward-only from paired_at; text-only. Returns the new
-- row's id + outcome, or NO row when the message was already taken in (a replayed webhook).
CREATE OR REPLACE FUNCTION assistant.append_intake(
    p_org_id uuid, p_connection_id uuid, p_waha_message_id text, p_chat_ref text,
    p_msg_type text, p_body text, p_received_at timestamptz
) RETURNS TABLE (id uuid, outcome text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$
DECLARE
    v_paired timestamptz;
    v_has_text boolean := coalesce(btrim(p_body), '') <> '';
    v_outcome text := 'pending';
    v_reason text;
    v_id uuid;
BEGIN
    SELECT c.paired_at INTO v_paired FROM assistant.whatsapp_connections c
     WHERE c.id = p_connection_id AND c.org_id = p_org_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown connection' USING ERRCODE = 'P0002';
    END IF;

    IF v_paired IS NULL THEN
        v_outcome := 'skipped'; v_reason := 'not_paired';
    ELSIF p_received_at < v_paired THEN
        v_outcome := 'skipped'; v_reason := 'before_pairing';
    ELSIF NOT v_has_text THEN
        v_outcome := 'skipped'; v_reason := 'no_text';
    END IF;

    INSERT INTO assistant.intake_messages
        (org_id, connection_id, waha_message_id, chat_ref, msg_type, has_text, body, outcome, outcome_reason, received_at)
    VALUES
        (p_org_id, p_connection_id, p_waha_message_id, p_chat_ref, coalesce(p_msg_type, 'chat'), v_has_text,
         CASE WHEN v_outcome = 'pending' THEN p_body ELSE NULL END, v_outcome, v_reason, p_received_at)
    ON CONFLICT (connection_id, waha_message_id) DO NOTHING
    RETURNING intake_messages.id INTO v_id;

    IF v_id IS NULL THEN
        RETURN;  -- duplicate: nothing written, no event
    END IF;

    INSERT INTO assistant.intake_messages_eventos (entidade_id, event_type, de, para, dados, actor_kind)
    VALUES (v_id, 'recebida', NULL, v_outcome,
            CASE WHEN v_reason IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('reason', v_reason) END, 'system');

    id := v_id; outcome := v_outcome;
    RETURN NEXT;
END;
$$;
REVOKE ALL ON FUNCTION assistant.append_intake(uuid, uuid, text, text, text, text, timestamptz) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.append_intake(uuid, uuid, text, text, text, text, timestamptz) TO service_role;

-- set_intake_outcome: the ONLY way an intake row's outcome changes (S3's worker calls it); refuses an unknown
-- outcome (the CHECK), a no-op change, and leaving a terminal skipped_* state. The change + its event, one transaction.
CREATE OR REPLACE FUNCTION assistant.set_intake_outcome(
    p_intake_id uuid, p_outcome text, p_reason text, p_actor_kind text DEFAULT 'agent'
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$
DECLARE
    v_old text;
BEGIN
    SELECT m.outcome INTO v_old FROM assistant.intake_messages m WHERE m.id = p_intake_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown intake row' USING ERRCODE = 'P0002';
    END IF;
    IF v_old = p_outcome THEN
        RETURN false;
    END IF;
    IF v_old LIKE 'skipped%' THEN
        RAISE EXCEPTION 'a skipped intake row is terminal' USING ERRCODE = 'P0001';
    END IF;

    UPDATE assistant.intake_messages
       SET outcome = p_outcome, outcome_reason = p_reason, outcome_at = now(),
           body = CASE WHEN p_outcome LIKE 'skipped%' THEN NULL ELSE body END
     WHERE id = p_intake_id;

    INSERT INTO assistant.intake_messages_eventos (entidade_id, event_type, de, para, dados, actor_kind)
    VALUES (p_intake_id, 'desfecho_alterado', v_old, p_outcome,
            CASE WHEN p_reason IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('reason', p_reason) END, p_actor_kind);
    RETURN true;
END;
$$;
REVOKE ALL ON FUNCTION assistant.set_intake_outcome(uuid, text, text, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.set_intake_outcome(uuid, text, text, text) TO service_role;
