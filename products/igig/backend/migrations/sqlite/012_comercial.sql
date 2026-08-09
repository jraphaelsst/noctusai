-- ============================================================================
-- IgIg — SQLite mirror of `012_igig_comercial.sql` (012 ↔ 012). Parity-tested.
--
-- SQLite's ALTER TABLE ADD COLUMN has no IF NOT EXISTS, and re-running must
-- stay idempotent, so `contrato`'s new columns are declared in the 006 mirror
-- instead — the mirrors are applied as a set, never incrementally against an
-- existing database.
-- ============================================================================

CREATE TABLE IF NOT EXISTS lead (
    id                   TEXT PRIMARY KEY,
    org_id               TEXT NOT NULL,
    nome                 TEXT NOT NULL,
    email                TEXT,
    telefone             TEXT,
    empresa              TEXT,
    nicho                TEXT,
    canais_atuais        TEXT,
    dores                TEXT,
    orcamento_disponivel REAL,
    origem               TEXT,
    status               TEXT NOT NULL DEFAULT 'novo'
                         CHECK (status IN ('novo', 'qualificado', 'descartado', 'convertido')),
    cliente_id           TEXT REFERENCES cliente (id) ON DELETE SET NULL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_lead_org ON lead (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_lead_status ON lead (org_id, status);

CREATE TABLE IF NOT EXISTS orcamento (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    lead_id         TEXT REFERENCES lead (id) ON DELETE SET NULL,
    cliente_id      TEXT REFERENCES cliente (id) ON DELETE CASCADE,
    titulo          TEXT NOT NULL,
    escopo          TEXT NOT NULL DEFAULT '[]',
    horas_estimadas REAL NOT NULL DEFAULT 0,
    custo_estimado  REAL NOT NULL DEFAULT 0,
    preco_sugerido  REAL NOT NULL DEFAULT 0,
    preco_final     REAL,
    margem_alvo     REAL NOT NULL DEFAULT 50,
    status          TEXT NOT NULL DEFAULT 'rascunho'
                    CHECK (status IN ('rascunho', 'enviado', 'aceito', 'recusado')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_orcamento_org ON orcamento (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_orcamento_lead ON orcamento (org_id, lead_id);
