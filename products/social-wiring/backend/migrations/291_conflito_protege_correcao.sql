-- ============================================================================
-- Migration 291 -- social_wiring: a re-read never overwrites an owner's
-- correction (cliente_campo_conflitos.protege_correcao)
-- ============================================================================
-- WHY
-- ---
-- Owner order 2026-10-20 (prod deal 876): the owner corrected a party's
-- profissao ("aposentanda", a typo printed on the ficha cadastral itself ->
-- "aposentada"); a later re-read of the same ficha put the typo back with no
-- conflict row, and the contract gate then refused the deal.
--
-- The rule (app.modules.card_hub.identidade_extracao_service.correcao_do_dono):
-- a field whose value a person TYPED (`<campo>_origem = 'manual'`, value set)
-- and that is not a form re-saved unchanged over a document (the deal-876
-- phantom `manual`, proven by its own audit row) is an OWNER CORRECTION. A
-- reading that disagrees with it never replaces it: it opens a `pendente`
-- conflict with protege_correcao = true -- "A leitura do documento sugere
-- outro valor para um campo que voce corrigiu". Approve -> the document's
-- value (with its document provenance); reject -> the owner's value stays and
-- the same proposal is never raised again (ja_rejeitado_pelo_usuario).
--
-- The flag is what lets the contract gate tell the two kinds of open conflict
-- apart: an ordinary conflict (two readings disagree, nobody chose) still
-- blocks generation; a protection conflict does NOT -- the owner's value
-- stands until they decide -- it is shown as a warning beside the readiness
-- report, with approve/reject.
--
-- FORWARD-ONLY, IDEMPOTENT. A plain column with a constant default (no
-- rewrite of existing rows' values: every conflict opened before this is an
-- ordinary one). NO SECURITY DEFINER function, no trigger, no constraint.
-- The tech-lead applies it with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.cliente_campo_conflitos
    ADD COLUMN IF NOT EXISTS protege_correcao BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN social_wiring.cliente_campo_conflitos.protege_correcao IS
    'true = valor_anterior is an OWNER CORRECTION (a value a person typed, '
    'origem manual, not an unchanged form re-save) that a document reading '
    'contests. Never overwritten automatically; approve applies the document '
    'value, reject keeps the correction and suppresses the same proposal. Does '
    'not block contract generation (shown as a warning). Migration 291.';
