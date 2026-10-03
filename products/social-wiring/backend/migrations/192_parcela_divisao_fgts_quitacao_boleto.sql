-- ============================================================================
-- Migration 192 · social_wiring: the payment shapes the office's signed
-- contracts use and the generator could not express
--
-- Read off the redacted catalog of the office's signed CCVs (34 texts).
-- Three gaps need storage; the rest (several sinal parcelas, several permuta
-- parcelas, an FGTS parcela of its own) already fit the existing rows and are
-- handled in the generator.
--
-- 1. `atendimento_parcela_favorecidos` — ONE parcela paid to SEVERAL payees
--    (6 signed deals: sub-items "1.1) R$ … em favor de …", or bullets with a
--    percentage of the parcela). A parcela keeps its single
--    `favorecido_id` (108) for the common case; this table holds the split
--    when there is one. The two are mutually exclusive — the service refuses
--    a parcela carrying both (400) and the generator blocks it
--    (`FAVORECIDO_E_DIVISAO`), so neither layer guesses which one wins.
--    Each row is EITHER a `valor` OR a `percentual` of the parcela, never
--    both (CHECK). Whether the shares add up to the parcela is the
--    generator's gate (`DIVISAO_SOMA_DIVERGE`), not a constraint: terms are
--    drafted over several sittings (108's header).
--    `favorecido_id` is ON DELETE SET NULL, like the parcela's own (108):
--    deleting a favorecido leaves the share and its amount, and the gate
--    names the missing payee instead of a sum silently changing.
--
-- 2. `atendimento_negociacao_parcelas.valor_fgts` — the FGTS portion of the
--    financiamento parcela. 5 signed deals print it explicitly ("onde será
--    utilizado {FGTS}, por meio do uso das contas vinculadas ao FGTS e {FIN}
--    por meio de recursos de financiamento imobiliário …"); the financed
--    part is `valor - valor_fgts`. NULL = the split is not known (the
--    combined wording is printed). Only a financiamento parcela may carry
--    it (CHECK), and it must be > 0; `< valor` is checked by the service
--    and the gate (valor itself is nullable since 171).
--
-- 3. `atendimento_negociacao_termos.onus_quitacao` gains
--    'vendedores_boleto' — the seller pays the lien off by bank slip within
--    `onus_prazo_dias` (2 signed deals). Drop-then-add is the idempotent
--    CHECK extension (114 declared it inline: `<table>_<column>_check`).
--
-- 🔴 LGPD — `atendimento_parcela_favorecidos` points at financial PII
-- (`atendimento_favorecidos`: bank account, PIX, CPF/CNPJ). It stores ids
-- and amounts only; same RLS posture and same never-log rule as 108.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. atendimento_parcela_favorecidos — one parcela, several payees
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_parcela_favorecidos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    parcela_id     UUID NOT NULL
        REFERENCES social_wiring.atendimento_negociacao_parcelas (id) ON DELETE CASCADE,
    favorecido_id  UUID
        REFERENCES social_wiring.atendimento_favorecidos (id) ON DELETE SET NULL,
    valor          NUMERIC(14,2) CHECK (valor IS NULL OR valor > 0),
    percentual     NUMERIC(7,4)
        CHECK (percentual IS NULL OR (percentual > 0 AND percentual <= 100)),
    ordem          INTEGER NOT NULL DEFAULT 0,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por    UUID
);

ALTER TABLE social_wiring.atendimento_parcela_favorecidos
    DROP CONSTRAINT IF EXISTS atendimento_parcela_favorecidos_valor_ou_percentual;
ALTER TABLE social_wiring.atendimento_parcela_favorecidos
    ADD CONSTRAINT atendimento_parcela_favorecidos_valor_ou_percentual
    CHECK (valor IS NULL OR percentual IS NULL);

COMMENT ON TABLE social_wiring.atendimento_parcela_favorecidos IS
    'A parcela paid to several favorecidos: one row per share, each a valor '
    'OR a percentual of the parcela. Mutually exclusive with the parcela''s '
    'own favorecido_id (service 400 + generator bloqueio). See the 192 header.';

CREATE INDEX IF NOT EXISTS idx_sw_parcela_favorecidos_org_parcela
    ON social_wiring.atendimento_parcela_favorecidos (org_id, parcela_id, ordem);
CREATE INDEX IF NOT EXISTS idx_sw_parcela_favorecidos_favorecido
    ON social_wiring.atendimento_parcela_favorecidos (org_id, favorecido_id)
    WHERE favorecido_id IS NOT NULL;

ALTER TABLE social_wiring.atendimento_parcela_favorecidos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_parcela_favorecidos_select_own_org"
    ON social_wiring.atendimento_parcela_favorecidos;
CREATE POLICY "atendimento_parcela_favorecidos_select_own_org"
    ON social_wiring.atendimento_parcela_favorecidos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_parcela_favorecidos_service_role"
    ON social_wiring.atendimento_parcela_favorecidos;
CREATE POLICY "atendimento_parcela_favorecidos_service_role"
    ON social_wiring.atendimento_parcela_favorecidos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. atendimento_negociacao_parcelas.valor_fgts — FGTS inside the financing
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_negociacao_parcelas
    ADD COLUMN IF NOT EXISTS valor_fgts NUMERIC(14,2);

ALTER TABLE social_wiring.atendimento_negociacao_parcelas
    DROP CONSTRAINT IF EXISTS atendimento_negociacao_parcelas_valor_fgts_check;
ALTER TABLE social_wiring.atendimento_negociacao_parcelas
    ADD CONSTRAINT atendimento_negociacao_parcelas_valor_fgts_check
    CHECK (valor_fgts IS NULL OR (valor_fgts > 0 AND tipo = 'financiamento'));

COMMENT ON COLUMN social_wiring.atendimento_negociacao_parcelas.valor_fgts IS
    'FGTS portion of a financiamento parcela (financed part = valor - '
    'valor_fgts). NULL = split unknown. See the 192 header.';

-- ----------------------------------------------------------------------------
-- 3. onus_quitacao: 'vendedores_boleto'
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_negociacao_termos
    DROP CONSTRAINT IF EXISTS atendimento_negociacao_termos_onus_quitacao_check;
ALTER TABLE social_wiring.atendimento_negociacao_termos
    ADD CONSTRAINT atendimento_negociacao_termos_onus_quitacao_check
    CHECK (onus_quitacao IS NULL OR onus_quitacao IN (
        'compradores_prazo', 'interveniente_quitante', 'parcela',
        'ja_quitado', 'vendedores_boleto'
    ));

COMMENT ON COLUMN social_wiring.atendimento_negociacao_termos.onus_quitacao IS
    'compradores_prazo | interveniente_quitante | parcela | ja_quitado | '
    'vendedores_boleto (seller pays off by bank slip within onus_prazo_dias, 192).';
