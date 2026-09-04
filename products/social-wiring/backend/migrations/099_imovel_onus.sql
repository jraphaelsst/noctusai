-- ============================================================================
-- Migration 099 -- social_wiring: situação de ônus do imóvel
--
-- WHAT THIS IS
-- ------------
-- Somewhere to record whether a property is encumbered.
--
-- The first clause of every promessa de compra e venda asserts the property is
-- sold "livre e desembaraçado de quaisquer ônus reais" — no mortgage, no
-- alienação fiduciária, no penhora. That is a statement of FACT about the
-- property, made by the agency, in a signed instrument. Nothing in this schema
-- could back it: `atendimento_financiamento` records the BUYER's financing,
-- which is the opposite side of the transaction from the SELLER's outstanding
-- debt, and `imoveis` is a listing mirror that has no concept of a lien.
--
-- 🔴 UNCONSTRAINED ON PURPOSE — THE RULES ARE NOT DECIDED YET
-- ------------------------------------------------------------
-- The user asked for the field now and the rules later ("later on we decide
-- the rules and instructions to it"). So this migration adds the PLACE and
-- refuses to invent the policy:
--
--   * `situacao_onus` is TEXT with no CHECK. The obvious vocabulary
--     (livre | hipoteca | alienacao_fiduciaria | penhora | usufruto |
--     indisponibilidade) is offered by the UI and lives in the service, where
--     changing it is an edit rather than a migration. Freezing a guessed
--     enum here is exactly the mistake migration 077 avoided with
--     `formas_pagamento`, and for the same reason.
--   * There is NO rule tying `situacao_onus` to anything else, and no gate
--     that refuses to emit a document on a stale reading. Both are real and
--     both are deliberately absent: a gate written before its policy is
--     decided is a gate that gets worked around.
--
-- WHAT *IS* MODELLED, BECAUSE IT IS NOT A POLICY QUESTION
-- --------------------------------------------------------
-- Provenance. A statement about liens is only worth the certidão behind it,
-- and a certidão has a date — an "livre" read from eight months ago is not
-- evidence of anything today. So the reading carries the document it came
-- from, the date of the certidão itself (NOT the upload date), and who
-- recorded it. That is the same provenance shape `numero_matricula` already
-- carries in migration 075, on the same table, for the same reason.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS situacao_onus            TEXT,
    ADD COLUMN IF NOT EXISTS onus_observacoes         TEXT,
    -- The date printed ON the certidão, not when someone uploaded it. A
    -- certidão de ônus has a validity window measured from its own emission,
    -- so the upload timestamp answers the wrong question.
    ADD COLUMN IF NOT EXISTS onus_certidao_em         DATE,
    ADD COLUMN IF NOT EXISTS onus_documento_id        UUID,
    ADD COLUMN IF NOT EXISTS onus_registrado_por      UUID,
    ADD COLUMN IF NOT EXISTS onus_registrado_em       TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.imovel_dados.situacao_onus IS
    'Encumbrance status of the property, as read off a Certidão de Ônus '
    'Reais. Unconstrained TEXT — the vocabulary (livre | hipoteca | '
    'alienacao_fiduciaria | penhora | usufruto | indisponibilidade | outro) '
    'lives in imovel_hub beside the dropdown, and the RULES that consume it '
    'are deliberately not decided yet (see the 099 header).';
COMMENT ON COLUMN social_wiring.imovel_dados.onus_observacoes IS
    'Free text for what the certidão actually says — creditor, value, '
    'registration number of the lien. Free text because a lien description is '
    'prose on the certidão and structuring it before anyone has read fifty of '
    'them would be a guess.';
COMMENT ON COLUMN social_wiring.imovel_dados.onus_certidao_em IS
    'Emission date printed on the certidão — NOT the upload date. Staleness '
    'is measured from here.';
COMMENT ON COLUMN social_wiring.imovel_dados.onus_documento_id IS
    'The imovel_documentos row this reading came from, when there is one. '
    'FK added below, matching numero_matricula_documento_id in 075.';

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_onus_documento_fk;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_onus_documento_fk
    FOREIGN KEY (onus_documento_id)
    REFERENCES social_wiring.imovel_documentos (id) ON DELETE SET NULL;

-- "Which properties have a lien recorded, oldest certidão first" is the sweep
-- a future staleness rule will run. Partial so the index only carries rows
-- that have been assessed at all.
CREATE INDEX IF NOT EXISTS idx_sw_imovel_dados_onus
    ON social_wiring.imovel_dados (org_id, situacao_onus, onus_certidao_em)
    WHERE situacao_onus IS NOT NULL;
