-- ============================================================================
-- Migration 077 · social_wiring: the commercial terms of a deal
--
-- Valor negociado, % de comissão, parceria and its split, formas de pagamento,
-- parcelas, financiamento e FGTS — plus the four percentages that decide who
-- gets what.
--
-- 🔴 WHY IT IS **NOT** CALLED `negociacoes`
-- ------------------------------------------
-- The user asked for "a new table called Negociação". That exact name is the
-- one thing this schema cannot have, and migration 060 is why:
--
--   `negociacoes_venda` was the card table AND `pipeline_stages` carries a
--   stage whose slug is `negociacao`. One word, two meanings, one line apart
--   [...] Same resolution, chosen by the user: rename the entity.
--   🔴 THE STAGE KEEPS ITS NAME. After this migration they are the ONLY
--   negociação in the system, which is the entire point of the rename.
--
-- Re-introducing an ENTITY called `negociacoes` would undo a rename the user
-- themselves chose, and would restore the exact collision it was chosen to
-- remove. So the data lands as `atendimento_negociacao`: subordinate to the
-- atendimento by name, so it reads as "this atendimento's negociação terms"
-- rather than competing as an entity. The user's word is kept; the collision
-- is not. → surfaced in the delivery note as an interpretation call.
--
-- 🔴 ONE ROW PER ATENDIMENTO, AND `atendimento_id` IS THE PRIMARY KEY
-- -------------------------------------------------------------------
-- Not a surrogate `id` with a unique index — the PK IS the relationship. A
-- deal has one set of commercial terms; a second row would be two answers to
-- "what was agreed", and every reader would have to pick one.
--
-- 🔴 THE PERCENTAGES ARE COPIED, NEVER REFERENCED
-- ------------------------------------------------
-- `negociacao_defaults` holds the org's current business rule. Those values
-- are COPIED onto the row when a negociação is created and are never read
-- again for it.
--
-- This is the whole point of the user's two requirements sitting together:
-- "These values can be modified per negotiation, as well as the default
-- values must be swappable in case business rules change." If the row
-- referenced the defaults, swapping the business rule would silently rewrite
-- what was agreed on every past deal — including closed ones, including ones
-- already paid out. A commission split is a record of an agreement, not a
-- current setting.
--
-- THE SPLIT, IN THE USER'S OWN TERMS
-- ----------------------------------
--   comissão total  = valor_negociado × pct_comissao
--   parceria        = comissão total × pct_parceria      (only if tem_parceria)
--   nossa parte     = comissão total − parceria
--   ├─ agência      = nossa parte × pct_agencia          (default 50%)
--   ├─ agentes      = nossa parte × pct_agentes          (default 45%)
--   └─ captador     = nossa parte × pct_captador         (default  5%)
--
-- The agentes slice is divided among the funnel card's membros
-- (`cliente_membros` → `lead_corretores`); the captador slice goes to
-- `imovel_dados.captador_user_id`.
--
-- Parceria defaults to 50/50 of the TOTAL (user correction: "default is
-- 50-50, not 60-40. our 50% half is to be split in-house, the Parceria has
-- the other 50%") — so the in-house percentages apply to OUR half, not to
-- the whole commission.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. negociacao_defaults — the org's CURRENT business rule (an override table)
-- ----------------------------------------------------------------------------
-- Deliberately OPTIONAL: no row is seeded for any org. The service falls back
-- to code constants, which are the canonical answer
-- (`KB § PATTERNS/architect/seed-canonical-defaults.md`) — so a brand-new org
-- works with no data step, and this table exists only to say "we differ".
--
-- `pct_comissao` is NULLABLE and seeded nowhere: the user specified the SPLIT
-- (50/45/5, parceria 50) but never a commission RATE, and inventing one would
-- put a number nobody chose onto every new deal.
CREATE TABLE IF NOT EXISTS social_wiring.negociacao_defaults (
    org_id        UUID PRIMARY KEY,

    pct_comissao  NUMERIC(6,3) CHECK (pct_comissao  IS NULL OR (pct_comissao  >= 0 AND pct_comissao  <= 100)),
    pct_parceria  NUMERIC(6,3) NOT NULL DEFAULT 50  CHECK (pct_parceria >= 0 AND pct_parceria <= 100),
    pct_agencia   NUMERIC(6,3) NOT NULL DEFAULT 50  CHECK (pct_agencia  >= 0 AND pct_agencia  <= 100),
    pct_agentes   NUMERIC(6,3) NOT NULL DEFAULT 45  CHECK (pct_agentes  >= 0 AND pct_agentes  <= 100),
    pct_captador  NUMERIC(6,3) NOT NULL DEFAULT 5   CHECK (pct_captador >= 0 AND pct_captador <= 100),

    updated_at    TIMESTAMPTZ,
    updated_por   UUID,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- An in-house split that does not total 100% either invents money or
    -- loses it. This is arithmetic, not a business preference, so it is
    -- enforced here rather than left to a service that could be bypassed.
    CONSTRAINT negociacao_defaults_split_soma_100
        CHECK (pct_agencia + pct_agentes + pct_captador = 100)
);

COMMENT ON TABLE social_wiring.negociacao_defaults IS
    'Per-org OVERRIDE of the commission split. No row means "use the code '
    'defaults" (50/45/5, parceria 50) — the canonical answer. Values are '
    'COPIED onto each negociação at creation and never read again for it, so '
    'changing the rule never rewrites a past agreement.';

ALTER TABLE social_wiring.negociacao_defaults ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "negociacao_defaults_select_own_org"
    ON social_wiring.negociacao_defaults;
CREATE POLICY "negociacao_defaults_select_own_org"
    ON social_wiring.negociacao_defaults
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "negociacao_defaults_service_role"
    ON social_wiring.negociacao_defaults;
CREATE POLICY "negociacao_defaults_service_role"
    ON social_wiring.negociacao_defaults
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. atendimento_negociacao — what was actually agreed on ONE deal
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_negociacao (
    atendimento_id UUID PRIMARY KEY
        REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE,
    org_id         UUID NOT NULL,

    -- Which property. Keyed to `imovel_registry`, never to the `imoveis`
    -- mirror — see migration 076 for the incident. NULLABLE: terms can be
    -- drafted before the imóvel is pinned down, and the captador slice is
    -- simply unallocated until it is.
    imovel_codigo  TEXT,

    valor_negociado NUMERIC(14,2)
        CHECK (valor_negociado IS NULL OR valor_negociado >= 0),
    pct_comissao    NUMERIC(6,3)
        CHECK (pct_comissao IS NULL OR (pct_comissao >= 0 AND pct_comissao <= 100)),

    -- Parceria: another agency splits the commission with us.
    tem_parceria   BOOLEAN NOT NULL DEFAULT false,
    pct_parceria   NUMERIC(6,3) NOT NULL DEFAULT 50
        CHECK (pct_parceria >= 0 AND pct_parceria <= 100),

    -- The in-house split of OUR share. Copied from the defaults at creation.
    pct_agencia    NUMERIC(6,3) NOT NULL DEFAULT 50,
    pct_agentes    NUMERIC(6,3) NOT NULL DEFAULT 45,
    pct_captador   NUMERIC(6,3) NOT NULL DEFAULT 5,

    -- Free text "for now", per the user. Deliberately NOT modelled into
    -- structured instalments yet: the shape is not known, and a guessed
    -- schema is harder to correct than free text is to parse later.
    formas_pagamento TEXT,
    parcelas         TEXT,

    financiamento  BOOLEAN NOT NULL DEFAULT false,
    -- 🔴 NO CHECK tying `fgts` to `financiamento`, deliberately. The user's
    -- phrasing ("Financiamento. If so, if he's gonna use FGTS") describes the
    -- UI flow, and the UI honours it. But FGTS can legitimately fund a
    -- purchase with no financing at all in Brazil, so freezing the
    -- conditional into the schema would make a real case unrecordable.
    fgts           BOOLEAN NOT NULL DEFAULT false,

    observacoes    TEXT,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por    UUID,
    updated_at     TIMESTAMPTZ,
    updated_por    UUID,

    CONSTRAINT atendimento_negociacao_split_soma_100
        CHECK (pct_agencia + pct_agentes + pct_captador = 100),

    CONSTRAINT atendimento_negociacao_imovel_fk
        FOREIGN KEY (org_id, imovel_codigo)
        REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical)
        ON DELETE SET NULL
);

COMMENT ON TABLE social_wiring.atendimento_negociacao IS
    'The commercial terms of one atendimento. NOT named `negociacoes`: that '
    'entity name collides with the funil STAGE `negociacao`, which migration '
    '060 renamed away from on the user''s instruction.';

COMMENT ON COLUMN social_wiring.atendimento_negociacao.pct_parceria IS
    'The PARTNER agency''s share of the TOTAL commission. Default 50 — our '
    'half is what the in-house split then divides.';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_negociacao_org
    ON social_wiring.atendimento_negociacao (org_id);

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_negociacao_imovel
    ON social_wiring.atendimento_negociacao (org_id, imovel_codigo)
    WHERE imovel_codigo IS NOT NULL;

ALTER TABLE social_wiring.atendimento_negociacao ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_negociacao_select_own_org"
    ON social_wiring.atendimento_negociacao;
CREATE POLICY "atendimento_negociacao_select_own_org"
    ON social_wiring.atendimento_negociacao
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_negociacao_service_role"
    ON social_wiring.atendimento_negociacao;
CREATE POLICY "atendimento_negociacao_service_role"
    ON social_wiring.atendimento_negociacao
    FOR ALL TO service_role USING (true) WITH CHECK (true);
