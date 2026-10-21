-- ============================================================================
-- Migration 299 · social_wiring: a human DECIDES a Crednet participação, and
-- the seller's typed obligations choose their clause (contract scoring, deal
-- 857, 2026-10-21).
-- ============================================================================
-- WHY
-- ---
-- 1. `cliente_empresa_participacoes` (167) already carries `confirmado_por/
--    _em`, but nothing ever set them for a Serasa Crednet row, so a seller's
--    REAL company read off the Crednet never reached the contract
--    (`contrato_gerador.carregador._participacao_vale` only admits a
--    confirmed or manual participação). The card's Empresas section now
--    confirms it — and, just as important, records "não é do vendedor": the
--    Crednet lists every company a CPF ever appeared in, and a dismissal must
--    SURVIVE the next Crednet re-read (`crednet_service._upsert_participacao`
--    only fills empty pct/desde on an existing row, it never re-creates or
--    resets one). Deleting the row instead would let the next read put it
--    back, unconfirmed, re-raising the readiness aviso forever.
--    -> `descartado_por` / `descartado_em`. Confirmed and dismissed are
--    mutually exclusive; the service (`card_hub.empresas_service.
--    decidir_participacao`) writes them as one decision.
--
-- 2. Operator-typed `obrigacoes_vendedor` (193) print only in the ÔNUS
--    clause. Signed deal 857 places them inside "DAS CERTIDÕES E DOCUMENTOS",
--    after the certidão groups, lettered "a) …; b) …". A per-deal choice:
--    `obrigacoes_vendedor_local` 'onus' (default — every existing deal keeps
--    rendering byte-identically) | 'certidoes'.
--
-- FORWARD-ONLY, IDEMPOTENT (ADD COLUMN IF NOT EXISTS only). Additive: an
-- un-migrated DB only lacks the new decision and the selector; apply BEFORE
-- deploying the image that writes them.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. cliente_empresa_participacoes — the "não é do vendedor" decision
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cliente_empresa_participacoes
    ADD COLUMN IF NOT EXISTS descartado_por UUID,
    ADD COLUMN IF NOT EXISTS descartado_em  TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.cliente_empresa_participacoes.confirmado_em IS
    'A human confirmed this participação (a Crednet-read one enters the '
    'contract only once confirmed). Mutually exclusive with descartado_em '
    '(migration 299).';
COMMENT ON COLUMN social_wiring.cliente_empresa_participacoes.descartado_em IS
    'A human said this company is NOT the person''s ("Não é do vendedor"): '
    'never enters the contract, never raises the unconfirmed-Crednet aviso, '
    'survives a Crednet re-read (migration 299).';

-- ----------------------------------------------------------------------------
-- 2. atendimento_negociacao_termos — where the seller's obligations print
-- ----------------------------------------------------------------------------
-- No DB CHECK on the vocabulary, on purpose: the only writer is the termos
-- PUT, whose body is a `Literal['onus','certidoes']` re-checked by the service
-- (`negociacao_estruturada_service.OBRIGACOES_VENDEDOR_LOCAIS`), and the
-- generator BLOCKS an unknown value (`OBRIGACOES_VENDEDOR_LOCAL_INVALIDO`) —
-- never a silent fallback. A CHECK here would be a guard with no behaviour
-- probe (`check_migration_guard_has_probe`).
ALTER TABLE social_wiring.atendimento_negociacao_termos
    ADD COLUMN IF NOT EXISTS obrigacoes_vendedor_local TEXT NOT NULL DEFAULT 'onus';

COMMENT ON COLUMN social_wiring.atendimento_negociacao_termos.obrigacoes_vendedor_local IS
    'Where the contract prints obrigacoes_vendedor: onus (default — a '
    'paragraph of the ÔNUS clause, deal 859) | certidoes (lettered a), b), … '
    'inside DAS CERTIDÕES E DOCUMENTOS after the certidão groups, deal 857). '
    'Migration 299.';
