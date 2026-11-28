-- ============================================================================
-- Migration 373 · social_wiring: CoreStudio criação pipeline, Diretor de Edição -- the approval -> production trigger
-- ============================================================================
-- WHY: projects/diretor-edicao-reels (the owner's brief 2026-11-27): approving BOTH the headline AND the roteiro must
-- start the Reel production by itself. Today the two approvals only unlock a HUMAN call (`POST /posts/{id}/criacao/iniciar`).
-- This migration is the data half of the trigger seam (decision-free: it names no storytelling, vendor or render choice):
--   1. `cs_posts.criacao_rota` admits the new route key `reel_dirigido` (the route whose steps are the Diretor's stages;
--      route data lives in app/modules/media_creation/criacao_rotas.py, the CHECK only enumerates the keys). Widening only.
--   2. `cs_post_eventos.tipo` admits two intent-named events (EOA, same vocabulary as 364, which stays the base):
--        direcao_solicitada -- the trigger accepted an approval pair and asked for a production run (ONCE per `chave`);
--        direcao_recusada   -- the trigger could not start the run (dados.codigo: rota_nao_implementada, cota, ...).
--   3. `cs_direcao_evento(...)` -- the ONLY writer of those two events. SECURITY DEFINER, service_role only. For
--      `direcao_solicitada` the idempotency is a database fact, not a convention: a partial UNIQUE index on
--      (post_id, dados->>'chave') makes a repeated trigger (double click, retried request, the reconcile sweep) a no-op
--      that returns false -- the caller then decides, from the step ledger, whether a graph still has to be queued.
--
-- Records -> metrics (measurement-by-design): approvals that started a run vs refused (by codigo), time from the second
-- approval (apr_events) to `direcao_solicitada`, runs per post (chave carries the roteiro versao: an edited + re-approved
-- roteiro is a NEW chave), and -- joined with 363's ledger and 364's midia_aprovada / midia_reprovada -- the approval rate of
-- the produced media per estilo / planner version carried in dados of the production steps.
-- Tier: org (service role only; the browser holds no grant). FORWARD-ONLY, IDEMPOTENT, backward-compatible (widening +
-- a new function + a new index; nothing existing dropped). Requires 362, 364.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_posts') IS NULL OR to_regclass('social_wiring.cs_post_eventos') IS NULL THEN
    RAISE EXCEPTION 'Migration 373 requires social_wiring.cs_posts and cs_post_eventos (241/342) -- apply them first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'social_wiring' AND table_name = 'cs_posts' AND column_name = 'criacao_rota') THEN
    RAISE EXCEPTION 'Migration 373 requires cs_posts.criacao_rota (362) -- apply 362 first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. the route key
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_posts DROP CONSTRAINT IF EXISTS cs_posts_criacao_rota_check;
ALTER TABLE social_wiring.cs_posts ADD CONSTRAINT cs_posts_criacao_rota_check
    CHECK (criacao_rota IN ('reel_narrado', 'reel_dirigido', 'carrossel', 'estatico', 'avatar', 'gravado')) NOT VALID;
ALTER TABLE social_wiring.cs_posts VALIDATE CONSTRAINT cs_posts_criacao_rota_check;
COMMENT ON COLUMN social_wiring.cs_posts.criacao_rota IS
    'Production route key (data in mc/criacao_rotas.py): reel_narrado | reel_dirigido | carrossel | estatico | avatar | gravado. Migrations 362, 373.';

-- ----------------------------------------------------------------------------
-- 2. the event vocabulary (364's list + the two direcao_* names)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_post_eventos DROP CONSTRAINT IF EXISTS cs_post_eventos_tipo_check;
ALTER TABLE social_wiring.cs_post_eventos ADD CONSTRAINT cs_post_eventos_tipo_check CHECK (tipo IN (
    -- 342 / 353 (unchanged)
    'midia_versao_criada', 'midia_status_alterado', 'insumos_apagados',
    'publicacao_agendada', 'publicacao_reagendada', 'publicado', 'publicacao_falhou', 'publicacao_cancelada',
    -- 364: roteiro loop
    'opcoes_geradas', 'opcoes_selecionadas', 'contraparte_gerada', 'refinamento_pedido',
    'headline_aprovada', 'roteiro_aprovado', 'publicacao_gerada',
    -- 364: criação
    'criacao_enfileirada', 'passo_iniciado', 'passo_concluido', 'passo_falhou', 'criacao_concluida',
    -- 364: final approval
    'midia_aprovada', 'midia_reprovada',
    -- 364: opt-in only
    'verificacao_transcricao_pedida', 'verificacao_transcricao_concluida',
    -- 364: system moves + quota
    'card_movido_automaticamente', 'cota_alterada', 'cota_excedida',
    -- 373: the Diretor de Edição trigger
    'direcao_solicitada', 'direcao_recusada')) NOT VALID;
ALTER TABLE social_wiring.cs_post_eventos VALIDATE CONSTRAINT cs_post_eventos_tipo_check;

-- ----------------------------------------------------------------------------
-- 3. idempotency: ONE direcao_solicitada per (post, chave)
-- ----------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS cs_post_eventos_direcao_solicitada_uq
    ON social_wiring.cs_post_eventos (post_id, (dados ->> 'chave'))
    WHERE tipo = 'direcao_solicitada';

-- ----------------------------------------------------------------------------
-- 4. the writer
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.cs_direcao_evento(
    p_org UUID, p_post UUID, p_tipo TEXT, p_chave TEXT,
    p_dados JSONB DEFAULT '{}'::jsonb, p_ator UUID DEFAULT NULL)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_dados JSONB := COALESCE(p_dados, '{}'::jsonb);
    v_linhas INTEGER;
BEGIN
    IF p_tipo NOT IN ('direcao_solicitada', 'direcao_recusada') THEN
        RAISE EXCEPTION 'tipo_invalido';
    END IF;
    IF p_chave IS NULL OR btrim(p_chave) = '' OR length(p_chave) > 200 THEN
        RAISE EXCEPTION 'chave_invalida';
    END IF;
    IF jsonb_typeof(v_dados) <> 'object' THEN
        RAISE EXCEPTION 'dados_invalidos';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM social_wiring.cs_posts WHERE id = p_post AND org_id = p_org) THEN
        RAISE EXCEPTION 'post_nao_encontrado';
    END IF;

    INSERT INTO social_wiring.cs_post_eventos (org_id, post_id, tipo, dados, ator_id)
    VALUES (p_org, p_post, p_tipo, v_dados || jsonb_build_object('chave', p_chave), p_ator)
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_linhas = ROW_COUNT;
    RETURN v_linhas = 1;   -- false = this chave was already requested (direcao_solicitada only)
END;
$fn$;

REVOKE ALL ON FUNCTION social_wiring.cs_direcao_evento(UUID, UUID, TEXT, TEXT, JSONB, UUID)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_direcao_evento(UUID, UUID, TEXT, TEXT, JSONB, UUID) TO service_role;

COMMENT ON FUNCTION social_wiring.cs_direcao_evento(UUID, UUID, TEXT, TEXT, JSONB, UUID) IS
    'The only writer of direcao_solicitada / direcao_recusada: true when the event row was written, false when this (post, chave) was already requested. Migration 373.';
