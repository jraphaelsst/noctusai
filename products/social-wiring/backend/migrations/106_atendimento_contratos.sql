-- ============================================================================
-- Migration 106 · social_wiring: Contratos — the deal's contract, in revision
--
-- Each atendimento needs its contracts stored in one place: uploaded
-- .docx/.pdf today, auto-generated .docx later (origem='gerado', a future
-- slice — the column exists now so that slice is additive, not a migration).
-- Legal works in REVISIONS ("REV 25.07", "REV FINAL"), so a contract is not
-- one file — it is a STATUS plus a list of VERSIONS, each an immutable
-- upload. Replacing a file in place would destroy the ability to answer
-- "what did REV 25.07 actually say", which is exactly the question a
-- disputed clause turns on.
--
-- 🔴 THESE DOCUMENTS ARE LGPD-RELEVANT, SAME CLASS AS MIGRATION 078
-- -------------------------------------------------------------------------
-- A compra e venda contract carries CPF/RG and bank data for every party.
-- Same posture as `atendimento_documentos`: every CONTENT read of a
-- version's bytes appends to an access log, and a soft-delete keeps its
-- log — soft delete is not erasure.
--
-- WHY ONE TABLE FOR THE CONTRACT AND A SEPARATE ONE FOR ITS VERSIONS
-- --------------------------------------------------------------------------
-- The contract is the thing with a lifecycle (`status`, who decided it, when
-- it was created); a version is a FILE, one row per upload. Collapsing them
-- would mean either the contract table grows unbounded rows for the same
-- deal (losing "the" status/titulo as a single value) or the version table
-- carries status/titulo duplicated onto every row. Splitting mirrors
-- `atendimento_financiamento` (one row, a decision) plus `atendimento_
-- documentos` (many rows, files) landing on the SAME atendimento — this is
-- that same shape, scoped one level down to a single contract instead of
-- the whole deal, because a deal can carry more than one contract.
--
-- `atendimento_contrato_versoes` reuses `app.services.documento_store.
-- DocumentoStore` (the N=3 formalization from migration 078's header) rather
-- than hand-rolling upload/list/url/remove again — `owner_col="contrato_id"`,
-- `acessos_table` set. `numero`/`rotulo`/`origem` are per-surface columns the
-- store's `extra=` passthrough carries; the store owns everything else.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. atendimento_contratos — one row per contract (an atendimento may have
--    more than one: an original and a permuta side-letter, for instance)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_contratos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    atendimento_id UUID NOT NULL
        REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE,

    titulo         TEXT NOT NULL,

    modelo         TEXT NOT NULL DEFAULT 'compra_venda'
        CHECK (modelo IN (
            'compra_venda', 'compra_venda_permuta', 'compra_venda_a_vista',
            'outro'
        )),

    -- rascunho -> em_revisao -> enviado_assinatura -> assinado, with
    -- cancelado reachable from any state (operators fix mistakes). Any
    -- status-to-any-status transition is allowed at the API layer; the CHECK
    -- here only pins the vocabulary, not the graph.
    status         TEXT NOT NULL DEFAULT 'rascunho'
        CHECK (status IN (
            'rascunho', 'em_revisao', 'enviado_assinatura', 'assinado',
            'cancelado'
        )),
    status_em      TIMESTAMPTZ,
    status_por     UUID,

    -- 'gerado' is NOT built by this migration — see this file's header.
    -- The column exists now so the future auto-generation slice is additive.
    origem         TEXT NOT NULL DEFAULT 'upload'
        CHECK (origem IN ('upload', 'gerado')),

    criado_por     UUID,

    -- Soft delete, same shape `atendimento_documentos` uses: a recorded
    -- reason and who asked, because an LGPD delete without one is not one.
    deleted_at     TIMESTAMPTZ,
    delete_motivo  TEXT,
    delete_solicitado_por UUID,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

COMMENT ON COLUMN social_wiring.atendimento_contratos.status IS
    'rascunho | em_revisao | enviado_assinatura | assinado | cancelado. '
    'Any-to-any transition allowed — operators fix mistakes.';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_contratos_atendimento
    ON social_wiring.atendimento_contratos (org_id, atendimento_id, created_at DESC)
    WHERE deleted_at IS NULL;

ALTER TABLE social_wiring.atendimento_contratos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_contratos_select_own_org"
    ON social_wiring.atendimento_contratos;
CREATE POLICY "atendimento_contratos_select_own_org"
    ON social_wiring.atendimento_contratos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_contratos_service_role"
    ON social_wiring.atendimento_contratos;
CREATE POLICY "atendimento_contratos_service_role"
    ON social_wiring.atendimento_contratos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. atendimento_contrato_versoes — one row per uploaded/generated file
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_contrato_versoes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    contrato_id    UUID NOT NULL
        REFERENCES social_wiring.atendimento_contratos (id) ON DELETE CASCADE,

    storage_path   TEXT NOT NULL,
    nome_original  TEXT NOT NULL,
    mime_type      TEXT NOT NULL,
    tamanho_bytes  BIGINT NOT NULL CHECK (tamanho_bytes >= 0),

    -- Fixed to 'contrato' in the service's `DocumentoStore.tipos` — a
    -- single-valued tuple, not a CHECK here, so the store's own `validar`
    -- (the ONE place every surface's type allow-list is enforced) stays the
    -- single source of truth per migration 078's header.
    tipo_documento TEXT NOT NULL,

    -- 1, 2, 3, ... per contrato — NEVER reused, including past a
    -- soft-deleted version, so a citation to "versão 2" always names the
    -- same bytes even after it is gone. The service computes this as
    -- max(numero) + 1 over ALL rows for the contrato, deleted or not; the
    -- UNIQUE constraint below is what makes a computation bug loud instead
    -- of silently overwriting a citation.
    numero         INT NOT NULL CHECK (numero >= 1),

    -- "REV 25.07", "REV FINAL" — how legal actually refers to a revision.
    -- Free text and optional: the number always identifies the version even
    -- when nobody bothered to label it.
    rotulo         TEXT,

    origem         TEXT NOT NULL DEFAULT 'upload'
        CHECK (origem IN ('upload', 'gerado')),

    enviado_por    UUID,
    deleted_at     TIMESTAMPTZ,
    delete_motivo  TEXT,
    delete_solicitado_por UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Enforced across ALL rows (not filtered by deleted_at) — see the `numero`
-- column comment: reuse is the bug, not just reuse-among-the-live-rows.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sw_atendimento_contrato_versoes_numero
    ON social_wiring.atendimento_contrato_versoes (contrato_id, numero);

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_contrato_versoes_contrato
    ON social_wiring.atendimento_contrato_versoes (org_id, contrato_id, numero DESC);

ALTER TABLE social_wiring.atendimento_contrato_versoes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_contrato_versoes_select_own_org"
    ON social_wiring.atendimento_contrato_versoes;
CREATE POLICY "atendimento_contrato_versoes_select_own_org"
    ON social_wiring.atendimento_contrato_versoes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_contrato_versoes_service_role"
    ON social_wiring.atendimento_contrato_versoes;
CREATE POLICY "atendimento_contrato_versoes_service_role"
    ON social_wiring.atendimento_contrato_versoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. atendimento_contrato_versao_acessos — who opened a version's content
-- ----------------------------------------------------------------------------
-- 🔴 Appended on every read of a version's CONTENT (a minted signed URL) and
-- on every delete. Listing metadata does not append — same contract
-- `atendimento_documento_acessos` (078) and `cliente_documento_acessos` have.
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_contrato_versao_acessos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    documento_id UUID NOT NULL
        REFERENCES social_wiring.atendimento_contrato_versoes (id) ON DELETE CASCADE,
    usuario_id   UUID,
    acao         TEXT NOT NULL CHECK (acao IN ('view', 'download', 'delete')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_contrato_versao_acessos_doc
    ON social_wiring.atendimento_contrato_versao_acessos (documento_id, created_at DESC);

ALTER TABLE social_wiring.atendimento_contrato_versao_acessos
    ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_contrato_versao_acessos_select_own_org"
    ON social_wiring.atendimento_contrato_versao_acessos;
CREATE POLICY "atendimento_contrato_versao_acessos_select_own_org"
    ON social_wiring.atendimento_contrato_versao_acessos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_contrato_versao_acessos_service_role"
    ON social_wiring.atendimento_contrato_versao_acessos;
CREATE POLICY "atendimento_contrato_versao_acessos_service_role"
    ON social_wiring.atendimento_contrato_versao_acessos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
