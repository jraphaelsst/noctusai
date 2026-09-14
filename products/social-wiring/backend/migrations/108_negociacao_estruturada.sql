-- ============================================================================
-- Migration 108 · social_wiring: Negociação estruturada — the deal terms a
-- contract instrument actually needs
--
-- Contract automation ("Promessa de Venda e Compra") needs structured
-- parcelas (not `atendimento_negociacao.parcelas TEXT`), who each payment
-- is owed to, who intermediated the deal, and the two people who witness a
-- signing. This migration adds four new tables plus three columns on the
-- existing `atendimento_negociacao` row (077).
--
-- 🔴 NEW TABLES, NOT A FOREIGN KEY INTO `erp.*`
-- ------------------------------------------------
-- `erp.parcelas_contrato` is a POST-signing payment ledger: it exists once a
-- contract has been generated and the buyer is paying it down, and its rows
-- carry `status` (pendente/pago/atrasado) and `data_pagamento` — collection
-- bookkeeping. What THIS migration models is the negotiation stage BEFORE a
-- contract exists: the terms an operator is drafting, still editable, still
-- routinely incomplete. Pointing at `erp.parcelas_contrato` would either
-- force draft terms to satisfy a payment-tracking schema they do not belong
-- to yet, or force `erp` to grow negotiation-stage columns onto its
-- collections ledger. Two different lifecycle stages, two different tables —
-- `social_wiring` owns the draft, `erp` (a different product) owns the
-- collection once a contract is signed. Nothing here writes into `erp`.
--
-- `forma_pagamento` VALUES MATCH THE ERP VOCABULARY, VERBATIM
-- -------------------------------------------------------------
-- `erp-imobiliario/frontend/src/pages/Financeiro.tsx`'s `FORMAS_PAGAMENTO`:
-- Dinheiro, PIX, Cartão de Crédito, Cartão de Débito, Transferência, Boleto,
-- Cheque. Neither erp's DB column nor its Pydantic field constrains these —
-- it is free `TEXT` there too (`app/routers/financeiro.py`,
-- `app/routers/contratos.py`). This migration keeps the same posture: TEXT,
-- not a CHECK, with the vocabulary a code constant on the service side
-- (`negociacao_estruturada_service.FORMAS_PAGAMENTO_SUGERIDAS`) so the two
-- products' dropdowns read the same words without either DB enforcing a
-- vocabulary erp itself does not.
--
-- 🔴 `atendimento_favorecidos` AND `atendimento_intermediarios` ARE
-- ATENDIMENTO-SCOPED, NOT ORG REGISTRIES
-- ---------------------------------------------------------------------------
-- Unlike `agentes_financeiros` (100) — a per-org registry of banks reused
-- across every deal — a favorecido (who a specific parcela's money is owed
-- to) and an intermediário (who brokered THIS specific deal) are facts about
-- ONE negotiation. The seller on one deal is not a reusable dropdown entry
-- for the next. So both tables key on `atendimento_id` and CASCADE with it,
-- the same shape `atendimento_negociacao` and `atendimento_contratos` use.
--
-- 🔴 `atendimento_favorecidos` IS FINANCIAL PII
-- ------------------------------------------------
-- Bank account + PIX key + CPF/CNPJ of a named natural or legal person. Same
-- class of data migration 078's header drew the LGPD line around (income tax
-- returns, FGTS statements) — RLS org-scoped like everything else in this
-- schema, and — the operative rule — **its VALUES are never logged**. No
-- service function here calls `logger.info`/`debug` with a favorecido row in
-- the message; only ids and counts are ever logged. This is a comment, not a
-- mechanism, because there is no generic "redact these columns" log filter
-- in this codebase to point at — the discipline is enforced by review, same
-- as every other `except:` clause in this module never printing a payload.
--
-- `org_testemunhas` IS THE ONE ORG REGISTRY IN THIS MIGRATION
-- ----------------------------------------------------------------
-- The two people who witness a signing are usually the same two people
-- (office staff), reused across every contract — the opposite shape from
-- favorecidos/intermediários. So this one IS org-scoped, same posture as
-- `agentes_financeiros`/`org_dados_cadastrais` (100): `authenticated` writes
-- its own org's rows, RLS scopes it, no service-role-only gate.
--
-- 🔴 MAX 2 TESTEMUNHAS, ENFORCED AT BOTH ENDS
-- -----------------------------------------------
-- A `BEFORE INSERT` trigger refuses a 3rd row per org — the constraint is
-- the backstop, same posture `atendimento_negociacao_split_soma_100` (077)
-- takes for the commission split. The service checks first and raises a
-- named, actionable 409 ("máximo de 2 testemunhas") so a caller never sees a
-- bare trigger exception; the trigger exists so the rule holds even for a
-- future writer that bypasses the service (a migration, a script).
--
-- `atendimento_negociacao_parcelas.favorecido_id` IS A PLAIN FK, VALIDATED
-- IN THE SERVICE — NOT A COMPOSITE FK
-- ---------------------------------------------------------------------------
-- A parcela's favorecido must belong to the SAME atendimento as the parcela.
-- A composite FK (org_id, atendimento_id, favorecido_id) could express that,
-- but Postgres' `ON DELETE SET NULL` on a composite FK nulls every
-- referencing column unless every column in the FK is itself nullable — and
-- `atendimento_id` here is NOT NULL by design (an orphan parcela is not a
-- state this schema wants). So the FK is `favorecido_id -> id` alone, and
-- `negociacao_estruturada_service._exigir_favorecido` does the cross-scoping
-- check the same way `contratos_service._exigir_contrato` checks org +
-- atendimento before a document write — a 404 naming the id, never a raw FK
-- violation surfaced as a 500.
--
-- `atendimento_negociacao` GROWS `posse_data`, `posse_condicoes`,
-- `permuta_ativo_id`
-- ---------------------------------------------------------------------------
-- When possession transfers and under what conditions ("na assinatura",
-- "30 dias após o registro", "mediante quitação do financiamento") is a term
-- of the deal, same category as `valor_negociado` — so it lands on the
-- existing one-row-per-atendimento table rather than a new one. Both
-- nullable: possession terms are routinely undecided while a deal is being
-- drafted, same posture the rest of 077 takes.
--
-- `permuta_ativo_id` points at `permuta_ativos` (101) — the unified
-- matchable row a swap component of this deal would already be recorded
-- as — `ON DELETE SET NULL`, mirroring how `imovel_codigo` itself is handled
-- on this same table: losing which specific ativo was swapped is not losing
-- the deal.
--
-- Legacy `atendimento_negociacao.parcelas TEXT` and `formas_pagamento TEXT`
-- are left UNTOUCHED — this migration does not migrate that free text into
-- the new structured rows. The new `atendimento_negociacao_parcelas` table
-- is additive; a card with only the old free text keeps reading it exactly
-- as before.
--
-- The pure "split N installments off a remaining balance, remainder on the
-- LAST one" math lives in `noctusai_lib.domain.real_estate.parcelamento` —
-- a NEW seed-lib helper, Decimal-exact (unlike
-- `erp-imobiliario/backend/app/services/contratos_service.py::gerar_parcelas`,
-- which does the same shape with `float`/`round()`; porting THAT call site to
-- the new helper is out of scope for this migration — see the delivery
-- note's scoped-improvement).
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. atendimento_favorecidos — who a parcela's payment is owed to
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_favorecidos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    atendimento_id UUID NOT NULL
        REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE,

    nome           TEXT NOT NULL CHECK (length(trim(nome)) > 0),
    cpf_cnpj       TEXT,
    banco          TEXT,
    agencia        TEXT,
    conta          TEXT,
    pix            TEXT,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por    UUID,
    updated_at     TIMESTAMPTZ,
    updated_por    UUID
);

COMMENT ON TABLE social_wiring.atendimento_favorecidos IS
    'Who a negotiation''s payments are owed to. Financial PII — RLS '
    'org-scoped, values never logged. ATENDIMENTO-scoped (not an org '
    'registry, unlike agentes_financeiros): a favorecido is a fact about ONE '
    'deal. See the 108 header.';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_favorecidos_atendimento
    ON social_wiring.atendimento_favorecidos (org_id, atendimento_id);

ALTER TABLE social_wiring.atendimento_favorecidos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_favorecidos_select_own_org"
    ON social_wiring.atendimento_favorecidos;
CREATE POLICY "atendimento_favorecidos_select_own_org"
    ON social_wiring.atendimento_favorecidos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_favorecidos_service_role"
    ON social_wiring.atendimento_favorecidos;
CREATE POLICY "atendimento_favorecidos_service_role"
    ON social_wiring.atendimento_favorecidos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. atendimento_negociacao_parcelas — the structured installment schedule
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_negociacao_parcelas (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    atendimento_id UUID NOT NULL
        REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE,

    -- 'sinal' (a down payment at signing), 'intermediaria' (a milestone
    -- payment mid-schedule), 'financiamento' (the bank-financed portion),
    -- 'fgts' (paid via FGTS withdrawal), 'saldo' (the remaining balance),
    -- 'direta' (a direct payment outside any of the above categories).
    -- CHECKed, not a TYPE — same reasoning migration 101 gives for
    -- `permuta_ativos.natureza`: adding a value to a CHECK is one migration,
    -- to a TYPE several objects depend on is many.
    tipo           TEXT NOT NULL
        CHECK (tipo IN (
            'sinal', 'intermediaria', 'financiamento', 'fgts', 'saldo',
            'direta'
        )),

    valor          NUMERIC(14,2) NOT NULL CHECK (valor >= 0),

    -- Nullable: a parcela can be recorded before its due date is fixed (e.g.
    -- "the parcela paid on delivery of keys" has no calendar date yet — see
    -- `evento` below).
    vencimento     DATE,

    -- Free text: "entrega_chaves", "liberacao_financiamento", or any other
    -- milestone the parties agreed a payment is contingent on, instead of a
    -- calendar date. NOT a CHECK'd vocabulary — this is prose describing a
    -- condition, not a closed set of states.
    evento         TEXT,

    -- Free TEXT, matching the erp vocabulary verbatim (see the 108 header)
    -- rather than a CHECK — erp itself does not constrain this column.
    forma_pagamento TEXT,

    -- Who this specific parcela is paid to. Plain FK, validated in the
    -- service against (org_id, atendimento_id) — see the 108 header for why
    -- this is not a composite FK.
    favorecido_id  UUID
        REFERENCES social_wiring.atendimento_favorecidos (id) ON DELETE SET NULL,

    -- A "confissão de dívida" clause applies to this specific parcela (a
    -- formal debt acknowledgment instrument, common when a balance is paid
    -- after the deed transfers). Per-parcela because it is a property of
    -- THAT payment's legal treatment, not of the deal as a whole.
    confissao_divida BOOLEAN NOT NULL DEFAULT false,

    -- Display/document order. Not `vencimento` DESC/ASC, because a parcela
    -- with no due date yet (see above) still needs a stable position in the
    -- instrument's payment schedule.
    ordem          INTEGER NOT NULL DEFAULT 0,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por    UUID,
    updated_at     TIMESTAMPTZ,
    updated_por    UUID
);

COMMENT ON TABLE social_wiring.atendimento_negociacao_parcelas IS
    'The structured installment schedule a contract instrument needs, '
    'replacing free-text `atendimento_negociacao.parcelas` for NEW terms '
    '(the legacy column is untouched). NOT `erp.parcelas_contrato` — this is '
    'the draft/negotiation stage, before a contract exists. See the 108 '
    'header.';
COMMENT ON COLUMN social_wiring.atendimento_negociacao_parcelas.tipo IS
    'sinal | intermediaria | financiamento | fgts | saldo | direta.';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_negociacao_parcelas_atendimento
    ON social_wiring.atendimento_negociacao_parcelas (org_id, atendimento_id, ordem);
CREATE INDEX IF NOT EXISTS idx_sw_atendimento_negociacao_parcelas_favorecido
    ON social_wiring.atendimento_negociacao_parcelas (org_id, favorecido_id)
    WHERE favorecido_id IS NOT NULL;

ALTER TABLE social_wiring.atendimento_negociacao_parcelas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_negociacao_parcelas_select_own_org"
    ON social_wiring.atendimento_negociacao_parcelas;
CREATE POLICY "atendimento_negociacao_parcelas_select_own_org"
    ON social_wiring.atendimento_negociacao_parcelas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_negociacao_parcelas_service_role"
    ON social_wiring.atendimento_negociacao_parcelas;
CREATE POLICY "atendimento_negociacao_parcelas_service_role"
    ON social_wiring.atendimento_negociacao_parcelas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. atendimento_intermediarios — who else brokered this deal
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_intermediarios (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    atendimento_id UUID NOT NULL
        REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE,

    -- NULLABLE: an in-house corretor from `lead_corretores` (101), OR an
    -- external intermediary who is not in the registry at all — the same
    -- distinction `agentes_financeiros` draws for banks, except here the
    -- "unregistered" case is common rather than exceptional (a partner
    -- agency's own agent), so `nome`/`creci` below are ALWAYS stored
    -- directly rather than resolved through the FK.
    corretor_id    UUID
        REFERENCES social_wiring.lead_corretores (id) ON DELETE SET NULL,

    nome           TEXT NOT NULL CHECK (length(trim(nome)) > 0),
    creci          TEXT,

    -- Their cut is either a PERCENTAGE of the commission or a FIXED amount —
    -- the CHECK below pins which range `valor` must fall in per `tipo`,
    -- mirroring how `atendimento_negociacao_split_soma_100` (077) enforces
    -- arithmetic at the table rather than leaving it to a caller.
    tipo           TEXT NOT NULL DEFAULT 'percentual'
        CHECK (tipo IN ('percentual', 'valor_fixo')),
    valor          NUMERIC(14,2)
        CHECK (
            valor IS NULL
            OR (tipo = 'percentual' AND valor BETWEEN 0 AND 100)
            OR (tipo = 'valor_fixo' AND valor >= 0)
        ),

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por    UUID,
    updated_at     TIMESTAMPTZ,
    updated_por    UUID
);

COMMENT ON TABLE social_wiring.atendimento_intermediarios IS
    'Who else brokered this deal (a partner agency''s agent, a referring '
    'corretor). `nome`/`creci` are always stored directly — `corretor_id` is '
    'an optional pointer INTO `lead_corretores` when the intermediary '
    'happens to be in-house, never the source of truth. See the 108 header.';
COMMENT ON COLUMN social_wiring.atendimento_intermediarios.tipo IS
    'percentual (of the commission, 0-100) | valor_fixo (a flat currency '
    'amount). Which range `valor` must fall in is pinned by the CHECK.';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_intermediarios_atendimento
    ON social_wiring.atendimento_intermediarios (org_id, atendimento_id);
CREATE INDEX IF NOT EXISTS idx_sw_atendimento_intermediarios_corretor
    ON social_wiring.atendimento_intermediarios (org_id, corretor_id)
    WHERE corretor_id IS NOT NULL;

ALTER TABLE social_wiring.atendimento_intermediarios ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_intermediarios_select_own_org"
    ON social_wiring.atendimento_intermediarios;
CREATE POLICY "atendimento_intermediarios_select_own_org"
    ON social_wiring.atendimento_intermediarios
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_intermediarios_service_role"
    ON social_wiring.atendimento_intermediarios;
CREATE POLICY "atendimento_intermediarios_service_role"
    ON social_wiring.atendimento_intermediarios
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 4. org_testemunhas — the org's standing signature witnesses (max 2)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.org_testemunhas (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,

    nome         TEXT NOT NULL CHECK (length(trim(nome)) > 0),
    cpf          TEXT,
    rg           TEXT,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por  UUID,
    updated_at   TIMESTAMPTZ,
    updated_por  UUID
);

COMMENT ON TABLE social_wiring.org_testemunhas IS
    'Per-org registry of standing signature witnesses, max 2 per org '
    '(enforced by the trigger below AND by the service, same '
    'backstop-not-message posture as 077''s commission-split CHECK). Unlike '
    'favorecidos/intermediários, reused across every contract — an org '
    'registry, not atendimento-scoped. See the 108 header.';

CREATE INDEX IF NOT EXISTS idx_sw_org_testemunhas_org
    ON social_wiring.org_testemunhas (org_id);

ALTER TABLE social_wiring.org_testemunhas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "org_testemunhas_select_own_org"
    ON social_wiring.org_testemunhas;
CREATE POLICY "org_testemunhas_select_own_org"
    ON social_wiring.org_testemunhas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

-- A settings-page registry a person maintains directly — same call
-- `agentes_financeiros`/`org_dados_cadastrais` (100) make for the identical
-- shape.
DROP POLICY IF EXISTS "org_testemunhas_write_own_org"
    ON social_wiring.org_testemunhas;
CREATE POLICY "org_testemunhas_write_own_org"
    ON social_wiring.org_testemunhas
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "org_testemunhas_service_role"
    ON social_wiring.org_testemunhas;
CREATE POLICY "org_testemunhas_service_role"
    ON social_wiring.org_testemunhas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION social_wiring.set_updated_at_org_testemunhas()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_org_testemunhas_updated
    ON social_wiring.org_testemunhas;
CREATE TRIGGER set_org_testemunhas_updated
    BEFORE UPDATE ON social_wiring.org_testemunhas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_org_testemunhas();

-- 🔴 The backstop half of "max 2 testemunhas per org" — the service checks
-- first (a named 409), this holds even for a writer that bypasses it.
CREATE OR REPLACE FUNCTION social_wiring.enforce_max_org_testemunhas()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    IF (
        SELECT COUNT(*) FROM social_wiring.org_testemunhas
        WHERE org_id = NEW.org_id
    ) >= 2 THEN
        RAISE EXCEPTION
            'org_testemunhas: máximo de 2 testemunhas por organização (org_id=%)',
            NEW.org_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS enforce_max_org_testemunhas_trigger
    ON social_wiring.org_testemunhas;
CREATE TRIGGER enforce_max_org_testemunhas_trigger
    BEFORE INSERT ON social_wiring.org_testemunhas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.enforce_max_org_testemunhas();

-- ----------------------------------------------------------------------------
-- 5. atendimento_negociacao grows three columns (see the 108 header)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_negociacao
    ADD COLUMN IF NOT EXISTS posse_data       DATE,
    ADD COLUMN IF NOT EXISTS posse_condicoes  TEXT,
    ADD COLUMN IF NOT EXISTS permuta_ativo_id UUID;

ALTER TABLE social_wiring.atendimento_negociacao
    DROP CONSTRAINT IF EXISTS atendimento_negociacao_permuta_ativo_fk;
ALTER TABLE social_wiring.atendimento_negociacao
    ADD CONSTRAINT atendimento_negociacao_permuta_ativo_fk
    FOREIGN KEY (permuta_ativo_id)
    REFERENCES social_wiring.permuta_ativos (id) ON DELETE SET NULL;

COMMENT ON COLUMN social_wiring.atendimento_negociacao.posse_data IS
    'When possession transfers. Nullable — routinely undecided while a deal '
    'is being drafted, same posture as every other term on this table.';
COMMENT ON COLUMN social_wiring.atendimento_negociacao.posse_condicoes IS
    'Free text: "na assinatura", "30 dias após o registro", "mediante '
    'quitação do financiamento" — the CONDITIONS under which posse_data '
    'applies, not a closed vocabulary.';
COMMENT ON COLUMN social_wiring.atendimento_negociacao.permuta_ativo_id IS
    'Which permuta_ativos (101) row, if any, is the swap component of this '
    'deal. ON DELETE SET NULL, mirroring imovel_codigo on this same table: '
    'losing which specific ativo was swapped is not losing the deal.';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_negociacao_permuta_ativo
    ON social_wiring.atendimento_negociacao (org_id, permuta_ativo_id)
    WHERE permuta_ativo_id IS NOT NULL;
