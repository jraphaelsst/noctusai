-- 073_council_ledger.sql — the council ledger records (contract: project-history/assistant-chatbot/contracts/council-ledger.md v1).
--
-- Four append-only record tables: session, objection, verdict (one per session), event. Ids are uuids SUPPLIED BY THE
-- WRITER (the ledger tool writes ndjson first, then upserts by id: INSERT ... ON CONFLICT (id) DO NOTHING), so there
-- is no default-generated id that could diverge from the ndjson. Closed sets are CHECK constraints (house style,
-- exactly the contract §2 enums). Service-role only: RLS on, no anon/authenticated policy, REVOKE ALL from the
-- client roles, service_role gets SELECT + INSERT only (no UPDATE/DELETE grant) and a trigger refuses both anyway.
-- Tier: platform (platform-admin). Schema `agents` is already exposed. No router/API in this slice.

SET search_path = agents, public;

-- 1 · session -------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents.council_sessions (
    session_id UUID PRIMARY KEY,
    stage TEXT NOT NULL CHECK (stage IN (
        'idealize', 'phase0', 'verify_seed', 'mockup', 'contract', 'build', 'wire', 'test_review',
        'security_pass', 'evaluate', 'ship', 'go_live', 'iterate', 'owner_question')),
    subject_kind TEXT NOT NULL CHECK (subject_kind IN (
        'plan', 'decision', 'agent_definition', 'skill', 'product', 'contract', 'refine', 'eval_run', 'question')),
    subject_ref TEXT NOT NULL,
    trigger TEXT NOT NULL CHECK (trigger IN (
        'stage_map', 'new_product', 'irreversible', 'trust_boundary', 'prod_exposure', 'money_legal_lgpd',
        'seed_fanout', 'large_estimate', 'unrebutted_objection')),
    mode TEXT NOT NULL CHECK (mode IN ('subagents', 'api', 'single_chat')),
    seats TEXT[] NOT NULL CHECK (cardinality(seats) >= 1),
    brief_sha256 TEXT NOT NULL,
    project TEXT NULL,
    recorded_by TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agents_council_sessions_stage ON agents.council_sessions (stage, recorded_at);

-- 2 · objection -----------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents.council_objections (
    objection_id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES agents.council_sessions(session_id),
    seat TEXT NOT NULL,
    anon_label TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('blocker', 'major', 'minor', 'note')),
    claim TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens INT NULL CHECK (tokens IS NULL OR tokens >= 0),
    recorded_by TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agents_council_objections_session ON agents.council_objections (session_id);
CREATE INDEX IF NOT EXISTS idx_agents_council_objections_seat ON agents.council_objections (seat);

-- 3 · verdict (one per session) -------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents.council_verdicts (
    session_id UUID PRIMARY KEY REFERENCES agents.council_sessions(session_id),
    chair_kind TEXT NOT NULL CHECK (chair_kind IN ('chair_agent', 'tech_lead', 'api_chair')),
    decision TEXT NOT NULL,
    biggest_risk TEXT NOT NULL,
    first_step TEXT NOT NULL,
    -- [{objection_id, disposition: accepted|rejected|deferred, reason}]; the tool validates each element (contract §1)
    dispositions JSONB NOT NULL CHECK (jsonb_typeof(dispositions) = 'array'),
    tokens INT NULL CHECK (tokens IS NULL OR tokens >= 0),
    recorded_by TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);

-- 4 · event (append-only state changes) -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents.council_events (
    event_id UUID PRIMARY KEY,
    event_kind TEXT NOT NULL CHECK (event_kind IN ('ratified', 'overruled', 'outcome')),
    session_id UUID NOT NULL REFERENCES agents.council_sessions(session_id),
    objection_id UUID NULL REFERENCES agents.council_objections(objection_id),
    outcome TEXT NULL CHECK (outcome IS NULL OR outcome IN ('vindicated', 'refuted', 'untested')),
    evidence_kind TEXT NULL CHECK (evidence_kind IS NULL OR evidence_kind IN (
        'commit', 'revert', 'incident', 'owner_reversal', 'eval_run', 'test', 'review')),
    evidence_ref TEXT NULL,
    note TEXT NULL,
    recorded_by TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    -- contract §1: objection_id / outcome / evidence_kind are required exactly when event_kind = outcome
    CONSTRAINT council_events_outcome_fields CHECK (
        (event_kind = 'outcome' AND objection_id IS NOT NULL AND outcome IS NOT NULL AND evidence_kind IS NOT NULL)
        OR (event_kind <> 'outcome' AND objection_id IS NULL AND outcome IS NULL AND evidence_kind IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_agents_council_events_session ON agents.council_events (session_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_agents_council_events_objection ON agents.council_events (objection_id) WHERE objection_id IS NOT NULL;

-- 5 · append-only guard (defence in depth over the missing grants) --------------------------------------------
CREATE OR REPLACE FUNCTION agents.council_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = agents, public AS $$
BEGIN
    RAISE EXCEPTION '% is append-only (a correction is a new council_events row)', TG_TABLE_NAME USING ERRCODE = 'P0001';
END;
$$;
REVOKE EXECUTE ON FUNCTION agents.council_append_only() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS council_sessions_append_only ON agents.council_sessions;
CREATE TRIGGER council_sessions_append_only BEFORE UPDATE OR DELETE ON agents.council_sessions
    FOR EACH ROW EXECUTE FUNCTION agents.council_append_only();
DROP TRIGGER IF EXISTS council_objections_append_only ON agents.council_objections;
CREATE TRIGGER council_objections_append_only BEFORE UPDATE OR DELETE ON agents.council_objections
    FOR EACH ROW EXECUTE FUNCTION agents.council_append_only();
DROP TRIGGER IF EXISTS council_verdicts_append_only ON agents.council_verdicts;
CREATE TRIGGER council_verdicts_append_only BEFORE UPDATE OR DELETE ON agents.council_verdicts
    FOR EACH ROW EXECUTE FUNCTION agents.council_append_only();
DROP TRIGGER IF EXISTS council_events_append_only ON agents.council_events;
CREATE TRIGGER council_events_append_only BEFORE UPDATE OR DELETE ON agents.council_events
    FOR EACH ROW EXECUTE FUNCTION agents.council_append_only();

-- 6 · service-role only, SELECT + INSERT (no UPDATE/DELETE), tier platform ------------------------------------
ALTER TABLE agents.council_sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_read" ON agents.council_sessions;
DROP POLICY IF EXISTS "service_role_insert" ON agents.council_sessions;
CREATE POLICY "service_role_read" ON agents.council_sessions FOR SELECT TO service_role USING (true);
CREATE POLICY "service_role_insert" ON agents.council_sessions FOR INSERT TO service_role WITH CHECK (true);
REVOKE ALL ON agents.council_sessions FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON agents.council_sessions TO service_role;
COMMENT ON TABLE agents.council_sessions IS 'tier:platform';

ALTER TABLE agents.council_objections ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_read" ON agents.council_objections;
DROP POLICY IF EXISTS "service_role_insert" ON agents.council_objections;
CREATE POLICY "service_role_read" ON agents.council_objections FOR SELECT TO service_role USING (true);
CREATE POLICY "service_role_insert" ON agents.council_objections FOR INSERT TO service_role WITH CHECK (true);
REVOKE ALL ON agents.council_objections FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON agents.council_objections TO service_role;
COMMENT ON TABLE agents.council_objections IS 'tier:platform';

ALTER TABLE agents.council_verdicts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_read" ON agents.council_verdicts;
DROP POLICY IF EXISTS "service_role_insert" ON agents.council_verdicts;
CREATE POLICY "service_role_read" ON agents.council_verdicts FOR SELECT TO service_role USING (true);
CREATE POLICY "service_role_insert" ON agents.council_verdicts FOR INSERT TO service_role WITH CHECK (true);
REVOKE ALL ON agents.council_verdicts FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON agents.council_verdicts TO service_role;
COMMENT ON TABLE agents.council_verdicts IS 'tier:platform';

ALTER TABLE agents.council_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_read" ON agents.council_events;
DROP POLICY IF EXISTS "service_role_insert" ON agents.council_events;
CREATE POLICY "service_role_read" ON agents.council_events FOR SELECT TO service_role USING (true);
CREATE POLICY "service_role_insert" ON agents.council_events FOR INSERT TO service_role WITH CHECK (true);
REVOKE ALL ON agents.council_events FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON agents.council_events TO service_role;
COMMENT ON TABLE agents.council_events IS 'tier:platform';
