-- ============================================================================
-- IgIg — Distribuição e Métricas (Módulo 5)
--
--   publicacao — one attempt to publish a pauta to ONE channel. A pauta going
--                to Instagram and TikTok is two rows, because each carries its
--                own external id, status and failure reason.
--   metrica    — an engagement SNAPSHOT for a publicacao at a point in time.
--                Append-only: metrics move, and overwriting them would destroy
--                the only record of how a post performed over its first week.
--
-- SQLite mirror: migrations/sqlite/009_distribuicao.sql (parity-tested).
-- ============================================================================
SET search_path = igig, public;

CREATE TABLE IF NOT EXISTS igig.publicacao (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    pauta_id       UUID NOT NULL REFERENCES igig.pauta (id) ON DELETE CASCADE,
    canal          TEXT NOT NULL
                   CHECK (canal IN ('instagram', 'facebook', 'tiktok', 'linkedin')),
    status         TEXT NOT NULL DEFAULT 'agendada'
                   CHECK (status IN ('agendada', 'publicando', 'publicada', 'falhou', 'cancelada')),
    agendada_para  TIMESTAMPTZ,
    publicada_em   TIMESTAMPTZ,
    -- The platform's own post id. Nullable until the publish succeeds; it is
    -- what every later metrics fetch keys on.
    external_id    TEXT,
    permalink      TEXT,
    -- Populated on failure so the operator sees WHY without reading logs.
    erro           TEXT,
    tentativas     INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_publicacao_org ON igig.publicacao (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_publicacao_pauta ON igig.publicacao (org_id, pauta_id);
CREATE INDEX IF NOT EXISTS idx_igig_publicacao_fila ON igig.publicacao (org_id, status, agendada_para);
-- One live publication per pauta per channel. A retry reuses its row; a
-- duplicate would double-post to the client's real account.
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_publicacao_unica
    ON igig.publicacao (org_id, pauta_id, canal)
    WHERE status <> 'cancelada';

CREATE TABLE IF NOT EXISTS igig.metrica (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    publicacao_id  UUID NOT NULL REFERENCES igig.publicacao (id) ON DELETE CASCADE,
    coletada_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
    curtidas       INTEGER NOT NULL DEFAULT 0,
    comentarios    INTEGER NOT NULL DEFAULT 0,
    compartilhamentos INTEGER NOT NULL DEFAULT 0,
    alcance        INTEGER NOT NULL DEFAULT 0,
    cliques_bio    INTEGER NOT NULL DEFAULT 0,
    visualizacoes  INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_metrica_org ON igig.metrica (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_metrica_publicacao
    ON igig.metrica (org_id, publicacao_id, coletada_em);

-- ============================================================================
-- RLS + updated_at triggers
-- ============================================================================
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['publicacao', 'metrica']
    LOOP
        EXECUTE format('ALTER TABLE igig.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON igig.%I', t || '_org_isolation', t);
        EXECUTE format(
            'CREATE POLICY %I ON igig.%I FOR ALL TO authenticated '
            'USING (org_id = public.current_org_id()) '
            'WITH CHECK (org_id = public.current_org_id())',
            t || '_org_isolation', t
        );
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON igig.%I', 'trg_' || t || '_updated_at', t);
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE ON igig.%I '
            'FOR EACH ROW EXECUTE FUNCTION igig.set_updated_at()',
            'trg_' || t || '_updated_at', t
        );
    END LOOP;
END $$;
