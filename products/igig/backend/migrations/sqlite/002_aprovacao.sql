-- ============================================================================
-- IgIg — Portal de Aprovação Externo (Módulo 4) — SQLite mirror of
-- `007_igig_aprovacao.sql`. Parity-tested by tests/test_schema_parity.py.
--
-- Same deliberate dialect differences as 001: TEXT ids, TEXT timestamps, no
-- RLS (app-layer org scoping instead), no updated_at trigger (the store
-- stamps it).
-- ============================================================================

CREATE TABLE IF NOT EXISTS aprovacao (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    tarefa_id   TEXT NOT NULL REFERENCES tarefa (id) ON DELETE CASCADE,
    token       TEXT NOT NULL UNIQUE,
    expira_em   TEXT,
    decidido_em TEXT,
    decisao     TEXT CHECK (decisao IN ('aprovado', 'ajuste')),
    observacao  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_aprovacao_org ON aprovacao (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_aprovacao_tarefa ON aprovacao (org_id, tarefa_id);
