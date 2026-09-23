-- ============================================================================
-- IgIg — SQLite mirror of `023_igig_automacoes.sql` (023 ↔ 023). Parity-tested.
--
-- The `automacao_execucao.movimento_id` column and the widened status CHECK
-- are declared in the 018 mirror (SQLite has no ADD COLUMN IF NOT EXISTS /
-- ALTER CONSTRAINT; the mirrors are applied as a set). Only the indexes live
-- here.
-- ============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_automacao_execucao_entrada
    ON automacao_execucao (automacao_id, entidade_id, movimento_id)
    WHERE movimento_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_igig_automacao_execucao_org
    ON automacao_execucao (org_id, executado_em);
