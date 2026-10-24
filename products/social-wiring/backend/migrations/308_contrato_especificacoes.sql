-- ============================================================================
-- Migration 308 -- social_wiring: the contract's SELECTED specifications
--
-- WHAT THIS IS
-- ------------
-- Owner direction, 2026-10-24: the contract's specifications (compra e
-- venda + à vista / sinal + saldo / financiamento bancário / FGTS / parcelas
-- diretas / intermediárias / confissão de dívida / permuta / intermediação)
-- are SELECTABLE in the UI and scope which data the readiness asks for --
-- real deals have no reference contract to copy the shape from.
--
-- `especificacoes`        the selected keys of the code catalogue
--                         (`contrato_gerador/especificacoes.py`, CATALOGO),
--                         stored in catalogue order;
-- `especificacoes_versao` the `CATALOGO_VERSAO` the selection was made
--                         against, so a later vocabulary change can tell an
--                         old selection from a current one.
--
-- NULL (both) = nothing selected: LEGACY mode -- the readiness asks what the
-- data-derived switches imply, exactly as before. No backfill; no existing
-- row changes meaning.
--
-- No CHECK on the vocabulary: it is a versioned CODE catalogue (house style,
-- like `modelo`'s MODELOS), validated on write by `especificacoes.validar`
-- (unknown key / missing `requer` / exclusive pair -> 400) --
-- `PUT /api/clientes/{cliente_id}/contratos/{contrato_id}/especificacoes`.
--
-- FORWARD-ONLY, IDEMPOTENT (every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.atendimento_contratos
    ADD COLUMN IF NOT EXISTS especificacoes TEXT[];

ALTER TABLE social_wiring.atendimento_contratos
    ADD COLUMN IF NOT EXISTS especificacoes_versao INTEGER;

COMMENT ON COLUMN social_wiring.atendimento_contratos.especificacoes IS
    'Selected contract specifications (contrato_gerador/especificacoes.py '
    'CATALOGO keys, catalogue order). NULL = legacy mode: readiness follows '
    'the data-derived switches.';

COMMENT ON COLUMN social_wiring.atendimento_contratos.especificacoes_versao IS
    'CATALOGO_VERSAO the especificacoes selection was made against; NULL '
    'with especificacoes NULL.';

NOTIFY pgrst, 'reload schema';
