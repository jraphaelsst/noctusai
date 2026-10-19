-- ============================================================================
-- 034_julia_v2_controles.sql -- the agent's controls: ligado / drenando /
-- desligado (Julia v2, A-THREAD; contract section 5, owner answers 0.3 Q3/Q5).
--
-- 1. agents.agents.modo_operacao -- the single source of "may this agent take a
--    lead": ligado (replies), drenando (keeps chatting in threads already open,
--    takes no new lead), desligado (replies to nobody). DEFAULT 'desligado':
--    a brand-new agent is off until the owner turns it on. Existing ACTIVE
--    agents are backfilled to 'ligado' so this migration switches nobody off.
-- 2. agents.agents.dreno_inatividade_dias -- an open thread idle this many days
--    counts as closed for the drain (Q3, default 7, editable in Studio).
-- 3. `ativo` stays for ONE release as a trigger-maintained mirror of
--    `modo_operacao <> 'desligado'`, so every pre-v2 reader (the legacy
--    `agent_inactive` gate, the toggle route) keeps working and stays consistent
--    with the new column. The sync is two-way on purpose: a legacy writer that
--    still sets `ativo` moves `modo_operacao` (ativo=true on an off agent -> ligado;
--    ativo=false -> desligado); a write that sets `modo_operacao` always wins.
-- 4. Every change of modo/dreno lands in agent_audit_log ('modo_alterado'), whatever
--    the write path (trigger; the actor is the transaction-local
--    `agents.audit_actor` that agents.set_agent_modo sets, like the threshold audit).
-- 5. agent_audit_log.acao CHECK grows modo_alterado / conversa_pausada /
--    conversa_retomada (+ conteudo_editado_mcp / padrao_publicado from the content
--    slice). The CHECK is rebuilt with the FULL union of the contract's list, so
--    it does not matter which of the two slices' migrations runs last.
--
-- Idempotent. NOT applied to any database by this slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

-- ── 1/2. columns ──────────────────────────────────────────────────────────

ALTER TABLE agents.agents
    ADD COLUMN IF NOT EXISTS modo_operacao TEXT NOT NULL DEFAULT 'desligado';
ALTER TABLE agents.agents
    ADD COLUMN IF NOT EXISTS dreno_inatividade_dias INTEGER NOT NULL DEFAULT 7;

ALTER TABLE agents.agents DROP CONSTRAINT IF EXISTS agents_modo_operacao_check;
ALTER TABLE agents.agents
    ADD CONSTRAINT agents_modo_operacao_check
        CHECK (modo_operacao IN ('ligado', 'drenando', 'desligado'));

ALTER TABLE agents.agents DROP CONSTRAINT IF EXISTS agents_dreno_inatividade_dias_check;
ALTER TABLE agents.agents
    ADD CONSTRAINT agents_dreno_inatividade_dias_check
        CHECK (dreno_inatividade_dias BETWEEN 1 AND 365);

-- Backfill BEFORE the sync trigger exists: an agent that is active today stays on.
UPDATE agents.agents
   SET modo_operacao = 'ligado'
 WHERE ativo AND modo_operacao = 'desligado';

-- ── 3. ativo <-> modo_operacao ────────────────────────────────────────────

CREATE OR REPLACE FUNCTION agents.sync_agent_modo_ativo()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- A legacy insert that only knows `ativo`.
        IF NEW.ativo AND NEW.modo_operacao = 'desligado' THEN
            NEW.modo_operacao := 'ligado';
        END IF;
    ELSIF NEW.modo_operacao IS DISTINCT FROM OLD.modo_operacao THEN
        NULL; -- the new column wins; ativo is derived below
    ELSIF NEW.ativo IS DISTINCT FROM OLD.ativo THEN
        -- A legacy writer flipped `ativo` only.
        IF NEW.ativo THEN
            IF NEW.modo_operacao = 'desligado' THEN
                NEW.modo_operacao := 'ligado';
            END IF;
        ELSE
            NEW.modo_operacao := 'desligado';
        END IF;
    END IF;
    NEW.ativo := (NEW.modo_operacao <> 'desligado');
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.sync_agent_modo_ativo() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.sync_agent_modo_ativo() TO service_role;

DROP TRIGGER IF EXISTS sync_agent_modo_ativo ON agents.agents;
CREATE TRIGGER sync_agent_modo_ativo
    BEFORE INSERT OR UPDATE ON agents.agents
    FOR EACH ROW EXECUTE FUNCTION agents.sync_agent_modo_ativo();

-- Rows already out of step (an agent left active=false with a stale mode, ...).
UPDATE agents.agents SET ativo = (modo_operacao <> 'desligado')
 WHERE ativo IS DISTINCT FROM (modo_operacao <> 'desligado');

-- ── 5. audit CHECK (before the audit trigger can write 'modo_alterado') ────

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
            'modo_alterado', 'conversa_pausada', 'conversa_retomada',
            'conteudo_editado_mcp', 'padrao_publicado'
        ));

-- ── 4. audit + the transactional setter ───────────────────────────────────

CREATE OR REPLACE FUNCTION agents.audit_agent_modo_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
BEGIN
    INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
    VALUES (
        NEW.org_id, NEW.id,
        NULLIF(current_setting('agents.audit_actor', true), '')::UUID,
        'modo_alterado',
        jsonb_build_object('modo_operacao', OLD.modo_operacao, 'dreno_inatividade_dias', OLD.dreno_inatividade_dias),
        jsonb_build_object('modo_operacao', NEW.modo_operacao, 'dreno_inatividade_dias', NEW.dreno_inatividade_dias)
    );
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.audit_agent_modo_change() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.audit_agent_modo_change() TO service_role;

DROP TRIGGER IF EXISTS audit_agent_modo_change ON agents.agents;
CREATE TRIGGER audit_agent_modo_change
    AFTER UPDATE ON agents.agents
    FOR EACH ROW
    WHEN (OLD.modo_operacao IS DISTINCT FROM NEW.modo_operacao
          OR OLD.dreno_inatividade_dias IS DISTINCT FROM NEW.dreno_inatividade_dias)
    EXECUTE FUNCTION agents.audit_agent_modo_change();

-- (No `UPDATE OF <cols>` list on purpose: it fires only for columns named in the SET
-- clause, and a legacy `SET ativo` reaches modo_operacao through the BEFORE sync trigger.)

-- Change the mode (and optionally the drain idle days) with an attributed audit
-- row, in one transaction. NULL `p_dreno_dias` keeps the current value. Raises
-- `agent_not_found`, `invalid_payload` (unknown mode / days out of 1..365).
CREATE OR REPLACE FUNCTION agents.set_agent_modo(
    p_org_id UUID,
    p_agent_id UUID,
    p_modo TEXT,
    p_dreno_dias INTEGER,
    p_actor UUID
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
BEGIN
    IF p_modo NOT IN ('ligado', 'drenando', 'desligado')
       OR (p_dreno_dias IS NOT NULL AND p_dreno_dias NOT BETWEEN 1 AND 365) THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    PERFORM set_config('agents.audit_actor', COALESCE(p_actor::TEXT, ''), true);
    UPDATE agents.agents
       SET modo_operacao = p_modo,
           dreno_inatividade_dias = COALESCE(p_dreno_dias, dreno_inatividade_dias)
     WHERE id = p_agent_id AND org_id = p_org_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent_not_found' USING ERRCODE = 'P0001';
    END IF;
    PERFORM set_config('agents.audit_actor', '', true);
END;
$$;

REVOKE ALL ON FUNCTION agents.set_agent_modo(UUID, UUID, TEXT, INTEGER, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.set_agent_modo(UUID, UUID, TEXT, INTEGER, UUID) TO service_role;
