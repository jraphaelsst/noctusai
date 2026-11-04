-- 055: up to three properties per offer run (owner's rule, 2026-11-03; Julia v3 contract §12.6).
--
-- Supersedes the one-per-batch interim: `qualificacao_parametros.lote_ofertas` is the size of each offer run
-- (default 3, 1..5) and the Studio editor shows the field again. Published versions are immutable (trigger) and
-- keep their value; a new draft copies its parent. Only the column default changes here.
ALTER TABLE agents.qualificacao_parametros ALTER COLUMN lote_ofertas SET DEFAULT 3;
