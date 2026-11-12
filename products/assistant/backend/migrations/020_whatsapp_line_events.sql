-- ============================================================================
-- Migration 020 -- Assistant: the append-only WhatsApp LINE EVENTS (the persistent LineEventSink)
--
-- `register_line_policy` refuses to register a `send: disabled` line while refusals would only reach the in-memory sink
-- (the Assistant crash-looped at boot for lack of it). This is the persistent half: one INSERT-only row per line-policy
-- event (`whatsapp.line.write_refused`, `whatsapp.line.repair_refused`), written by
-- noctusai_lib.integrations.whatsapp.line_event_sink.SupabaseLineEventSink. Rendered from
-- noctusai_lib.domain.sql_templates.whatsapp_line_events_table_sql('assistant') (do not hand-edit; a test pins it).
-- Service role only, tier:service, no UPDATE/DELETE grant + a trigger that refuses both. No message content, no phone.
-- Forward-only + idempotent.
-- ============================================================================
SET search_path = assistant, public;

CREATE TABLE IF NOT EXISTS assistant.whatsapp_line_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event       TEXT NOT NULL,
    line        TEXT NOT NULL,
    op          TEXT NOT NULL,
    reason      TEXT NOT NULL,
    policy      JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS whatsapp_line_events_line_idx ON assistant.whatsapp_line_events (line, occurred_at DESC);
ALTER TABLE assistant.whatsapp_line_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS service_role_select ON assistant.whatsapp_line_events;
CREATE POLICY service_role_select ON assistant.whatsapp_line_events FOR SELECT TO service_role USING (true);
DROP POLICY IF EXISTS service_role_insert ON assistant.whatsapp_line_events;
CREATE POLICY service_role_insert ON assistant.whatsapp_line_events FOR INSERT TO service_role WITH CHECK (true);
REVOKE ALL ON assistant.whatsapp_line_events FROM PUBLIC, anon, authenticated;
REVOKE UPDATE, DELETE, TRUNCATE ON assistant.whatsapp_line_events FROM service_role;
GRANT SELECT, INSERT ON assistant.whatsapp_line_events TO service_role;
COMMENT ON TABLE assistant.whatsapp_line_events IS 'tier:service';

CREATE OR REPLACE FUNCTION assistant.guard_whatsapp_line_events_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$
BEGIN
    RAISE EXCEPTION 'append_only' USING ERRCODE = 'P0001';
END;
$$;
REVOKE ALL ON FUNCTION assistant.guard_whatsapp_line_events_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.guard_whatsapp_line_events_append_only() TO service_role;
DROP TRIGGER IF EXISTS guard_whatsapp_line_events_append_only ON assistant.whatsapp_line_events;
CREATE TRIGGER guard_whatsapp_line_events_append_only
    BEFORE UPDATE OR DELETE ON assistant.whatsapp_line_events
    FOR EACH ROW EXECUTE FUNCTION assistant.guard_whatsapp_line_events_append_only();
