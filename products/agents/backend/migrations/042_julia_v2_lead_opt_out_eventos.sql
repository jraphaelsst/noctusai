-- ============================================================================
-- 042_julia_v2_lead_opt_out_eventos.sql -- a lead that asks to stop is never dropped silently.
--
-- Owner decision (2026-10-21): when a lead asks an agent to stop, record a LEAD-level opt-out that stops every
-- agent, leave a record of what happened and why so the owner can see it, and notify -- never disengage in
-- silence. 033's `lead_refs.opt_out_em` + `registrar_opt_out` already stop every agent; what was missing is the
-- WHO / WHY / WHAT-THE-LEAD-SAID and the notification state.
--
--   * `agents.lead_opt_out_eventos`: one row per opt-out that took effect (origin agente | operador |
--     integracao, the agent / thread / operator, the reason in the actor's words, the lead's own message that
--     triggered it, how many participations it ended, and the notification state -- pendente | enviada |
--     falhou -- so a notification that failed is a visible row, not a lost log line).
--   * `agents.registrar_opt_out` gains optional params (the 4-argument call keeps working) and writes the event in
--     the SAME transaction as the opt-out and the participant moves. It returns JSONB
--     `{encontrado, participantes_encerrados, evento_id, evento_novo}`; the return type changes, so the old
--     INTEGER-returning function is dropped first (the backend is its only caller). Idempotent: an opt-out
--     that is already in force records NO second event (`evento_novo` false, the existing event id returned), so
--     the caller notifies once per event.
--
-- `motivo` is the actor's words (capped 500); when the caller gives none the RPC stores the code
-- `nao_informado` (a code, not prose). `mensagem_lead` is the lead's own words (capped 1000): personal data --
-- the table is service-role only and the rows go with the lead (FK ON DELETE CASCADE from `lead_refs`, so
-- delete-by-lead erases them).
--
-- Forward-only + idempotent. NOT applied by the slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

CREATE TABLE IF NOT EXISTS agents.lead_opt_out_eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    lead_ref_id UUID NOT NULL REFERENCES agents.lead_refs(id) ON DELETE CASCADE,
    em TIMESTAMPTZ NOT NULL DEFAULT now(),
    origem TEXT NOT NULL CONSTRAINT lead_opt_out_eventos_origem_check
        CHECK (origem IN ('agente', 'operador', 'integracao')),
    agent_id UUID NULL REFERENCES agents.agents(id) ON DELETE SET NULL,
    thread_id UUID NULL REFERENCES agents.conversations(id) ON DELETE SET NULL,
    ator_user_id UUID NULL,
    motivo TEXT NOT NULL CONSTRAINT lead_opt_out_eventos_motivo_check
        CHECK (char_length(btrim(motivo)) BETWEEN 1 AND 500),
    mensagem_lead TEXT NULL CONSTRAINT lead_opt_out_eventos_mensagem_check
        CHECK (mensagem_lead IS NULL OR char_length(mensagem_lead) <= 1000),
    participantes_encerrados INTEGER NOT NULL DEFAULT 0 CHECK (participantes_encerrados >= 0),
    notificacao_status TEXT NOT NULL DEFAULT 'pendente' CONSTRAINT lead_opt_out_eventos_notificacao_check
        CHECK (notificacao_status IN ('pendente', 'enviada', 'falhou')),
    notificacao_erro TEXT NULL,
    notificado_em TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lead_opt_out_eventos_org_em
    ON agents.lead_opt_out_eventos (org_id, em DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_lead_opt_out_eventos_lead
    ON agents.lead_opt_out_eventos (lead_ref_id, em DESC);

ALTER TABLE agents.lead_opt_out_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.lead_opt_out_eventos;
CREATE POLICY "service_role_bypass" ON agents.lead_opt_out_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
-- Lead data: no direct client access of any kind (036's lockdown pattern); the API reads it org-scoped.
REVOKE ALL ON agents.lead_opt_out_eventos FROM PUBLIC, anon, authenticated;

-- ── the RPC ────────────────────────────────────────────────────────────────

DROP FUNCTION IF EXISTS agents.registrar_opt_out(UUID, TEXT, TEXT, TIMESTAMPTZ);

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
         WHERE lead_ref_id = v_lead ORDER BY em DESC, created_at DESC LIMIT 1;
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

-- Assertion: the new table is unreachable by anon/authenticated.
DO $assert$
BEGIN
    IF has_table_privilege('authenticated', 'agents.lead_opt_out_eventos', 'SELECT, INSERT, UPDATE, DELETE')
       OR has_table_privilege('anon', 'agents.lead_opt_out_eventos', 'SELECT, INSERT, UPDATE, DELETE') THEN
        RAISE EXCEPTION '042: agents.lead_opt_out_eventos must be service-role only';
    END IF;
END $assert$;
