-- ============================================================================
-- Migration 241 · social_wiring: Esteira de reels (CoreStudio) -- cs_posts, cs_equipe,
-- the `esteira` pipeline (widened CHECKs), the post card hub, cs_rebind_roteiro, status_pagina rows
-- ============================================================================
-- WHY
-- ---
-- Contract: projects/core-studio/specs/esteira-contract.md section 2 (+ 2.6 probes, 2.7 pages).
-- ONE shared migration written by BE-0; no other slice writes SQL.
--
-- * The Esteira board is ONE more `PipelineConfig` on the shared `pipeline_stages` /
--   `pipeline_movimentos`: their pipeline CHECK gains 'esteira' and the `papel` CHECK gains
--   gravacao / postado / cancelado (dropped and re-added by name).
-- * `cs_posts` is the reel. headline_id / roteiro_id are COMPOSITE FKs on (id, marca_id)
--   with ON DELETE SET NULL (column-list, PG >= 15): a post can never point at another
--   marca's headline/roteiro, and deleting the headline nulls only the FK column, never
--   the NOT NULL marca_id.
-- * `cs_equipe` is the card hub's member source (the org's content team).
-- * The section between the BEGIN/END GENERATED markers is produced by
--   app/modules/media_creation/esteira_config.py :: gerar_migration_card_hub(); a test asserts
--   it is byte-identical. Never hand-edit it.
-- * cs_rebind_roteiro(p_org, p_post, p_old, p_new) is the atomic roteiro take-over on
--   "Reprocessar" (contract 3.5): row-locked, true only when the post still held p_old.
--
-- The legacy `media_creation` status_pagina row is deliberately NOT touched: it is deactivated
-- only in wave 3 (A-3), after Branding and Carrosseis ship as `producao`.
--
-- GuardProbes: `_SW_241_PROBES` in mcp/noctusai/tools/noctus/dev/verify_db_guards.py.
--
-- NOC-REMEDIATE[mc-brand-owners-legacy]: the legacy Criacao de midia brand tables keep
-- their own owner columns; this migration does not touch them and the legacy page's
-- tables stay (contract section A, C11) -- 2026-10-10.
--
-- FORWARD-ONLY, IDEMPOTENT. Requires 034 (pipeline_stages), 087 (kanban_pos numeric),
-- 224 and 229 (cs_headlines, cs_roteiros).
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'Migration 241 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regclass('social_wiring.pipeline_stages') IS NULL THEN
    RAISE EXCEPTION 'Migration 241 requires social_wiring.pipeline_stages (migration 034) -- apply 034 first';
  END IF;
  IF to_regclass('social_wiring.cs_headlines') IS NULL OR to_regclass('social_wiring.cs_roteiros') IS NULL THEN
    RAISE EXCEPTION 'Migration 241 requires social_wiring.cs_headlines / cs_roteiros (migration 229) -- apply 229 first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. Pipeline widening (esteira board on the shared stage + history tables)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.pipeline_stages     DROP CONSTRAINT IF EXISTS pipeline_stages_pipeline_check;
ALTER TABLE social_wiring.pipeline_stages     ADD  CONSTRAINT pipeline_stages_pipeline_check
  CHECK (pipeline IN ('funil', 'processos_venda', 'esteira'));
ALTER TABLE social_wiring.pipeline_movimentos DROP CONSTRAINT IF EXISTS pipeline_movimentos_pipeline_check;
ALTER TABLE social_wiring.pipeline_movimentos ADD  CONSTRAINT pipeline_movimentos_pipeline_check
  CHECK (pipeline IN ('funil', 'processos_venda', 'esteira'));
ALTER TABLE social_wiring.pipeline_stages     DROP CONSTRAINT IF EXISTS pipeline_stages_papel_check;
ALTER TABLE social_wiring.pipeline_stages     ADD  CONSTRAINT pipeline_stages_papel_check
  CHECK (papel IN ('proposta_aceite', 'final', 'gravacao', 'postado', 'cancelado'));

-- ----------------------------------------------------------------------------
-- 2. cs_equipe -- the content team (card hub member source)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_equipe (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    nome        TEXT NOT NULL CHECK (char_length(nome) BETWEEN 1 AND 80 AND nome = btrim(nome)),
    funcao      TEXT CHECK (funcao IS NULL OR char_length(funcao) <= 60),
    cor         TEXT CHECK (cor IS NULL OR cor IN ('primary', 'secondary', 'success', 'warning', 'destructive', 'muted')),
    user_id     UUID,
    ativo       BOOLEAN NOT NULL DEFAULT true,
    created_by  UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE social_wiring.cs_equipe IS
    'Migration 241 - the org content team (videomaker, editor, roteirista...). user_id is optional: freelancers are often not platform users.';

CREATE UNIQUE INDEX IF NOT EXISTS cs_equipe_nome_uq
    ON social_wiring.cs_equipe (org_id, lower(nome));

-- ----------------------------------------------------------------------------
-- 3. Composite-FK targets on the library tables
-- ----------------------------------------------------------------------------
DO $uq$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cs_headlines_id_marca_uq') THEN
    ALTER TABLE social_wiring.cs_headlines
      ADD CONSTRAINT cs_headlines_id_marca_uq UNIQUE (id, marca_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cs_roteiros_id_marca_uq') THEN
    ALTER TABLE social_wiring.cs_roteiros
      ADD CONSTRAINT cs_roteiros_id_marca_uq UNIQUE (id, marca_id);
  END IF;
END
$uq$;

-- ----------------------------------------------------------------------------
-- 4. cs_posts -- the reel
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_posts (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id              UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    formato               TEXT NOT NULL DEFAULT 'reel',
    titulo                TEXT NOT NULL,
    etapa_id              UUID NOT NULL REFERENCES social_wiring.pipeline_stages (id) ON DELETE RESTRICT,
    kanban_pos            NUMERIC NOT NULL DEFAULT 0,
    headline_id           UUID,
    roteiro_id            UUID,
    conta_id              UUID REFERENCES social_wiring.integration_accounts (id) ON DELETE SET NULL,
    gravacao_em           DATE,
    legenda               TEXT,
    hashtags              TEXT[] NOT NULL DEFAULT '{}',
    primeiro_comentario   TEXT,
    links_producao        JSONB NOT NULL DEFAULT '[]'::jsonb,
    postado_em            TIMESTAMPTZ,
    permalink             TEXT,
    ig_media_id           TEXT,
    motivo_bloqueio       TEXT,
    arquivado             BOOLEAN NOT NULL DEFAULT false,
    created_by            UUID,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cs_posts_formato_check
        CHECK (formato IN ('reel')),
    CONSTRAINT cs_posts_titulo_check
        CHECK (char_length(titulo) BETWEEN 1 AND 200 AND titulo = btrim(titulo)),
    CONSTRAINT cs_posts_legenda_check
        CHECK (legenda IS NULL OR char_length(legenda) <= 2200),
    CONSTRAINT cs_posts_hashtags_max
        CHECK (cardinality(hashtags) <= 30),
    CONSTRAINT cs_posts_primeiro_comentario_check
        CHECK (primeiro_comentario IS NULL OR char_length(primeiro_comentario) <= 2200),
    CONSTRAINT cs_posts_links_producao_check
        CHECK (jsonb_typeof(links_producao) = 'array'),
    CONSTRAINT cs_posts_permalink_check
        CHECK (permalink IS NULL OR permalink ~ '^https://(www\.)?instagram\.com/'),
    CONSTRAINT cs_posts_motivo_bloqueio_check
        CHECK (motivo_bloqueio IS NULL OR char_length(motivo_bloqueio) <= 1000),
    -- Composite FKs: a post can only bind a headline/roteiro of ITS OWN marca. SET NULL on the
    -- named column only (PG >= 15) -- never on marca_id, which is NOT NULL.
    CONSTRAINT cs_posts_headline_marca_fk
        FOREIGN KEY (headline_id, marca_id) REFERENCES social_wiring.cs_headlines (id, marca_id)
        ON DELETE SET NULL (headline_id),
    CONSTRAINT cs_posts_roteiro_marca_fk
        FOREIGN KEY (roteiro_id, marca_id) REFERENCES social_wiring.cs_roteiros (id, marca_id)
        ON DELETE SET NULL (roteiro_id)
);
COMMENT ON TABLE social_wiring.cs_posts IS
    'Migration 241 - the reel on the Esteira board. Owns at most one headline and one roteiro (composite FKs on (id, marca_id)); the library keeps every row.';

-- A headline / roteiro belongs to at most one post.
CREATE UNIQUE INDEX IF NOT EXISTS cs_posts_headline_uq
    ON social_wiring.cs_posts (headline_id) WHERE headline_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS cs_posts_roteiro_uq
    ON social_wiring.cs_posts (roteiro_id) WHERE roteiro_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS cs_posts_board_idx
    ON social_wiring.cs_posts (org_id, etapa_id, kanban_pos);
CREATE INDEX IF NOT EXISTS cs_posts_marca_idx
    ON social_wiring.cs_posts (marca_id, arquivado, created_at DESC);

-- A batch generated from inside a post remembers it (never binds a headline by itself).
ALTER TABLE social_wiring.cs_headline_lotes
    ADD COLUMN IF NOT EXISTS post_id UUID REFERENCES social_wiring.cs_posts (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS cs_headline_lotes_post_idx
    ON social_wiring.cs_headline_lotes (post_id) WHERE post_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 5. updated_at triggers
-- ----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS set_updated_at_cs_equipe ON social_wiring.cs_equipe;
CREATE TRIGGER set_updated_at_cs_equipe
    BEFORE UPDATE ON social_wiring.cs_equipe
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_posts ON social_wiring.cs_posts;
CREATE TRIGGER set_updated_at_cs_posts
    BEFORE UPDATE ON social_wiring.cs_posts
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

-- ----------------------------------------------------------------------------
-- 6. RLS (the 229 shape: own-org authenticated, service_role ALL)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_equipe ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_equipe_select_own_org" ON social_wiring.cs_equipe;
CREATE POLICY "cs_equipe_select_own_org"
    ON social_wiring.cs_equipe
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_equipe_write_own_org" ON social_wiring.cs_equipe;
CREATE POLICY "cs_equipe_write_own_org"
    ON social_wiring.cs_equipe
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_equipe_service_role" ON social_wiring.cs_equipe;
CREATE POLICY "cs_equipe_service_role"
    ON social_wiring.cs_equipe
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_posts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_posts_select_own_org" ON social_wiring.cs_posts;
CREATE POLICY "cs_posts_select_own_org"
    ON social_wiring.cs_posts
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_posts_write_own_org" ON social_wiring.cs_posts;
CREATE POLICY "cs_posts_write_own_org"
    ON social_wiring.cs_posts
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_posts_service_role" ON social_wiring.cs_posts;
CREATE POLICY "cs_posts_service_role"
    ON social_wiring.cs_posts
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 7. Card hub for the post
-- ----------------------------------------------------------------------------
-- BEGIN GENERATED card_hub(post)
-- Card hub (post) -- generated by noctusai_lib.domain.card_hub.sql

SET search_path = social_wiring, public;

-- Notes: one `descricao` per card (partial unique index) + many `comentario`.
-- Soft-delete only: a deleted note leaves a tombstone.
CREATE TABLE IF NOT EXISTS social_wiring.cs_post_notas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    post_id UUID NOT NULL REFERENCES social_wiring.cs_posts(id) ON DELETE CASCADE,
    autor_id    UUID,
    tipo        TEXT NOT NULL DEFAULT 'comentario' CHECK (tipo IN ('descricao', 'comentario')),
    corpo       TEXT NOT NULL,
    editado_em  TIMESTAMPTZ,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cs_post_notas_entity ON social_wiring.cs_post_notas (post_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cs_post_notas_org ON social_wiring.cs_post_notas (org_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_cs_post_notas_one_descricao
    ON social_wiring.cs_post_notas (post_id)
    WHERE tipo = 'descricao' AND deleted_at IS NULL;
ALTER TABLE social_wiring.cs_post_notas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_notas_select_own_org" ON social_wiring.cs_post_notas;
CREATE POLICY "cs_post_notas_select_own_org" ON social_wiring.cs_post_notas FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.cs_post_notas;
CREATE POLICY "service_role_bypass" ON social_wiring.cs_post_notas FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ONE org tag catalogue (case-insensitive unique name) + per-card links.
CREATE TABLE IF NOT EXISTS social_wiring.cs_post_tags (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    nome        TEXT NOT NULL,
    cor         TEXT NOT NULL CHECK (cor ~ '^#[0-9a-fA-F]{6}$'),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_cs_post_tags_org_nome ON social_wiring.cs_post_tags (org_id, lower(nome));
ALTER TABLE social_wiring.cs_post_tags ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_tags_select_own_org" ON social_wiring.cs_post_tags;
CREATE POLICY "cs_post_tags_select_own_org" ON social_wiring.cs_post_tags FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.cs_post_tags;
CREATE POLICY "service_role_bypass" ON social_wiring.cs_post_tags FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE IF NOT EXISTS social_wiring.cs_post_tag_links (
    post_id UUID NOT NULL REFERENCES social_wiring.cs_posts(id) ON DELETE CASCADE,
    tag_id      UUID NOT NULL REFERENCES social_wiring.cs_post_tags(id) ON DELETE CASCADE,
    org_id      UUID NOT NULL,
    criado_por  UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (post_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_cs_post_tag_links_tag ON social_wiring.cs_post_tag_links (tag_id);
CREATE INDEX IF NOT EXISTS idx_cs_post_tag_links_org ON social_wiring.cs_post_tag_links (org_id);
ALTER TABLE social_wiring.cs_post_tag_links ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_tag_links_select_own_org" ON social_wiring.cs_post_tag_links;
CREATE POLICY "cs_post_tag_links_select_own_org" ON social_wiring.cs_post_tag_links FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.cs_post_tag_links;
CREATE POLICY "service_role_bypass" ON social_wiring.cs_post_tag_links FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Assignment: points at the member source's id, NEVER at a name.
CREATE TABLE IF NOT EXISTS social_wiring.cs_post_membros (
    post_id UUID NOT NULL REFERENCES social_wiring.cs_posts(id) ON DELETE CASCADE,
    equipe_id UUID NOT NULL REFERENCES social_wiring.cs_equipe(id) ON DELETE CASCADE,
    org_id      UUID NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (post_id, equipe_id)
);
CREATE INDEX IF NOT EXISTS idx_cs_post_membros_member ON social_wiring.cs_post_membros (equipe_id);
CREATE INDEX IF NOT EXISTS idx_cs_post_membros_org ON social_wiring.cs_post_membros (org_id);
ALTER TABLE social_wiring.cs_post_membros ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_membros_select_own_org" ON social_wiring.cs_post_membros;
CREATE POLICY "cs_post_membros_select_own_org" ON social_wiring.cs_post_membros FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.cs_post_membros;
CREATE POLICY "service_role_bypass" ON social_wiring.cs_post_membros FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Trello "Datas" on the entity row.
ALTER TABLE social_wiring.cs_posts
    ADD COLUMN IF NOT EXISTS data_inicio             TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS data_entrega            TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS entrega_concluida       BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS lembrete_minutos_antes  INTEGER,
    ADD COLUMN IF NOT EXISTS recorrencia             TEXT;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cs_posts_recorrencia_valid') THEN
        ALTER TABLE social_wiring.cs_posts
            ADD CONSTRAINT cs_posts_recorrencia_valid
            CHECK (recorrencia IS NULL OR recorrencia IN ('diaria', 'semanal', 'mensal', 'anual'));
    END IF;
END $$;

-- One row per scheduled reminder fire; the partial index is the drain path.
CREATE TABLE IF NOT EXISTS social_wiring.cs_post_lembretes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    post_id UUID NOT NULL REFERENCES social_wiring.cs_posts(id) ON DELETE CASCADE,
    titulo         TEXT NOT NULL DEFAULT '',
    responsavel_id UUID REFERENCES social_wiring.cs_equipe(id) ON DELETE SET NULL,
    dispara_em    TIMESTAMPTZ NOT NULL,
    enviado_em    TIMESTAMPTZ,
    cancelado_em  TIMESTAMPTZ,
    destinatarios JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cs_post_lembretes_pending ON social_wiring.cs_post_lembretes (dispara_em)
    WHERE enviado_em IS NULL AND cancelado_em IS NULL;
CREATE INDEX IF NOT EXISTS idx_cs_post_lembretes_entity ON social_wiring.cs_post_lembretes (post_id, created_at DESC);
ALTER TABLE social_wiring.cs_post_lembretes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_lembretes_select_own_org" ON social_wiring.cs_post_lembretes;
CREATE POLICY "cs_post_lembretes_select_own_org" ON social_wiring.cs_post_lembretes FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.cs_post_lembretes;
CREATE POLICY "service_role_bypass" ON social_wiring.cs_post_lembretes FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Checklists (ad-hoc or stage-instantiated; many per card) + items.
CREATE TABLE IF NOT EXISTS social_wiring.cs_post_checklists (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    post_id UUID NOT NULL REFERENCES social_wiring.cs_posts(id) ON DELETE CASCADE,
    titulo      TEXT NOT NULL,
    posicao     INTEGER NOT NULL DEFAULT 0,
    origem      TEXT NOT NULL CHECK (origem IN ('ad_hoc', 'etapa')),
    etapa_id    UUID REFERENCES social_wiring.pipeline_stages(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cs_post_checklists_entity ON social_wiring.cs_post_checklists (post_id, posicao);
ALTER TABLE social_wiring.cs_post_checklists ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_checklists_select_own_org" ON social_wiring.cs_post_checklists;
CREATE POLICY "cs_post_checklists_select_own_org" ON social_wiring.cs_post_checklists FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.cs_post_checklists;
CREATE POLICY "service_role_bypass" ON social_wiring.cs_post_checklists FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE IF NOT EXISTS social_wiring.cs_post_checklist_itens (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    checklist_id   UUID NOT NULL REFERENCES social_wiring.cs_post_checklists(id) ON DELETE CASCADE,
    texto          TEXT NOT NULL,
    concluido      BOOLEAN NOT NULL DEFAULT false,
    concluido_em   TIMESTAMPTZ,
    concluido_por  UUID,
    posicao        INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cs_post_checklist_itens_checklist ON social_wiring.cs_post_checklist_itens (checklist_id, posicao);
ALTER TABLE social_wiring.cs_post_checklist_itens ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_checklist_itens_select_own_org" ON social_wiring.cs_post_checklist_itens;
CREATE POLICY "cs_post_checklist_itens_select_own_org" ON social_wiring.cs_post_checklist_itens FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.cs_post_checklist_itens;
CREATE POLICY "service_role_bypass" ON social_wiring.cs_post_checklist_itens FOR ALL TO service_role USING (true) WITH CHECK (true);

-- The table-driven retention + upload allow-list (platform-wide, no org_id).
CREATE TABLE IF NOT EXISTS social_wiring.cs_post_documento_tipos (
    tipo_documento  TEXT PRIMARY KEY,
    categoria_lgpd  TEXT NOT NULL,
    retencao_dias   INTEGER,
    identidade      BOOLEAN NOT NULL DEFAULT false,
    ativo           BOOLEAN NOT NULL DEFAULT true,
    descricao       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE social_wiring.cs_post_documento_tipos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_documento_tipos_select_authenticated" ON social_wiring.cs_post_documento_tipos;
CREATE POLICY "cs_post_documento_tipos_select_authenticated" ON social_wiring.cs_post_documento_tipos FOR SELECT TO authenticated
  USING (true);
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.cs_post_documento_tipos;
CREATE POLICY "service_role_bypass" ON social_wiring.cs_post_documento_tipos FOR ALL TO service_role USING (true) WITH CHECK (true);
INSERT INTO social_wiring.cs_post_documento_tipos
    (tipo_documento, categoria_lgpd, retencao_dias, identidade, ativo, descricao)
VALUES
    ('referencia', 'nao_classificado', 365, false, true, 'Referências visuais e briefings'),
    ('outro', 'nao_classificado', 365, false, true, 'Outro documento')
ON CONFLICT (tipo_documento) DO NOTHING;

-- Documents (soft delete with reason) + the append-only access log.
CREATE TABLE IF NOT EXISTS social_wiring.cs_post_documentos (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                 UUID NOT NULL,
    post_id UUID NOT NULL REFERENCES social_wiring.cs_posts(id) ON DELETE CASCADE,
    storage_path           TEXT NOT NULL,
    nome_original          TEXT NOT NULL,
    mime_type              TEXT NOT NULL,
    tamanho_bytes          BIGINT NOT NULL CHECK (tamanho_bytes >= 0),
    tipo_documento         TEXT NOT NULL REFERENCES social_wiring.cs_post_documento_tipos(tipo_documento),
    categoria_lgpd         TEXT NOT NULL,
    retencao_ate           DATE,
    enviado_por            UUID,
    deleted_at             TIMESTAMPTZ,
    delete_motivo          TEXT,
    delete_solicitado_por  UUID,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cs_post_documentos_entity ON social_wiring.cs_post_documentos (post_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cs_post_documentos_org ON social_wiring.cs_post_documentos (org_id);
CREATE INDEX IF NOT EXISTS idx_cs_post_documentos_retencao ON social_wiring.cs_post_documentos (retencao_ate)
    WHERE deleted_at IS NULL AND retencao_ate IS NOT NULL;
ALTER TABLE social_wiring.cs_post_documentos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_documentos_select_own_org" ON social_wiring.cs_post_documentos;
CREATE POLICY "cs_post_documentos_select_own_org" ON social_wiring.cs_post_documentos FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.cs_post_documentos;
CREATE POLICY "service_role_bypass" ON social_wiring.cs_post_documentos FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE IF NOT EXISTS social_wiring.cs_post_documento_acessos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    documento_id  UUID NOT NULL REFERENCES social_wiring.cs_post_documentos(id) ON DELETE CASCADE,
    usuario_id    UUID,
    acao          TEXT NOT NULL CHECK (acao IN ('view', 'download', 'delete')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cs_post_documento_acessos_documento ON social_wiring.cs_post_documento_acessos (documento_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cs_post_documento_acessos_org ON social_wiring.cs_post_documento_acessos (org_id);
ALTER TABLE social_wiring.cs_post_documento_acessos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_documento_acessos_select_own_org" ON social_wiring.cs_post_documento_acessos;
CREATE POLICY "cs_post_documento_acessos_select_own_org" ON social_wiring.cs_post_documento_acessos FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.cs_post_documento_acessos;
CREATE POLICY "service_role_bypass" ON social_wiring.cs_post_documento_acessos FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Private document bucket; object RLS keys on the org_id first path segment.
INSERT INTO storage.buckets (id, name, public)
VALUES ('sw-esteira', 'sw-esteira', false)
ON CONFLICT (id) DO NOTHING;
DROP POLICY IF EXISTS "sw-esteira_storage_select" ON storage.objects;
CREATE POLICY "sw-esteira_storage_select" ON storage.objects FOR SELECT TO authenticated
  USING (bucket_id = 'sw-esteira' AND (storage.foldername(name))[1] = (SELECT public.current_org_id())::text);
DROP POLICY IF EXISTS "sw-esteira_storage_insert" ON storage.objects;
CREATE POLICY "sw-esteira_storage_insert" ON storage.objects FOR INSERT TO authenticated
  WITH CHECK (bucket_id = 'sw-esteira' AND (storage.foldername(name))[1] = (SELECT public.current_org_id())::text);
DROP POLICY IF EXISTS "sw-esteira_storage_update" ON storage.objects;
CREATE POLICY "sw-esteira_storage_update" ON storage.objects FOR UPDATE TO authenticated
  USING (bucket_id = 'sw-esteira' AND (storage.foldername(name))[1] = (SELECT public.current_org_id())::text);
DROP POLICY IF EXISTS "sw-esteira_storage_delete" ON storage.objects;
CREATE POLICY "sw-esteira_storage_delete" ON storage.objects FOR DELETE TO authenticated
  USING (bucket_id = 'sw-esteira' AND (storage.foldername(name))[1] = (SELECT public.current_org_id())::text);
DROP POLICY IF EXISTS "sw-esteira_storage_service" ON storage.objects;
CREATE POLICY "sw-esteira_storage_service" ON storage.objects FOR ALL TO service_role
  USING (bucket_id = 'sw-esteira')
  WITH CHECK (bucket_id = 'sw-esteira');

-- Operator-authored checklist lines. NO `concluido` column: completion is
-- DERIVED (valor_texto / a live documento_id). Deleting the file keeps the line.
CREATE TABLE IF NOT EXISTS social_wiring.cs_post_checklist_extras (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    post_id UUID NOT NULL REFERENCES social_wiring.cs_posts(id) ON DELETE CASCADE,
    label         TEXT NOT NULL,
    tipo          TEXT NOT NULL CHECK (tipo IN ('texto', 'arquivo')),
    valor_texto   TEXT,
    documento_id  UUID REFERENCES social_wiring.cs_post_documentos(id) ON DELETE SET NULL,
    ordem         INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_cs_post_checklist_extras_entity ON social_wiring.cs_post_checklist_extras (post_id, ordem, created_at)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_cs_post_checklist_extras_org ON social_wiring.cs_post_checklist_extras (org_id);
CREATE INDEX IF NOT EXISTS idx_cs_post_checklist_extras_documento ON social_wiring.cs_post_checklist_extras (documento_id)
    WHERE documento_id IS NOT NULL;
ALTER TABLE social_wiring.cs_post_checklist_extras ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_checklist_extras_select_own_org" ON social_wiring.cs_post_checklist_extras;
CREATE POLICY "cs_post_checklist_extras_select_own_org" ON social_wiring.cs_post_checklist_extras FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.cs_post_checklist_extras;
CREATE POLICY "service_role_bypass" ON social_wiring.cs_post_checklist_extras FOR ALL TO service_role USING (true) WITH CHECK (true);

-- END GENERATED

SET search_path = social_wiring, public;

-- "Postagem prevista" (data_entrega) is added by the generated section above.
CREATE INDEX IF NOT EXISTS cs_posts_data_entrega_idx
    ON social_wiring.cs_posts (org_id, data_entrega);

-- ----------------------------------------------------------------------------
-- 8. cs_rebind_roteiro -- atomic take-over of the binding on "Reprocessar" (contract 3.5)
-- ----------------------------------------------------------------------------
-- Row-locks the post; true only when the post still held p_old (false = it moved on -> the
-- service answers 409). p_new must be the same marca as the post (composite FK).
CREATE OR REPLACE FUNCTION social_wiring.cs_rebind_roteiro(p_org uuid, p_post uuid, p_old uuid, p_new uuid)
RETURNS boolean
LANGUAGE plpgsql
SET search_path = social_wiring, public
AS $fn$
DECLARE
  v_current uuid;
BEGIN
  SELECT roteiro_id INTO v_current
    FROM social_wiring.cs_posts
   WHERE id = p_post AND org_id = p_org
     FOR UPDATE;
  IF NOT FOUND OR v_current IS DISTINCT FROM p_old THEN
    RETURN false;
  END IF;
  UPDATE social_wiring.cs_posts SET roteiro_id = p_new WHERE id = p_post AND org_id = p_org;
  RETURN true;
END
$fn$;

REVOKE EXECUTE ON FUNCTION social_wiring.cs_rebind_roteiro(uuid, uuid, uuid, uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_rebind_roteiro(uuid, uuid, uuid, uuid)
    TO service_role;

-- ----------------------------------------------------------------------------
-- 9. Nav: status_pagina (contract 2.7)
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao) VALUES
    ('media-creation-esteira', 'desenvolvimento', 'CoreStudio — Esteira de reels'),
    ('media-creation-branding', 'producao', 'CoreStudio — Branding por marca'),
    ('media-creation-carrosseis', 'producao', 'CoreStudio — Carrosséis e posts de imagem')
ON CONFLICT (nome_pagina) DO NOTHING;
