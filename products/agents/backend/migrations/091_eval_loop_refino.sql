-- 091_eval_loop_refino.sql -- the eval-loop REFINE step (owner 2026-11-19: "gotta take value from those expensive calls").
--
-- Between two rounds of an AUTOMATIC loop the server proposes ONE bounded edit of ONE own draft row (a section, a text or a tool
-- description), writes it to the DRAFT only and records it as an immutable event. This migration adds exactly what that needs:
--
-- 1. three loop events: `refinamento_proposto` (the edit + its row diff), `refinamento_recusado` (the step ran and nothing was
--    written: the reason + the cost already spent) and `refinamento_avaliado` (the next round closed: did the score improve).
-- 2. at most ONE `refinamento_proposto|recusado` per (loop, base round): a partial unique index, so two drivers racing for the same
--    round cannot both write an edit (the loser's whole transaction rolls back, draft write included).
-- 3. `agents.aplicar_refinamento_loop(...)`: the draft-row edit, the loop's spend (`eval_loops.gasto_usd += custo`) and the event in
--    ONE transaction -- event-oriented: no edit without its event, no event for an edit that did not land. It is a targeted
--    UPDATE of one row guarded by compare-and-set on the draft's compiled_hash AND on the row's old text, never a replace-set.
-- Tier: Platform IP (service role only). Forward-only + idempotent: the previous image reads none of it.

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
    'refinamento_proposto', 'refinamento_recusado', 'refinamento_avaliado'));

-- 2 . one refine decision per (loop, base round) ------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_eval_loop_eventos_refino_por_rodada
    ON agents.eval_loop_eventos (loop_id, rodada_seq)
    WHERE evento IN ('refinamento_proposto', 'refinamento_recusado');

-- 3 . the atomic refine -------------------------------------------------------------------------------------------------
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
    p_expected_hash TEXT DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_loop_status TEXT;
    v_status TEXT;
    v_hash TEXT;
    v_n INT;
    v_id UUID;
BEGIN
    IF p_evento NOT IN ('refinamento_proposto', 'refinamento_recusado') THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    IF p_custo_usd IS NULL OR p_custo_usd < 0 THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;

    SELECT status INTO v_loop_status FROM agents.eval_loops WHERE id = p_loop_id AND org_id = p_org_id FOR UPDATE;
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
        SELECT status, compiled_hash INTO v_status, v_hash FROM agents.agent_versions
        WHERE id = p_version_id AND org_id = p_org_id
        FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
        END IF;
        IF v_status <> 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        -- compare-and-set on the draft (the row is locked above: the compare and the write are one step) AND on the row's old text
        IF v_hash IS DISTINCT FROM p_expected_hash THEN
            RAISE EXCEPTION 'conflito_de_versao' USING ERRCODE = 'P0001';
        END IF;

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

    IF p_custo_usd > 0 THEN
        UPDATE agents.eval_loops SET gasto_usd = round(gasto_usd + p_custo_usd, 4)
        WHERE id = p_loop_id AND org_id = p_org_id;
    END IF;

    -- UNIQUE (loop_id, rodada_seq) over the two refine events: a racing second decision rolls the whole transaction back
    INSERT INTO agents.eval_loop_eventos (org_id, loop_id, rodada_seq, evento, detalhe)
    VALUES (p_org_id, p_loop_id, p_rodada_seq, p_evento, COALESCE(p_detalhe, '{}'::jsonb))
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

REVOKE ALL ON FUNCTION agents.aplicar_refinamento_loop(UUID, UUID, INT, TEXT, JSONB, NUMERIC, UUID, TEXT, TEXT, TEXT, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.aplicar_refinamento_loop(UUID, UUID, INT, TEXT, JSONB, NUMERIC, UUID, TEXT, TEXT, TEXT, TEXT, TEXT)
    TO service_role;
