-- 093_eval_loop_refino_endurecimento.sql -- red-team hardening of the eval-loop refine step (owner 2026-11-19; 092 may already be applied,
-- so nothing of 092 is edited: everything below is forward-only and idempotent).
--
-- 1. two more loop events: `refinamento_sem_edicao` (the refiner answered "nothing to edit": a person should look) and
--    `refinamento_revisado` (a platform admin accepted or reverted an edit the step wrote into the draft).
-- 2. one refine decision per (loop, base round) now also counts `refinamento_sem_edicao`; ONE review per (loop, round).
-- 3. `agents.aplicar_refinamento_loop` re-created with the checks the database makes BY ITSELF, whatever the caller sends:
--      * the version belongs to the loop's agent                          (versao_de_outro_agente)
--      * the agent is not a base layer: platform-scope definition, or the parent of another agent (camada_base)
--      * the row is not protective: a section that declares rules (regras <> '{}') or whose key is a must-have (opt-out / seguranca /
--        transferencia / privacidade / honestidade / identidade / obrigac*), a hand-off / stop / consent / data-subject / alert tool, or a
--        registry text the caller listed in `p_protegidas` ('texto:<chave>')                                      (linha_protegida)
--      * at most 3 edits per loop and 1 per row                           (limite_de_refinos / linha_ja_refinada)
--    The two key patterns are the SAME the app validator reads (app/studio/eval_loop_refino_protegido.py; a test keeps them equal).
--    The old 12-argument signature is DROPPED: it is the function without these checks.
-- 4. `agents.revisar_refinamento_loop`: the human review, atomic -- `aceito` records the event; `revertido` puts the row back through the
--    same compare-and-set (draft hash + the row's current text) and records the event, in ONE transaction.
-- Tier: Platform IP (service role only). The previous image calls the new function with the same named arguments (p_protegidas defaults).

SET search_path = agents, public;

-- 1 . widen the events CHECK (found by definition, not by name) ---------------------------------------------------------
DO $$
DECLARE c record;
BEGIN
    FOR c IN SELECT conname FROM pg_constraint
              WHERE contype = 'c' AND conrelid = 'agents.eval_loop_eventos'::regclass
                AND pg_get_constraintdef(oid) LIKE '%loop_iniciado%'
    LOOP
        EXECUTE format('ALTER TABLE agents.eval_loop_eventos DROP CONSTRAINT %I', c.conname);
    END LOOP;
END $$;
ALTER TABLE agents.eval_loop_eventos DROP CONSTRAINT IF EXISTS eval_loop_eventos_evento_check;
ALTER TABLE agents.eval_loop_eventos ADD CONSTRAINT eval_loop_eventos_evento_check CHECK (evento IN (
    'loop_iniciado', 'rodada_aberta', 'rodada_fechada', 'rodada_com_erro', 'run_com_erro', 'preflight_recusado',
    'driver_aguardando', 'driver_retomado', 'loop_parado', 'modo_alterado',
    'refinamento_proposto', 'refinamento_recusado', 'refinamento_sem_edicao', 'refinamento_avaliado', 'refinamento_revisado'));

-- 2 . one decision per (loop, base round) incl. "no edit"; one review per (loop, round) ---------------------------------
DROP INDEX IF EXISTS agents.uq_agents_eval_loop_eventos_refino_por_rodada;
CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_eval_loop_eventos_refino_por_rodada
    ON agents.eval_loop_eventos (loop_id, rodada_seq)
    WHERE evento IN ('refinamento_proposto', 'refinamento_recusado', 'refinamento_sem_edicao');
CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_eval_loop_eventos_revisao_por_rodada
    ON agents.eval_loop_eventos (loop_id, rodada_seq)
    WHERE evento = 'refinamento_revisado';

-- 3 . the atomic refine, with the checks the database makes itself -------------------------------------------------------
DROP FUNCTION IF EXISTS agents.aplicar_refinamento_loop(UUID, UUID, INT, TEXT, JSONB, NUMERIC, UUID, TEXT, TEXT, TEXT, TEXT, TEXT);

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
        -- never a base layer: a platform definition, or an agent other agents inherit from
        SELECT definition_scope INTO v_scope FROM agents.agents WHERE id = v_loop_agent AND org_id = p_org_id;
        IF v_scope IS NULL OR v_scope = 'plataforma'
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

-- 4 . the human review of a refine edit -----------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION agents.revisar_refinamento_loop(
    p_org_id UUID,
    p_loop_id UUID,
    p_rodada_seq INT,
    p_decisao TEXT,
    p_ator UUID,
    p_detalhe JSONB,
    p_version_id UUID DEFAULT NULL,
    p_tipo TEXT DEFAULT NULL,
    p_chave TEXT DEFAULT NULL,
    p_antes TEXT DEFAULT NULL,
    p_depois TEXT DEFAULT NULL,
    p_expected_hash TEXT DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_loop_agent UUID;
    v_ver_agent UUID;
    v_status TEXT;
    v_hash TEXT;
    v_n INT;
    v_id UUID;
BEGIN
    IF p_decisao NOT IN ('aceito', 'revertido') OR p_ator IS NULL THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;

    SELECT agent_id INTO v_loop_agent FROM agents.eval_loops WHERE id = p_loop_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'loop_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM agents.eval_loop_eventos
                    WHERE loop_id = p_loop_id AND rodada_seq = p_rodada_seq AND evento = 'refinamento_proposto') THEN
        RAISE EXCEPTION 'refino_nao_encontrado' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM agents.eval_loop_eventos
                WHERE loop_id = p_loop_id AND rodada_seq = p_rodada_seq AND evento = 'refinamento_revisado') THEN
        RAISE EXCEPTION 'refino_ja_revisado' USING ERRCODE = 'P0001';
    END IF;

    IF p_decisao = 'revertido' THEN
        IF p_version_id IS NULL OR p_tipo IS NULL OR p_chave IS NULL OR p_antes IS NULL OR p_depois IS NULL OR p_expected_hash IS NULL THEN
            RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
        END IF;
        SELECT status, compiled_hash, agent_id INTO v_status, v_hash, v_ver_agent FROM agents.agent_versions
        WHERE id = p_version_id AND org_id = p_org_id
        FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
        END IF;
        IF v_ver_agent IS DISTINCT FROM v_loop_agent THEN
            RAISE EXCEPTION 'versao_de_outro_agente' USING ERRCODE = 'P0001';
        END IF;
        IF v_status <> 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        IF v_hash IS DISTINCT FROM p_expected_hash THEN
            RAISE EXCEPTION 'conflito_de_versao' USING ERRCODE = 'P0001';
        END IF;

        -- p_antes = what the row holds NOW (the edit), p_depois = what it held before the edit
        IF p_tipo = 'secao' THEN
            UPDATE agents.agent_prompt_sections SET conteudo = p_depois
            WHERE version_id = p_version_id AND org_id = p_org_id AND chave = p_chave AND conteudo = p_antes;
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

    -- UNIQUE (loop_id, rodada_seq) over the review events: a racing second review rolls the whole transaction back
    INSERT INTO agents.eval_loop_eventos (org_id, loop_id, rodada_seq, evento, detalhe, ator)
    VALUES (p_org_id, p_loop_id, p_rodada_seq, 'refinamento_revisado',
            COALESCE(p_detalhe, '{}'::jsonb) || jsonb_build_object('decisao', p_decisao), p_ator)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

REVOKE ALL ON FUNCTION agents.revisar_refinamento_loop(UUID, UUID, INT, TEXT, UUID, JSONB, UUID, TEXT, TEXT, TEXT, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.revisar_refinamento_loop(UUID, UUID, INT, TEXT, UUID, JSONB, UUID, TEXT, TEXT, TEXT, TEXT, TEXT)
    TO service_role;
