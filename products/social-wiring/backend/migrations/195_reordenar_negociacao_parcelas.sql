-- ============================================================================
-- 195 — social_wiring.reordenar_negociacao_parcelas(): atomic parcela reorder
-- ============================================================================
-- The negociação panel could only edit/remove a parcela, never MOVE it, so a
-- sinal created after an auto-suggested financiamento/intermediária printed as
-- "Parcela 03" (`ordem` drives the contract's "Parcela NN" numbering, the
-- VENCIMENTOS_FORA_DE_ORDEM blocker and the posse-marco citation — see 144).
--
-- A reorder rewrites `ordem` on EVERY parcela of one atendimento. Done as N
-- PostgREST PATCHes, a failure halfway leaves a half-renumbered schedule (two
-- parcelas tied on one `ordem`, the order then decided by `created_at` again —
-- exactly what 144 removed). This function is the one atomic write: the whole
-- new order, as the full ordered list of the atendimento's parcela ids, in a
-- single UPDATE inside the function's own transaction.
--
-- Refuses (SQLSTATE 22023, nothing written) unless `p_parcela_ids` is EXACTLY
-- the atendimento's current parcela set — no missing, extra, foreign or
-- duplicated id — so a stale client (a parcela added/removed in another tab)
-- cannot silently drop a parcela out of the numbering. The service validates
-- the same thing first to answer with a named 400; this is the backstop.
--
-- Dense `ordem` 0..N-1 in list order. Org-scoped by an explicit parameter like
-- every sibling RPC (185/133); SECURITY INVOKER; service_role only — the
-- backend is the sole caller.
--
-- `forma_pagamento`: NO DDL. Both parcela tables already store it as
-- unbounded TEXT (108 + 190); the 50/60-char limit the owner hit (2026-10-03)
-- lived only in the HTTP schemas + the FE input and is removed there.
--
-- Forward-only, idempotent (CREATE OR REPLACE).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE OR REPLACE FUNCTION social_wiring.reordenar_negociacao_parcelas(
    p_org_id         UUID,
    p_atendimento_id UUID,
    p_parcela_ids    UUID[],
    p_usuario_id     UUID DEFAULT NULL
)
RETURNS INTEGER
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = social_wiring, public
AS $$
DECLARE
    v_atuais    INTEGER;
    v_enviados  INTEGER := coalesce(array_length(p_parcela_ids, 1), 0);
    v_distintos INTEGER;
    v_casados   INTEGER;
    v_alterados INTEGER;
BEGIN
    -- Lock the atendimento's parcelas for the duration of the reorder so a
    -- concurrent create/delete cannot slip between the check and the write.
    PERFORM 1
       FROM social_wiring.atendimento_negociacao_parcelas p
      WHERE p.org_id = p_org_id
        AND p.atendimento_id = p_atendimento_id
        FOR UPDATE;

    SELECT count(*) INTO v_atuais
      FROM social_wiring.atendimento_negociacao_parcelas p
     WHERE p.org_id = p_org_id
       AND p.atendimento_id = p_atendimento_id;

    SELECT count(DISTINCT x) INTO v_distintos FROM unnest(p_parcela_ids) AS x;

    SELECT count(*) INTO v_casados
      FROM social_wiring.atendimento_negociacao_parcelas p
     WHERE p.org_id = p_org_id
       AND p.atendimento_id = p_atendimento_id
       AND p.id = ANY (p_parcela_ids);

    IF v_enviados <> v_atuais OR v_distintos <> v_enviados OR v_casados <> v_atuais THEN
        RAISE EXCEPTION
            'a nova ordem deve listar exatamente as % parcelas desta negociação (recebidas %)',
            v_atuais, v_enviados
            USING ERRCODE = '22023';
    END IF;

    UPDATE social_wiring.atendimento_negociacao_parcelas p
       SET ordem      = (t.pos - 1)::INTEGER,
           updated_at = now(),
           updated_por = p_usuario_id
      FROM unnest(p_parcela_ids) WITH ORDINALITY AS t(id, pos)
     WHERE p.id = t.id
       AND p.org_id = p_org_id
       AND p.atendimento_id = p_atendimento_id
       AND p.ordem IS DISTINCT FROM (t.pos - 1)::INTEGER;
    GET DIAGNOSTICS v_alterados = ROW_COUNT;

    RETURN v_alterados;
END;
$$;

COMMENT ON FUNCTION social_wiring.reordenar_negociacao_parcelas(UUID, UUID, UUID[], UUID) IS
    'Atomically sets ordem = position (0..N-1) for every parcela of one '
    'atendimento, from the full ordered id list; refuses (22023) unless the '
    'list is exactly the current set. Returns rows changed. service_role only. '
    'Migration 195.';

REVOKE ALL ON FUNCTION social_wiring.reordenar_negociacao_parcelas(UUID, UUID, UUID[], UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION social_wiring.reordenar_negociacao_parcelas(UUID, UUID, UUID[], UUID) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.reordenar_negociacao_parcelas(UUID, UUID, UUID[], UUID) TO service_role;
