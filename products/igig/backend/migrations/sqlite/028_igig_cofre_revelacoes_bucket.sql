-- ============================================================================
-- IgIg — SQLite mirror of `028_igig_cofre_revelacoes_bucket.sql` (028 ↔ 028).
-- Parity-tested by tests/test_schema_parity.py.
--
-- No `storage.buckets` mirror: SQLite dev/tests use the seed's
-- `FakeStorageBackend` / `LocalFilesystemStorageBackend`, neither of which
-- has a bucket-provisioning step to mirror.
--
-- Same dialect differences as 008: TEXT ids, TEXT timestamps, no RLS
-- (app-layer org scoping), no service-role bypass policy (SQLite has no
-- roles).
-- ============================================================================

CREATE TABLE IF NOT EXISTS cofre_revelacoes (
    id           TEXT PRIMARY KEY,
    org_id       TEXT NOT NULL,
    acesso_id    TEXT NOT NULL REFERENCES acesso (id) ON DELETE CASCADE,
    revelado_por TEXT,
    revelado_em  TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_igig_cofre_revelacoes_org ON cofre_revelacoes (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_cofre_revelacoes_acesso
    ON cofre_revelacoes (org_id, acesso_id, revelado_em DESC);

-- achado 22: precise per-segment duration. `minutos` stays for existing
-- readers; `minutos_da_tarefa` now sums this BEFORE converting to minutes.
ALTER TABLE apontamento ADD COLUMN duracao_segundos INTEGER;
