-- ============================================================================
-- Migration 075 · social_wiring: the cartório data an imóvel needs for a sale
--
-- WHAT
-- ----
-- Número da matrícula, número do registro de imóveis, prefeitura do cadastro
-- imobiliário, the captador who brought the property in, and the two documents
-- those numbers are read off (the matrícula itself and the guia de IPTU).
--
-- 🔴 WHY A SEPARATE TABLE AND NOT COLUMNS ON `imoveis`
-- ----------------------------------------------------
-- `imoveis` is a MIRROR. `imoveis_service.sync()` walks the Vista catalog and
-- upserts every property with `on_conflict="org_id,codigo"`. PostgREST's upsert
-- only writes the columns present in the payload, so columns we added would in
-- fact survive today — but that safety is a property of the current payload,
-- not of the schema. It is one `select("*")` round-trip, one widened DTO, or
-- one "let's just send the whole row" refactor away from silently nulling
-- them, and nothing in the type system or the tests would notice.
--
-- The data at risk is not cosmetic. A número de matrícula is what identifies a
-- property in the registry; losing it mid-sale means re-requesting a certidão.
-- Authored data does not belong inside a mirror of somebody else's system, and
-- this is the case where that principle has teeth.
--
-- So: same key (`org_id`, `codigo`), FK'd to the catalog, ours to write.
-- A `LEFT JOIN` is the cost, and it is the correct cost — an imóvel with no
-- cartório data yet is the normal state, not a missing row to paper over.
--
-- 🔴 WHY THE DOCUMENTS ARE A TABLE, NOT TWO PATH COLUMNS
-- -------------------------------------------------------
-- Two `TEXT` columns would model "the matrícula" as a single slot. Real
-- matrículas get re-issued: an updated certidão arrives, and the old one still
-- has to be produceable because it is what an earlier step of the process was
-- decided against. A slot forces overwriting; a table keeps the history and
-- gets soft-delete, re-upload and per-type extraction for free — the same
-- shape `cliente_documentos` already uses, for the same reasons.
--
-- It also means adding "certidão negativa" later is a row, not a migration.
--
-- WHAT THIS TABLE DELIBERATELY DOES *NOT* COPY FROM `cliente_documentos`
-- ---------------------------------------------------------------------
-- No `categoria_lgpd`, no `retencao_ate`, no access log. Those exist because a
-- cliente's RG is personal data about a natural person with a retention clock
-- and an audit obligation. A matrícula is a public registry document about a
-- PROPERTY. Copying the identity machinery here would imply an LGPD posture
-- this data does not have and would make the real one harder to read.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — apply after the tech-lead has stated the row counts
-- and the user has given an explicit go-ahead.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. imovel_dados — what WE know about a property, beside what Vista tells us
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.imovel_dados (
    org_id  UUID NOT NULL,
    codigo  TEXT NOT NULL,

    -- The registry identifiers. All TEXT: a matrícula number is an identifier,
    -- not a quantity — it has leading zeros, occasional letters and dots, and
    -- nobody ever does arithmetic on one.
    numero_matricula                TEXT,
    numero_registro_imoveis         TEXT,
    prefeitura_cadastro_imobiliario TEXT,

    -- Provenance for the ONE field a machine can fill in, mirroring the
    -- `clientes.data_nascimento_origem` triplet (068) for the same reason: a
    -- number an OCR pass read off a scan and a number a human typed do not
    -- deserve equal trust, and only storing the origin keeps the value
    -- attributable and correctable instead of anonymous.
    -- Values: 'manual' | 'matricula' (read off the uploaded document).
    numero_matricula_origem         TEXT,
    numero_matricula_documento_id   UUID,
    numero_matricula_em             TIMESTAMPTZ,
    numero_matricula_confirmado_por UUID,
    numero_matricula_confirmado_em  TIMESTAMPTZ,

    -- 🔴 The captador is a USER, not a name. The 5% commission slice
    -- (migration 076) is attributed to whoever brought the property in, and a
    -- free-text name cannot be aggregated: two spellings become two people and
    -- "what did I earn this month" stops being answerable. A property with no
    -- recorded captador leaves this NULL and its slice unallocated, which is
    -- the honest state — never silently reassigned to the agency.
    captador_user_id                UUID,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ,

    PRIMARY KEY (org_id, codigo),
    CONSTRAINT imovel_dados_imovel_fk
        FOREIGN KEY (org_id, codigo)
        REFERENCES social_wiring.imoveis (org_id, codigo) ON DELETE CASCADE
);

COMMENT ON TABLE social_wiring.imovel_dados IS
    'Cartório/registry data WE author for an imóvel. Deliberately separate '
    'from `imoveis`, which is a Vista sync mirror — see the migration header.';

CREATE INDEX IF NOT EXISTS idx_sw_imovel_dados_captador
    ON social_wiring.imovel_dados (org_id, captador_user_id)
    WHERE captador_user_id IS NOT NULL;

-- Finding a property by its registry number is a real lookup (a certidão
-- arrives naming only the matrícula), and it must not be a full scan.
CREATE INDEX IF NOT EXISTS idx_sw_imovel_dados_matricula
    ON social_wiring.imovel_dados (org_id, numero_matricula)
    WHERE numero_matricula IS NOT NULL;

ALTER TABLE social_wiring.imovel_dados ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovel_dados_select_own_org" ON social_wiring.imovel_dados;
CREATE POLICY "imovel_dados_select_own_org" ON social_wiring.imovel_dados
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "imovel_dados_service_role" ON social_wiring.imovel_dados;
CREATE POLICY "imovel_dados_service_role" ON social_wiring.imovel_dados
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. imovel_documentos — the files those numbers come off
-- ----------------------------------------------------------------------------
-- `tipo_documento` is unconstrained TEXT validated in the service against a
-- code-owned tuple, the same call `documento_checklist_service.ITENS` makes:
-- the set will grow (certidão negativa, habite-se, convenção de condomínio)
-- and a CHECK would make each addition a migration.
CREATE TABLE IF NOT EXISTS social_wiring.imovel_documentos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    codigo         TEXT NOT NULL,
    storage_path   TEXT NOT NULL,
    nome_original  TEXT NOT NULL,
    mime_type      TEXT NOT NULL,
    tamanho_bytes  BIGINT NOT NULL CHECK (tamanho_bytes >= 0),
    tipo_documento TEXT NOT NULL,

    -- Extraction of the matrícula number, held ON the document because the
    -- document IS the provenance — same placement as `cliente_documentos`'
    -- extraction columns (068/071), and the same reason: a low-confidence read
    -- needs somewhere to sit that is not the record.
    extracao_status    TEXT
        CHECK (extracao_status IN ('pendente', 'processando', 'ok', 'sem_dados', 'erro')),
    extracao_em        TIMESTAMPTZ,
    extracao_matricula TEXT,
    extracao_confianca TEXT,
    extracao_fonte     TEXT,
    extracao_rotulo    TEXT,
    extracao_erro      TEXT,
    extracao_tentativas INTEGER NOT NULL DEFAULT 0,

    enviado_por    UUID,
    deleted_at     TIMESTAMPTZ,
    delete_motivo  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT imovel_documentos_imovel_fk
        FOREIGN KEY (org_id, codigo)
        REFERENCES social_wiring.imoveis (org_id, codigo) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sw_imovel_documentos_imovel
    ON social_wiring.imovel_documentos (org_id, codigo, created_at DESC);

-- The background reader's claim path: every matrícula not yet read.
CREATE INDEX IF NOT EXISTS idx_sw_imovel_documentos_extracao_pendente
    ON social_wiring.imovel_documentos (extracao_status)
    WHERE deleted_at IS NULL AND extracao_status IN ('pendente', 'processando');

ALTER TABLE social_wiring.imovel_documentos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovel_documentos_select_own_org"
    ON social_wiring.imovel_documentos;
CREATE POLICY "imovel_documentos_select_own_org"
    ON social_wiring.imovel_documentos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "imovel_documentos_service_role"
    ON social_wiring.imovel_documentos;
CREATE POLICY "imovel_documentos_service_role"
    ON social_wiring.imovel_documentos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Deferred FK: the provenance column points at a document row, and the table
-- it points at is created above.
ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_matricula_documento_fk;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_matricula_documento_fk
    FOREIGN KEY (numero_matricula_documento_id)
    REFERENCES social_wiring.imovel_documentos (id) ON DELETE SET NULL;
