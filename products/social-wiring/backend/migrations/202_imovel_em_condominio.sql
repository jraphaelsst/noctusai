-- ============================================================================
-- Migration 202 · social_wiring: imovel_dados gains the EXPLICIT "not in a
-- condomínio" answer the vistoria clause needs
-- ============================================================================
-- Owner decision 2026-10-05 (counts over 93 signed/draft contracts): the
-- "DA VISTORIA PRÉVIA" clause carries the CONDOMÍNIO wording in 91/93. The
-- generator used to infer it from `imoveis.empreendimento` being set, which a
-- hand-registered imóvel (149) never has — so it silently printed the
-- non-condomínio wording. New rule: condomínio wording UNLESS the card says
-- explicitly the property is NOT in a condomínio.
--
-- SHAPE: a nullable BOOLEAN, three states — NULL = not stated (condomínio
-- wording, the corpus default), TRUE = in a condomínio, FALSE = explicitly NOT
-- (the only value that switches the wording). A plain operator-typed choice:
-- no machine reading to reconcile and no stamp pair, so no CHECK and no
-- GuardProbe is needed.
--
-- Code shipping with this file: `dados_service.CAMPOS_EDITAVEIS`/`._saida`,
-- `imovel_hub.schemas`, `contrato_gerador.carregador`/`contexto`, the imóvel
-- page control (`ImovelCartorioCard.tsx`).
--
-- FORWARD-ONLY, IDEMPOTENT. 🔴 MIGRATION FILE ONLY — not applied to any DB by
-- this change. Apply via noctus.dev.migrate_product with explicit consent.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS em_condominio BOOLEAN;

COMMENT ON COLUMN social_wiring.imovel_dados.em_condominio IS
    'Whether the imóvel sits in a condomínio (migration 202). NULL = not '
    'stated — the contract''s vistoria clause then uses the condomínio '
    'wording (91/93 signed contracts); FALSE = explicitly NOT in a condomínio '
    '(the only value that switches the wording off); TRUE = in one. Typed by '
    'an operator; read by `carregador._imovel` -> `contexto`.';
