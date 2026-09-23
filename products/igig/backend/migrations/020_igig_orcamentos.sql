-- ============================================================================
-- IgIg — Orçamentos, Produtos e Serviços (wave 2, slice A)
--
--   produto_servico.formato — the pauta FORMAT a criação-de-conteúdo product
--       delivers (feed/carrossel/reels/story/…). Accepting an orçamento turns
--       every recurring criação item into calendar pautas (roadmap R9), and a
--       pauta without its format is a guess the operator has to redo. NULL for
--       products that are not a content format (Gestão de conta items).
--   produto_servico (org_id, secao, nome) UNIQUE — one catalogue entry per
--       name per section. It is also the conflict key that makes the lazy
--       first-read catalogue seed idempotent under concurrent first reads.
--
-- SQLite mirror: migrations/sqlite/020_orcamentos.sql (the new column is
-- declared in the 018 mirror's CREATE TABLE — mirrors apply as a set).
-- ============================================================================
SET search_path = igig, public;

ALTER TABLE igig.produto_servico ADD COLUMN IF NOT EXISTS formato TEXT;
ALTER TABLE igig.produto_servico DROP CONSTRAINT IF EXISTS produto_servico_formato_check;
ALTER TABLE igig.produto_servico ADD CONSTRAINT produto_servico_formato_check
    CHECK (formato IS NULL OR formato IN ('feed', 'carrossel', 'reels', 'story', 'artigo', 'video'));

CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_produto_servico_nome
    ON igig.produto_servico (org_id, secao, nome);
