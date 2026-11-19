-- ============================================================================
-- Migration 369 · social_wiring: CoreStudio criação pipeline, S5 -- the criação sub-state writer (state + event, one tx)
-- ============================================================================
-- WHY: criacao-pipeline-contract.md section 1 ("criacao_estado is a projection, written in the same transaction as its
-- cs_post_eventos row") and section 2.2. PostgREST is one call = one transaction, so the state column and its event row
-- can only be written atomically by an RPC. `cs_post_criacao_transicionar` is that writer:
--   * locks the post row (FOR UPDATE), refuses `post_nao_encontrado` for a foreign org's id;
--   * optimistic check: `p_de` is the state the caller read (NULL = a post that never had one); a different current
--     state raises `estado_mudou` (a concurrent mover won) -- the caller re-reads, never overwrites;
--   * writes criacao_estado, `falha_codigo` (only for `falhou`, REQUIRED there, cleared otherwise -- the 362 CHECK),
--     `aprovado_em` (first time the state is `aprovado`) and optionally `criacao_rota`;
--   * inserts the cs_post_eventos row (type validated by 364's CHECK) with de/para/dados/ator in the same transaction
--     (unless the state follows an event its own writer already recorded: `p_tipo` NULL, see the body).
-- The transition MATRIX is data in app/modules/media_creation/services/criacao_estado.py (one derivation); the database
-- enforces the enum (362), the optimistic check and the atomicity, not a second copy of the matrix.
-- Records -> metrics: time per sub-state (event ts), refinement rounds, rejection rate (midia_reprovada), failure mix
-- (falha_codigo). Tier: reached only through the service role (REVOKEd from PUBLIC/anon/authenticated).
-- FORWARD-ONLY, IDEMPOTENT, backward-compatible (a new function). Requires 362, 364.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_posts') IS NULL OR to_regclass('social_wiring.cs_post_eventos') IS NULL THEN
    RAISE EXCEPTION 'Migration 369 requires social_wiring.cs_posts and cs_post_eventos (241/342) -- apply them first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'social_wiring' AND table_name = 'cs_posts' AND column_name = 'criacao_estado') THEN
    RAISE EXCEPTION 'Migration 369 requires cs_posts.criacao_estado (362) -- apply 362 first';
  END IF;
END
$guard$;

CREATE OR REPLACE FUNCTION social_wiring.cs_post_criacao_transicionar(
    p_org UUID, p_post UUID, p_de TEXT, p_para TEXT, p_tipo TEXT,
    p_dados JSONB DEFAULT '{}'::jsonb, p_falha_codigo TEXT DEFAULT NULL, p_ator UUID DEFAULT NULL,
    p_rota TEXT DEFAULT NULL)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_atual TEXT;
    v_dados JSONB := COALESCE(p_dados, '{}'::jsonb);
BEGIN
    IF p_para IS NULL THEN
        RAISE EXCEPTION 'parametros_invalidos';
    END IF;
    IF jsonb_typeof(v_dados) <> 'object' THEN
        RAISE EXCEPTION 'dados_invalidos';
    END IF;
    IF p_para = 'falhou' AND (p_falha_codigo IS NULL OR p_falha_codigo !~ '^[a-z0-9_]{1,60}$') THEN
        RAISE EXCEPTION 'falha_codigo_obrigatorio';
    END IF;

    SELECT criacao_estado INTO v_atual FROM social_wiring.cs_posts
     WHERE id = p_post AND org_id = p_org FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'post_nao_encontrado';
    END IF;
    IF v_atual IS DISTINCT FROM p_de THEN
        RAISE EXCEPTION 'estado_mudou: esperado %, atual %', COALESCE(p_de, 'nulo'), COALESCE(v_atual, 'nulo');
    END IF;

    UPDATE social_wiring.cs_posts SET
        criacao_estado = p_para,
        falha_codigo = CASE WHEN p_para = 'falhou' THEN p_falha_codigo END,
        aprovado_em = CASE WHEN p_para = 'aprovado' THEN COALESCE(aprovado_em, now()) ELSE aprovado_em END,
        criacao_rota = COALESCE(p_rota, criacao_rota)
     WHERE id = p_post AND org_id = p_org;

    -- p_tipo NULL = the state follows an event its OWN writer already recorded (a step's event by 363's
    -- cs_criacao_passo_registrar, an approval's apr_events row, a cancel's pipeline_movimentos row); the service only
    -- allows that for the states in criacao_estado.ESTADOS_COM_EVENTO_PROPRIO -- a second event would double-count.
    IF p_tipo IS NOT NULL THEN
        INSERT INTO social_wiring.cs_post_eventos (org_id, post_id, tipo, de, para, dados, ator_id)
        VALUES (p_org, p_post, p_tipo, v_atual, p_para, v_dados, p_ator);
    END IF;

    RETURN jsonb_build_object('post_id', p_post, 'de', v_atual, 'para', p_para);
END;
$fn$;

REVOKE ALL ON FUNCTION social_wiring.cs_post_criacao_transicionar(UUID, UUID, TEXT, TEXT, TEXT, JSONB, TEXT, UUID, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_post_criacao_transicionar(UUID, UUID, TEXT, TEXT, TEXT, JSONB, TEXT, UUID, TEXT)
    TO service_role;

COMMENT ON FUNCTION social_wiring.cs_post_criacao_transicionar(UUID, UUID, TEXT, TEXT, TEXT, JSONB, TEXT, UUID, TEXT) IS
    'The only writer of cs_posts.criacao_estado: state + its cs_post_eventos row, one transaction, optimistic on p_de (criacao-pipeline-contract 1). Migration 369.';
