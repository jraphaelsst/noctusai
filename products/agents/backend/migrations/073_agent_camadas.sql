-- ============================================================================
-- 073_agent_camadas.sql -- agent LAYERS: BASE -> SDR -> agent (roadmap agent-templates-2026-11, owner rules
-- 2026-11-09). A child agent holds only its own rows; the app merges the parent chain (app/studio/camadas.py).
--
-- 1. agents.agents.modelo      -- a TEMPLATE (agente-base, sdr-base): a platform definition that only exists to be
--    inherited and evaluated. Never instanced into an org, never wired to a channel (the app refuses both).
-- 2. agents.agents.pai_agent_id -- the template this agent inherits from. Same org, must be a template, no cycle,
--    chain at most 4 deep. Raises pai_invalido.
-- 3. agents.agent_versions.pai_versao_id -- the parent's PUBLISHED version a published child pins. Written ONLY
--    by publish_agent_version (the rascunho -> ativa transition); any other write raises pai_invalido.
-- 4. publish_agent_version gains p_pai_versao_id: the pin must be the parent's CURRENT active version
--    (pai_nao_publicado / pai_desatualizado); every 072 gate is unchanged.
--
-- Forward-only + idempotent.
-- ============================================================================

SET search_path = agents, public;

-- ── 1 + 2. template flag and parent link ─────────────────────────────────────────

ALTER TABLE agents.agents
    ADD COLUMN IF NOT EXISTS modelo BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS pai_agent_id UUID NULL REFERENCES agents.agents(id) ON DELETE RESTRICT;

ALTER TABLE agents.agents DROP CONSTRAINT IF EXISTS agents_camada_check;
ALTER TABLE agents.agents ADD CONSTRAINT agents_camada_check
    CHECK ((NOT modelo OR definition_scope = 'plataforma') AND (pai_agent_id IS NULL OR pai_agent_id <> id));

CREATE INDEX IF NOT EXISTS idx_agents_pai_agent_id ON agents.agents (pai_agent_id) WHERE pai_agent_id IS NOT NULL;

CREATE OR REPLACE FUNCTION agents.guard_agent_camada()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_pai agents.agents;
    v_cursor UUID;
    v_nivel INT := 1;
BEGIN
    IF NEW.pai_agent_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.pai_agent_id IS NOT DISTINCT FROM OLD.pai_agent_id THEN
        RETURN NEW;
    END IF;
    SELECT * INTO v_pai FROM agents.agents WHERE id = NEW.pai_agent_id;
    IF NOT FOUND OR v_pai.org_id <> NEW.org_id OR NOT v_pai.modelo THEN
        RAISE EXCEPTION 'pai_invalido' USING ERRCODE = 'P0001';
    END IF;
    v_cursor := v_pai.pai_agent_id;
    WHILE v_cursor IS NOT NULL LOOP
        v_nivel := v_nivel + 1;
        IF v_cursor = NEW.id OR v_nivel >= 4 THEN
            RAISE EXCEPTION 'pai_invalido' USING ERRCODE = 'P0001';
        END IF;
        SELECT a.pai_agent_id INTO v_cursor FROM agents.agents a WHERE a.id = v_cursor;
    END LOOP;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION agents.guard_agent_camada() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_agent_camada() TO service_role;

CREATE OR REPLACE TRIGGER guard_agent_camada
    BEFORE INSERT OR UPDATE OF pai_agent_id ON agents.agents
    FOR EACH ROW EXECUTE FUNCTION agents.guard_agent_camada();

-- ── 3. the published pin ──────────────────────────────────────────────────────────

ALTER TABLE agents.agent_versions
    ADD COLUMN IF NOT EXISTS pai_versao_id UUID NULL REFERENCES agents.agent_versions(id) ON DELETE RESTRICT;

CREATE OR REPLACE FUNCTION agents.guard_version_pai_pin()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.pai_versao_id IS NOT NULL THEN
            RAISE EXCEPTION 'pai_invalido' USING ERRCODE = 'P0001';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.pai_versao_id IS DISTINCT FROM OLD.pai_versao_id
       AND NOT (OLD.status = 'rascunho' AND NEW.status = 'ativa') THEN
        RAISE EXCEPTION 'pai_invalido' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION agents.guard_version_pai_pin() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_version_pai_pin() TO service_role;

CREATE OR REPLACE TRIGGER guard_version_pai_pin
    BEFORE INSERT OR UPDATE OF pai_versao_id ON agents.agent_versions
    FOR EACH ROW EXECUTE FUNCTION agents.guard_version_pai_pin();

-- ── 4. publish pins the parent ────────────────────────────────────────────────────

DROP FUNCTION IF EXISTS agents.publish_agent_version(UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, JSONB);

CREATE OR REPLACE FUNCTION agents.publish_agent_version(
    p_org_id UUID,
    p_version_id UUID,
    p_published_by UUID,
    p_eval_run_id UUID,
    p_override_reason TEXT,
    p_expected_hash TEXT,
    p_texto TEXT,
    p_manifest JSONB,
    p_pai_versao_id UUID
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_row agents.agent_versions;
    v_prev agents.agent_versions;
    v_limiar NUMERIC(4,3);
    v_score NUMERIC(4,3);
    v_reason TEXT := NULLIF(btrim(p_override_reason, E' \t\r\n'), '');
    v_mec agents.eval_mecanismo_runs;
    v_mec_cases INT;
    v_mec_exige BOOLEAN;
    v_pai_agent UUID;
    v_pai_ativa UUID;
BEGIN
    SELECT * INTO v_row FROM agents.agent_versions
    WHERE id = p_version_id AND org_id = p_org_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF v_row.status <> 'rascunho' THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    IF p_expected_hash IS NULL OR v_row.compiled_hash IS DISTINCT FROM p_expected_hash THEN
        RAISE EXCEPTION 'draft_changed' USING ERRCODE = 'P0001';
    END IF;

    -- 073 layers: a child version pins its parent's CURRENT published version (FOR SHARE: a parent publish waits
    -- for this one). The router compiled the child against exactly this pin and found the evaluated hash, so a
    -- pin that moved in between is refused, never silently swapped. An agent without a parent pins nothing.
    SELECT a.pai_agent_id INTO v_pai_agent FROM agents.agents a WHERE a.id = v_row.agent_id AND a.org_id = p_org_id;
    IF v_pai_agent IS NULL THEN
        IF p_pai_versao_id IS NOT NULL THEN
            RAISE EXCEPTION 'pai_invalido' USING ERRCODE = 'P0001';
        END IF;
    ELSE
        SELECT v.id INTO v_pai_ativa FROM agents.agent_versions v
        WHERE v.agent_id = v_pai_agent AND v.status = 'ativa'
        FOR SHARE;
        IF v_pai_ativa IS NULL THEN
            RAISE EXCEPTION 'pai_nao_publicado' USING ERRCODE = 'P0001';
        END IF;
        IF p_pai_versao_id IS DISTINCT FROM v_pai_ativa THEN
            RAISE EXCEPTION 'pai_desatualizado' USING ERRCODE = 'P0001';
        END IF;
    END IF;

    -- Julia v2 A-EVAL: the mechanism suite is a hard gate with no override, enforced here so a direct
    -- DB publish cannot bypass the router. Required when the agent says so or has an active mecanismo
    -- case; satisfied only by the newest LIVE-driver run of THIS version for THIS hash that finished,
    -- was complete, stayed under budget and passed every case (an empty required suite is never green).
    SELECT a.exige_mecanismo INTO v_mec_exige FROM agents.agents a
    WHERE a.id = v_row.agent_id AND a.org_id = p_org_id;
    SELECT count(*) INTO v_mec_cases FROM agents.eval_cases c
    WHERE c.org_id = p_org_id AND c.agent_id = v_row.agent_id AND c.ativo AND c.suite = 'mecanismo';
    IF COALESCE(v_mec_exige, false) OR v_mec_cases > 0 THEN
        SELECT * INTO v_mec FROM agents.eval_mecanismo_runs r
        WHERE r.org_id = p_org_id AND r.version_id = p_version_id AND r.driver = 'live' AND r.status = 'concluida'
        ORDER BY r.finished_at DESC NULLS LAST, r.created_at DESC
        LIMIT 1;
        IF NOT FOUND
           OR v_mec.compiled_hash IS DISTINCT FROM p_expected_hash
           OR NOT v_mec.aprovado OR NOT v_mec.completa OR v_mec.orcamento_excedido
           OR (v_mec.total_casos < v_mec_cases
               AND NOT agents.eval_run_cobre_casos(p_org_id, v_row.agent_id, v_mec.id, 'mecanismo', 'mecanismo'))
           OR (EXISTS (SELECT 1 FROM agents.eval_casos_pulados p WHERE p.run_id = v_mec.id AND p.run_tipo = 'mecanismo')
               AND NOT agents.eval_run_cobre_casos(p_org_id, v_row.agent_id, v_mec.id, 'mecanismo', 'mecanismo'))
           OR v_mec.casos_aprovados <> v_mec.total_casos THEN
            RAISE EXCEPTION 'mecanismo_required' USING ERRCODE = 'P0001';
        END IF;
    END IF;

    -- FOR SHARE: a concurrent threshold change waits for this publish, so
    -- the snapshot is the threshold the gate was actually held to.
    SELECT publicacao_limiar INTO v_limiar FROM agents.agents
    WHERE id = v_row.agent_id AND org_id = p_org_id
    FOR SHARE;

    IF p_eval_run_id IS NOT NULL THEN
        SELECT r.score INTO v_score FROM agents.eval_runs r
        WHERE r.id = p_eval_run_id
          AND r.org_id = p_org_id
          AND r.version_id = p_version_id
          AND r.status = 'concluida'
          AND r.completa
          AND r.total >= 1
          AND r.compiled_hash = p_expected_hash
          AND r.score IS NOT NULL
          AND r.score >= v_limiar;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'eval_required' USING ERRCODE = 'P0001';
        END IF;
        -- Consolidated coverage (owner decision 2026-11-09): a run that skipped consolidated cases only counts when EVERY
        -- active case is executed in it or still validly consolidated (state re-read NOW, threshold met).
        IF EXISTS (SELECT 1 FROM agents.eval_casos_pulados p WHERE p.run_id = p_eval_run_id AND p.run_tipo = 'comportamento')
           AND NOT agents.eval_run_cobre_casos(p_org_id, v_row.agent_id, p_eval_run_id, 'comportamento', 'comportamento') THEN
            RAISE EXCEPTION 'eval_required' USING ERRCODE = 'P0001';
        END IF;
        PERFORM 1 FROM agents.eval_cases c
        WHERE c.org_id = p_org_id AND c.agent_id = v_row.agent_id AND c.ativo;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'eval_required' USING ERRCODE = 'P0001';
        END IF;
        v_reason := NULL;
    ELSIF v_reason IS NULL OR length(regexp_replace(v_reason, '\s', '', 'g')) < 20 THEN
        RAISE EXCEPTION 'eval_required' USING ERRCODE = 'P0001';
    END IF;

    IF p_texto IS NULL OR p_manifest IS NULL THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO agents.compiled_prompts (org_id, hash, version_id, client_id, texto, manifest)
    VALUES (p_org_id, p_expected_hash, p_version_id, NULL, p_texto, p_manifest)
    ON CONFLICT (org_id, hash) DO NOTHING;

    SELECT * INTO v_prev FROM agents.agent_versions
    WHERE org_id = p_org_id AND agent_id = v_row.agent_id AND status = 'ativa'
    FOR UPDATE;

    UPDATE agents.agent_versions
    SET status = 'substituida'
    WHERE org_id = p_org_id AND agent_id = v_row.agent_id AND status = 'ativa';

    UPDATE agents.agent_versions
    SET status = 'ativa',
        published_by = p_published_by,
        published_at = now(),
        eval_run_id = p_eval_run_id,
        publish_override_reason = v_reason,
        limiar_aplicado = v_limiar,
        eval_score = v_score,
        pai_versao_id = p_pai_versao_id
    WHERE id = p_version_id AND org_id = p_org_id;

    INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
    VALUES (
        p_org_id, v_row.agent_id, p_published_by,
        CASE WHEN p_eval_run_id IS NULL THEN 'publicado_override' ELSE 'publicado' END,
        CASE WHEN v_prev.id IS NULL THEN NULL
             ELSE jsonb_build_object('version_id', v_prev.id, 'versao', v_prev.versao) END,
        jsonb_build_object(
            'version_id', v_row.id, 'versao', v_row.versao, 'compiled_hash', v_row.compiled_hash,
            'eval_run_id', p_eval_run_id, 'eval_score', v_score, 'limiar_aplicado', v_limiar,
            'override_reason', v_reason, 'pai_versao_id', p_pai_versao_id
        )
    );
END;
$$;

REVOKE ALL ON FUNCTION agents.publish_agent_version(UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, JSONB, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.publish_agent_version(UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, JSONB, UUID) TO service_role;
