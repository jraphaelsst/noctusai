-- ============================================================================
-- 048_agent_lifecycle_delete.sql -- an agent can be DELETED (and the audit log survives it).
--
--   Until now no path deleted an agent: `agent_audit_log.agent_id` was NOT NULL REFERENCES agents(id) behind an
--   append-only trigger, so even an empty, never-published shell was undeletable. This migration:
--
--   1. snapshots the agent's identity onto every audit row (`agent_key`, `agent_nome`; backfilled, and filled by a
--      BEFORE INSERT trigger from then on) so a row still says WHICH agent it was about after the agent is gone;
--   2. makes `agent_id` nullable with ON DELETE SET NULL -- the audit rows OUTLIVE the agent;
--   3. teaches the append-only guard exactly ONE mutation: `agent_id` -> NULL, and only while the
--      transaction-local flag `agents.agent_delete` is on (the `agents.excluir_agente` RPC sets it around its
--      DELETE; same carve-out shape as core.audit_logs' purge flag and `agents.compiled_prompt_erasure`);
--   4. admits 'agente_excluido' / 'agente_criado' in the acao CHECK (matches AUDIT_ACOES -- the pin in
--      tests/test_migration_audit_acao_check.py reads the LAST definition);
--   5. `agents.excluir_agente(p_org_id, p_agent_id, p_actor)` -- SECURITY DEFINER, service_role only. It
--      re-checks the guards in SQL (a stale UI / a racing publish cannot slip past), deletes the dependents in FK
--      order, writes the tombstone audit row and deletes the agent. Guard codes are raised as
--      'excluir_agente_<codigo>' (distinct text: the Python mapper substring-matches P0001 messages).
--
-- Forward-only + idempotent.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. snapshot columns ──────────────────────────────────────────────────────
ALTER TABLE agents.agent_audit_log ADD COLUMN IF NOT EXISTS agent_key TEXT NULL;
ALTER TABLE agents.agent_audit_log ADD COLUMN IF NOT EXISTS agent_nome TEXT NULL;

-- Backfill: the append-only guard (and updated_at) would refuse/alter an UPDATE, so the USER triggers are off for
-- this one statement. Idempotent: only rows without a snapshot.
ALTER TABLE agents.agent_audit_log DISABLE TRIGGER USER;
UPDATE agents.agent_audit_log l
   SET agent_key = a.key, agent_nome = a.nome
  FROM agents.agents a
 WHERE a.id = l.agent_id AND l.agent_key IS NULL;
ALTER TABLE agents.agent_audit_log ENABLE TRIGGER USER;

-- ── 2. agent_id nullable, FK -> ON DELETE SET NULL ───────────────────────────
ALTER TABLE agents.agent_audit_log ALTER COLUMN agent_id DROP NOT NULL;

DO $$
DECLARE
    v_con TEXT;
BEGIN
    FOR v_con IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'agents.agent_audit_log'::regclass
           AND contype = 'f'
           AND confrelid = 'agents.agents'::regclass
    LOOP
        EXECUTE format('ALTER TABLE agents.agent_audit_log DROP CONSTRAINT %I', v_con);
    END LOOP;
END
$$;

ALTER TABLE agents.agent_audit_log
    ADD CONSTRAINT agent_audit_log_agent_id_fkey
        FOREIGN KEY (agent_id) REFERENCES agents.agents(id) ON DELETE SET NULL;

ALTER TABLE agents.agent_audit_log DROP CONSTRAINT IF EXISTS agent_audit_log_identifica_agente;
ALTER TABLE agents.agent_audit_log
    ADD CONSTRAINT agent_audit_log_identifica_agente
        CHECK (agent_id IS NOT NULL OR agent_key IS NOT NULL);

-- A new row carries the agent's identity without every writer having to say so.
CREATE OR REPLACE FUNCTION agents.audit_log_snapshot_agent()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    IF NEW.agent_id IS NOT NULL AND (NEW.agent_key IS NULL OR NEW.agent_nome IS NULL) THEN
        SELECT COALESCE(NEW.agent_key, a.key), COALESCE(NEW.agent_nome, a.nome)
          INTO NEW.agent_key, NEW.agent_nome
          FROM agents.agents a WHERE a.id = NEW.agent_id;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.audit_log_snapshot_agent() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.audit_log_snapshot_agent() TO service_role;

DROP TRIGGER IF EXISTS audit_log_snapshot_agent ON agents.agent_audit_log;
CREATE TRIGGER audit_log_snapshot_agent
    BEFORE INSERT ON agents.agent_audit_log
    FOR EACH ROW EXECUTE FUNCTION agents.audit_log_snapshot_agent();

-- ── 3. append-only guard with the single carve-out ───────────────────────────
CREATE OR REPLACE FUNCTION agents.guard_audit_log_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    -- The ONLY permitted mutation: the FK's SET NULL when `excluir_agente` deletes the agent (flag on), and
    -- only that column. Every other UPDATE, and every DELETE, still raises.
    IF TG_OP = 'UPDATE'
       AND current_setting('agents.agent_delete', true) = 'on'
       AND OLD.agent_id IS NOT NULL AND NEW.agent_id IS NULL
       AND NEW.id IS NOT DISTINCT FROM OLD.id
       AND NEW.org_id IS NOT DISTINCT FROM OLD.org_id
       AND NEW.actor IS NOT DISTINCT FROM OLD.actor
       AND NEW.acao IS NOT DISTINCT FROM OLD.acao
       AND NEW.antes IS NOT DISTINCT FROM OLD.antes
       AND NEW.depois IS NOT DISTINCT FROM OLD.depois
       AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
       AND NEW.agent_key IS NOT DISTINCT FROM OLD.agent_key
       AND NEW.agent_nome IS NOT DISTINCT FROM OLD.agent_nome THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'audit_log_append_only' USING ERRCODE = 'P0001';
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_audit_log_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_audit_log_append_only() TO service_role;

-- ── 4. the acao CHECK: 047's union + the two lifecycle actions ───────────────
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
            'agente_excluido', 'agente_criado'
        ));

-- ── 5. the deletion RPC ──────────────────────────────────────────────────────
-- Raises (P0001): agent_not_found | excluir_agente_publicado | excluir_agente_tem_instancias |
--                 excluir_agente_tem_conversas | excluir_agente_tem_canal | excluir_agente_ativo.
-- "tem_conversas" = any conversation of the agent holding >=1 message, any message the agent authored, or any
-- lead record it collected (history that must not vanish). Empty conversations are deleted with the agent.
-- "tem_canal" = an unrevoked, unexpired channel token whose principal is this agent.
CREATE OR REPLACE FUNCTION agents.excluir_agente(
    p_org_id UUID,
    p_agent_id UUID,
    p_actor UUID
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_agent agents.agents;
BEGIN
    SELECT * INTO v_agent FROM agents.agents WHERE id = p_agent_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent_not_found' USING ERRCODE = 'P0001';
    END IF;

    IF EXISTS (SELECT 1 FROM agents.agent_versions WHERE agent_id = p_agent_id AND status <> 'rascunho') THEN
        RAISE EXCEPTION 'excluir_agente_publicado' USING ERRCODE = 'P0001';
    END IF;
    IF v_agent.definition_scope = 'plataforma'
       AND EXISTS (SELECT 1 FROM agents.agents WHERE definition_agent_id = p_agent_id) THEN
        RAISE EXCEPTION 'excluir_agente_tem_instancias' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (
            SELECT 1 FROM agents.messages m JOIN agents.conversations c ON c.id = m.conversation_id
             WHERE c.agent_id = p_agent_id)
       OR EXISTS (SELECT 1 FROM agents.messages WHERE agent_id = p_agent_id)
       OR EXISTS (SELECT 1 FROM agents.lead_qualificacao_registros WHERE agent_id = p_agent_id)
       OR EXISTS (SELECT 1 FROM agents.lead_imovel_eventos WHERE agent_id = p_agent_id)
       OR EXISTS (SELECT 1 FROM agents.lead_identificacao WHERE coletado_por_agent_id = p_agent_id) THEN
        RAISE EXCEPTION 'excluir_agente_tem_conversas' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (
            SELECT 1 FROM agents.api_tokens
             WHERE principal_agent_id = p_agent_id AND revoked_at IS NULL
               AND (expires_at IS NULL OR expires_at > now())) THEN
        RAISE EXCEPTION 'excluir_agente_tem_canal' USING ERRCODE = 'P0001';
    END IF;
    IF v_agent.ativo OR v_agent.modo_operacao <> 'desligado' THEN
        RAISE EXCEPTION 'excluir_agente_ativo' USING ERRCODE = 'P0001';
    END IF;

    -- Dependents, leaves first. Conversations here are all empty (guard above); their thread_* children, session
    -- transcripts and lead back-references cascade / SET NULL by FK.
    DELETE FROM agents.approvals
     WHERE conversation_id IN (SELECT id FROM agents.conversations WHERE agent_id = p_agent_id);
    DELETE FROM agents.thread_handoffs WHERE de_agent_id = p_agent_id OR para_agent_id = p_agent_id;
    DELETE FROM agents.thread_participante_eventos WHERE agent_id = p_agent_id;
    DELETE FROM agents.thread_participantes WHERE agent_id = p_agent_id;
    DELETE FROM agents.conversations WHERE agent_id = p_agent_id;

    -- compiled_prompts are write-once; their erasure gate is the one `erase_compiled_prompts` uses.
    PERFORM set_config('agents.compiled_prompt_erasure', 'on', true);
    DELETE FROM agents.compiled_prompts
     WHERE version_id IN (SELECT id FROM agents.agent_versions WHERE agent_id = p_agent_id)
        OR client_id IN (SELECT id FROM agents.agent_clients WHERE agent_id = p_agent_id);
    PERFORM set_config('agents.compiled_prompt_erasure', 'off', true);

    UPDATE agents.agent_versions SET eval_run_id = NULL WHERE agent_id = p_agent_id AND eval_run_id IS NOT NULL;
    DELETE FROM agents.eval_mecanismo_runs WHERE agent_id = p_agent_id;
    DELETE FROM agents.eval_runs WHERE agent_id = p_agent_id;
    DELETE FROM agents.eval_cases WHERE agent_id = p_agent_id;
    DELETE FROM agents.knowledge_documents WHERE agent_id = p_agent_id;
    DELETE FROM agents.knowledge_collections WHERE agent_id = p_agent_id;
    DELETE FROM agents.agent_clients WHERE agent_id = p_agent_id;
    DELETE FROM agents.agent_package_trees WHERE agent_id = p_agent_id;
    DELETE FROM agents.agent_project_sources WHERE agent_id = p_agent_id;
    DELETE FROM agents.agent_learnings WHERE agent_id = p_agent_id;
    DELETE FROM agents.agent_personas WHERE agent_id = p_agent_id;
    DELETE FROM agents.agent_versions WHERE agent_id = p_agent_id;   -- drafts only (guard above)

    -- The tombstone: written with a NULL agent_id (the agent is about to stop existing); the snapshot columns
    -- say which agent it was. The older rows lose their agent_id through the FK's SET NULL under the flag.
    INSERT INTO agents.agent_audit_log (org_id, agent_id, agent_key, agent_nome, actor, acao, antes, depois)
    VALUES (
        p_org_id, NULL, v_agent.key, v_agent.nome, p_actor, 'agente_excluido',
        jsonb_build_object(
            'id', v_agent.id, 'key', v_agent.key, 'nome', v_agent.nome,
            'definition_scope', v_agent.definition_scope, 'conteudo_modo', v_agent.conteudo_modo
        ),
        NULL
    );

    PERFORM set_config('agents.agent_delete', 'on', true);
    DELETE FROM agents.agents WHERE id = p_agent_id AND org_id = p_org_id;
    PERFORM set_config('agents.agent_delete', 'off', true);
END;
$$;

REVOKE ALL ON FUNCTION agents.excluir_agente(UUID, UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.excluir_agente(UUID, UUID, UUID) TO service_role;
