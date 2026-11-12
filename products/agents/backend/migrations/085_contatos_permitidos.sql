-- ============================================================================
-- 085_contatos_permitidos.sql -- per-agent PHONE allow-list ("contatos permitidos"), owner 2026-11-12.
--
-- The owner's personal WhatsApp line is a live agent ("assistente pessoal"). He edits a list of phone numbers; the agent
-- answers ONLY those numbers, and an EMPTY list means EVERY number (the opposite of evaluation mode, where empty = nobody).
-- The on/off is the existing `agents.modo_operacao` (ligado / drenando / desligado; a new agent is `desligado`).
--
-- `agents.agents.contatos_permitidos` holds E.164 strings (plus sign, country code, number), per agent row (an instance carries its own;
-- unlike the evaluation state it is NOT inherited from a core). Written only through `agents.set_agent_contatos_permitidos`
-- (service_role): normalisation + the cap + the attributed audit row (`contatos_permitidos_alterados`, EOA: same transaction,
-- the row carries the COUNTS only, never the numbers) land together. Julia's rows keep the default '{}' = everybody = unchanged.
--
-- agent_audit_log.acao CHECK gains 'contatos_permitidos_alterados' (the union of every action the code writes;
-- tests/test_migration_audit_acao_check.py pins it against studio_definitions.AUDIT_ACOES). Idempotent; runs twice.
-- ============================================================================

SET search_path = agents, public;

ALTER TABLE agents.agents ADD COLUMN IF NOT EXISTS contatos_permitidos TEXT[] NOT NULL DEFAULT '{}';

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
            'plataforma_desligada', 'plataforma_religada', 'fase_testes_alterada', 'modo_avaliacao_alterado',
            'contatos_permitidos_alterados'
        ));

-- Replace the allow-list and audit it in one transaction. `p_numeros` are already E.164 ('+' + 8..15 digits) -- the API
-- normalises; the function refuses anything else (`invalid_payload`) and more than 100 entries. De-duplicates, order kept.
CREATE OR REPLACE FUNCTION agents.set_agent_contatos_permitidos(
    p_org_id UUID,
    p_agent_id UUID,
    p_numeros TEXT[],
    p_actor UUID
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_antes TEXT[];
    v_novos TEXT[];
BEGIN
    SELECT contatos_permitidos INTO v_antes
      FROM agents.agents WHERE id = p_agent_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF p_numeros IS NULL THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    SELECT COALESCE(array_agg(n ORDER BY ord), '{}') INTO v_novos
      FROM (SELECT n, min(ord) AS ord FROM unnest(p_numeros) WITH ORDINALITY AS t(n, ord) GROUP BY n) d;
    IF cardinality(v_novos) > 100
       OR EXISTS (SELECT 1 FROM unnest(v_novos) AS n WHERE n !~ '^\+[0-9]{8,15}$') THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    IF v_novos IS DISTINCT FROM v_antes THEN
        UPDATE agents.agents SET contatos_permitidos = v_novos WHERE id = p_agent_id AND org_id = p_org_id;
        INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
        VALUES (p_org_id, p_agent_id, p_actor, 'contatos_permitidos_alterados',
                jsonb_build_object('total', cardinality(v_antes)),
                jsonb_build_object('total', cardinality(v_novos)));
    END IF;
END
$$;

REVOKE ALL ON FUNCTION agents.set_agent_contatos_permitidos(UUID, UUID, TEXT[], UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.set_agent_contatos_permitidos(UUID, UUID, TEXT[], UUID) TO service_role;
