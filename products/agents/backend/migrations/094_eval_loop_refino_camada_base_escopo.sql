-- 094_eval_loop_refino_camada_base_escopo.sql -- the refine's `camada_base` refusal no longer treats platform scope as a base layer.
--
-- Every Studio-authored agent is definition_scope='plataforma' (the per-org runtime copies are 'instancia' rows running the PUBLISHED
-- version), so 093's "scope = plataforma OR has a child" refused every Studio agent and auto-improvement could never run. New rule: a base
-- layer = an agent that is the PARENT of another agent (some agents.agents row has pai_agent_id = its id). The refine edits only the
-- agent's own DRAFT; publishing stays human-only and 093 still blocks publish while an edit is unreviewed. Every other 093 guard is
-- unchanged. Forward-only and idempotent (CREATE OR REPLACE, same signature, same SECURITY DEFINER / search_path / grants).

SET search_path = agents, public;

CREATE OR REPLACE FUNCTION agents.aplicar_refinamento_loop(
    p_org_id UUID,
    p_loop_id UUID,
    p_rodada_seq INT,
    p_evento TEXT,
    p_detalhe JSONB,
    p_custo_usd NUMERIC,
    p_version_id UUID DEFAULT NULL,
    p_tipo TEXT DEFAULT NULL,
    p_chave TEXT DEFAULT NULL,
    p_antes TEXT DEFAULT NULL,
    p_depois TEXT DEFAULT NULL,
    p_expected_hash TEXT DEFAULT NULL,
    p_protegidas TEXT[] DEFAULT '{}'
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_loop_status TEXT;
    v_loop_agent UUID;
    v_ver_agent UUID;
    v_scope TEXT;
    v_status TEXT;
    v_hash TEXT;
    v_regras TEXT[];
    v_n INT;
    v_id UUID;
BEGIN
    IF p_evento NOT IN ('refinamento_proposto', 'refinamento_recusado', 'refinamento_sem_edicao') THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    IF p_custo_usd IS NULL OR p_custo_usd < 0 THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;

    SELECT status, agent_id INTO v_loop_status, v_loop_agent FROM agents.eval_loops WHERE id = p_loop_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'loop_not_found' USING ERRCODE = 'P0001';
    END IF;

    IF p_evento = 'refinamento_proposto' THEN
        IF v_loop_status <> 'ativo' THEN
            RAISE EXCEPTION 'loop_encerrado' USING ERRCODE = 'P0001';
        END IF;
        IF p_version_id IS NULL OR p_tipo IS NULL OR p_chave IS NULL OR p_antes IS NULL OR p_depois IS NULL
           OR p_expected_hash IS NULL OR p_antes = p_depois THEN
            RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
        END IF;
        SELECT status, compiled_hash, agent_id INTO v_status, v_hash, v_ver_agent FROM agents.agent_versions
        WHERE id = p_version_id AND org_id = p_org_id
        FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
        END IF;
        IF v_status <> 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;

        -- the version is the loop agent's own (a refine never writes into another agent's draft)
        IF v_ver_agent IS DISTINCT FROM v_loop_agent THEN
            RAISE EXCEPTION 'versao_de_outro_agente' USING ERRCODE = 'P0001';
        END IF;
        -- never a base layer: an agent other agents inherit from (platform scope alone is NOT one)
        SELECT definition_scope INTO v_scope FROM agents.agents WHERE id = v_loop_agent AND org_id = p_org_id;
        IF v_scope IS NULL
           OR EXISTS (SELECT 1 FROM agents.agents a WHERE a.pai_agent_id = v_loop_agent) THEN
            RAISE EXCEPTION 'camada_base' USING ERRCODE = 'P0001';
        END IF;
        -- never a protective row (the SAME patterns as app/studio/eval_loop_refino_protegido.py)
        IF p_tipo = 'secao' THEN
            IF lower(p_chave) ~ 'opt[-_]?out|seguranca|transferencia|privacidade|honestidade|identidade|obrigac' THEN
                RAISE EXCEPTION 'linha_protegida' USING ERRCODE = 'P0001';
            END IF;
            SELECT regras INTO v_regras FROM agents.agent_prompt_sections
            WHERE version_id = p_version_id AND org_id = p_org_id AND chave = p_chave;
            IF v_regras IS NOT NULL AND cardinality(v_regras) > 0 THEN
                RAISE EXCEPTION 'linha_protegida' USING ERRCODE = 'P0001';
            END IF;
        ELSIF p_tipo = 'ferramenta' THEN
            IF lower(p_chave) ~ 'handoff|encerr|titular|consentimento|alerta|opt[-_]?out' THEN
                RAISE EXCEPTION 'linha_protegida' USING ERRCODE = 'P0001';
            END IF;
        END IF;
        IF (p_tipo || ':' || p_chave) = ANY (COALESCE(p_protegidas, '{}')) THEN
            RAISE EXCEPTION 'linha_protegida' USING ERRCODE = 'P0001';
        END IF;
        -- the caps: 3 edits per loop, 1 per row
        SELECT count(*) INTO v_n FROM agents.eval_loop_eventos WHERE loop_id = p_loop_id AND evento = 'refinamento_proposto';
        IF v_n >= 3 THEN
            RAISE EXCEPTION 'limite_de_refinos' USING ERRCODE = 'P0001';
        END IF;
        IF EXISTS (SELECT 1 FROM agents.eval_loop_eventos
                    WHERE loop_id = p_loop_id AND evento = 'refinamento_proposto'
                      AND detalhe -> 'alvo' ->> 'tipo' = p_tipo AND detalhe -> 'alvo' ->> 'chave' = p_chave) THEN
            RAISE EXCEPTION 'linha_ja_refinada' USING ERRCODE = 'P0001';
        END IF;

        -- compare-and-set on the draft (the row is locked above: the compare and the write are one step) AND on the row's old text
        IF v_hash IS DISTINCT FROM p_expected_hash THEN
            RAISE EXCEPTION 'conflito_de_versao' USING ERRCODE = 'P0001';
        END IF;

        IF p_tipo = 'secao' THEN
            UPDATE agents.agent_prompt_sections SET conteudo = p_depois
            WHERE version_id = p_version_id AND org_id = p_org_id AND chave = p_chave AND conteudo = p_antes AND cardinality(regras) = 0;
        ELSIF p_tipo = 'texto' THEN
            UPDATE agents.agent_version_textos SET conteudo = p_depois
            WHERE version_id = p_version_id AND org_id = p_org_id AND chave = p_chave AND conteudo = p_antes;
        ELSIF p_tipo = 'ferramenta' THEN
            UPDATE agents.agent_version_ferramentas SET descricao = p_depois
            WHERE version_id = p_version_id AND org_id = p_org_id AND ferramenta = p_chave AND descricao = p_antes;
        ELSE
            RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
        END IF;
        GET DIAGNOSTICS v_n = ROW_COUNT;
        IF v_n <> 1 THEN
            RAISE EXCEPTION 'linha_alterada' USING ERRCODE = 'P0001';
        END IF;
    END IF;

    IF p_custo_usd > 0 THEN
        UPDATE agents.eval_loops SET gasto_usd = round(gasto_usd + p_custo_usd, 4)
        WHERE id = p_loop_id AND org_id = p_org_id;
    END IF;

    -- UNIQUE (loop_id, rodada_seq) over the three refine decisions: a racing second decision rolls the whole transaction back
    INSERT INTO agents.eval_loop_eventos (org_id, loop_id, rodada_seq, evento, detalhe)
    VALUES (p_org_id, p_loop_id, p_rodada_seq, p_evento, COALESCE(p_detalhe, '{}'::jsonb))
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

REVOKE ALL ON FUNCTION agents.aplicar_refinamento_loop(UUID, UUID, INT, TEXT, JSONB, NUMERIC, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT[])
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.aplicar_refinamento_loop(UUID, UUID, INT, TEXT, JSONB, NUMERIC, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT[])
    TO service_role;
