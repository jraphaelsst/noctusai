-- ============================================================================
-- 043_julia_v2_lead_reativacao.sql -- an opt-out can be lifted by an operator, on the record.
--
-- Owner decision (2026-10-21): the opt-out is a per-ORG setting of social-wiring (leads are the org's, not
-- noc's); agents only STORES and ENFORCES it. Someone tells the agent to stop, and later the org needs to put that
-- lead back into the agents flow -- on the record, never by quietly editing a column.
--
--   * `lead_opt_out_eventos.tipo` ('opt_out' | 'reativacao', default 'opt_out'): the same table now carries the
--     lead's consent history in both directions. Every existing row is an opt-out.
--   * `lead_refs.opt_in_origem` accepts 'reativacao_manual' (the origin a reactivation stamps).
--   * `agents.reativar_lead`: ONE transaction -- lift the opt-out (`opt_in_em` = now, `opt_in_origem` =
--     'reativacao_manual') and record the event (`tipo` 'reativacao', origem 'operador', who, why). It returns JSONB
--     `{encontrado, reativado, evento_id}`: `encontrado` false = unknown lead, `reativado` false = the lead had no
--     active opt-out (nothing written). Putting the lead back in the flow needs no participant move: an
--     `encerrado` participant (motivo opt_out) is reopened by the lead's next message (controles.decidir), the
--     opt-out gate being the only thing that refused it.
--   * `agents.registrar_opt_out` reads "the opt-out already in force" among `tipo = 'opt_out'` events only, so a
--     reactivation event is never mistaken for it.
--
-- Forward-only + idempotent. NOT applied by the slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

ALTER TABLE agents.lead_opt_out_eventos
    ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'opt_out'
        CONSTRAINT lead_opt_out_eventos_tipo_check CHECK (tipo IN ('opt_out', 'reativacao'));

ALTER TABLE agents.lead_refs DROP CONSTRAINT IF EXISTS lead_refs_opt_in_origem_check;
ALTER TABLE agents.lead_refs ADD CONSTRAINT lead_refs_opt_in_origem_check
    CHECK (opt_in_origem IS NULL OR opt_in_origem IN
        ('lead_iniciou', 'formulario_meta', 'campanha_ctwa', 'importado', 'reativacao_manual'));

CREATE OR REPLACE FUNCTION agents.registrar_opt_out(
    p_org_id UUID,
    p_produto TEXT,
    p_ref_externa TEXT,
    p_em TIMESTAMPTZ,
    p_origem TEXT DEFAULT 'integracao',
    p_motivo TEXT DEFAULT NULL,
    p_mensagem_lead TEXT DEFAULT NULL,
    p_agent_id UUID DEFAULT NULL,
    p_thread_id UUID DEFAULT NULL,
    p_ator_user_id UUID DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_lead UUID;
    v_opt_out TIMESTAMPTZ;
    v_opt_in TIMESTAMPTZ;
    v_em TIMESTAMPTZ := COALESCE(p_em, now());
    v_n INTEGER := 0;
    v_evento UUID;
    v_novo BOOLEAN := false;
    r RECORD;
BEGIN
    SELECT id, opt_out_em, opt_in_em INTO v_lead, v_opt_out, v_opt_in FROM agents.lead_refs
     WHERE org_id = p_org_id AND produto = p_produto AND ref_externa = p_ref_externa
     FOR UPDATE;
    IF v_lead IS NULL THEN
        RETURN jsonb_build_object('encontrado', false, 'participantes_encerrados', 0, 'evento_id', NULL, 'evento_novo', false);
    END IF;

    -- already in force (an opt-out the lead has not lifted by opting in again since): no second event.
    IF v_opt_out IS NOT NULL AND (v_opt_in IS NULL OR v_opt_in < v_opt_out) THEN
        SELECT id INTO v_evento FROM agents.lead_opt_out_eventos
         WHERE lead_ref_id = v_lead AND tipo = 'opt_out' ORDER BY em DESC, created_at DESC LIMIT 1;
    ELSE
        UPDATE agents.lead_refs SET opt_out_em = v_em WHERE id = v_lead;
    END IF;

    FOR r IN
        SELECT p.thread_id, p.agent_id, p.estado
          FROM agents.thread_participantes p
          JOIN agents.conversations c ON c.id = p.thread_id
         WHERE c.lead_ref_id = v_lead AND p.org_id = p_org_id AND p.estado IN ('ativo', 'pausado')
    LOOP
        PERFORM agents.set_participante_estado(
            p_org_id, r.thread_id, r.agent_id, ARRAY['ativo', 'pausado'], 'encerrado', 'sistema', NULL, 'opt_out', NULL
        );
        v_n := v_n + 1;
    END LOOP;

    IF v_evento IS NULL THEN
        INSERT INTO agents.lead_opt_out_eventos (
            org_id, lead_ref_id, em, origem, agent_id, thread_id, ator_user_id, motivo, mensagem_lead,
            participantes_encerrados
        ) VALUES (
            p_org_id, v_lead, v_em, COALESCE(p_origem, 'integracao'), p_agent_id, p_thread_id, p_ator_user_id,
            left(COALESCE(NULLIF(btrim(p_motivo), ''), 'nao_informado'), 500),
            left(NULLIF(p_mensagem_lead, ''), 1000),
            v_n
        ) RETURNING id INTO v_evento;
        v_novo := true;
    END IF;

    RETURN jsonb_build_object(
        'encontrado', true, 'participantes_encerrados', v_n, 'evento_id', v_evento, 'evento_novo', v_novo
    );
END;
$$;

REVOKE ALL ON FUNCTION agents.registrar_opt_out(UUID, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT, UUID, UUID, UUID)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.registrar_opt_out(UUID, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT, UUID, UUID, UUID)
    TO service_role;


CREATE OR REPLACE FUNCTION agents.reativar_lead(
    p_org_id UUID,
    p_produto TEXT,
    p_ref_externa TEXT,
    p_ator_user_id UUID,
    p_motivo TEXT,
    p_em TIMESTAMPTZ DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_lead UUID;
    v_opt_out TIMESTAMPTZ;
    v_opt_in TIMESTAMPTZ;
    v_em TIMESTAMPTZ;
    v_evento UUID;
BEGIN
    SELECT id, opt_out_em, opt_in_em INTO v_lead, v_opt_out, v_opt_in FROM agents.lead_refs
     WHERE org_id = p_org_id AND produto = p_produto AND ref_externa = p_ref_externa
     FOR UPDATE;
    IF v_lead IS NULL THEN
        RETURN jsonb_build_object('encontrado', false, 'reativado', false, 'evento_id', NULL);
    END IF;
    IF v_opt_out IS NULL OR (v_opt_in IS NOT NULL AND v_opt_in >= v_opt_out) THEN
        RETURN jsonb_build_object('encontrado', true, 'reativado', false, 'evento_id', NULL);
    END IF;

    -- never earlier than the opt-out it lifts (a future-dated opt-out must still be lifted).
    v_em := GREATEST(COALESCE(p_em, now()), v_opt_out);
    UPDATE agents.lead_refs
       SET opt_in_em = v_em, opt_in_origem = 'reativacao_manual', updated_at = now()
     WHERE id = v_lead;
    INSERT INTO agents.lead_opt_out_eventos (org_id, lead_ref_id, em, tipo, origem, ator_user_id, motivo)
    VALUES (p_org_id, v_lead, v_em, 'reativacao', 'operador', p_ator_user_id, left(btrim(p_motivo), 500))
    RETURNING id INTO v_evento;

    RETURN jsonb_build_object('encontrado', true, 'reativado', true, 'evento_id', v_evento);
END;
$$;

REVOKE ALL ON FUNCTION agents.reativar_lead(UUID, TEXT, TEXT, UUID, TEXT, TIMESTAMPTZ)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.reativar_lead(UUID, TEXT, TEXT, UUID, TEXT, TIMESTAMPTZ) TO service_role;
