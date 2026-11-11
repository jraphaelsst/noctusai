-- ============================================================================
-- Migration 018 -- Assistant S4: the owner's BLIND labels of the scheduling classifier (the evaluation, D46 item 8)
--
--   1. assistant.ai_feedback_events -- the seed ai_feedback organ's APPEND-ONLY labelled-verdict seam, rendered from
--      noctusai_lib.domain.sql_templates.ai_feedback_events_table_sql('assistant', labels) (do not hand-edit that
--      section; the test pins it). One event per (labeler, intake row, round); a re-judgement is a NEW event with the
--      next round, never an update (a trigger refuses UPDATE/DELETE). Service role only, like every Assistant table.
--      It holds the verdict enum and uuids -- never message text, never a phone.
--   2. assistant.registrar_rotulo(...) -- the ONE writer: checks the ai_output belongs to this org and to that intake
--      row, then inserts; a repeated (labeler, intake, round) is a no-op that returns the existing event (repetido).
--   3. assistant.rotulos_do_rotulador(...) -- the caller's own latest label per intake row (progress + "already done").
--   4. assistant.resumo_rotulos(...) -- the agreement input: counts of (model verdict x owner label) per
--      prompt_version/model, over each labeller's LATEST judgement of each message, joined to EVERY classification of
--      that message (so one human label scores every prompt version that classified it).
--   5. status_pagina row for the `/avaliacao` nav page (a nav-listed route without one is hidden from everyone).
-- Forward-only + idempotent. NOT applied by the slice that authored it -- the tech-lead applies it.
-- ============================================================================

-- ----- 1. ai_feedback_events: rendered from sql_templates.ai_feedback_events_table_sql (do not hand-edit) -----
SET search_path = assistant, public;

CREATE TABLE IF NOT EXISTS assistant.ai_feedback_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL DEFAULT public.current_org_id_for('assistant'),
    labeler_id  UUID NOT NULL,
    subject_id  UUID NOT NULL,
    output_id   UUID,
    label       TEXT NOT NULL,
    round       INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_feedback_events_label_check CHECK (label IN ('agendamento', 'nao_agendamento', 'nao_sei')),
    CONSTRAINT ai_feedback_events_round_check CHECK (round >= 1),
    CONSTRAINT ai_feedback_events_once_per_round UNIQUE (labeler_id, subject_id, round)
);
CREATE INDEX IF NOT EXISTS ai_feedback_events_subject_idx ON assistant.ai_feedback_events (subject_id, labeler_id, round DESC);
CREATE INDEX IF NOT EXISTS ai_feedback_events_org_idx ON assistant.ai_feedback_events (org_id);
ALTER TABLE assistant.ai_feedback_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS service_role_bypass ON assistant.ai_feedback_events;
CREATE POLICY service_role_bypass ON assistant.ai_feedback_events FOR ALL TO service_role
    USING (true) WITH CHECK (true);
REVOKE ALL ON assistant.ai_feedback_events FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.ai_feedback_events TO service_role;
COMMENT ON TABLE assistant.ai_feedback_events IS 'tier:org';

CREATE OR REPLACE FUNCTION assistant.guard_ai_feedback_events_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$
BEGIN
    RAISE EXCEPTION 'append_only' USING ERRCODE = 'P0001';
END;
$$;
REVOKE ALL ON FUNCTION assistant.guard_ai_feedback_events_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.guard_ai_feedback_events_append_only() TO service_role;
DROP TRIGGER IF EXISTS guard_ai_feedback_events_append_only ON assistant.ai_feedback_events;
CREATE TRIGGER guard_ai_feedback_events_append_only
    BEFORE UPDATE OR DELETE ON assistant.ai_feedback_events
    FOR EACH ROW EXECUTE FUNCTION assistant.guard_ai_feedback_events_append_only();

-- ----- 2. The writer -----
CREATE OR REPLACE FUNCTION assistant.registrar_rotulo(
    p_org_id uuid, p_labeler_id uuid, p_intake_id uuid, p_output_id uuid, p_rotulo text, p_rodada int
) RETURNS TABLE (evento_id uuid, repetido boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$
DECLARE
    v_id uuid;
BEGIN
    -- The output must be a classification of THIS intake row in THIS org: no row back = a 404 at the route.
    IF NOT EXISTS (
        SELECT 1 FROM assistant.ai_outputs o
        WHERE o.id = p_output_id AND o.org_id = p_org_id AND o.ref_type = 'intake_message'
          AND o.ref_id = p_intake_id AND o.kind = 'classification'
    ) THEN
        RETURN;
    END IF;
    INSERT INTO assistant.ai_feedback_events (org_id, labeler_id, subject_id, output_id, label, round)
    VALUES (p_org_id, p_labeler_id, p_intake_id, p_output_id, p_rotulo, p_rodada)
    ON CONFLICT ON CONSTRAINT ai_feedback_events_once_per_round DO NOTHING
    RETURNING ai_feedback_events.id INTO v_id;
    IF v_id IS NOT NULL THEN
        RETURN QUERY SELECT v_id, false;
        RETURN;
    END IF;
    SELECT e.id INTO v_id FROM assistant.ai_feedback_events e
    WHERE e.labeler_id = p_labeler_id AND e.subject_id = p_intake_id AND e.round = p_rodada;
    RETURN QUERY SELECT v_id, true;
END;
$$;
REVOKE ALL ON FUNCTION assistant.registrar_rotulo(uuid, uuid, uuid, uuid, text, int) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.registrar_rotulo(uuid, uuid, uuid, uuid, text, int) TO service_role;

-- ----- 3. The labeller's own latest label per intake row -----
CREATE OR REPLACE FUNCTION assistant.rotulos_do_rotulador(p_org_id uuid, p_labeler_id uuid)
RETURNS TABLE (intake_id uuid, rotulo text, rodada int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = assistant, public
AS $$
    SELECT DISTINCT ON (e.subject_id) e.subject_id, e.label, e.round
    FROM assistant.ai_feedback_events e
    WHERE e.org_id = p_org_id AND e.labeler_id = p_labeler_id
    ORDER BY e.subject_id, e.round DESC;
$$;
REVOKE ALL ON FUNCTION assistant.rotulos_do_rotulador(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.rotulos_do_rotulador(uuid, uuid) TO service_role;

-- ----- 4. The agreement input: (model verdict x owner label) counts per prompt_version / model -----
CREATE OR REPLACE FUNCTION assistant.resumo_rotulos(p_org_id uuid)
RETURNS TABLE (prompt_version text, modelo text, veredito text, rotulo text, n bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = assistant, public
AS $$
    WITH ultimo AS (
        SELECT DISTINCT ON (e.labeler_id, e.subject_id) e.subject_id, e.label
        FROM assistant.ai_feedback_events e
        WHERE e.org_id = p_org_id
        ORDER BY e.labeler_id, e.subject_id, e.round DESC
    )
    SELECT o.prompt_version, o.model_version, o.label, u.label, count(*)
    FROM ultimo u
    JOIN assistant.ai_outputs o ON o.ref_id = u.subject_id AND o.org_id = p_org_id
         AND o.ref_type = 'intake_message' AND o.kind = 'classification'
    GROUP BY o.prompt_version, o.model_version, o.label, u.label
    ORDER BY o.prompt_version, o.model_version, o.label, u.label;
$$;
REVOKE ALL ON FUNCTION assistant.resumo_rotulos(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.resumo_rotulos(uuid) TO service_role;

-- ----- 5. status_pagina: the "Avaliação" nav page (`/avaliacao`; KB § PATTERNS/frontend/status-pagina-dev-visibility.md) -----
INSERT INTO assistant.status_pagina (nome_pagina, status) VALUES
    ('avaliacao', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
