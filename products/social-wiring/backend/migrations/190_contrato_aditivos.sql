-- ============================================================================
-- Migration 190 · social_wiring: ADITIVOS — amendments to a signed contract
--
-- Owner, 2026-09-24: aditivos are in scope — "model, store and generate them".
-- The office's corpus (5 deals, REDACTED) has two styles: the house
-- "ADITIVO AO INSTRUMENTO…" and the formal "PRIMEIRO TERMO ADITIVO". Every
-- one re-qualifies the parties, cites the ORIGINAL instrument by its signing
-- date, amends payments (5/5), posse (2/5) or the commission (3/5), and
-- closes with a "demais cláusulas inalteradas" ratification.
--
-- WHAT THIS STORES
-- ----------------
-- 1. atendimento_contrato_aditivos — one row per aditivo of ONE contract.
--    `ordinal` (1 = PRIMEIRO, 2 = SEGUNDO, …) is assigned by the service as
--    max+1 over EVERY row of the contract, deleted or not, and is never
--    reused: "o Segundo Termo Aditivo" has to keep naming the same
--    instrument after a later one is cancelled. The UNIQUE index below makes
--    a computation bug loud. `alteracoes` is the STRUCTURED amendment list
--    (see the service's schemas): [{tipo, clausula_alvo, …parameters}],
--    tipo ∈ pagamento | posse | comissao | outro. Status vocabulary and the
--    any-to-any rule are the contract's own (migration 106).
-- 2. atendimento_contrato_aditivo_parcelas — a payment amendment is NOT free
--    text: it is the restated schedule, one row per parcela, the SAME shape
--    as `atendimento_negociacao_parcelas` (108/114) so the generator's own
--    sum/order/favorecido gate and parcela wording apply unchanged.
-- 3. atendimento_contrato_aditivo_versoes (+ _acessos) — the generated
--    versions, the same row shape as `atendimento_contrato_versoes`
--    (106/112/120/157/177): PDF + .docx sibling, contexto_sha256, and the
--    legal-review columns. An aditivo version is ALWAYS born awaiting the
--    legal review (its `revisao_juridica_campos` is never empty), so the
--    same `revisao_juridica_status` predicate gates it.
--
-- 🔴 LGPD: same class as migration 106 — an aditivo re-qualifies every party
-- (CPF/RG, address, bank data in parcelas). Every content read of a version
-- appends to the access log; soft delete is not erasure.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. atendimento_contrato_aditivos
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_contrato_aditivos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    atendimento_id UUID NOT NULL
        REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE,
    contrato_id    UUID NOT NULL
        REFERENCES social_wiring.atendimento_contratos (id) ON DELETE CASCADE,

    -- 1 = PRIMEIRO, 2 = SEGUNDO, … — never reused (see header).
    ordinal        INT NOT NULL CHECK (ordinal >= 1),

    -- 'house' = "ADITIVO AO INSTRUMENTO…" (CLÁUSULA ordinals);
    -- 'formal' = "{ORDINAL} TERMO ADITIVO" (numbered sections).
    estilo         TEXT NOT NULL DEFAULT 'house'
        CHECK (estilo IN ('house', 'formal')),

    status         TEXT NOT NULL DEFAULT 'rascunho'
        CHECK (status IN (
            'rascunho', 'em_revisao', 'enviado_assinatura', 'assinado',
            'cancelado'
        )),
    status_em      TIMESTAMPTZ,
    status_por     UUID,

    -- [{tipo, clausula_alvo, …}] — validated by the service; the DB pins
    -- only that it is an array.
    alteracoes     JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(alteracoes) = 'array'),

    -- The date the aditivo is signed (dates the instrument); NULL = today
    -- in São Paulo at generation.
    assinatura_data       DATE,
    modalidade_assinatura TEXT NOT NULL DEFAULT 'digital'
        CHECK (modalidade_assinatura IN ('digital', 'fisica')),

    criado_por     UUID,
    deleted_at     TIMESTAMPTZ,
    delete_motivo  TEXT,
    delete_solicitado_por UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

-- Across ALL rows, deleted or not — reuse is the bug.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_contrato_aditivos_ordinal
    ON social_wiring.atendimento_contrato_aditivos (contrato_id, ordinal);

CREATE INDEX IF NOT EXISTS idx_sw_contrato_aditivos_contrato
    ON social_wiring.atendimento_contrato_aditivos (org_id, contrato_id, ordinal)
    WHERE deleted_at IS NULL;

ALTER TABLE social_wiring.atendimento_contrato_aditivos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_contrato_aditivos_select_own_org"
    ON social_wiring.atendimento_contrato_aditivos;
CREATE POLICY "atendimento_contrato_aditivos_select_own_org"
    ON social_wiring.atendimento_contrato_aditivos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_contrato_aditivos_service_role"
    ON social_wiring.atendimento_contrato_aditivos;
CREATE POLICY "atendimento_contrato_aditivos_service_role"
    ON social_wiring.atendimento_contrato_aditivos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE social_wiring.atendimento_contrato_aditivos IS
    'Aditivos (amendments) of one signed contract — migration 190. ordinal is '
    'never reused; alteracoes is the structured amendment list.';

-- ----------------------------------------------------------------------------
-- 2. atendimento_contrato_aditivo_parcelas — the restated payment schedule
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_contrato_aditivo_parcelas (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    aditivo_id       UUID NOT NULL
        REFERENCES social_wiring.atendimento_contrato_aditivos (id) ON DELETE CASCADE,

    -- Same vocabulary as atendimento_negociacao_parcelas, minus 'permuta'
    -- (a permuta parcela is settled by deed; an aditivo that touches it is an
    -- 'outro' amendment for the legal review, never a generated one).
    tipo             TEXT NOT NULL
        CHECK (tipo IN ('sinal', 'intermediaria', 'financiamento', 'fgts', 'saldo', 'direta')),
    valor            NUMERIC(14, 2) NOT NULL CHECK (valor > 0),
    vencimento       DATE,
    evento           TEXT,
    forma_pagamento  TEXT,
    favorecido_id    UUID
        REFERENCES social_wiring.atendimento_favorecidos (id) ON DELETE SET NULL,
    confissao_divida BOOLEAN NOT NULL DEFAULT FALSE,
    ordem            INT NOT NULL CHECK (ordem >= 0),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_contrato_aditivo_parcelas_ordem
    ON social_wiring.atendimento_contrato_aditivo_parcelas (aditivo_id, ordem);

ALTER TABLE social_wiring.atendimento_contrato_aditivo_parcelas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_contrato_aditivo_parcelas_select_own_org"
    ON social_wiring.atendimento_contrato_aditivo_parcelas;
CREATE POLICY "atendimento_contrato_aditivo_parcelas_select_own_org"
    ON social_wiring.atendimento_contrato_aditivo_parcelas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_contrato_aditivo_parcelas_service_role"
    ON social_wiring.atendimento_contrato_aditivo_parcelas;
CREATE POLICY "atendimento_contrato_aditivo_parcelas_service_role"
    ON social_wiring.atendimento_contrato_aditivo_parcelas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. atendimento_contrato_aditivo_versoes — generated versions
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_contrato_aditivo_versoes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    aditivo_id     UUID NOT NULL
        REFERENCES social_wiring.atendimento_contrato_aditivos (id) ON DELETE CASCADE,

    storage_path   TEXT NOT NULL,
    nome_original  TEXT NOT NULL,
    mime_type      TEXT NOT NULL,
    tamanho_bytes  BIGINT NOT NULL CHECK (tamanho_bytes >= 0),
    tipo_documento TEXT NOT NULL,

    numero         INT NOT NULL CHECK (numero >= 1),
    rotulo         TEXT,
    origem         TEXT NOT NULL DEFAULT 'gerado'
        CHECK (origem IN ('upload', 'gerado')),

    contexto_sha256    TEXT,
    docx_storage_path  TEXT,
    docx_tamanho_bytes BIGINT
        CHECK (docx_tamanho_bytes IS NULL OR docx_tamanho_bytes >= 0),
    modalidade_assinatura TEXT
        CHECK (modalidade_assinatura IS NULL
               OR modalidade_assinatura IN ('digital', 'fisica')),

    revisao_juridica_campos JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(revisao_juridica_campos) = 'array'),
    revisado_por   UUID,
    revisado_em    TIMESTAMPTZ,

    enviado_por    UUID,
    deleted_at     TIMESTAMPTZ,
    delete_motivo  TEXT,
    delete_solicitado_por UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT atendimento_contrato_aditivo_versoes_gerado_completo CHECK (
        (origem = 'gerado'
            AND contexto_sha256 ~ '^[0-9a-f]{64}$'
            AND docx_storage_path IS NOT NULL
            AND docx_tamanho_bytes IS NOT NULL)
        OR (origem = 'upload'
            AND contexto_sha256 IS NULL
            AND docx_storage_path IS NULL
            AND docx_tamanho_bytes IS NULL)
    ),
    CONSTRAINT atendimento_contrato_aditivo_versoes_revisado_par
        CHECK (revisado_por IS NULL OR revisado_em IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_contrato_aditivo_versoes_numero
    ON social_wiring.atendimento_contrato_aditivo_versoes (aditivo_id, numero);

CREATE INDEX IF NOT EXISTS idx_sw_contrato_aditivo_versoes_aditivo
    ON social_wiring.atendimento_contrato_aditivo_versoes (org_id, aditivo_id, numero DESC);

ALTER TABLE social_wiring.atendimento_contrato_aditivo_versoes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_contrato_aditivo_versoes_select_own_org"
    ON social_wiring.atendimento_contrato_aditivo_versoes;
CREATE POLICY "atendimento_contrato_aditivo_versoes_select_own_org"
    ON social_wiring.atendimento_contrato_aditivo_versoes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_contrato_aditivo_versoes_service_role"
    ON social_wiring.atendimento_contrato_aditivo_versoes;
CREATE POLICY "atendimento_contrato_aditivo_versoes_service_role"
    ON social_wiring.atendimento_contrato_aditivo_versoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 4. atendimento_contrato_aditivo_versao_acessos — LGPD access log
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_contrato_aditivo_versao_acessos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    documento_id UUID NOT NULL
        REFERENCES social_wiring.atendimento_contrato_aditivo_versoes (id) ON DELETE CASCADE,
    usuario_id   UUID,
    acao         TEXT NOT NULL CHECK (acao IN ('view', 'download', 'delete')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_contrato_aditivo_versao_acessos_doc
    ON social_wiring.atendimento_contrato_aditivo_versao_acessos (documento_id, created_at DESC);

ALTER TABLE social_wiring.atendimento_contrato_aditivo_versao_acessos
    ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_contrato_aditivo_versao_acessos_select_own_org"
    ON social_wiring.atendimento_contrato_aditivo_versao_acessos;
CREATE POLICY "atendimento_contrato_aditivo_versao_acessos_select_own_org"
    ON social_wiring.atendimento_contrato_aditivo_versao_acessos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_contrato_aditivo_versao_acessos_service_role"
    ON social_wiring.atendimento_contrato_aditivo_versao_acessos;
CREATE POLICY "atendimento_contrato_aditivo_versao_acessos_service_role"
    ON social_wiring.atendimento_contrato_aditivo_versao_acessos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

NOTIFY pgrst, 'reload schema';
