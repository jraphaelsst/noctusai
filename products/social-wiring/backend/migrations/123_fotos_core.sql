-- 123_fotos_core.sql -- social_wiring: edicao-fotos core pipeline tables
--
-- Numbering: this SW series is 121 (jobs) / 122 (llm_usage) / 123+ (this
-- file onward) -- see 121_jobs.sql's header for the full renumbering
-- trail. This migration is R1 (engine + review + zip, NO billing;
-- Econômico deferred per projects/edicao-fotos/PROJECT.md §C7/§C8).
--
-- Org-scoped tables for the photo-editing pipeline: settings, batches
-- (lotes), photos, the append-only event log the throughput charts read,
-- edit attempts, AI verdicts (a SEPARATE table -- see below), review
-- decisions, and the training-ready dataset export.
--
-- 🔴 fotos_avaliacoes IS ITS OWN TABLE, deliberately -- per the API
-- contract §1: "The AI verdict is hidden from corretores by table
-- separation, not by field omission — fotos_avaliacoes is its own table
-- so RLS can withhold the whole row. A response shape that merely omits
-- the field is a leak waiting for a refactor." Do not fold this table
-- into fotos_edicoes or fotos_fotos.
--
-- `fotos_lotes_openai` (the Econômico batch-metadata table of the approved
-- plan) was deferred here while C8 blocked Econômico; it now lives in
-- 132_fotos_lotes_openai.sql (W4), together with the FK on
-- `fotos_fotos.openai_batch_id` below. Comment-only note -- this file's
-- DDL is unchanged since it was applied.
--
-- Every org table: org_id + RLS org_id = public.current_org_id() +
-- service_role_bypass, per CLAUDE.md §1 and projects/edicao-fotos/
-- PROJECT.md §5. Batch/photo visibility additionally gates on
-- creator-or-org-admin-or-platform-admin (contract §1: "Batch visible to
-- its creator + that agency's admins + platform admin") via the shared
-- `fotos_lote_visivel()` helper.
--
-- FORWARD-ONLY. MIGRATION FILE ONLY -- not applied to any database by this
-- change. Applying needs owner consent.

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. fotos_org_settings -- per-org config (edit types, editor model, speed)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_org_settings (
    org_id                 UUID PRIMARY KEY,
    -- Subset of the fixed edit-type vocabulary the owner defined
    -- (contract §0/plan §1): cor_luz (color/light), ceu (sky
    -- replacement), declutter, staging_virtual (virtual staging --
    -- watermark + filename-suffix obligations live in the engine, not
    -- here).
    tipos_edicao_ativos    TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
        CHECK (tipos_edicao_ativos <@ ARRAY['cor_luz', 'ceu', 'declutter', 'staging_virtual']::TEXT[]),
    -- NULL = no editor model configured -> batch creation is BLOCKED
    -- (contract §2 `modelo_configurado=false`). No platform default
    -- exists, deliberately (plan §1: "no default; set per org").
    modelo_editor_id       TEXT,
    -- NULL = follow the platform default (fotos_platform_settings.
    -- velocidade_default). Non-NULL overrides it for this org.
    velocidade_override    TEXT CHECK (velocidade_override IN ('urgente', 'economico')),
    limite_fotos_por_lote  INTEGER NOT NULL DEFAULT 100 CHECK (limite_fotos_por_lote > 0),
    limite_bytes_por_foto  BIGINT NOT NULL DEFAULT 26214400 CHECK (limite_bytes_por_foto > 0),
    -- Agency-admin-controllable off-switch (plan §1: "agency admins opt in
    -- per user; platform admin can switch the whole notification off/on"
    -- -- the platform-wide switch lives on fotos_platform_settings; this
    -- is the org-level layer of that cascade).
    notificacoes_ativas    BOOLEAN NOT NULL DEFAULT true,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.fotos_org_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fotos_org_settings_select_own_org" ON social_wiring.fotos_org_settings
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "fotos_org_settings_admin_write" ON social_wiring.fotos_org_settings
    FOR ALL TO authenticated
    USING (
        org_id = public.current_org_id()
        AND (public.current_org_role() = ANY (ARRAY['owner', 'admin', 'manager']) OR public.is_platform_admin())
    )
    WITH CHECK (
        org_id = public.current_org_id()
        AND (public.current_org_role() = ANY (ARRAY['owner', 'admin', 'manager']) OR public.is_platform_admin())
    );

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_org_settings
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. fotos_platform_settings -- singleton platform-admin defaults
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_platform_settings (
    id                            INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    velocidade_default            TEXT NOT NULL DEFAULT 'urgente' CHECK (velocidade_default IN ('urgente', 'economico')),
    notificacoes_globais_ativas   BOOLEAN NOT NULL DEFAULT true,
    -- Admin setting (contract §10 open item): USD per GB-month, used by
    -- the storage cost metric. NULL = not yet configured; the dashboard
    -- reports the storage line as unpriced rather than assuming a value.
    preco_storage_gb_mes_usd      NUMERIC(10, 4),
    updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO social_wiring.fotos_platform_settings (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;

ALTER TABLE social_wiring.fotos_platform_settings ENABLE ROW LEVEL SECURITY;

-- Platform config is not org data -- readable by platform admin only.
-- Backend computes /capacidades server-side via its own admin client, so
-- no broader read policy is needed for the live path.
CREATE POLICY "fotos_platform_settings_select_platform_admin" ON social_wiring.fotos_platform_settings
    FOR SELECT TO authenticated
    USING (public.is_platform_admin());

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_platform_settings
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ----------------------------------------------------------------------------
-- 3. fotos_lotes -- batches
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_lotes (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL,
    nome                 TEXT NOT NULL,
    criado_por           UUID NOT NULL,
    -- Optional link to a Vista imóvel (plan §1: "optional link to imóvel
    -- (org_id, codigo)"). Not a hard FK -- Vista data lives outside this
    -- schema.
    imovel_org_id        UUID,
    imovel_codigo        TEXT,
    origem               TEXT NOT NULL CHECK (origem IN ('upload', 'vista')),
    velocidade           TEXT NOT NULL CHECK (velocidade IN ('urgente', 'economico')),
    -- Effective guide snapshot at submit (contract §6: "snapshotted onto
    -- the batch at submit so an in-flight batch never changes mid-run").
    guia_efetivo_id      UUID,
    guia_efetivo_sha256  TEXT,
    modelo_editor_id     TEXT,
    status               TEXT NOT NULL DEFAULT 'rascunho'
        CHECK (status IN ('rascunho', 'submetido', 'processando', 'pronto')),
    submetido_at         TIMESTAMPTZ,
    pronto_at            TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_fotos_lotes_org_created
    ON social_wiring.fotos_lotes (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_fotos_lotes_criado_por
    ON social_wiring.fotos_lotes (criado_por);

-- ----------------------------------------------------------------------------
-- Shared visibility predicate -- creator OR org admin-tier role OR
-- platform admin, scoped to the lote's own org. Reused by every child
-- table's SELECT policy below (contract §1's batch-visibility rule).
-- The predicate is created AFTER fotos_lotes: a LANGUAGE sql body is
-- validated at CREATE time, so defining it first fails with 42P01 on a
-- real database (caught applying this file to prod on 2026-09-16; the
-- parse-only tests could not see it).
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION social_wiring.fotos_lote_visivel(p_lote_id UUID)
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = social_wiring, public
AS $$
    SELECT public.is_platform_admin() OR EXISTS (
        SELECT 1 FROM social_wiring.fotos_lotes l
        WHERE l.id = p_lote_id
          AND l.org_id = public.current_org_id()
          AND (
              l.criado_por = (SELECT auth.uid())
              OR public.current_org_role() = ANY (ARRAY['owner', 'admin', 'manager'])
          )
    );
$$;

ALTER TABLE social_wiring.fotos_lotes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fotos_lotes_select_visivel" ON social_wiring.fotos_lotes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id() AND social_wiring.fotos_lote_visivel(id));

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_lotes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 4. fotos_fotos -- one row per photo
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_fotos (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL,
    lote_id                 UUID NOT NULL REFERENCES social_wiring.fotos_lotes (id) ON DELETE CASCADE,
    -- Upload order -- the zip filename's NN prefix (plan §2: "zip NN in
    -- upload order, 2 digits (3 when >99)").
    ordem                   INTEGER NOT NULL,
    storage_path_original   TEXT NOT NULL,
    storage_path_editada    TEXT,
    vista_codigo            TEXT,
    largura_original        INTEGER,
    altura_original         INTEGER,
    status                  TEXT NOT NULL DEFAULT 'recebida'
        CHECK (status IN (
            'recebida', 'normalizando', 'pronta', 'editando',
            'em_lote_openai', 'editada', 'avaliando',
            'aguardando_decisao', 'aprovada', 'rejeitada', 'falhou'
        )),
    tentativas               INTEGER NOT NULL DEFAULT 0,
    falha_motivo             TEXT,
    -- Econômico provider batch id; FK added by 132_fotos_lotes_openai.sql.
    openai_batch_id          TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (lote_id, ordem)
);

CREATE INDEX IF NOT EXISTS ix_fotos_fotos_lote
    ON social_wiring.fotos_fotos (lote_id, ordem);
CREATE INDEX IF NOT EXISTS ix_fotos_fotos_org
    ON social_wiring.fotos_fotos (org_id);
CREATE INDEX IF NOT EXISTS ix_fotos_fotos_status
    ON social_wiring.fotos_fotos (status);

ALTER TABLE social_wiring.fotos_fotos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fotos_fotos_select_visivel" ON social_wiring.fotos_fotos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id() AND social_wiring.fotos_lote_visivel(lote_id));

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_fotos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 5. fotos_eventos -- append-only state-transition log (throughput charts)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_eventos (
    id           BIGSERIAL PRIMARY KEY,
    org_id       UUID NOT NULL,
    lote_id      UUID NOT NULL REFERENCES social_wiring.fotos_lotes (id) ON DELETE CASCADE,
    foto_id      UUID REFERENCES social_wiring.fotos_fotos (id) ON DELETE CASCADE,
    tipo         TEXT NOT NULL,   -- e.g. 'transicao_estado' | 'retry_manual' | 'falha'
    estado_de    TEXT,
    estado_para  TEXT,
    detalhe      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_fotos_eventos_lote_created
    ON social_wiring.fotos_eventos (lote_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_fotos_eventos_foto
    ON social_wiring.fotos_eventos (foto_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_fotos_eventos_org_created
    ON social_wiring.fotos_eventos (org_id, created_at DESC);

ALTER TABLE social_wiring.fotos_eventos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fotos_eventos_select_visivel" ON social_wiring.fotos_eventos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id() AND social_wiring.fotos_lote_visivel(lote_id));

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 6. fotos_edicoes -- one row per AI edit attempt
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_edicoes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    lote_id        UUID NOT NULL REFERENCES social_wiring.fotos_lotes (id) ON DELETE CASCADE,
    foto_id        UUID NOT NULL REFERENCES social_wiring.fotos_fotos (id) ON DELETE CASCADE,
    tentativa      INTEGER NOT NULL DEFAULT 1,
    tipos_edicao   TEXT[] NOT NULL
        CHECK (tipos_edicao <@ ARRAY['cor_luz', 'ceu', 'declutter', 'staging_virtual']::TEXT[]),
    modelo_id      TEXT NOT NULL,
    modelo_versao  TEXT,
    velocidade     TEXT NOT NULL CHECK (velocidade IN ('urgente', 'economico')),
    status         TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'concluida', 'falhou')),
    erro           TEXT,
    -- Points at social_wiring.llm_usage.id (122_llm_usage.sql). No FK --
    -- llm_usage is a cross-cutting sink table written by the seed's
    -- SupabaseUsageSink, not owned by this pipeline.
    llm_usage_id   BIGINT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    concluida_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_fotos_edicoes_lote
    ON social_wiring.fotos_edicoes (lote_id);
CREATE INDEX IF NOT EXISTS ix_fotos_edicoes_foto
    ON social_wiring.fotos_edicoes (foto_id, tentativa DESC);
CREATE INDEX IF NOT EXISTS ix_fotos_edicoes_modelo
    ON social_wiring.fotos_edicoes (modelo_id);

ALTER TABLE social_wiring.fotos_edicoes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fotos_edicoes_select_visivel" ON social_wiring.fotos_edicoes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id() AND social_wiring.fotos_lote_visivel(lote_id));

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_edicoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 7. fotos_avaliacoes -- AI verdict, SEPARATE TABLE (see header)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_avaliacoes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    lote_id        UUID NOT NULL REFERENCES social_wiring.fotos_lotes (id) ON DELETE CASCADE,
    foto_id        UUID NOT NULL REFERENCES social_wiring.fotos_fotos (id) ON DELETE CASCADE,
    edicao_id      UUID REFERENCES social_wiring.fotos_edicoes (id) ON DELETE SET NULL,
    recomendacao   TEXT NOT NULL CHECK (recomendacao IN ('aprovar', 'rejeitar')),
    score          NUMERIC(4, 2) NOT NULL CHECK (score >= 0 AND score <= 10),
    motivo         TEXT,
    modelo_id      TEXT NOT NULL,
    modelo_versao  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_fotos_avaliacoes_foto
    ON social_wiring.fotos_avaliacoes (foto_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_fotos_avaliacoes_lote
    ON social_wiring.fotos_avaliacoes (lote_id);

ALTER TABLE social_wiring.fotos_avaliacoes ENABLE ROW LEVEL SECURITY;

-- 🔴 Corretor NEVER — contract §1 role matrix: "See AI verdict ... corretor:
-- never". No creator-based branch here, unlike fotos_lotes/fotos_fotos —
-- admin-tier role or platform admin ONLY, regardless of who created the batch.
CREATE POLICY "fotos_avaliacoes_select_admins" ON social_wiring.fotos_avaliacoes
    FOR SELECT TO authenticated
    USING (
        org_id = public.current_org_id()
        AND public.current_org_role() = ANY (ARRAY['owner', 'admin', 'manager'])
    );

CREATE POLICY "fotos_avaliacoes_select_platform_admin" ON social_wiring.fotos_avaliacoes
    FOR SELECT TO authenticated
    USING (public.is_platform_admin());

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_avaliacoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 8. fotos_decisoes -- review decisions, append-only (always changeable:
--    a new decision is a new row; the latest by created_at is current)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_decisoes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    lote_id       UUID NOT NULL REFERENCES social_wiring.fotos_lotes (id) ON DELETE CASCADE,
    foto_id       UUID NOT NULL REFERENCES social_wiring.fotos_fotos (id) ON DELETE CASCADE,
    decisao       TEXT NOT NULL CHECK (decisao IN ('aprovar', 'rejeitar')),
    comentario    TEXT,
    decidido_por  UUID NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Contract §4: "comentario is required when decisao='rejeitar' (422
    -- otherwise)" -- enforced at the API layer for the clean error
    -- envelope; this CHECK is the DB-level backstop.
    CHECK (decisao <> 'rejeitar' OR comentario IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_fotos_decisoes_foto_created
    ON social_wiring.fotos_decisoes (foto_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_fotos_decisoes_lote
    ON social_wiring.fotos_decisoes (lote_id);

ALTER TABLE social_wiring.fotos_decisoes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fotos_decisoes_select_visivel" ON social_wiring.fotos_decisoes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id() AND social_wiring.fotos_lote_visivel(lote_id));

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_decisoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 9. fotos_dataset -- append-only training-ready export (plan §1: "Every
--    decision is stored as a training-ready dataset for a future
--    trainable model")
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_dataset (
    id                       BIGSERIAL PRIMARY KEY,
    org_id                   UUID NOT NULL,
    lote_id                  UUID NOT NULL REFERENCES social_wiring.fotos_lotes (id) ON DELETE CASCADE,
    foto_id                  UUID NOT NULL REFERENCES social_wiring.fotos_fotos (id) ON DELETE CASCADE,
    decisao_id               UUID NOT NULL REFERENCES social_wiring.fotos_decisoes (id) ON DELETE CASCADE,
    tipos_edicao             TEXT[] NOT NULL,
    guia_efetivo_sha256      TEXT NOT NULL,
    avaliacao_score          NUMERIC(4, 2),
    avaliacao_recomendacao   TEXT CHECK (avaliacao_recomendacao IN ('aprovar', 'rejeitar')),
    decisao_final            TEXT NOT NULL CHECK (decisao_final IN ('aprovar', 'rejeitar')),
    comentario                TEXT,
    storage_path_original     TEXT NOT NULL,
    storage_path_editada       TEXT,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_fotos_dataset_org_created
    ON social_wiring.fotos_dataset (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_fotos_dataset_foto
    ON social_wiring.fotos_dataset (foto_id);

ALTER TABLE social_wiring.fotos_dataset ENABLE ROW LEVEL SECURITY;

-- Append-only for everyone but service_role -- same "no UPDATE/DELETE
-- policy for any role" shape as social_wiring.cliente_documento_acessos
-- (057_card_hub_documentos.sql). SELECT stays admin-tier visible only
-- (this is training data derived from fotos_avaliacoes, which corretor
-- never sees).
CREATE POLICY "fotos_dataset_select_admins" ON social_wiring.fotos_dataset
    FOR SELECT TO authenticated
    USING (
        org_id = public.current_org_id()
        AND public.current_org_role() = ANY (ARRAY['owner', 'admin', 'manager'])
    );

CREATE POLICY "fotos_dataset_select_platform_admin" ON social_wiring.fotos_dataset
    FOR SELECT TO authenticated
    USING (public.is_platform_admin());

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_dataset
    FOR ALL TO service_role USING (true) WITH CHECK (true);
