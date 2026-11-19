-- ============================================================================
-- Migration 368 · social_wiring: cs_post_criacao_projetar -- the criação sub-state projection + its events, one transaction
-- ============================================================================
-- WHY
-- ---
-- criacao-pipeline-contract.md section 1: `cs_posts.criacao_estado` is a PROJECTION "written in the same transaction as
-- its event". PostgREST is one call = one transaction, so the media worker (S6) cannot update the column and insert the
-- cs_post_eventos rows as two calls without a window where one exists and the other does not. This definer RPC is that
-- single call: it row-locks the post, moves the projection, and appends the given events (criacao_enfileirada /
-- criacao_concluida / card_movido_automaticamente; names admitted by 364) with de/para = the old/new sub-state.
--
--   * IDEMPOTENT: when the sub-state already equals the target (and the failure code too) nothing is written and no event
--     is appended -- a retried job never double-logs.
--   * p_somente_de (optional text[]): only move when the CURRENT sub-state is one of these (the worker's `na_fila ->
--     gerando` step must never overwrite `falhou` / `midia_reprovada` set by someone else); otherwise a no-op.
--   * falha_codigo is written only with estado = 'falhou' and cleared otherwise (the 362 CHECK).
--
-- Records -> metrics: criação lead time per sub-state (cs_post_eventos de/para), failures by code. Tier: the function is
-- service_role-only (the browser has no grant). Backward compatible with the previous image: a NEW function, nothing
-- existing touched. FORWARD-ONLY, IDEMPOTENT. Requires 362 + 364.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_post_eventos') IS NULL OR to_regclass('social_wiring.cs_posts') IS NULL THEN
    RAISE EXCEPTION 'Migration 368 requires cs_posts and cs_post_eventos (241 / 342) -- apply them first';
  END IF;
END
$guard$;

CREATE OR REPLACE FUNCTION social_wiring.cs_post_criacao_projetar(
    p_org UUID, p_post UUID, p_estado TEXT, p_falha TEXT, p_eventos JSONB, p_somente_de TEXT[])
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_old TEXT;
    v_old_falha TEXT;
    v_falha TEXT;
    v_ev JSONB;
BEGIN
    IF p_estado IS NULL OR p_estado NOT IN (
        'aguardando_aprovacao', 'refinando', 'aprovado', 'na_fila', 'gerando', 'aguardando_edicao',
        'aguardando_aprovacao_midia', 'midia_aprovada', 'midia_reprovada', 'falhou', 'cancelado') THEN
        RAISE EXCEPTION 'estado_invalido';
    END IF;
    IF p_eventos IS NOT NULL AND jsonb_typeof(p_eventos) <> 'array' THEN
        RAISE EXCEPTION 'eventos_invalidos';
    END IF;
    IF p_estado = 'falhou' AND (p_falha IS NULL OR p_falha !~ '^[a-z0-9_]{1,60}$') THEN
        RAISE EXCEPTION 'falha_obrigatoria';
    END IF;

    SELECT criacao_estado, falha_codigo INTO v_old, v_old_falha
      FROM social_wiring.cs_posts WHERE id = p_post AND org_id = p_org FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'post_nao_encontrado';
    END IF;

    v_falha := CASE WHEN p_estado = 'falhou' THEN p_falha END;
    IF p_somente_de IS NOT NULL AND (v_old IS NULL OR NOT (v_old = ANY (p_somente_de))) THEN
        RETURN jsonb_build_object('mudou', false, 'estado', v_old, 'motivo', 'estado_atual_fora_de_somente_de');
    END IF;
    IF v_old IS NOT DISTINCT FROM p_estado AND v_old_falha IS NOT DISTINCT FROM v_falha THEN
        RETURN jsonb_build_object('mudou', false, 'estado', v_old);
    END IF;

    UPDATE social_wiring.cs_posts
       SET criacao_estado = p_estado, falha_codigo = v_falha
     WHERE id = p_post AND org_id = p_org;

    FOR v_ev IN SELECT * FROM jsonb_array_elements(COALESCE(p_eventos, '[]'::jsonb)) LOOP
        INSERT INTO social_wiring.cs_post_eventos (org_id, post_id, tipo, de, para, dados, ator_id)
        VALUES (p_org, p_post, v_ev ->> 'tipo', v_old, p_estado,
                COALESCE(v_ev -> 'dados', '{}'::jsonb), NULLIF(v_ev ->> 'ator_id', '')::uuid);
    END LOOP;

    RETURN jsonb_build_object('mudou', true, 'estado', p_estado, 'de', v_old);
END;
$fn$;

REVOKE ALL ON FUNCTION social_wiring.cs_post_criacao_projetar(UUID, UUID, TEXT, TEXT, JSONB, TEXT[])
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_post_criacao_projetar(UUID, UUID, TEXT, TEXT, JSONB, TEXT[])
    TO service_role;

COMMENT ON FUNCTION social_wiring.cs_post_criacao_projetar(UUID, UUID, TEXT, TEXT, JSONB, TEXT[]) IS
    'Moves cs_posts.criacao_estado and appends its cs_post_eventos in ONE transaction; idempotent (criacao-pipeline-contract 1).';
