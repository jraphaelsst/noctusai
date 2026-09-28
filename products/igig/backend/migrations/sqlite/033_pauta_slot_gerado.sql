-- SQLite mirror of ../033_igig_pauta_slot_gerado.sql — no RLS (not supported).
CREATE TABLE IF NOT EXISTS pauta_slot_gerado (
    id                  TEXT PRIMARY KEY,
    org_id              TEXT NOT NULL,
    orcamento_item_id   TEXT NOT NULL REFERENCES orcamento_item (id) ON DELETE CASCADE,
    slot_date           TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    UNIQUE (org_id, orcamento_item_id, slot_date)
);

CREATE INDEX IF NOT EXISTS idx_pauta_slot_gerado_item ON pauta_slot_gerado (orcamento_item_id);
