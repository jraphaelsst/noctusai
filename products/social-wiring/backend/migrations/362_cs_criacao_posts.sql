-- ============================================================================
-- Migration 362 · social_wiring: CoreStudio criação pipeline, M-A -- cs_posts criação state + the Esteira stage model
-- ============================================================================
-- WHY
-- ---
-- Spec: products/social-wiring/projects/core-studio-build/specs/criacao-pipeline-contract.md sections 1, 2 (M-A), 2.3,
-- 10 (owner decisions 2026-11-19). One headline/roteiro becomes final media on the Esteira by construction, so the post
-- needs (a) a criação sub-state, (b) the CTA objective + its justification, the verified sources and the failure code,
-- (c) at most 5 hashtags (the generator writes exactly 5), and (d) a stage model that has the new roles.
--
--   * cs_posts          -- + criacao_estado (the sub-state, a PROJECTION written in the same transaction as its
--                          cs_post_eventos row, by the S5 mover), criacao_rota (route key, data in mc/criacao_rotas.py),
--                          falha_codigo (only while estado = 'falhou'), aprovado_em, cta_objetivo (enum) +
--                          cta_justificativa, fontes jsonb (array). NO link column: the post link is `permalink` (10.2).
--                          hashtags: the 30-cap becomes a 5-cap (NOT VALID -> cleanup -> VALIDATE).
--   * pipeline_stages   -- the `papel` CHECK also admits roteiro / criacao / edicao / aprovacao_midia / pronto
--                          (`gravacao` stays accepted: a one-release alias).
--   * DATA (esteira)    -- per existing org: "Gravação" -> "Criação" (label only while still the default; role becomes
--                          `criacao`; slug becomes `criacao` when free); the default-labelled "Headline + roteiro"
--                          becomes "Roteiro"; roles are set on the roteiro / edicao / pronto stages; the missing
--                          "Aprovação final" stage (role aprovacao_midia) is inserted before Pronto. Stage ids never
--                          change, so cs_posts.etapa_id / pipeline_movimentos stay valid.
--
-- ORDERING (owner-gated, read before applying): the DATA step moves the role of the Criação stage from `gravacao` to
-- `criacao`. The previous image gates on `gravacao` (esteira_service.py), so apply this migration TOGETHER with the S5
-- image (which keys on `criacao` and accepts `gravacao`), not before it. Everything else here is additive and
-- backward-compatible with the previous image.
--
-- Records -> metrics (measurement-by-design): time to approval (aprovado_em - created_at), CTA objective mix
-- (cta_objetivo), failure mix (falha_codigo). Tier: cs_posts is already `tier:org` (330). FORWARD-ONLY, IDEMPOTENT.
-- Requires 241, 342, 348, 352.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_posts') IS NULL OR to_regclass('social_wiring.pipeline_stages') IS NULL THEN
    RAISE EXCEPTION 'Migration 362 requires social_wiring.cs_posts (241) and pipeline_stages (034) -- apply them first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. cs_posts: criação state, CTA, sources
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_posts ADD COLUMN IF NOT EXISTS criacao_estado TEXT;
ALTER TABLE social_wiring.cs_posts ADD COLUMN IF NOT EXISTS criacao_rota TEXT;
ALTER TABLE social_wiring.cs_posts ADD COLUMN IF NOT EXISTS falha_codigo TEXT;
ALTER TABLE social_wiring.cs_posts ADD COLUMN IF NOT EXISTS aprovado_em TIMESTAMPTZ;
ALTER TABLE social_wiring.cs_posts ADD COLUMN IF NOT EXISTS cta_objetivo TEXT;
ALTER TABLE social_wiring.cs_posts ADD COLUMN IF NOT EXISTS cta_justificativa TEXT;
ALTER TABLE social_wiring.cs_posts ADD COLUMN IF NOT EXISTS fontes JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE social_wiring.cs_posts DROP CONSTRAINT IF EXISTS cs_posts_criacao_estado_check;
ALTER TABLE social_wiring.cs_posts ADD CONSTRAINT cs_posts_criacao_estado_check CHECK (criacao_estado IN (
    'aguardando_aprovacao', 'refinando', 'aprovado', 'na_fila', 'gerando', 'aguardando_edicao',
    'aguardando_aprovacao_midia', 'midia_aprovada', 'midia_reprovada', 'falhou', 'cancelado')) NOT VALID;
ALTER TABLE social_wiring.cs_posts VALIDATE CONSTRAINT cs_posts_criacao_estado_check;

ALTER TABLE social_wiring.cs_posts DROP CONSTRAINT IF EXISTS cs_posts_criacao_rota_check;
ALTER TABLE social_wiring.cs_posts ADD CONSTRAINT cs_posts_criacao_rota_check
    CHECK (criacao_rota IN ('reel_narrado', 'carrossel', 'estatico', 'avatar', 'gravado')) NOT VALID;
ALTER TABLE social_wiring.cs_posts VALIDATE CONSTRAINT cs_posts_criacao_rota_check;

-- a failure code exists only while the post is in the `falhou` sub-state (the mover clears it when leaving)
ALTER TABLE social_wiring.cs_posts DROP CONSTRAINT IF EXISTS cs_posts_falha_codigo_check;
ALTER TABLE social_wiring.cs_posts ADD CONSTRAINT cs_posts_falha_codigo_check
    CHECK (falha_codigo IS NULL OR (criacao_estado IS NOT DISTINCT FROM 'falhou' AND falha_codigo ~ '^[a-z0-9_]{1,60}$')) NOT VALID;
ALTER TABLE social_wiring.cs_posts VALIDATE CONSTRAINT cs_posts_falha_codigo_check;

ALTER TABLE social_wiring.cs_posts DROP CONSTRAINT IF EXISTS cs_posts_cta_objetivo_check;
ALTER TABLE social_wiring.cs_posts ADD CONSTRAINT cs_posts_cta_objetivo_check CHECK (cta_objetivo IN (
    'alcance', 'salvamentos', 'conversa', 'seguidores', 'autoridade', 'reflexao', 'nenhum')) NOT VALID;
ALTER TABLE social_wiring.cs_posts VALIDATE CONSTRAINT cs_posts_cta_objetivo_check;

ALTER TABLE social_wiring.cs_posts DROP CONSTRAINT IF EXISTS cs_posts_cta_justificativa_check;
ALTER TABLE social_wiring.cs_posts ADD CONSTRAINT cs_posts_cta_justificativa_check
    CHECK (cta_justificativa IS NULL OR char_length(cta_justificativa) <= 1000) NOT VALID;
ALTER TABLE social_wiring.cs_posts VALIDATE CONSTRAINT cs_posts_cta_justificativa_check;

ALTER TABLE social_wiring.cs_posts DROP CONSTRAINT IF EXISTS cs_posts_fontes_check;
ALTER TABLE social_wiring.cs_posts ADD CONSTRAINT cs_posts_fontes_check
    CHECK (jsonb_typeof(fontes) = 'array') NOT VALID;
ALTER TABLE social_wiring.cs_posts VALIDATE CONSTRAINT cs_posts_fontes_check;

COMMENT ON COLUMN social_wiring.cs_posts.criacao_estado IS
    'Criação sub-state (criacao-pipeline-contract 1): a projection, written in the same transaction as its cs_post_eventos row. Migration 362.';
COMMENT ON COLUMN social_wiring.cs_posts.criacao_rota IS
    'Production route key (data in mc/criacao_rotas.py): reel_narrado | carrossel | estatico | avatar | gravado. Migration 362.';
COMMENT ON COLUMN social_wiring.cs_posts.falha_codigo IS
    'Machine failure code, present only while criacao_estado = falhou. Migration 362.';
COMMENT ON COLUMN social_wiring.cs_posts.cta_objetivo IS
    'The post objective the CTA was chosen from (nenhum is a valid, justified choice). Migration 362.';
COMMENT ON COLUMN social_wiring.cs_posts.fontes IS
    'JSON array of the sources the roteiro cites; only what a tool returned (contract 4). Migration 362.';

CREATE INDEX IF NOT EXISTS cs_posts_criacao_estado_idx
    ON social_wiring.cs_posts (org_id, criacao_estado) WHERE criacao_estado IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 2. hashtags: cap 30 -> 5 (the generator writes exactly 5)
-- ----------------------------------------------------------------------------
-- Cleanup first (legacy rows above the cap keep their first 5), so the VALIDATE cannot fail on old data.
UPDATE social_wiring.cs_posts SET hashtags = hashtags[1:5] WHERE cardinality(hashtags) > 5;

ALTER TABLE social_wiring.cs_posts DROP CONSTRAINT IF EXISTS cs_posts_hashtags_max;
ALTER TABLE social_wiring.cs_posts ADD CONSTRAINT cs_posts_hashtags_max
    CHECK (cardinality(hashtags) <= 5) NOT VALID;
ALTER TABLE social_wiring.cs_posts VALIDATE CONSTRAINT cs_posts_hashtags_max;

-- ----------------------------------------------------------------------------
-- 3. pipeline_stages.papel: the new roles (gravacao kept as a one-release alias)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.pipeline_stages DROP CONSTRAINT IF EXISTS pipeline_stages_papel_check;
ALTER TABLE social_wiring.pipeline_stages ADD CONSTRAINT pipeline_stages_papel_check
  CHECK (papel IN ('proposta_aceite', 'final', 'gravacao', 'agendado', 'postado', 'cancelado',
                   'roteiro', 'criacao', 'edicao', 'aprovacao_midia', 'pronto'));

-- ----------------------------------------------------------------------------
-- 4. DATA: per existing org's esteira board (stage ids are never changed)
-- ----------------------------------------------------------------------------
DO $dados$
DECLARE
    v_org UUID;
    v_pos INTEGER;
BEGIN
    -- 4a. "Gravação" -> "Criação": role first (semantic), label only while still the default, slug when free.
    UPDATE social_wiring.pipeline_stages s
       SET papel = 'criacao', updated_at = now()
     WHERE s.pipeline = 'esteira' AND s.papel = 'gravacao'
       AND NOT EXISTS (SELECT 1 FROM social_wiring.pipeline_stages x
                        WHERE x.org_id = s.org_id AND x.pipeline = 'esteira' AND x.papel = 'criacao');
    UPDATE social_wiring.pipeline_stages s
       SET label = 'Criação', updated_at = now()
     WHERE s.pipeline = 'esteira' AND s.papel = 'criacao' AND s.label = 'Gravação';
    UPDATE social_wiring.pipeline_stages s
       SET slug = 'criacao', updated_at = now()
     WHERE s.pipeline = 'esteira' AND s.papel = 'criacao' AND s.slug = 'gravacao'
       AND NOT EXISTS (SELECT 1 FROM social_wiring.pipeline_stages x
                        WHERE x.org_id = s.org_id AND x.pipeline = 'esteira' AND x.slug = 'criacao');

    -- 4b. roles on the stages that had none (a stage that already carries a role is left alone)
    UPDATE social_wiring.pipeline_stages s
       SET papel = 'roteiro', updated_at = now()
     WHERE s.pipeline = 'esteira' AND s.slug = 'headline_roteiro' AND s.papel IS NULL
       AND NOT EXISTS (SELECT 1 FROM social_wiring.pipeline_stages x
                        WHERE x.org_id = s.org_id AND x.pipeline = 'esteira' AND x.papel = 'roteiro');
    UPDATE social_wiring.pipeline_stages s
       SET label = 'Roteiro', updated_at = now()
     WHERE s.pipeline = 'esteira' AND s.papel = 'roteiro' AND s.label = 'Headline + roteiro';
    UPDATE social_wiring.pipeline_stages s
       SET papel = 'edicao', updated_at = now()
     WHERE s.pipeline = 'esteira' AND s.slug = 'edicao' AND s.papel IS NULL
       AND NOT EXISTS (SELECT 1 FROM social_wiring.pipeline_stages x
                        WHERE x.org_id = s.org_id AND x.pipeline = 'esteira' AND x.papel = 'edicao');
    UPDATE social_wiring.pipeline_stages s
       SET papel = 'pronto', updated_at = now()
     WHERE s.pipeline = 'esteira' AND s.slug = 'pronto' AND s.papel IS NULL
       AND NOT EXISTS (SELECT 1 FROM social_wiring.pipeline_stages x
                        WHERE x.org_id = s.org_id AND x.pipeline = 'esteira' AND x.papel = 'pronto');

    -- 4c. the missing "Aprovação final" stage, placed right before Pronto (else right after Edição, else last)
    FOR v_org IN
        SELECT DISTINCT org_id FROM social_wiring.pipeline_stages p
         WHERE p.pipeline = 'esteira'
           AND NOT EXISTS (SELECT 1 FROM social_wiring.pipeline_stages x
                            WHERE x.org_id = p.org_id AND x.pipeline = 'esteira'
                              AND (x.slug = 'aprovacao_final' OR x.papel = 'aprovacao_midia'))
    LOOP
        SELECT posicao INTO v_pos FROM social_wiring.pipeline_stages
         WHERE org_id = v_org AND pipeline = 'esteira' AND (papel = 'pronto' OR slug = 'pronto')
         ORDER BY posicao LIMIT 1;
        IF v_pos IS NULL THEN
            SELECT posicao + 1 INTO v_pos FROM social_wiring.pipeline_stages
             WHERE org_id = v_org AND pipeline = 'esteira' AND (papel = 'edicao' OR slug = 'edicao')
             ORDER BY posicao LIMIT 1;
        END IF;
        IF v_pos IS NULL THEN
            SELECT COALESCE(max(posicao), -1) + 1 INTO v_pos FROM social_wiring.pipeline_stages
             WHERE org_id = v_org AND pipeline = 'esteira';
        END IF;
        UPDATE social_wiring.pipeline_stages SET posicao = posicao + 1, updated_at = now()
         WHERE org_id = v_org AND pipeline = 'esteira' AND posicao >= v_pos;
        INSERT INTO social_wiring.pipeline_stages (org_id, pipeline, slug, label, cor, posicao, papel, ativo)
        VALUES (v_org, 'esteira', 'aprovacao_final', 'Aprovação final', 'warning', v_pos, 'aprovacao_midia', true)
        ON CONFLICT (org_id, pipeline, slug) DO NOTHING;
    END LOOP;
END
$dados$;
