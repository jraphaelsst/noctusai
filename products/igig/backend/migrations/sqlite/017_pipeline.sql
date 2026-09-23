-- ============================================================================
-- IgIg — SQLite mirror of `017_igig_pipeline.sql` (017 ↔ 017). Parity-tested.
--
-- The pipeline tables are read and written through PostgREST in every real
-- path (app/pipelines.py — seed `noctusai_lib.domain.pipeline`, decision
-- D-A1), never through the SQLite store. They are mirrored anyway so the two
-- schema sets stay one-to-one: a mirror that skips tables is a mirror nobody
-- can trust for the tables it does carry.
--
-- The tarefa / apontamento / aprovacao columns 017 adds are declared in the
-- 006 / 007 mirrors (SQLite has no ADD COLUMN IF NOT EXISTS). The refação
-- function has no SQLite counterpart — SQLite has no stored functions; the
-- atomic increment is a Postgres-side guarantee by design.
-- ============================================================================

CREATE TABLE IF NOT EXISTS pipeline_stages (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    pipeline    TEXT NOT NULL CHECK (pipeline IN ('comercial', 'esteira')),
    slug        TEXT NOT NULL,
    label       TEXT NOT NULL CHECK (length(trim(label)) > 0),
    cor         TEXT NOT NULL DEFAULT 'secondary'
                CHECK (cor IN ('primary', 'secondary', 'success', 'warning', 'destructive', 'muted')),
    posicao     INTEGER NOT NULL DEFAULT 0,
    papel       TEXT CHECK (papel IN ('fechado', 'aprovacao_cliente', 'agendado')),
    ativo       INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    UNIQUE (org_id, pipeline, slug)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_pipeline_stages_papel
    ON pipeline_stages (org_id, pipeline, papel)
    WHERE papel IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_igig_pipeline_stages_board
    ON pipeline_stages (org_id, pipeline, posicao);

CREATE TABLE IF NOT EXISTS pipeline_movimentos (
    id             TEXT PRIMARY KEY,
    org_id         TEXT NOT NULL,
    pipeline       TEXT NOT NULL CHECK (pipeline IN ('comercial', 'esteira')),
    entidade_id    TEXT NOT NULL,
    cliente_id     TEXT REFERENCES cliente (id) ON DELETE SET NULL,
    de_etapa_id    TEXT REFERENCES pipeline_stages (id) ON DELETE SET NULL,
    para_etapa_id  TEXT REFERENCES pipeline_stages (id) ON DELETE SET NULL,
    responsavel_id TEXT,
    motivo         TEXT,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_igig_pipeline_movimentos_entidade
    ON pipeline_movimentos (org_id, pipeline, entidade_id, created_at);
