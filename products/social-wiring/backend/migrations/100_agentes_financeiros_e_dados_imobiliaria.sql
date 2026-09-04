-- ============================================================================
-- Migration 100 -- social_wiring: agentes financeiros + dados da imobiliária
--
-- WHAT THIS IS
-- ------------
-- The two cadastral surfaces a contract needs and this product never had: WHO
-- the intermediating agency is (its own qualification, for the instrument's
-- header and its corretagem clause), and WHICH bank is financing a given deal.
--
-- ── 1. agentes_financeiros ──────────────────────────────────────────────────
--
-- A per-org registry of financing agents, managed on its own page and offered
-- as a dropdown on the card's Financiamento tab.
--
-- 🔴 A TABLE, NOT A TEXT COLUMN ON `atendimento_financiamento`
-- -------------------------------------------------------------
-- The cheap version is `banco TEXT` on the financing row. It loses for a
-- reason that shows up immediately in this business: an agency works with the
-- same four or five agents over and over, each with a manager, a branch and a
-- phone number that the operator has to reach for on every deal. Typed per
-- deal, "Caixa Econômica Federal" becomes "CAIXA", "Caixa Econômica" and
-- "caixa economica federal" inside a month, and the question "how many deals
-- went through Caixa this quarter" stops having an answer.
--
-- 🔴 `ON DELETE RESTRICT` ON THE REFERENCE, NOT CASCADE OR SET NULL
-- ------------------------------------------------------------------
-- Deleting an agent that deals point at would either destroy the deals
-- (CASCADE — absurd) or silently blank which bank financed them (SET NULL —
-- quiet history loss on a click that reads as tidying a list). RESTRICT makes
-- the attempt fail loudly, and `ativo = false` is the way to retire an agent
-- without touching what it is already attached to. The service filters the
-- dropdown on `ativo` while still resolving inactive agents for display, so a
-- retired bank keeps rendering on the deals it financed.
--
-- ── 2. org_dados_cadastrais ─────────────────────────────────────────────────
--
-- The agency's own qualification: razão social, CNPJ, CRECI PJ, address.
--
-- 🔴 WHY PRODUCT-LOCAL AND NOT ON `public.organizations` — ACCEPT WITH RATIONALE
-- ------------------------------------------------------------------------------
-- `public.organizations` is the platform-level tenant row shared by all 13
-- products, so putting cadastral fields there is a FLEET change, and the
-- replication-to-seed-symmetry rule says a fleet-shaped need belongs upstream.
-- It is genuinely borderline. The call, and why:
--
--   * `creci_pj` does not generalize. A CRECI registration is a real-estate
--     brokerage licence; it is meaningless to therapy-platform, igig or
--     personal-finance, and a column on the shared tenant row that eleven
--     products must ignore is a worse shape than a table one product owns.
--   * `razao_social` / `cnpj` DO generalize, and are the half that will
--     eventually want promoting. Nothing here blocks that: this table is
--     keyed on `org_id`, so a future seed-level org profile absorbs these two
--     columns and this table keeps only the brokerage-specific ones.
--
-- So: [A]ccepted as product-local, with the promotion path named. If a second
-- product asks for razão social/CNPJ, that is N=2 and it goes to the seed
-- rather than being copied — this note is the trigger.
--
-- ── 3. nav gating ───────────────────────────────────────────────────────────
--
-- `agentes_financeiros` gets a `status_pagina` row seeded 'producao', the same
-- way 091 and 092 gated Certidões and Matrículas. A page with no row is
-- returned to nobody and its sidebar item never renders.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. agentes_financeiros
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.agentes_financeiros (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,

    nome          TEXT NOT NULL CHECK (length(trim(nome)) > 0),
    -- Bank code as in the Brazilian payment system ("104" for Caixa, "001"
    -- for Banco do Brasil). TEXT, not INTEGER: the codes are zero-padded and
    -- "001" is not 1 on any document that prints it.
    codigo_banco  TEXT,
    agencia       TEXT,
    -- Who the agency actually talks to. This is the whole reason operators
    -- reach for a registry instead of typing a bank name.
    contato_nome  TEXT,
    contato_email TEXT,
    contato_telefone TEXT,
    observacoes   TEXT,

    -- Retirement, not deletion. See the header: the reference is RESTRICT, so
    -- this is how an agent leaves the dropdown without orphaning history.
    ativo         BOOLEAN NOT NULL DEFAULT true,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por   UUID,
    updated_at    TIMESTAMPTZ,
    updated_por   UUID
);

COMMENT ON TABLE social_wiring.agentes_financeiros IS
    'Per-org registry of financing agents (banks). Offered as the dropdown on '
    'the card''s Financiamento tab and managed on its own page. A table '
    'rather than a TEXT column so the same bank spells the same way on every '
    'deal — see the 100 header.';
COMMENT ON COLUMN social_wiring.agentes_financeiros.ativo IS
    'false retires the agent from the dropdown WITHOUT detaching it from the '
    'deals it already finances. Deleting is refused by the RESTRICT on '
    'atendimento_financiamento.agente_financeiro_id.';

-- Two agents with the same name in one org is a duplicate, not a variant.
-- Case-insensitive because "Caixa" and "CAIXA" are the same entry typed by
-- two people. Same shape as uq_sw_cliente_tags_org_nome.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_agentes_financeiros_org_nome
    ON social_wiring.agentes_financeiros (org_id, lower(trim(nome)));

CREATE INDEX IF NOT EXISTS idx_sw_agentes_financeiros_org_ativo
    ON social_wiring.agentes_financeiros (org_id, ativo, nome);

ALTER TABLE social_wiring.agentes_financeiros ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agentes_financeiros_select_own_org"
    ON social_wiring.agentes_financeiros;
CREATE POLICY "agentes_financeiros_select_own_org"
    ON social_wiring.agentes_financeiros
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "agentes_financeiros_service_role"
    ON social_wiring.agentes_financeiros;
CREATE POLICY "agentes_financeiros_service_role"
    ON social_wiring.agentes_financeiros
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION social_wiring.set_updated_at_agentes_financeiros()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_agentes_financeiros_updated
    ON social_wiring.agentes_financeiros;
CREATE TRIGGER set_agentes_financeiros_updated
    BEFORE UPDATE ON social_wiring.agentes_financeiros
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_agentes_financeiros();

-- ----------------------------------------------------------------------------
-- 2. The financing row points at one agent
-- ----------------------------------------------------------------------------
-- NULLABLE: `situacao` starts at 'pendente' and the bank is frequently not
-- chosen yet. A NOT NULL here would mean no financing row could exist until
-- one was, which is backwards — the pending state is exactly the state where
-- the agent is still being decided.
ALTER TABLE social_wiring.atendimento_financiamento
    ADD COLUMN IF NOT EXISTS agente_financeiro_id UUID,
    -- Proposal/contract number at the bank. Free text: every agent formats it
    -- differently and none of them ask us to validate it.
    ADD COLUMN IF NOT EXISTS numero_proposta      TEXT;

ALTER TABLE social_wiring.atendimento_financiamento
    DROP CONSTRAINT IF EXISTS atendimento_financiamento_agente_fk;
ALTER TABLE social_wiring.atendimento_financiamento
    ADD CONSTRAINT atendimento_financiamento_agente_fk
    FOREIGN KEY (agente_financeiro_id)
    REFERENCES social_wiring.agentes_financeiros (id) ON DELETE RESTRICT;

COMMENT ON COLUMN social_wiring.atendimento_financiamento.agente_financeiro_id IS
    'Which registered agent is financing this deal. NULLABLE — pendente is '
    'exactly the state where it has not been chosen. RESTRICT on delete: '
    'retire an agent with ativo = false, never by deleting it.';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_financiamento_agente
    ON social_wiring.atendimento_financiamento (org_id, agente_financeiro_id)
    WHERE agente_financeiro_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. org_dados_cadastrais -- the agency's own qualification
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.org_dados_cadastrais (
    org_id           UUID PRIMARY KEY
        REFERENCES public.organizations(id) ON DELETE CASCADE,

    razao_social     TEXT,
    nome_fantasia    TEXT,
    cnpj             TEXT,
    -- The brokerage licence. This is the column that keeps this table out of
    -- public.organizations — see the header.
    creci_pj         TEXT,
    -- The responsible broker, who signs as the intermediary.
    responsavel_nome  TEXT,
    responsavel_creci TEXT,

    telefone         TEXT,
    email            TEXT,

    -- Same column names as clientes (093) and imoveis (040), so all three
    -- addresses in this schema read alike.
    endereco_cep         TEXT,
    endereco_logradouro  TEXT,
    endereco_numero      TEXT,
    endereco_complemento TEXT,
    endereco_bairro      TEXT,
    endereco_cidade      TEXT,
    endereco_uf          TEXT,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ,
    updated_por      UUID
);

COMMENT ON TABLE social_wiring.org_dados_cadastrais IS
    'The agency''s own cadastral data, for the header and corretagem clause '
    'of a generated instrument. Product-local by an explicit [A]ccept — '
    'creci_pj does not generalize to the fleet. razao_social/cnpj are the '
    'half that promotes to a seed-level org profile if a second product asks. '
    'See the 100 header.';

-- One row per org, enforced by the PK. Every column is nullable: this is a
-- settings form an operator fills over time, and refusing to save a partly
-- filled form loses whatever they had typed.

ALTER TABLE social_wiring.org_dados_cadastrais ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "org_dados_cadastrais_select_own_org"
    ON social_wiring.org_dados_cadastrais;
CREATE POLICY "org_dados_cadastrais_select_own_org"
    ON social_wiring.org_dados_cadastrais
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "org_dados_cadastrais_service_role"
    ON social_wiring.org_dados_cadastrais;
CREATE POLICY "org_dados_cadastrais_service_role"
    ON social_wiring.org_dados_cadastrais
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION social_wiring.set_updated_at_org_dados_cadastrais()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_org_dados_cadastrais_updated
    ON social_wiring.org_dados_cadastrais;
CREATE TRIGGER set_org_dados_cadastrais_updated
    BEFORE UPDATE ON social_wiring.org_dados_cadastrais
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_org_dados_cadastrais();

-- ----------------------------------------------------------------------------
-- 4. Nav gating for the new page
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status)
VALUES ('agentes_financeiros', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
