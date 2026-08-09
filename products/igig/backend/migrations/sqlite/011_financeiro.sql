-- ============================================================================
-- IgIg — SQLite mirror of `011_igig_financeiro.sql` (011 ↔ 011). Parity-tested.
-- ============================================================================

CREATE TABLE IF NOT EXISTS fatura (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    cliente_id  TEXT NOT NULL REFERENCES cliente (id) ON DELETE CASCADE,
    contrato_id TEXT REFERENCES contrato (id) ON DELETE SET NULL,
    competencia TEXT NOT NULL,
    valor_total REAL NOT NULL DEFAULT 0,
    vencimento  TEXT,
    status      TEXT NOT NULL DEFAULT 'aberta'
                CHECK (status IN ('aberta', 'enviada', 'paga', 'vencida', 'cancelada')),
    pago_em     TEXT,
    gateway_id  TEXT,
    nfse_id     TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_fatura_org ON fatura (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_fatura_cliente ON fatura (org_id, cliente_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_fatura_competencia
    ON fatura (org_id, contrato_id, competencia)
    WHERE contrato_id IS NOT NULL AND status <> 'cancelada';

CREATE TABLE IF NOT EXISTS fatura_item (
    id         TEXT PRIMARY KEY,
    org_id     TEXT NOT NULL,
    fatura_id  TEXT NOT NULL REFERENCES fatura (id) ON DELETE CASCADE,
    descricao  TEXT NOT NULL,
    tipo       TEXT NOT NULL DEFAULT 'mensalidade'
               CHECK (tipo IN ('mensalidade', 'excedente', 'desconto', 'avulso')),
    quantidade INTEGER NOT NULL DEFAULT 1,
    valor_unit REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_fatura_item_org ON fatura_item (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_fatura_item_fatura ON fatura_item (org_id, fatura_id);
