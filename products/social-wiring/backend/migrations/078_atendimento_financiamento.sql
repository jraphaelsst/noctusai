-- ============================================================================
-- Migration 078 · social_wiring: Financiamento / Escritura, and its documents
--
-- Certidão de casamento, escritura do pacto, registro do pacto, comprovante de
-- residência; aprovado/recusado; and — when FGTS is used — imposto de renda
-- com recibo de entrega, carteira de trabalho, extratos do FGTS e comprovante
-- de residência datado há um ano.
--
-- ONE SET PER DEAL, NOT PER PERSON (user, verbatim: "The atendimento's — one
-- set for the deal"). So everything here hangs off `atendimento_id`, and the
-- documents are a THIRD document table rather than rows on
-- `cliente_documentos`: a certidão de casamento belongs to the transaction,
-- not to either spouse individually, and filing it under one of them would
-- make it invisible from the other's card.
--
-- 🔴 THESE DOCUMENTS ARE LGPD-RELEVANT, UNLIKE THE IMÓVEL'S
-- ----------------------------------------------------------
-- Migration 075 deliberately gave `imovel_documentos` NO access log and no
-- retention clock, because a matrícula is a public registry document about a
-- PROPERTY. That argument does not survive contact with this set.
--
-- An imposto de renda com recibo de entrega is a person's full declared
-- income. A carteira de trabalho is their employment history. Extratos do
-- FGTS are their savings. A certidão de casamento names a spouse. These are
-- personal — several of them financial — data about natural persons, and they
-- are exactly the category where "who opened this file, and when" has to be
-- answerable.
--
-- So this table carries the same machinery `cliente_documentos` does:
-- `categoria_lgpd`, `retencao_ate`, soft delete with a recorded reason, and a
-- companion access log that every CONTENT read appends to.
--
-- 🔴 A NEW LGPD INTAKE. Reading a buyer's income tax return and employment
-- record is a processing purpose this product has never had. Recorded via
-- `noctus.dev.lgpd_flag` in the same change — see LGPD-WARNINGS.md.
--
-- WHY THERE IS NO SEPARATE `fgts` TABLE
-- -------------------------------------
-- The user asked for "fgts_id to another table containing FGTS data". That
-- table's entire contents would be four file uploads — and files already have
-- a home here, keyed by `tipo_documento`. A dedicated table would hold an id,
-- an org_id and nothing else, existing only to be joined through.
--
-- So `financiamento.fgts` is the boolean, and the four FGTS documents are four
-- `tipo_documento` values in this same table. The UI groups them under an FGTS
-- section that appears when the flag is on, which is the behaviour that was
-- actually asked for. → surfaced in the delivery note as an interpretation
-- call; if FGTS later grows data of its own (a protocol number, a status, a
-- date), it earns its table then.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. atendimento_financiamento — one row per deal
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_financiamento (
    atendimento_id UUID PRIMARY KEY
        REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE,
    org_id         UUID NOT NULL,

    -- 🔴 THREE-VALUED, NOT A BOOLEAN. "Not yet decided" is the state a
    -- financing application spends most of its life in, and it is NOT the
    -- same as "recusado". A nullable boolean would spell it, but every reader
    -- would have to remember that null means pending — so it is named.
    situacao TEXT NOT NULL DEFAULT 'pendente'
        CHECK (situacao IN ('pendente', 'aprovado', 'recusado')),
    situacao_em    TIMESTAMPTZ,
    situacao_por   UUID,
    situacao_motivo TEXT,

    -- Mirrors `atendimento_negociacao.fgts` rather than referencing it: the
    -- negociação records what the buyer SAID they would do; this records what
    -- the financing process is actually collecting. They can legitimately
    -- disagree while a deal is in flight.
    fgts           BOOLEAN NOT NULL DEFAULT false,

    observacoes    TEXT,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por    UUID,
    updated_at     TIMESTAMPTZ,
    updated_por    UUID
);

COMMENT ON COLUMN social_wiring.atendimento_financiamento.situacao IS
    'pendente | aprovado | recusado. Three-valued on purpose — "not yet '
    'decided" is where an application spends most of its life and is not the '
    'same as a refusal.';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_financiamento_org
    ON social_wiring.atendimento_financiamento (org_id, situacao);

ALTER TABLE social_wiring.atendimento_financiamento ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_financiamento_select_own_org"
    ON social_wiring.atendimento_financiamento;
CREATE POLICY "atendimento_financiamento_select_own_org"
    ON social_wiring.atendimento_financiamento
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_financiamento_service_role"
    ON social_wiring.atendimento_financiamento;
CREATE POLICY "atendimento_financiamento_service_role"
    ON social_wiring.atendimento_financiamento
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. atendimento_documentos — the deal's paperwork (LGPD-complete)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_documentos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    atendimento_id UUID NOT NULL
        REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE,

    storage_path   TEXT NOT NULL,
    nome_original  TEXT NOT NULL,
    mime_type      TEXT NOT NULL,
    tamanho_bytes  BIGINT NOT NULL CHECK (tamanho_bytes >= 0),

    -- Validated in the service against a code-owned tuple, same call
    -- `imovel_documentos` makes: the set will grow and a CHECK would make each
    -- addition a migration.
    tipo_documento TEXT NOT NULL,

    -- LGPD. Present here and absent from `imovel_documentos` for the reason in
    -- this file's header: an imposto de renda is not a matrícula.
    categoria_lgpd TEXT NOT NULL DEFAULT 'financeiro',
    retencao_ate   DATE,

    enviado_por    UUID,
    deleted_at     TIMESTAMPTZ,
    delete_motivo  TEXT,
    delete_solicitado_por UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_documentos_atendimento
    ON social_wiring.atendimento_documentos (org_id, atendimento_id, created_at DESC);

-- The retention sweep's claim path.
CREATE INDEX IF NOT EXISTS idx_sw_atendimento_documentos_retencao
    ON social_wiring.atendimento_documentos (retencao_ate)
    WHERE deleted_at IS NULL AND retencao_ate IS NOT NULL;

ALTER TABLE social_wiring.atendimento_documentos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_documentos_select_own_org"
    ON social_wiring.atendimento_documentos;
CREATE POLICY "atendimento_documentos_select_own_org"
    ON social_wiring.atendimento_documentos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_documentos_service_role"
    ON social_wiring.atendimento_documentos;
CREATE POLICY "atendimento_documentos_service_role"
    ON social_wiring.atendimento_documentos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. atendimento_documento_acessos — who opened what, and when
-- ----------------------------------------------------------------------------
-- 🔴 Appended on every read of a document's CONTENT (a minted signed URL) and
-- on every delete. Listing METADATA does not append — that is not an access to
-- the file's bytes. Same contract `cliente_documento_acessos` has, because
-- these documents are the same kind of thing.
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_documento_acessos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    documento_id UUID NOT NULL
        REFERENCES social_wiring.atendimento_documentos (id) ON DELETE CASCADE,
    usuario_id   UUID,
    acao         TEXT NOT NULL CHECK (acao IN ('view', 'download', 'delete')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_documento_acessos_doc
    ON social_wiring.atendimento_documento_acessos (documento_id, created_at DESC);

ALTER TABLE social_wiring.atendimento_documento_acessos
    ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_documento_acessos_select_own_org"
    ON social_wiring.atendimento_documento_acessos;
CREATE POLICY "atendimento_documento_acessos_select_own_org"
    ON social_wiring.atendimento_documento_acessos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_documento_acessos_service_role"
    ON social_wiring.atendimento_documento_acessos;
CREATE POLICY "atendimento_documento_acessos_service_role"
    ON social_wiring.atendimento_documento_acessos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
