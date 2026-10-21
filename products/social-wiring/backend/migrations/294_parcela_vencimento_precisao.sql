-- ============================================================================
-- Migration 294 -- social_wiring: month-precision parcela deadline
-- ============================================================================
-- WHY: signed contracts carry "prazo máximo de pagamento até maio de 2027" --
-- a deadline expressed as a MONTH, not a day. The operator had to invent a day
-- (31/05/2027) and the generator printed a date the contract never states.
-- `vencimento_precisao` says how much of `vencimento` is meaningful: 'dia'
-- (exact date, the default and every existing row) or 'mes' (only year+month;
-- the date is normalised to the 1st by the service). The date column stays
-- queryable/sortable, which an evento free-text kind would not.
-- Idempotent, additive.
-- ============================================================================
SET search_path = social_wiring, public;

ALTER TABLE social_wiring.atendimento_negociacao_parcelas
    ADD COLUMN IF NOT EXISTS vencimento_precisao TEXT NOT NULL DEFAULT 'dia';
-- No DB CHECK: the closed set {dia, mes} is enforced at the HTTP boundary
-- (Literal) and in the service (_normalizar_vencimento), like the sibling
-- free-vocabulary columns; a CHECK would need a verify_db_guards probe.
