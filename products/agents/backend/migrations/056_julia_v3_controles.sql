-- ============================================================================
-- 056: Julia v3 controls (contract §12.1 / §12.2).
--
-- 1. agents.plataforma_controles -- the PLATFORM kill switch, one row per agent key. `desligado` stops that agent
--    for EVERY org (the turn endpoint answers `agente_desligado_plataforma`, no model call). Toggled only by a
--    platform admin through agents.set_plataforma_controle (one transaction, attributed audit row).
--    SERVICE-ROLE ONLY (platform-wide, no org_id): RLS on, the single service_role_bypass policy, no grant to
--    authenticated / anon.
-- 2. agents.agents.fase_testes -- per org instance: while true the agent may tell the lead the service is in a
--    testing phase (rendered into the turn state). Changed through agents.set_agent_fase_testes (audited).
-- 3. agent_audit_log.acao CHECK gains 'plataforma_desligada', 'plataforma_religada', 'fase_testes_alterada'
--    (the union of every action the code writes; tests/test_migration_audit_acao_check.py pins it).
-- ============================================================================

SET search_path = agents, public;

CREATE TABLE IF NOT EXISTS agents.plataforma_controles (
    agent_key TEXT PRIMARY KEY CHECK (agent_key ~ '^[a-z0-9]+([-_][a-z0-9]+)*$' AND length(agent_key) <= 64),
    desligado BOOLEAN NOT NULL DEFAULT false,
    motivo TEXT NULL CHECK (motivo IS NULL OR length(motivo) <= 500),
    alterado_por UUID NULL,
    alterado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.plataforma_controles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.plataforma_controles;
CREATE POLICY "service_role_bypass" ON agents.plataforma_controles
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.plataforma_controles FROM anon, authenticated;

ALTER TABLE agents.agents ADD COLUMN IF NOT EXISTS fase_testes BOOLEAN NOT NULL DEFAULT true;

DO $$
DECLARE
    v_con TEXT;
BEGIN
    FOR v_con IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'agents.agent_audit_log'::regclass
           AND contype = 'c'
           AND pg_get_constraintdef(oid) ILIKE '%acao%'
    LOOP
        EXECUTE format('ALTER TABLE agents.agent_audit_log DROP CONSTRAINT %I', v_con);
    END LOOP;
END
$$;

ALTER TABLE agents.agent_audit_log
    ADD CONSTRAINT agent_audit_log_acao_check
        CHECK (acao IN (
            'limiar_alterado', 'publicado', 'publicado_override', 'rascunho_descartado',
            'conteudo_editado_mcp', 'specs_org_editadas', 'definicao_lida',
            'modo_alterado', 'conversa_pausada', 'conversa_retomada', 'padrao_publicado',
            'agente_excluido', 'agente_criado', 'agente_gerado',
            'historico_transferido', 'agente_arquivado',
            'plataforma_desligada', 'plataforma_religada', 'fase_testes_alterada'
        ));

-- Flip the platform switch and audit it in one transaction. The audit row hangs on the PLATFORM definition of the
-- agent (definition_scope 'plataforma'); raises `agent_not_found` when no such definition exists.
CREATE OR REPLACE FUNCTION agents.set_plataforma_controle(
    p_agent_key TEXT,
    p_desligado BOOLEAN,
    p_motivo TEXT,
    p_actor UUID
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_agent agents.agents%ROWTYPE;
    v_antes BOOLEAN;
BEGIN
    SELECT * INTO v_agent FROM agents.agents
     WHERE key = p_agent_key AND definition_scope = 'plataforma' LIMIT 1;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent_not_found' USING ERRCODE = 'P0001';
    END IF;
    SELECT desligado INTO v_antes FROM agents.plataforma_controles WHERE agent_key = p_agent_key;
    v_antes := COALESCE(v_antes, false);
    INSERT INTO agents.plataforma_controles (agent_key, desligado, motivo, alterado_por, alterado_em)
    VALUES (p_agent_key, p_desligado, p_motivo, p_actor, now())
    ON CONFLICT (agent_key) DO UPDATE
        SET desligado = EXCLUDED.desligado, motivo = EXCLUDED.motivo,
            alterado_por = EXCLUDED.alterado_por, alterado_em = EXCLUDED.alterado_em;
    INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
    VALUES (
        v_agent.org_id, v_agent.id, p_actor,
        CASE WHEN p_desligado THEN 'plataforma_desligada' ELSE 'plataforma_religada' END,
        jsonb_build_object('desligado', v_antes),
        jsonb_build_object('desligado', p_desligado, 'motivo', p_motivo)
    );
END;
$$;

REVOKE ALL ON FUNCTION agents.set_plataforma_controle(TEXT, BOOLEAN, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.set_plataforma_controle(TEXT, BOOLEAN, TEXT, UUID) TO service_role;

-- Change an org instance's testing-phase switch with an attributed audit row. Raises `agent_not_found`.
CREATE OR REPLACE FUNCTION agents.set_agent_fase_testes(
    p_org_id UUID,
    p_agent_id UUID,
    p_fase_testes BOOLEAN,
    p_actor UUID
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_antes BOOLEAN;
BEGIN
    SELECT fase_testes INTO v_antes FROM agents.agents WHERE id = p_agent_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF v_antes IS DISTINCT FROM p_fase_testes THEN
        UPDATE agents.agents SET fase_testes = p_fase_testes WHERE id = p_agent_id AND org_id = p_org_id;
        INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
        VALUES (p_org_id, p_agent_id, p_actor, 'fase_testes_alterada',
                jsonb_build_object('fase_testes', v_antes), jsonb_build_object('fase_testes', p_fase_testes));
    END IF;
END;
$$;

REVOKE ALL ON FUNCTION agents.set_agent_fase_testes(UUID, UUID, BOOLEAN, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.set_agent_fase_testes(UUID, UUID, BOOLEAN, UUID) TO service_role;
