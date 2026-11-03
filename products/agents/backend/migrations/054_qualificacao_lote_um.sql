-- 054: one property per offer batch (owner's rule, 2026-11-03).
--
-- `qualificacao_parametros.lote_ofertas` was the size of each property batch Julia offers (default 3). The
-- business offers ONE property at a time, so 1 is the canonical default and the Studio editor no longer shows
-- the field. Published versions are immutable (trigger) and keep their value; a new draft copies its parent,
-- so the standard's next version sets 1 explicitly. Only the column default changes here.
ALTER TABLE agents.qualificacao_parametros ALTER COLUMN lote_ofertas SET DEFAULT 1;
