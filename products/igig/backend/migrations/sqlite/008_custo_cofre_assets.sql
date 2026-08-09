-- ============================================================================
-- IgIg — SQLite mirror of `008_igig_custo_cofre_assets.sql` (008 ↔ 008).
-- Parity-tested by tests/test_schema_parity.py.
--
-- Same deliberate dialect differences as 006/007: TEXT ids, TEXT timestamps,
-- REAL for NUMERIC, INTEGER for BOOLEAN, no RLS (app-layer org scoping), no
-- updated_at trigger (the store stamps it).
-- ============================================================================

CREATE TABLE IF NOT EXISTS funcao (
    id                TEXT PRIMARY KEY,
    org_id            TEXT NOT NULL,
    nome              TEXT NOT NULL,
    custo_hora_padrao REAL NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_funcao_org ON funcao (org_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_funcao_nome ON funcao (org_id, nome);

CREATE TABLE IF NOT EXISTS profissional (
    id                  TEXT PRIMARY KEY,
    org_id              TEXT NOT NULL,
    usuario_id          TEXT,
    nome                TEXT NOT NULL,
    funcao_id           TEXT REFERENCES funcao (id) ON DELETE SET NULL,
    custo_hora_override REAL,
    ativo               INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL,
    updated_at          TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_profissional_org ON profissional (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_profissional_usuario ON profissional (org_id, usuario_id);

CREATE TABLE IF NOT EXISTS acesso (
    id            TEXT PRIMARY KEY,
    org_id        TEXT NOT NULL,
    cliente_id    TEXT NOT NULL REFERENCES cliente (id) ON DELETE CASCADE,
    rotulo        TEXT NOT NULL,
    plataforma    TEXT,
    url           TEXT,
    usuario       TEXT,
    senha_cifrada TEXT,
    observacoes   TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_acesso_org ON acesso (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_acesso_cliente ON acesso (org_id, cliente_id);

CREATE TABLE IF NOT EXISTS peca (
    id            TEXT PRIMARY KEY,
    org_id        TEXT NOT NULL,
    pauta_id      TEXT NOT NULL REFERENCES pauta (id) ON DELETE CASCADE,
    storage_key   TEXT NOT NULL,
    nome_arquivo  TEXT,
    mime_type     TEXT,
    tamanho_bytes INTEGER,
    ordem         INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_peca_org ON peca (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_peca_pauta ON peca (org_id, pauta_id, ordem);
