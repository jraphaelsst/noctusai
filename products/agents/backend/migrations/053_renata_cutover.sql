-- ============================================================================
-- 053_renata_cutover.sql -- the academia agent moves off the code-defined chat runtime (agents-unified,
-- Renata cutover; runbook products/agents/projects/agents-unified/RENATA-CUTOVER.md).
--
--   1. `agents.agents.definition_mode` gains 'arquivado': a RETIRED code-defined agent. Its row stays (every
--      history table references it by id), its key is renamed so the key is FREE for a new agent, and no listing,
--      chat path or seed treats it as live (`AgentRecord.chat_legado` needs 'legacy').
--   2. The audit CHECK admits the two new definition events, 'historico_transferido' and 'agente_arquivado'
--      (the list equals `app.stores.studio_definitions.AUDIT_ACOES`; tests/test_migration_audit_acao_check.py pins
--      the LATEST definition across all migrations to that tuple).
--   3. `agents.transferir_historico_agente` -- ONE transaction: the in-app conversations of a code-defined agent
--      (and with them every row hanging off a conversation: messages, approvals, session transcripts) move to a
--      Studio agent of the SAME org; the tokens bound to the old agent as principal (agents.api_tokens, and
--      academia_de_reciclagem.api_tokens when that schema exists) are re-bound. Counts first;
--      writes only with p_executar. Idempotent: a second run finds nothing left on the source and writes nothing.
--   4. `agents.arquivar_agente_legado` -- retires the code-defined rows of a key (one org, or every org with
--      p_org_id NULL): refuses (nothing written) while any of them still owns a conversation.
--   5. The academia principal credential is renamed `bia_agent_id` -> `academia_agent_id` (the setting's neutral
--      name; the env var BIA_AGENT_ID is still read, logged as deprecated).
--
-- Both functions are SECURITY DEFINER, service_role only (REVOKE from PUBLIC/anon/authenticated in this file).
-- Forward-only; re-run safe (CHECKs dropped by definition and re-added; CREATE OR REPLACE; guarded UPDATE).
-- ============================================================================

SET search_path = agents, public;

-- ── 1. definition_mode admits 'arquivado' ──────────────────────────────────
DO $$
DECLARE
    v_con TEXT;
BEGIN
    FOR v_con IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'agents.agents'::regclass
           AND contype = 'c'
           AND pg_get_constraintdef(oid) ILIKE '%definition_mode%'
    LOOP
        EXECUTE format('ALTER TABLE agents.agents DROP CONSTRAINT %I', v_con);
    END LOOP;
END
$$;

ALTER TABLE agents.agents
    ADD CONSTRAINT agents_definition_mode_check
        CHECK (definition_mode IN ('legacy', 'studio', 'arquivado'));


-- ── 2. audit actions ───────────────────────────────────────────────────────
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
            'historico_transferido', 'agente_arquivado'
        ));


-- ── 3. history transfer ────────────────────────────────────────────────────
-- Raises (P0001): transferir_origem_invalida (not this org's code-defined agent) · transferir_destino_invalido (not
-- this org's Studio agent) · transferir_mesmo_agente.
CREATE OR REPLACE FUNCTION agents.transferir_historico_agente(
    p_org_id UUID,
    p_source_id UUID,
    p_target_id UUID,
    p_actor UUID,
    p_executar BOOLEAN
)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_src agents.agents;
    v_tgt agents.agents;
    v_conversas INT;
    v_mensagens INT;
    v_aprovacoes INT;
    v_transcricoes INT;
    v_tokens INT;
    v_tokens_academia INT := 0;
    v_tem_academia BOOLEAN := to_regclass('academia_de_reciclagem.api_tokens') IS NOT NULL;
    v_contagens JSONB;
    v_escreve BOOLEAN;
BEGIN
    IF p_source_id = p_target_id THEN
        RAISE EXCEPTION 'transferir_mesmo_agente' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_src FROM agents.agents WHERE id = p_source_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'transferir_origem_invalida' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_tgt FROM agents.agents WHERE id = p_target_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'transferir_destino_invalido' USING ERRCODE = 'P0001';
    END IF;
    -- an already-retired source is accepted (it owns nothing: arquivar refuses while it does) so a re-run is a no-op.
    IF v_src.definition_mode NOT IN ('legacy', 'arquivado') THEN
        RAISE EXCEPTION 'transferir_origem_invalida' USING ERRCODE = 'P0001';
    END IF;
    IF v_tgt.definition_mode <> 'studio' THEN
        RAISE EXCEPTION 'transferir_destino_invalido' USING ERRCODE = 'P0001';
    END IF;

    SELECT count(*) INTO v_conversas
      FROM agents.conversations c WHERE c.org_id = p_org_id AND c.agent_id = p_source_id;
    SELECT count(*) INTO v_mensagens
      FROM agents.messages m JOIN agents.conversations c ON c.id = m.conversation_id
     WHERE c.org_id = p_org_id AND c.agent_id = p_source_id;
    SELECT count(*) INTO v_aprovacoes
      FROM agents.approvals a JOIN agents.conversations c ON c.id = a.conversation_id
     WHERE c.org_id = p_org_id AND c.agent_id = p_source_id;
    SELECT count(*) INTO v_transcricoes
      FROM agents.session_transcript_entries t JOIN agents.conversations c ON c.id = t.conversation_id
     WHERE c.org_id = p_org_id AND c.agent_id = p_source_id;
    SELECT count(*) INTO v_tokens
      FROM agents.api_tokens k WHERE k.org_id = p_org_id AND k.principal_agent_id = p_source_id;
    -- The academia product verifies an approval assertion's `sub` against ITS token's principal (academia 008);
    -- agent ids are global UUIDs, so the principal alone names the rows. Skipped where academia is not installed.
    IF v_tem_academia THEN
        EXECUTE 'SELECT count(*) FROM academia_de_reciclagem.api_tokens WHERE principal_agent_id = $1'
           INTO v_tokens_academia USING p_source_id;
    END IF;

    v_contagens := jsonb_build_object(
        'conversas', v_conversas, 'mensagens', v_mensagens, 'aprovacoes', v_aprovacoes,
        'transcricoes', v_transcricoes, 'tokens', v_tokens, 'tokens_academia', v_tokens_academia
    );
    v_escreve := p_executar AND (v_conversas + v_tokens + v_tokens_academia) > 0;

    IF v_escreve THEN
        -- messages / approvals / transcripts reference the conversation, so they move with it.
        UPDATE agents.conversations SET agent_id = p_target_id
         WHERE org_id = p_org_id AND agent_id = p_source_id;
        UPDATE agents.api_tokens SET principal_agent_id = p_target_id
         WHERE org_id = p_org_id AND principal_agent_id = p_source_id;
        IF v_tem_academia THEN
            EXECUTE 'UPDATE academia_de_reciclagem.api_tokens SET principal_agent_id = $1 WHERE principal_agent_id = $2'
              USING p_target_id, p_source_id;
        END IF;
        INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
        VALUES (
            p_org_id, p_target_id, p_actor, 'historico_transferido',
            jsonb_build_object('de_key', v_src.key, 'de_agent_id', p_source_id),
            v_contagens || jsonb_build_object('para_key', v_tgt.key)
        );
    END IF;

    RETURN v_contagens || jsonb_build_object('executado', v_escreve);
END;
$$;

REVOKE ALL ON FUNCTION agents.transferir_historico_agente(UUID, UUID, UUID, UUID, BOOLEAN)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.transferir_historico_agente(UUID, UUID, UUID, UUID, BOOLEAN) TO service_role;


-- ── 4. retire the code-defined rows of a key ───────────────────────────────
-- p_org_id NULL = every org. Raises (P0001) arquivar_historico_pendente when p_executar and any row still owns a
-- conversation (nothing is written: move the history first).
CREATE OR REPLACE FUNCTION agents.arquivar_agente_legado(
    p_key TEXT,
    p_org_id UUID,
    p_actor UUID,
    p_executar BOOLEAN
)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_linhas INT;
    v_com_historico INT;
    v_row agents.agents;
    v_nova TEXT;
BEGIN
    SELECT count(*) INTO v_linhas FROM agents.agents a
     WHERE a.key = p_key AND a.definition_mode = 'legacy' AND (p_org_id IS NULL OR a.org_id = p_org_id);
    SELECT count(DISTINCT a.id) INTO v_com_historico
      FROM agents.agents a JOIN agents.conversations c ON c.agent_id = a.id
     WHERE a.key = p_key AND a.definition_mode = 'legacy' AND (p_org_id IS NULL OR a.org_id = p_org_id);

    IF p_executar AND v_com_historico > 0 THEN
        RAISE EXCEPTION 'arquivar_historico_pendente' USING ERRCODE = 'P0001';
    END IF;

    IF p_executar THEN
        FOR v_row IN
            SELECT * FROM agents.agents a
             WHERE a.key = p_key AND a.definition_mode = 'legacy' AND (p_org_id IS NULL OR a.org_id = p_org_id)
             FOR UPDATE
        LOOP
            v_nova := v_row.key || '-arquivado-' || left(v_row.id::text, 8);
            UPDATE agents.agents
               SET definition_mode = 'arquivado', ativo = false, key = v_nova
             WHERE id = v_row.id;
            INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
            VALUES (
                v_row.org_id, v_row.id, p_actor, 'agente_arquivado',
                jsonb_build_object('key', v_row.key, 'definition_mode', v_row.definition_mode, 'ativo', v_row.ativo),
                jsonb_build_object('key', v_nova, 'definition_mode', 'arquivado', 'ativo', false)
            );
        END LOOP;
    END IF;

    RETURN jsonb_build_object(
        'linhas', v_linhas, 'com_historico', v_com_historico, 'executado', p_executar AND v_linhas > 0
    );
END;
$$;

REVOKE ALL ON FUNCTION agents.arquivar_agente_legado(TEXT, UUID, UUID, BOOLEAN)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.arquivar_agente_legado(TEXT, UUID, UUID, BOOLEAN) TO service_role;


-- ── 5. credential rename ───────────────────────────────────────────────────
UPDATE agents.app_integration_config c
   SET key = 'academia_agent_id'
 WHERE c.key = 'bia_agent_id'
   AND NOT EXISTS (SELECT 1 FROM agents.app_integration_config d WHERE d.key = 'academia_agent_id');
