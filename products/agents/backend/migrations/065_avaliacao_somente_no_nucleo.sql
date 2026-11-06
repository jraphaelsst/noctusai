-- ============================================================================
-- 065_avaliacao_somente_no_nucleo.sql -- ONE testing switch, on Julia's CORE (owner 2026-11-05).
--
-- "test mode is meant to be in julia agents app, not per instance": the evaluation mode + its list of NoctusAI evaluators
-- (`agents.agents.modo_avaliacao` / `avaliacao_usuarios`, migration 056) live ONLY on the core -- the `definition_scope =
-- 'plataforma'` row an instance points at through `definition_agent_id` (031) -- and every company instance obeys it. The app
-- reads the state from the core and never from an instance row.
--
-- This migration is the DB backstop of the write path: `agents.set_agent_avaliacao` refuses an INSTANCE (`definition_scope =
-- 'instancia'`) with `avaliacao_somente_no_nucleo`. The instance columns stay (an old image still selects them) but nothing
-- reads or writes them: NOC-REMEDIATE[drop-instance-modo-avaliacao] -- drop `modo_avaliacao` / `avaliacao_usuarios` from
-- instance rows' use (and, once no old image reads them, the columns' instance values) in a later migration.
--
-- Backward compatible with the previous image (same signature; it merely gets a typed refusal for an instance). Idempotent
-- (CREATE OR REPLACE); runs twice. SECURITY DEFINER keeps its REVOKE from PUBLIC/anon/authenticated.
-- ============================================================================

SET search_path = agents, public;

CREATE OR REPLACE FUNCTION agents.set_agent_avaliacao(
    p_org_id UUID,
    p_agent_id UUID,
    p_modo_avaliacao BOOLEAN,
    p_usuarios UUID[],
    p_actor UUID
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_modo BOOLEAN;
    v_usuarios UUID[];
    v_escopo TEXT;
    v_novo_modo BOOLEAN;
    v_novos UUID[];
BEGIN
    SELECT modo_avaliacao, avaliacao_usuarios, definition_scope INTO v_modo, v_usuarios, v_escopo
      FROM agents.agents WHERE id = p_agent_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF v_escopo = 'instancia' THEN
        RAISE EXCEPTION 'avaliacao_somente_no_nucleo' USING ERRCODE = 'P0001';
    END IF;
    v_novo_modo := COALESCE(p_modo_avaliacao, v_modo);
    v_novos := COALESCE(p_usuarios, v_usuarios);
    IF cardinality(v_novos) > 20 THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    IF v_novo_modo IS DISTINCT FROM v_modo OR v_novos IS DISTINCT FROM v_usuarios THEN
        UPDATE agents.agents SET modo_avaliacao = v_novo_modo, avaliacao_usuarios = v_novos
         WHERE id = p_agent_id AND org_id = p_org_id;
        INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
        VALUES (p_org_id, p_agent_id, p_actor, 'modo_avaliacao_alterado',
                jsonb_build_object('modo_avaliacao', v_modo, 'usuarios', to_jsonb(v_usuarios)),
                jsonb_build_object('modo_avaliacao', v_novo_modo, 'usuarios', to_jsonb(v_novos)));
    END IF;
END;
$$;

REVOKE ALL ON FUNCTION agents.set_agent_avaliacao(UUID, UUID, BOOLEAN, UUID[], UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.set_agent_avaliacao(UUID, UUID, BOOLEAN, UUID[], UUID) TO service_role;
