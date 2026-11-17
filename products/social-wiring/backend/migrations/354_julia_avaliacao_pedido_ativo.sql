-- ============================================================================
-- 354_julia_avaliacao_pedido_ativo.sql -- Lais study S7 (owner decision 2026-11-17)
-- ============================================================================
-- No satisfaction survey and no Google-review ask for now. The ask code stays, behind a per-org switch that is OFF by
-- default: `julia_avaliacao_config.pedido_ativo`. Existing rows are switched off too (the owner's decision is fleet-wide;
-- an org that wants the ask back turns it on in Julia > Avaliacoes).
--
-- FORWARD-ONLY, IDEMPOTENT. No SECURITY DEFINER. RLS of the table is untouched (migration 280/287).
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.julia_avaliacao_config
    ADD COLUMN IF NOT EXISTS pedido_ativo boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN social_wiring.julia_avaliacao_config.pedido_ativo IS
    'Lais study S7 (migration 354): the Google-review ask is sent only when true. Default false (owner 2026-11-17).';
