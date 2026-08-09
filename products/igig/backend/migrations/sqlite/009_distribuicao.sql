-- ============================================================================
-- IgIg — SQLite mirror of `009_igig_distribuicao.sql` (009 ↔ 009).
-- Parity-tested by tests/test_schema_parity.py.
-- Same dialect differences as 006-008: TEXT ids/timestamps, no RLS, no trigger.
-- ============================================================================

CREATE TABLE IF NOT EXISTS publicacao (
    id            TEXT PRIMARY KEY,
    org_id        TEXT NOT NULL,
    pauta_id      TEXT NOT NULL REFERENCES pauta (id) ON DELETE CASCADE,
    canal         TEXT NOT NULL
                  CHECK (canal IN ('instagram', 'facebook', 'tiktok', 'linkedin')),
    status        TEXT NOT NULL DEFAULT 'agendada'
                  CHECK (status IN ('agendada', 'publicando', 'publicada', 'falhou', 'cancelada')),
    agendada_para TEXT,
    publicada_em  TEXT,
    external_id   TEXT,
    permalink     TEXT,
    erro          TEXT,
    tentativas    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_publicacao_org ON publicacao (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_publicacao_pauta ON publicacao (org_id, pauta_id);
CREATE INDEX IF NOT EXISTS idx_igig_publicacao_fila ON publicacao (org_id, status, agendada_para);
-- Partial unique index — SQLite supports these, so the no-double-post
-- invariant is enforced identically on both backends.
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_publicacao_unica
    ON publicacao (org_id, pauta_id, canal)
    WHERE status <> 'cancelada';

CREATE TABLE IF NOT EXISTS metrica (
    id                TEXT PRIMARY KEY,
    org_id            TEXT NOT NULL,
    publicacao_id     TEXT NOT NULL REFERENCES publicacao (id) ON DELETE CASCADE,
    coletada_em       TEXT NOT NULL,
    curtidas          INTEGER NOT NULL DEFAULT 0,
    comentarios       INTEGER NOT NULL DEFAULT 0,
    compartilhamentos INTEGER NOT NULL DEFAULT 0,
    alcance           INTEGER NOT NULL DEFAULT 0,
    cliques_bio       INTEGER NOT NULL DEFAULT 0,
    visualizacoes     INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_metrica_org ON metrica (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_metrica_publicacao
    ON metrica (org_id, publicacao_id, coletada_em);
