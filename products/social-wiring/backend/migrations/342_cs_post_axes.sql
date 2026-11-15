-- ============================================================================
-- Migration 342 · social_wiring: CoreStudio post axes -- cs_post_assets, cs_post_publicacoes, cs_post_eventos
-- ============================================================================
-- WHY
-- ---
-- Spec: products/social-wiring/CORESTUDIO-STRUCTURE.md section 1.2 (owner decision 2026-11-13, Q3): ONE post table
-- (`cs_posts`), but media kind, composition, placement and network are SEPARATE axes, each on its own row:
--
--   * cs_post_assets       -- one row per FILE (tipo_midia imagem|video, ordem, versao, proporcao + duracao_s READ
--                             from the file by the backend, never typed). Composition (unica|sequencia) is DERIVED
--                             from the current asset set, never stored.
--   * cs_post_publicacoes  -- one row per publication TARGET (rede x formato x conta, publicar_em, status, media_id,
--                             permalink). Placement (feed/carrossel/reel/story/short/video_longo) belongs to the
--                             target, not to the post. The rede x formato x assets validity matrix is DATA in
--                             app/modules/media_creation/post_formatos.py and is checked by the service (422).
--   * cs_post_eventos      -- the append-only event ledger (EOA). Written by AFTER triggers on the two tables above,
--                             so every insert/update lands its event IN THE SAME TRANSACTION by construction
--                             (PostgREST is one call = one transaction; two calls could never be). The actor rides
--                             on the row (`atualizado_por`), set by the service.
--
-- `cs_posts.formato` is DEPRECATED (kept readable, no longer written, not dropped): a post has no single format.
-- GuardProbes: `_SW_342_PROBES` in mcp/noctusai/tools/noctus/dev/verify_db_guards.py (append-only trigger + target unique index).
-- FORWARD-ONLY, IDEMPOTENT, backward-compatible with the previous image (new tables + a comment only).
-- Requires 241 (cs_posts), 005 (integration_accounts). Service-only like every table since 328/330.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_posts') IS NULL THEN
    RAISE EXCEPTION 'Migration 342 requires social_wiring.cs_posts (migration 241) -- apply 241 first';
  END IF;
  IF to_regclass('social_wiring.integration_accounts') IS NULL THEN
    RAISE EXCEPTION 'Migration 342 requires social_wiring.integration_accounts (migration 005) -- apply 005 first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. cs_post_assets -- one row per file
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_post_assets (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    post_id        UUID NOT NULL REFERENCES social_wiring.cs_posts (id) ON DELETE CASCADE,
    tipo_midia     TEXT NOT NULL,
    ordem          INTEGER NOT NULL DEFAULT 1,
    versao         INTEGER NOT NULL DEFAULT 1,
    proporcao      TEXT NOT NULL,
    largura        INTEGER NOT NULL,
    altura         INTEGER NOT NULL,
    duracao_s      NUMERIC(10, 3),
    storage_path   TEXT NOT NULL,
    mime_type      TEXT,
    tamanho_bytes  BIGINT,
    status         TEXT NOT NULL DEFAULT 'pronto',
    criado_por     UUID,
    atualizado_por UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (tipo_midia IN ('imagem', 'video')),
    CHECK (ordem >= 1),
    CHECK (versao >= 1),
    CHECK (proporcao IN ('1:1', '4:5', '9:16', '16:9', 'outra')),
    CHECK (largura > 0 AND altura > 0),
    CHECK (
        (tipo_midia = 'video' AND duracao_s IS NOT NULL AND duracao_s > 0)
        OR (tipo_midia = 'imagem' AND duracao_s IS NULL)),
    CHECK (status IN ('em_producao', 'pronto', 'aprovado', 'reprovado', 'arquivado')),
    CHECK (char_length(storage_path) BETWEEN 1 AND 1024),
    UNIQUE (post_id, ordem, versao)
);
CREATE INDEX IF NOT EXISTS cs_post_assets_post_idx ON social_wiring.cs_post_assets (org_id, post_id, ordem, versao DESC);

-- ----------------------------------------------------------------------------
-- 2. cs_post_publicacoes -- one row per publication target
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_post_publicacoes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    post_id        UUID NOT NULL REFERENCES social_wiring.cs_posts (id) ON DELETE CASCADE,
    rede           TEXT NOT NULL,
    formato        TEXT NOT NULL,
    conta_id       UUID REFERENCES social_wiring.integration_accounts (id) ON DELETE SET NULL,
    publicar_em    TIMESTAMPTZ NOT NULL,
    status         TEXT NOT NULL DEFAULT 'agendado',
    origem         TEXT NOT NULL DEFAULT 'app',
    assets_ids     UUID[] NOT NULL DEFAULT '{}',
    media_id       TEXT,
    permalink      TEXT,
    motivo_falha   TEXT,
    publicado_em   TIMESTAMPTZ,
    criado_por     UUID,
    atualizado_por UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (rede IN ('instagram', 'facebook', 'youtube')),
    CHECK (formato IN ('feed', 'carrossel', 'reel', 'story', 'short', 'video_longo')),
    CHECK (status IN ('agendado', 'publicado', 'falhou', 'cancelado')),
    CHECK (origem IN ('app', 'manual', 'migracao')),
    CHECK (motivo_falha IS NULL OR char_length(motivo_falha) <= 500),
    CHECK (status <> 'publicado' OR (publicado_em IS NOT NULL))
);
-- The same post is never queued twice for the same rede x formato x conta while it is live.
CREATE UNIQUE INDEX IF NOT EXISTS cs_post_publicacoes_alvo_uq
    ON social_wiring.cs_post_publicacoes (post_id, rede, formato, conta_id)
    WHERE status IN ('agendado', 'publicado');
-- The scheduler's due-scan (slice S4).
CREATE INDEX IF NOT EXISTS cs_post_publicacoes_devidas_idx
    ON social_wiring.cs_post_publicacoes (publicar_em) WHERE status = 'agendado';
CREATE INDEX IF NOT EXISTS cs_post_publicacoes_post_idx ON social_wiring.cs_post_publicacoes (org_id, post_id, created_at);

-- ----------------------------------------------------------------------------
-- 3. cs_post_eventos -- append-only ledger (no FK: an event outlives its row)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_post_eventos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    post_id       UUID NOT NULL,
    asset_id      UUID,
    publicacao_id UUID,
    tipo          TEXT NOT NULL,
    de            TEXT,
    para          TEXT,
    dados         JSONB NOT NULL DEFAULT '{}'::jsonb,
    ator_id       UUID,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (tipo IN (
        'midia_versao_criada', 'midia_status_alterado',
        'publicacao_agendada', 'publicacao_reagendada', 'publicado', 'publicacao_falhou', 'publicacao_cancelada'))
);
CREATE INDEX IF NOT EXISTS cs_post_eventos_post_idx ON social_wiring.cs_post_eventos (org_id, post_id, criado_em);
CREATE INDEX IF NOT EXISTS cs_post_eventos_tipo_idx ON social_wiring.cs_post_eventos (org_id, tipo, criado_em);

CREATE OR REPLACE FUNCTION social_wiring.cs_post_eventos_imutavel()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'cs_post_eventos_imutavel: cs_post_eventos is append-only (% refused)', TG_OP USING ERRCODE = 'insufficient_privilege';
END;
$$;
DROP TRIGGER IF EXISTS cs_post_eventos_imutavel ON social_wiring.cs_post_eventos;
CREATE TRIGGER cs_post_eventos_imutavel
    BEFORE UPDATE OR DELETE ON social_wiring.cs_post_eventos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.cs_post_eventos_imutavel();

-- ----------------------------------------------------------------------------
-- 4. Event triggers -- the SAME transaction as the write, by construction
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.cs_post_assets_evento()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = social_wiring, pg_catalog, pg_temp
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO social_wiring.cs_post_eventos (org_id, post_id, asset_id, tipo, para, dados, ator_id)
        VALUES (NEW.org_id, NEW.post_id, NEW.id, 'midia_versao_criada', NEW.status,
                jsonb_build_object('tipo_midia', NEW.tipo_midia, 'ordem', NEW.ordem, 'versao', NEW.versao,
                                   'proporcao', NEW.proporcao, 'duracao_s', NEW.duracao_s),
                COALESCE(NEW.atualizado_por, NEW.criado_por));
    ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO social_wiring.cs_post_eventos (org_id, post_id, asset_id, tipo, de, para, dados, ator_id)
        VALUES (NEW.org_id, NEW.post_id, NEW.id, 'midia_status_alterado', OLD.status, NEW.status,
                jsonb_build_object('ordem', NEW.ordem, 'versao', NEW.versao), NEW.atualizado_por);
    END IF;
    RETURN NULL;
END;
$$;
DROP TRIGGER IF EXISTS cs_post_assets_evento ON social_wiring.cs_post_assets;
CREATE TRIGGER cs_post_assets_evento
    AFTER INSERT OR UPDATE ON social_wiring.cs_post_assets
    FOR EACH ROW EXECUTE FUNCTION social_wiring.cs_post_assets_evento();

CREATE OR REPLACE FUNCTION social_wiring.cs_post_publicacoes_evento()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = social_wiring, pg_catalog, pg_temp
AS $$
DECLARE
    v_tipo TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO social_wiring.cs_post_eventos (org_id, post_id, publicacao_id, tipo, para, dados, ator_id)
        VALUES (NEW.org_id, NEW.post_id, NEW.id, 'publicacao_agendada', NEW.status,
                jsonb_build_object('rede', NEW.rede, 'formato', NEW.formato, 'conta_id', NEW.conta_id,
                                   'publicar_em', NEW.publicar_em, 'origem', NEW.origem, 'assets_ids', NEW.assets_ids),
                COALESCE(NEW.atualizado_por, NEW.criado_por));
        RETURN NULL;
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        v_tipo := CASE NEW.status WHEN 'publicado' THEN 'publicado' WHEN 'falhou' THEN 'publicacao_falhou'
                                  WHEN 'cancelado' THEN 'publicacao_cancelada' ELSE 'publicacao_reagendada' END;
    ELSIF NEW.publicar_em IS DISTINCT FROM OLD.publicar_em THEN
        v_tipo := 'publicacao_reagendada';
    ELSE
        RETURN NULL;
    END IF;
    INSERT INTO social_wiring.cs_post_eventos (org_id, post_id, publicacao_id, tipo, de, para, dados, ator_id)
    VALUES (NEW.org_id, NEW.post_id, NEW.id, v_tipo, OLD.status, NEW.status,
            jsonb_build_object('rede', NEW.rede, 'formato', NEW.formato, 'media_id', NEW.media_id,
                               'permalink', NEW.permalink, 'motivo_falha', NEW.motivo_falha,
                               'publicar_em', NEW.publicar_em),
            NEW.atualizado_por);
    RETURN NULL;
END;
$$;
DROP TRIGGER IF EXISTS cs_post_publicacoes_evento ON social_wiring.cs_post_publicacoes;
CREATE TRIGGER cs_post_publicacoes_evento
    AFTER INSERT OR UPDATE ON social_wiring.cs_post_publicacoes
    FOR EACH ROW EXECUTE FUNCTION social_wiring.cs_post_publicacoes_evento();

-- ----------------------------------------------------------------------------
-- 5. RLS + grants (service-only), tiers
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_post_assets ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_assets_service_role" ON social_wiring.cs_post_assets;
CREATE POLICY "cs_post_assets_service_role" ON social_wiring.cs_post_assets FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_post_assets FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE social_wiring.cs_post_assets TO service_role;

ALTER TABLE social_wiring.cs_post_publicacoes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_publicacoes_service_role" ON social_wiring.cs_post_publicacoes;
CREATE POLICY "cs_post_publicacoes_service_role" ON social_wiring.cs_post_publicacoes FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_post_publicacoes FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE social_wiring.cs_post_publicacoes TO service_role;

ALTER TABLE social_wiring.cs_post_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_post_eventos_service_role" ON social_wiring.cs_post_eventos;
CREATE POLICY "cs_post_eventos_service_role" ON social_wiring.cs_post_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_post_eventos FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON TABLE social_wiring.cs_post_eventos TO service_role;

COMMENT ON TABLE social_wiring.cs_post_assets IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_publicacoes IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_eventos IS 'tier:org';
COMMENT ON COLUMN social_wiring.cs_post_assets.proporcao IS
    'Derived by the backend from largura x altura read from the file (never typed). Migration 342.';
COMMENT ON COLUMN social_wiring.cs_post_eventos.dados IS
    'Event payload, written by the AFTER triggers on cs_post_assets / cs_post_publicacoes. Migration 342.';
COMMENT ON COLUMN social_wiring.cs_posts.formato IS
    'DEPRECATED (migration 342, owner decision 2026-11-13): placement belongs to cs_post_publicacoes.formato, media kind to cs_post_assets.tipo_midia. Kept readable, no longer written.';

-- ----------------------------------------------------------------------------
-- 6. Private bucket for post media (signed URLs only)
-- ----------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('sw-posts-midia', 'sw-posts-midia', false, 524288000,
        ARRAY['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'video/mp4', 'video/quicktime']::text[])
ON CONFLICT (id) DO UPDATE SET file_size_limit = EXCLUDED.file_size_limit, allowed_mime_types = EXCLUDED.allowed_mime_types;
