-- ============================================================================
-- Migration 109 · social_wiring: Matrícula estruturada — atos, seleção por
-- contrato, e as fontes do título aquisitivo e dos ônus
--
-- WHAT THIS IS FOR
-- ----------------
-- The promessa de compra e venda describes the property by QUOTING its
-- matrícula. USER DECISION (2026-09): the quote is the LITERAL transcription,
-- typos and OCR spacing included — a cartório compares it against its own
-- book, so a "cleaned up" description is a different description. The system
-- splits the transcription into the abertura plus each R-/AV- act and the
-- operator SELECTS which acts enter the contract. Nothing is rewritten.
--
-- 🔴 OFFSETS, NEVER COPIED TEXT
-- ----------------------------
-- `matricula_atos` stores `(char_inicio, char_fim)` into
-- `matricula_extracoes.texto_extraido`, produced by the seed segmenter
-- (`noctusai_lib.integrations.documents.segment_matricula_atos`). There is no
-- text column on it, on the contract selection, or on the imovel_dados
-- pointers. A second copy of an act's text is a copy that can drift from the
-- one the cartório will compare against; a slice of the one transcription
-- cannot. Offsets are Python/Postgres CHARACTER positions (code points).
--
-- An extraction's text is written exactly once (`status -> concluida`) and
-- its acts are inserted once and never re-segmented, so the offsets stay
-- valid for the life of the row. That immutability is what makes the
-- RESTRICT foreign keys below the right choice: deleting an extraction that a
-- contract quotes, or that the imóvel's título/ônus point into, must fail
-- loudly instead of silently orphaning the citation.
--
-- WHAT CHANGES ON EXISTING TABLES
-- -------------------------------
-- 1. `matricula_extracoes` (092) gains an imóvel link (`codigo`, keyed to
--    `imovel_registry` exactly like 076 re-keyed imovel_dados/documentos) and
--    an `imovel_documento_id`. The PDF itself is KEPT as that imovel_documentos
--    row — 092's workflow discarded the bytes, which is why its recovery sweep
--    could only say "send the file again".
-- 2. `imovel_documentos` (075) becomes LGPD-logged. 075's module docstring
--    claimed a matrícula is a public registry document with no personal data
--    to log. A certidão de matrícula names every owner with CPF, estado civil,
--    cônjuge and regime de bens — it IS personal data, and a contract flow now
--    opens these files routinely. Same posture as 078 / 106: every CONTENT
--    read appends to an access log, and a soft-delete records who asked.
-- 3. `imovel_dados` (075/099) gains source pointers for the título aquisitivo
--    and for the ônus, each with origem ('sugerido' | 'manual') and a
--    confirmation stamp. They do NOT touch 099's manual `situacao_onus` /
--    `onus_observacoes`: the heuristic suggester never writes anything, and a
--    human's recorded reading is never overwritten by a pointer.
--
-- RLS shape: org-scoped SELECT for authenticated + service_role ALL, the pair
-- 106 uses. Every write to the new tables goes through the service-role
-- client with an explicit org_id predicate in application code
-- (`app/modules/matriculas/estrutura_service.py`).
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. matricula_extracoes -> the imóvel (and the kept PDF)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.matricula_extracoes
    ADD COLUMN IF NOT EXISTS codigo              TEXT,
    ADD COLUMN IF NOT EXISTS imovel_documento_id UUID;

COMMENT ON COLUMN social_wiring.matricula_extracoes.codigo IS
    'Canonical imóvel código this matrícula belongs to. NULL for a legacy '
    'unlinked upload (092 shape). Keyed to imovel_registry, not the Vista '
    'mirror — see 076.';
COMMENT ON COLUMN social_wiring.matricula_extracoes.imovel_documento_id IS
    'The imovel_documentos row holding the PDF this text was transcribed from. '
    'NULL for a legacy upload whose bytes were never kept.';

-- MATCH SIMPLE: a NULL codigo (legacy unlinked row) is not checked.
ALTER TABLE social_wiring.matricula_extracoes
    DROP CONSTRAINT IF EXISTS matricula_extracoes_registry_fk;
ALTER TABLE social_wiring.matricula_extracoes
    ADD CONSTRAINT matricula_extracoes_registry_fk
    FOREIGN KEY (org_id, codigo)
    REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical);

ALTER TABLE social_wiring.matricula_extracoes
    DROP CONSTRAINT IF EXISTS matricula_extracoes_imovel_documento_fk;
ALTER TABLE social_wiring.matricula_extracoes
    ADD CONSTRAINT matricula_extracoes_imovel_documento_fk
    FOREIGN KEY (imovel_documento_id)
    REFERENCES social_wiring.imovel_documentos (id) ON DELETE SET NULL;

-- A kept document is always an imóvel's document.
ALTER TABLE social_wiring.matricula_extracoes
    DROP CONSTRAINT IF EXISTS matricula_extracoes_documento_exige_codigo;
ALTER TABLE social_wiring.matricula_extracoes
    ADD CONSTRAINT matricula_extracoes_documento_exige_codigo
    CHECK (imovel_documento_id IS NULL OR codigo IS NOT NULL);

-- "Every matrícula transcription for this imóvel, newest first."
CREATE INDEX IF NOT EXISTS idx_sw_matricula_extracoes_org_codigo
    ON social_wiring.matricula_extracoes (org_id, codigo, created_at DESC)
    WHERE codigo IS NOT NULL;

-- "Is this document already being / been transcribed?"
CREATE INDEX IF NOT EXISTS idx_sw_matricula_extracoes_documento
    ON social_wiring.matricula_extracoes (imovel_documento_id)
    WHERE imovel_documento_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 2. imovel_documentos -> LGPD access log (mirror 078 / 106)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_documentos
    ADD COLUMN IF NOT EXISTS delete_solicitado_por UUID;

CREATE TABLE IF NOT EXISTS social_wiring.imovel_documento_acessos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    documento_id UUID NOT NULL
        REFERENCES social_wiring.imovel_documentos (id) ON DELETE CASCADE,
    usuario_id   UUID,
    acao         TEXT NOT NULL CHECK (acao IN ('view', 'download', 'delete')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_imovel_documento_acessos_doc
    ON social_wiring.imovel_documento_acessos (documento_id, created_at DESC);

ALTER TABLE social_wiring.imovel_documento_acessos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovel_documento_acessos_select_own_org"
    ON social_wiring.imovel_documento_acessos;
CREATE POLICY "imovel_documento_acessos_select_own_org"
    ON social_wiring.imovel_documento_acessos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "imovel_documento_acessos_service_role"
    ON social_wiring.imovel_documento_acessos;
CREATE POLICY "imovel_documento_acessos_service_role"
    ON social_wiring.imovel_documento_acessos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. matricula_atos — the acts, as offsets into the transcription
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.matricula_atos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    extracao_id   UUID NOT NULL
        REFERENCES social_wiring.matricula_extracoes (id) ON DELETE CASCADE,

    -- 0-based position in the matrícula. The segmenter's spans are
    -- contiguous and cover the whole text, so ordering by this and
    -- concatenating the slices reproduces texto_extraido byte for byte.
    ordem         INT  NOT NULL CHECK (ordem >= 0),
    kind          TEXT NOT NULL CHECK (kind IN ('abertura', 'R', 'AV')),
    numero        INT  CHECK (numero IS NULL OR numero >= 0),

    char_inicio   INT  NOT NULL CHECK (char_inicio >= 0),
    char_fim      INT  NOT NULL,
    -- The recognised header token (`R-1/12.345`) for UI highlighting.
    header_inicio INT,
    header_fim    INT,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT matricula_atos_span_valido CHECK (char_fim >= char_inicio),
    CONSTRAINT matricula_atos_numero_por_kind
        CHECK ((kind = 'abertura') = (numero IS NULL)),
    CONSTRAINT matricula_atos_header_por_kind
        CHECK (
            (kind = 'abertura') = (header_inicio IS NULL)
            AND (header_inicio IS NULL) = (header_fim IS NULL)
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sw_matricula_atos_ordem
    ON social_wiring.matricula_atos (extracao_id, ordem);

CREATE INDEX IF NOT EXISTS idx_sw_matricula_atos_org_extracao
    ON social_wiring.matricula_atos (org_id, extracao_id);

ALTER TABLE social_wiring.matricula_atos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "matricula_atos_select_own_org"
    ON social_wiring.matricula_atos;
CREATE POLICY "matricula_atos_select_own_org"
    ON social_wiring.matricula_atos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "matricula_atos_service_role"
    ON social_wiring.matricula_atos;
CREATE POLICY "matricula_atos_service_role"
    ON social_wiring.matricula_atos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 4. atendimento_contrato_matricula_atos — which acts a contract quotes
-- ----------------------------------------------------------------------------
-- One extraction per contract (enforced in the service: every selected act
-- must belong to the same extraction). RESTRICT on the act and the
-- extraction: a quoted act disappearing would silently change the contract.
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_contrato_matricula_atos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    contrato_id     UUID NOT NULL
        REFERENCES social_wiring.atendimento_contratos (id) ON DELETE CASCADE,
    extracao_id     UUID NOT NULL
        REFERENCES social_wiring.matricula_extracoes (id) ON DELETE RESTRICT,
    ato_id          UUID NOT NULL
        REFERENCES social_wiring.matricula_atos (id) ON DELETE RESTRICT,
    -- 1-based order the acts appear in the contract — the operator's order,
    -- not necessarily the matrícula's.
    ordem           INT  NOT NULL CHECK (ordem >= 1),
    selecionado_por UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sw_contrato_matricula_atos_ordem
    ON social_wiring.atendimento_contrato_matricula_atos (contrato_id, ordem);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sw_contrato_matricula_atos_ato
    ON social_wiring.atendimento_contrato_matricula_atos (contrato_id, ato_id);
CREATE INDEX IF NOT EXISTS idx_sw_contrato_matricula_atos_extracao
    ON social_wiring.atendimento_contrato_matricula_atos (org_id, extracao_id);

ALTER TABLE social_wiring.atendimento_contrato_matricula_atos
    ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_contrato_matricula_atos_select_own_org"
    ON social_wiring.atendimento_contrato_matricula_atos;
CREATE POLICY "atendimento_contrato_matricula_atos_select_own_org"
    ON social_wiring.atendimento_contrato_matricula_atos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_contrato_matricula_atos_service_role"
    ON social_wiring.atendimento_contrato_matricula_atos;
CREATE POLICY "atendimento_contrato_matricula_atos_service_role"
    ON social_wiring.atendimento_contrato_matricula_atos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 5. imovel_dados -> título aquisitivo + ônus source pointers
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS titulo_aquisitivo_extracao_id    UUID,
    ADD COLUMN IF NOT EXISTS titulo_aquisitivo_ato_id         UUID,
    ADD COLUMN IF NOT EXISTS titulo_aquisitivo_char_inicio    INT,
    ADD COLUMN IF NOT EXISTS titulo_aquisitivo_char_fim       INT,
    ADD COLUMN IF NOT EXISTS titulo_aquisitivo_origem         TEXT,
    ADD COLUMN IF NOT EXISTS titulo_aquisitivo_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS titulo_aquisitivo_confirmado_em  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS onus_fonte_extracao_id           UUID,
    -- [{"ato_id": uuid, "char_inicio": int, "char_fim": int}, ...] in the
    -- operator's order. JSONB rather than a child table because the set is
    -- read and replaced whole, always alongside its one extraction pointer.
    ADD COLUMN IF NOT EXISTS onus_fonte_atos                  JSONB,
    ADD COLUMN IF NOT EXISTS onus_fonte_origem                TEXT,
    ADD COLUMN IF NOT EXISTS onus_fonte_confirmado_por        UUID,
    ADD COLUMN IF NOT EXISTS onus_fonte_confirmado_em         TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.imovel_dados.titulo_aquisitivo_origem IS
    'sugerido = the operator confirmed the heuristic''s pick; manual = the '
    'operator chose a different act. The heuristic itself never writes.';
COMMENT ON COLUMN social_wiring.imovel_dados.onus_fonte_atos IS
    'Offsets into matricula_extracoes.texto_extraido of onus_fonte_extracao_id. '
    'Pointers only — the manual situacao_onus (099) is independent of them.';

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_titulo_aquisitivo_origem_check;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_titulo_aquisitivo_origem_check
    CHECK (titulo_aquisitivo_origem IS NULL
           OR titulo_aquisitivo_origem IN ('sugerido', 'manual'));

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_onus_fonte_origem_check;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_onus_fonte_origem_check
    CHECK (onus_fonte_origem IS NULL
           OR onus_fonte_origem IN ('sugerido', 'manual'));

-- A pointer is all-or-nothing: an act without its extraction (or an origem
-- without a pointer) is a half-written citation.
ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_titulo_aquisitivo_completo;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_titulo_aquisitivo_completo
    CHECK (
        (titulo_aquisitivo_ato_id IS NULL) = (titulo_aquisitivo_extracao_id IS NULL)
        AND (titulo_aquisitivo_ato_id IS NULL) = (titulo_aquisitivo_origem IS NULL)
        AND (titulo_aquisitivo_ato_id IS NULL) = (titulo_aquisitivo_char_inicio IS NULL)
        AND (titulo_aquisitivo_ato_id IS NULL) = (titulo_aquisitivo_char_fim IS NULL)
    );

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_onus_fonte_completa;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_onus_fonte_completa
    CHECK (
        (onus_fonte_extracao_id IS NULL) = (onus_fonte_origem IS NULL)
        AND (onus_fonte_extracao_id IS NULL) = (onus_fonte_atos IS NULL)
        AND (onus_fonte_atos IS NULL OR jsonb_typeof(onus_fonte_atos) = 'array')
    );

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_titulo_aquisitivo_extracao_fk;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_titulo_aquisitivo_extracao_fk
    FOREIGN KEY (titulo_aquisitivo_extracao_id)
    REFERENCES social_wiring.matricula_extracoes (id) ON DELETE RESTRICT;

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_titulo_aquisitivo_ato_fk;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_titulo_aquisitivo_ato_fk
    FOREIGN KEY (titulo_aquisitivo_ato_id)
    REFERENCES social_wiring.matricula_atos (id) ON DELETE RESTRICT;

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_onus_fonte_extracao_fk;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_onus_fonte_extracao_fk
    FOREIGN KEY (onus_fonte_extracao_id)
    REFERENCES social_wiring.matricula_extracoes (id) ON DELETE RESTRICT;

-- The delete guard's lookups ("does the imóvel cite this extraction?").
CREATE INDEX IF NOT EXISTS idx_sw_imovel_dados_titulo_extracao
    ON social_wiring.imovel_dados (titulo_aquisitivo_extracao_id)
    WHERE titulo_aquisitivo_extracao_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sw_imovel_dados_onus_extracao
    ON social_wiring.imovel_dados (onus_fonte_extracao_id)
    WHERE onus_fonte_extracao_id IS NOT NULL;
