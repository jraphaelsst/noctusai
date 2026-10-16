-- ============================================================================
-- Migration 283 -- social_wiring: owner-confirmed price kind (Lais "Atualizacao de imoveis")
-- ============================================================================
-- WHY
-- ---
-- Until now an owner's confirmed status / price (lais_proprietarios_contatos.status_confirmado /
-- preco_confirmado / confirmado_at, migration 275) was ALSO written into the Vista mirror
-- `imoveis` (status / valor_venda / valor_locacao). Those columns belong to the Vista sync, which overwrites
-- them on its next run, so the confirmation silently vanished. The confirmation now lives ONLY here (Lais-owned,
-- never touched by the sync) and the read side (Julia's tools, the Atualizacao page) overlays it on the Vista
-- value when it is newer, with provenance.
--
-- The price needs to say WHICH price it is (venda or locacao): the old write path knew it and then dropped it.
--   preco_tipo_confirmado   'venda' | 'locacao' | NULL (rows confirmed before this migration have no kind
--                           recorded; their price is not overlaid, only their status is).
--
-- Additive, nullable, no table rewrite. RLS unchanged (table-scoped policies from 275 cover the column).
-- NO SECURITY DEFINER function. FORWARD-ONLY, IDEMPOTENT. Applied by the tech-lead with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.lais_proprietarios_contatos
    ADD COLUMN IF NOT EXISTS preco_tipo_confirmado text;

ALTER TABLE social_wiring.lais_proprietarios_contatos
    DROP CONSTRAINT IF EXISTS lais_proprietarios_preco_tipo_valido;
ALTER TABLE social_wiring.lais_proprietarios_contatos
    ADD CONSTRAINT lais_proprietarios_preco_tipo_valido
    CHECK (preco_tipo_confirmado IS NULL OR preco_tipo_confirmado IN ('venda', 'locacao'));

COMMENT ON COLUMN social_wiring.lais_proprietarios_contatos.preco_tipo_confirmado IS
    'Which price preco_confirmado is: venda | locacao (migration 283). NULL on rows confirmed before it existed.';
