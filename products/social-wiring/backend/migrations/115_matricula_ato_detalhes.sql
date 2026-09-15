-- ============================================================================
-- Migration 115 · social_wiring: Detalhes dos atos da matrícula — natureza,
-- data, valor, partes, credor, instrumento — e o que o contrato precisa deles
--
-- WHAT THIS IS FOR
-- ----------------
-- 109 split a matrícula into acts, as offsets. Nothing captured WHAT an act
-- says: its date, its nature, who sold to whom, which bank holds the
-- hipoteca, which escritura it registers. The promessa de compra e venda
-- needs three of those readings:
--
--   1. a paraphrased título aquisitivo ("adquirido por Escritura Pública de
--      Venda e Compra lavrada em ... registrada sob o R-3");
--   2. the ônus creditor (who must give quitação);
--   3. OFFICE RULE: the previous owners and the date of the last registered
--      compra e venda — their certidões are required when that sale is less
--      than 5 years old.
--
-- The readings come from the SEED (`noctusai_lib.integrations.documents.
-- extrair_detalhes_ato` — deterministic, no LLM), are stored as `origem =
-- 'sugestao'` when the acts are segmented, and become `'confirmado'` only
-- when an operator confirms or edits them.
--
-- WHAT CHANGES
-- ------------
-- 1. `matricula_ato_detalhes` — one row per R/AV act (never the abertura).
--    Composite FK `(org_id, extracao_id, ato_id)` -> `matricula_atos` (the
--    same-org guarantee 111 gave `imovel_documento_id`, extended to also pin
--    the row to the act's OWN extraction). ON DELETE CASCADE: a detail has
--    no meaning without its act. Every field carries a confidence
--    (`alta`/`baixa`/`nenhuma`), mirroring the seed value object.
-- 2. `imovel_documento_acessos.acao` gains `'detalhes_view'`. 🔴 LGPD: party
--    names and CPFs lifted out of the matrícula are personal data (KB
--    PATTERNS/security/lgpd.md §10) — a route that returns them without the
--    text itself logs this, exactly as 111 logs `text_view`.
-- 3. `imovel_dados` gains `titulo_aquisitivo_texto` + `onus_credor`, each with
--    its confirmation stamp. They are the CONFIRMED contract wording; the
--    suggestion is recomputed from the acts on every read and never stored.
-- 4. `atendimento_contrato_matricula_atos` gains `papel` ('objeto' |
--    'permuta') + `permuta_ativo_id`: a permuta contract quotes the matrícula
--    of the property given in exchange too. The unique ordering becomes
--    per-group. The app refuses a permuta selection whose extraction's
--    `codigo` is not the permuta ativo's `imovel_codigo` — the same check 111
--    applies between an `objeto` selection and the negotiated imóvel.
--
-- 🔴 BACKFILL IS APPLICATION-SIDE, NOT SQL
-- ----------------------------------------
-- The extractor is a Python function; SQL cannot run it. Existing acts get
-- their `sugestao` row on first read (`app/modules/matriculas/
-- ato_detalhes_service.py::detalhes_por_ato`), the same heal-on-read 109 uses
-- for acts of an extraction concluded before that migration existed. An
-- empty all-NULL row inserted here would read as "the extractor found
-- nothing", which is a false statement about the text.
--
-- RETENTION: follows the `imovel` surface (111). `purgar_texto_expirado`
-- deletes the detail rows of every extraction whose text it purges — a CPF
-- lifted out of a purged transcription must not outlive it.
--
-- RLS shape: org-scoped SELECT for authenticated + service_role ALL (the pair
-- 109 uses). Writes go through the service-role client with an explicit
-- org_id predicate in application code.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. matricula_ato_detalhes
-- ----------------------------------------------------------------------------
-- A composite FK target needs a UNIQUE constraint on exactly those columns;
-- `id` is already the primary key, so this adds no new uniqueness.
ALTER TABLE social_wiring.matricula_atos
    DROP CONSTRAINT IF EXISTS matricula_atos_org_extracao_id_key;
ALTER TABLE social_wiring.matricula_atos
    ADD CONSTRAINT matricula_atos_org_extracao_id_key UNIQUE (org_id, extracao_id, id);

CREATE TABLE IF NOT EXISTS social_wiring.matricula_ato_detalhes (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                    UUID NOT NULL,
    extracao_id               UUID NOT NULL,
    ato_id                    UUID NOT NULL,

    natureza                  TEXT
        CHECK (natureza IS NULL OR natureza IN (
            'compra_e_venda', 'doacao', 'permuta', 'partilha', 'dacao',
            'arrematacao', 'hipoteca', 'alienacao_fiduciaria', 'cancelamento',
            'penhora', 'usufruto', 'indisponibilidade', 'construcao', 'outro'
        )),
    natureza_confianca        TEXT NOT NULL DEFAULT 'nenhuma'
        CHECK (natureza_confianca IN ('alta', 'baixa', 'nenhuma')),

    data_registro             DATE,
    data_registro_confianca   TEXT NOT NULL DEFAULT 'nenhuma'
        CHECK (data_registro_confianca IN ('alta', 'baixa', 'nenhuma')),

    valor                     NUMERIC(15, 2) CHECK (valor IS NULL OR valor >= 0),
    valor_confianca           TEXT NOT NULL DEFAULT 'nenhuma'
        CHECK (valor_confianca IN ('alta', 'baixa', 'nenhuma')),

    -- [{"nome": text, "cpf_cnpj": text|null}, ...] — names are literal
    -- substrings of the act; CPF/CNPJ formatted.
    transmitentes             JSONB NOT NULL DEFAULT '[]'::jsonb,
    transmitentes_confianca   TEXT NOT NULL DEFAULT 'nenhuma'
        CHECK (transmitentes_confianca IN ('alta', 'baixa', 'nenhuma')),
    adquirentes               JSONB NOT NULL DEFAULT '[]'::jsonb,
    adquirentes_confianca     TEXT NOT NULL DEFAULT 'nenhuma'
        CHECK (adquirentes_confianca IN ('alta', 'baixa', 'nenhuma')),

    credor                    TEXT,
    credor_confianca          TEXT NOT NULL DEFAULT 'nenhuma'
        CHECK (credor_confianca IN ('alta', 'baixa', 'nenhuma')),

    -- {"tipo", "data" (ISO date), "tabelionato", "livro", "folhas", "cidade"}
    instrumento               JSONB,
    instrumento_confianca     TEXT NOT NULL DEFAULT 'nenhuma'
        CHECK (instrumento_confianca IN ('alta', 'baixa', 'nenhuma')),

    -- [{"kind": "R"|"AV", "numero": int}, ...]
    atos_referidos            JSONB NOT NULL DEFAULT '[]'::jsonb,
    atos_referidos_confianca  TEXT NOT NULL DEFAULT 'nenhuma'
        CHECK (atos_referidos_confianca IN ('alta', 'baixa', 'nenhuma')),

    origem                    TEXT NOT NULL DEFAULT 'sugestao'
        CHECK (origem IN ('sugestao', 'confirmado')),
    confirmado_por            UUID,
    confirmado_em             TIMESTAMPTZ,

    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ,

    CONSTRAINT matricula_ato_detalhes_ato_fk
        FOREIGN KEY (org_id, extracao_id, ato_id)
        REFERENCES social_wiring.matricula_atos (org_id, extracao_id, id)
        ON DELETE CASCADE,
    -- A confirmation is a stamp: 'confirmado' without WHEN is a claim.
    CONSTRAINT matricula_ato_detalhes_confirmacao
        CHECK ((origem = 'confirmado') = (confirmado_em IS NOT NULL)),
    CONSTRAINT matricula_ato_detalhes_formas_json
        CHECK (
            jsonb_typeof(transmitentes) = 'array'
            AND jsonb_typeof(adquirentes) = 'array'
            AND jsonb_typeof(atos_referidos) = 'array'
            AND (instrumento IS NULL OR jsonb_typeof(instrumento) = 'object')
        )
);

COMMENT ON TABLE social_wiring.matricula_ato_detalhes IS
    'Typed reading of one matrícula act (migration 115). origem=sugestao is '
    'the seed extractor''s output; confirmado is an operator''s. Carries '
    'personal data (party names/CPFs) — reads are logged as detalhes_view.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_sw_matricula_ato_detalhes_ato
    ON social_wiring.matricula_ato_detalhes (ato_id);

CREATE INDEX IF NOT EXISTS idx_sw_matricula_ato_detalhes_org_extracao
    ON social_wiring.matricula_ato_detalhes (org_id, extracao_id);

ALTER TABLE social_wiring.matricula_ato_detalhes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "matricula_ato_detalhes_select_own_org"
    ON social_wiring.matricula_ato_detalhes;
CREATE POLICY "matricula_ato_detalhes_select_own_org"
    ON social_wiring.matricula_ato_detalhes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "matricula_ato_detalhes_service_role"
    ON social_wiring.matricula_ato_detalhes;
CREATE POLICY "matricula_ato_detalhes_service_role"
    ON social_wiring.matricula_ato_detalhes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. imovel_documento_acessos — a detalhes read is its own logged access
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_documento_acessos
    DROP CONSTRAINT IF EXISTS imovel_documento_acessos_acao_check;
ALTER TABLE social_wiring.imovel_documento_acessos
    ADD CONSTRAINT imovel_documento_acessos_acao_check
    CHECK (acao IN ('view', 'download', 'delete', 'text_view', 'detalhes_view'));

-- ----------------------------------------------------------------------------
-- 3. imovel_dados — the confirmed título wording and ônus creditor
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS titulo_aquisitivo_texto                TEXT,
    ADD COLUMN IF NOT EXISTS titulo_aquisitivo_texto_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS titulo_aquisitivo_texto_confirmado_em  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS onus_credor                            TEXT,
    ADD COLUMN IF NOT EXISTS onus_credor_confirmado_por             UUID,
    ADD COLUMN IF NOT EXISTS onus_credor_confirmado_em              TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.imovel_dados.titulo_aquisitivo_texto IS
    'The título aquisitivo phrase as the operator confirmed it (migration 115). '
    'Suggested from the confirmed título act''s instrumento; never written by '
    'the suggester.';
COMMENT ON COLUMN social_wiring.imovel_dados.onus_credor IS
    'The ônus creditor as the operator confirmed it (migration 115). Suggested '
    'from the confirmed ônus acts; independent of 099''s manual situacao_onus.';

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_titulo_aquisitivo_texto_confirmado;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_titulo_aquisitivo_texto_confirmado
    CHECK ((titulo_aquisitivo_texto IS NULL) = (titulo_aquisitivo_texto_confirmado_em IS NULL));

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_onus_credor_confirmado;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_onus_credor_confirmado
    CHECK ((onus_credor IS NULL) = (onus_credor_confirmado_em IS NULL));

-- ----------------------------------------------------------------------------
-- 4. atendimento_contrato_matricula_atos — objeto vs permuta
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.permuta_ativos
    DROP CONSTRAINT IF EXISTS permuta_ativos_org_id_id_key;
ALTER TABLE social_wiring.permuta_ativos
    ADD CONSTRAINT permuta_ativos_org_id_id_key UNIQUE (org_id, id);

-- NOT NULL DEFAULT: every existing selection row reads as 'objeto', which is
-- what every one of them is.
ALTER TABLE social_wiring.atendimento_contrato_matricula_atos
    ADD COLUMN IF NOT EXISTS papel            TEXT NOT NULL DEFAULT 'objeto',
    ADD COLUMN IF NOT EXISTS permuta_ativo_id UUID;

ALTER TABLE social_wiring.atendimento_contrato_matricula_atos
    DROP CONSTRAINT IF EXISTS atendimento_contrato_matricula_atos_papel_check;
ALTER TABLE social_wiring.atendimento_contrato_matricula_atos
    ADD CONSTRAINT atendimento_contrato_matricula_atos_papel_check
    CHECK (papel IN ('objeto', 'permuta'));

ALTER TABLE social_wiring.atendimento_contrato_matricula_atos
    DROP CONSTRAINT IF EXISTS atendimento_contrato_matricula_atos_permuta_por_papel;
ALTER TABLE social_wiring.atendimento_contrato_matricula_atos
    ADD CONSTRAINT atendimento_contrato_matricula_atos_permuta_por_papel
    CHECK ((papel = 'permuta') = (permuta_ativo_id IS NOT NULL));

-- Same-org by construction (the 111 composite shape). RESTRICT: a quoted
-- permuta disappearing would silently change the contract. MATCH SIMPLE: an
-- 'objeto' row (NULL permuta_ativo_id) is not checked.
ALTER TABLE social_wiring.atendimento_contrato_matricula_atos
    DROP CONSTRAINT IF EXISTS atendimento_contrato_matricula_atos_permuta_fk;
ALTER TABLE social_wiring.atendimento_contrato_matricula_atos
    ADD CONSTRAINT atendimento_contrato_matricula_atos_permuta_fk
    FOREIGN KEY (org_id, permuta_ativo_id)
    REFERENCES social_wiring.permuta_ativos (org_id, id)
    ON DELETE RESTRICT;

-- The operator's order is per group now: objeto 1..N, each permuta 1..M.
DROP INDEX IF EXISTS social_wiring.idx_sw_contrato_matricula_atos_ordem;
CREATE UNIQUE INDEX IF NOT EXISTS idx_sw_contrato_matricula_atos_grupo_ordem
    ON social_wiring.atendimento_contrato_matricula_atos (
        contrato_id,
        papel,
        COALESCE(permuta_ativo_id, '00000000-0000-0000-0000-000000000000'::uuid),
        ordem
    );

CREATE INDEX IF NOT EXISTS idx_sw_contrato_matricula_atos_permuta
    ON social_wiring.atendimento_contrato_matricula_atos (org_id, permuta_ativo_id)
    WHERE permuta_ativo_id IS NOT NULL;
