-- ============================================================================
-- IgIg — SQLite mirror of `010_igig_integracoes.sql` (010 ↔ 010).
-- Parity-tested. Same dialect differences as 006-009.
-- ============================================================================

CREATE TABLE IF NOT EXISTS integracao (
    id            TEXT PRIMARY KEY,
    org_id        TEXT NOT NULL,
    canal         TEXT NOT NULL
                  CHECK (canal IN ('instagram', 'facebook', 'tiktok', 'linkedin')),
    token_cifrado TEXT,
    conta_externa TEXT,
    conectado_em  TEXT,
    ultimo_erro   TEXT,
    ativo         INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_integracao_org ON integracao (org_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_integracao_canal
    ON integracao (org_id, canal);
