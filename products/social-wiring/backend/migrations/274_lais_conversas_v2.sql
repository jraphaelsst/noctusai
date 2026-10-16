-- ============================================================================
-- Migration 274 -- social_wiring: Lais wave 7, Conversas v2
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md section 9 (Wave 7) + A7.
--
--   lais_etiquetas          org tags (nome + cor): the kanban columns of Conversas.
--   lais_contato_etiquetas  contato <-> etiqueta junction.
--   lais_notas              internal notes on a contato (<= 4000 chars, SOFT delete).
--   lais_feedback           like/dislike (+ comment) on Julia's service; stored, feeds evals.
--   lais_contatos           + arquivado (hands the chat back to Julia on the next inbound)
--                           + bloqueado (Julia stops; inbound turns for the number are dropped).
--
-- RLS: select_own_org + service_role (writes through the backend only), pattern 267.
-- Access to a single contato (history link, A7) is enforced in the backend (`lais_acesso`), never in RLS.
--
-- FORWARD-ONLY, IDEMPOTENT. PREREQUISITES: 267 (lais_contatos), core 070. Applied by the tech-lead with
-- noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regclass('social_wiring.lais_contatos') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.lais_contatos (migration 267) -- apply 267 first';
  END IF;
END
$guard$;

-- -- 1. lais_contatos: arquivado / bloqueado ---------------------------------------
ALTER TABLE social_wiring.lais_contatos ADD COLUMN IF NOT EXISTS arquivado boolean NOT NULL DEFAULT false;
ALTER TABLE social_wiring.lais_contatos ADD COLUMN IF NOT EXISTS bloqueado boolean NOT NULL DEFAULT false;

-- -- 2. lais_etiquetas ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_etiquetas (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid        NOT NULL,
    nome       text        NOT NULL,
    cor        text        NOT NULL DEFAULT '#6366f1',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_etiquetas_nome_valido CHECK (char_length(btrim(nome)) BETWEEN 1 AND 40),
    CONSTRAINT lais_etiquetas_cor_valida CHECK (cor ~ '^#[0-9a-fA-F]{6}$')
);

COMMENT ON TABLE social_wiring.lais_etiquetas IS
    'Org tag of Conversas (migration 274, contract 9): one kanban column per etiqueta.';

CREATE UNIQUE INDEX IF NOT EXISTS lais_etiquetas_org_nome_uq
    ON social_wiring.lais_etiquetas (org_id, lower(nome));

-- -- 3. lais_contato_etiquetas -------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_contato_etiquetas (
    contato_id  uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    etiqueta_id uuid        NOT NULL REFERENCES social_wiring.lais_etiquetas (id) ON DELETE CASCADE,
    org_id      uuid        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_contato_etiquetas_pk PRIMARY KEY (contato_id, etiqueta_id)
);

CREATE INDEX IF NOT EXISTS idx_lais_contato_etiquetas_etiqueta
    ON social_wiring.lais_contato_etiquetas (etiqueta_id);

-- -- 4. lais_notas -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_notas (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid        NOT NULL,
    contato_id     uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    autor_user_id  uuid,
    texto          text        NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    deleted_at     timestamptz,
    CONSTRAINT lais_notas_texto_valido CHECK (char_length(btrim(texto)) BETWEEN 1 AND 4000)
);

CREATE INDEX IF NOT EXISTS idx_lais_notas_contato
    ON social_wiring.lais_notas (contato_id, created_at DESC) WHERE deleted_at IS NULL;

-- -- 5. lais_feedback ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_feedback (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid        NOT NULL,
    contato_id   uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    interacao_id uuid        REFERENCES social_wiring.lais_interacoes (id) ON DELETE SET NULL,
    user_id      uuid,
    nota         text        NOT NULL,
    comentario   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_feedback_nota_valida CHECK (nota IN ('like', 'dislike')),
    CONSTRAINT lais_feedback_comentario_tamanho CHECK (comentario IS NULL OR char_length(comentario) <= 1000)
);

CREATE INDEX IF NOT EXISTS idx_lais_feedback_contato
    ON social_wiring.lais_feedback (contato_id, created_at DESC);

-- -- 6. RLS --------------------------------------------------------------------------
ALTER TABLE social_wiring.lais_etiquetas         ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_contato_etiquetas ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_notas             ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_feedback          ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_etiquetas_select_own_org" ON social_wiring.lais_etiquetas;
CREATE POLICY "lais_etiquetas_select_own_org" ON social_wiring.lais_etiquetas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_etiquetas_service_role" ON social_wiring.lais_etiquetas;
CREATE POLICY "lais_etiquetas_service_role" ON social_wiring.lais_etiquetas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_contato_etiquetas_select_own_org" ON social_wiring.lais_contato_etiquetas;
CREATE POLICY "lais_contato_etiquetas_select_own_org" ON social_wiring.lais_contato_etiquetas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_contato_etiquetas_service_role" ON social_wiring.lais_contato_etiquetas;
CREATE POLICY "lais_contato_etiquetas_service_role" ON social_wiring.lais_contato_etiquetas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_notas_select_own_org" ON social_wiring.lais_notas;
CREATE POLICY "lais_notas_select_own_org" ON social_wiring.lais_notas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_notas_service_role" ON social_wiring.lais_notas;
CREATE POLICY "lais_notas_service_role" ON social_wiring.lais_notas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_feedback_select_own_org" ON social_wiring.lais_feedback;
CREATE POLICY "lais_feedback_select_own_org" ON social_wiring.lais_feedback
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_feedback_service_role" ON social_wiring.lais_feedback;
CREATE POLICY "lais_feedback_service_role" ON social_wiring.lais_feedback
    FOR ALL TO service_role USING (true) WITH CHECK (true);
