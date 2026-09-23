-- SQLite mirror of 020_igig_orcamentos.sql. `produto_servico.formato` is
-- declared in 018_crm.sql's CREATE TABLE (SQLite has no ADD COLUMN IF NOT
-- EXISTS; the mirrors apply as a set).
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_produto_servico_nome
    ON produto_servico (org_id, secao, nome);
