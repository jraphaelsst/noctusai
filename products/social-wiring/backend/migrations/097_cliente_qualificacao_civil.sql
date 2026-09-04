-- ============================================================================
-- Migration 097 -- social_wiring: qualificação civil do cliente
--
-- WHAT THIS IS
-- ------------
-- The columns a CONTRACT needs to name a person, which a CRM never needed to
-- collect. `clientes` could say who someone is well enough to call them back:
-- name, phone, email, birthdate, profession, gender. An "Instrumento
-- Particular de Promessa de Compra e Venda" qualifies each party by name,
-- nacionalidade, estado civil (with regime de bens), profissão, CPF, RG with
-- issuing body, and address. Of those seven this schema had two.
--
-- 🔴 ESTADO CIVIL IS THE LOAD-BEARING ONE, AND IT IS NOT A PREFERENCE FIELD
-- -------------------------------------------------------------------------
-- It decides whether a spouse must sign. A sale of real property by a married
-- person without the other spouse's outorga is voidable (CC art. 1.647), so
-- "casado" is not decoration on a card — it changes how many signature lines
-- the document has and who has to be in the room. `conjuge_cliente_id` points
-- at the spouse's own `clientes` row rather than storing a name, for the same
-- reason `atendimento_partes` references clientes: the spouse needs the same
-- checklist, the same uploads and the same extraction as anybody else who
-- signs. A name in a TEXT column signs nothing.
--
-- 🔴 CPF AND RG CARRY PROVENANCE, MIRRORING `nome_oficial` (MIGRATION 071)
-- ------------------------------------------------------------------------
-- Both are read off a document by `noctusai_lib.integrations.documents`, and
-- the platform already settled how a machine-read identity value is stored:
-- the value, where it came from (`_origem`), which upload it was read from
-- (`_documento_id`), when (`_em`), and — when a human had to vouch for a
-- low-confidence read — who and when (`_confirmado_por` / `_confirmado_em`).
-- A NULL `_confirmado_por` beside a set value means the extractor was
-- confident enough to write it unattended. Copied verbatim rather than
-- invented, so the three identity fields read the same way.
--
-- 🔴 NO UNIQUE INDEX ON CPF, DELIBERATELY
-- ----------------------------------------
-- A CPF does identify exactly one person, so a UNIQUE constraint looks
-- obviously correct. It is not, for this table, today:
--
--   * `identidade_incerta` rows exist precisely because the same human can be
--     in here twice under two channels; the merge path in `clientes_service`
--     resolves that AFTER the fact, and a UNIQUE would make the second insert
--     fail before anyone could.
--   * The XLSX importer bulk-upserts. One malformed CPF repeated across rows
--     would abort an entire import rather than land 4,000 good rows and flag
--     one.
--
-- So it is INDEXED (lookups and dedup reports are the real use) and left
-- non-unique, and duplicate-CPF detection belongs with the existing dedup
-- surface rather than as a hard constraint discovered at import time.
--
-- 🔴 UNCONSTRAINED TEXT FOR estado_civil / regime_bens / nacionalidade
-- --------------------------------------------------------------------
-- Same call migration 073 made for `genero`, for the same reason: the UI
-- offers a list, but the taxonomy is a product decision and a CHECK would turn
-- every addition ("união estável", "separação obrigatória de bens") into a
-- migration. The vocabulary lives in the service, next to the dropdown.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. Comparison form for a document number
-- ----------------------------------------------------------------------------
-- `52.179.965-X` and `52179965x` are the same RG, and the operator will type
-- either. Same problem `normalizar_nome` (migration 071) solved for names, and
-- the same shape of answer: an IMMUTABLE comparison form that can be indexed,
-- so a lookup never depends on how the value was punctuated when it was
-- stored. Digits and letters both survive — an RG can legitimately end in `X`,
-- which is a check digit, not a typo.
CREATE OR REPLACE FUNCTION social_wiring.normalizar_documento(txt TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT NULLIF(regexp_replace(upper(COALESCE(txt, '')), '[^0-9A-Z]', '', 'g'), '');
$$;

COMMENT ON FUNCTION social_wiring.normalizar_documento(TEXT) IS
    'Comparison form of a CPF/RG: punctuation dropped, upper-cased, empty to '
    'NULL. Letters survive because an RG check digit can be X. IMMUTABLE so '
    'it can be indexed.';

-- ----------------------------------------------------------------------------
-- 2. CPF + RG, with the provenance quintet `nome_oficial` established
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS cpf                    TEXT,
    ADD COLUMN IF NOT EXISTS cpf_origem             TEXT,
    ADD COLUMN IF NOT EXISTS cpf_documento_id       UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS cpf_em                 TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cpf_confirmado_por     UUID,
    ADD COLUMN IF NOT EXISTS cpf_confirmado_em      TIMESTAMPTZ,

    ADD COLUMN IF NOT EXISTS rg                     TEXT,
    ADD COLUMN IF NOT EXISTS rg_orgao_expedidor     TEXT,
    ADD COLUMN IF NOT EXISTS rg_origem              TEXT,
    ADD COLUMN IF NOT EXISTS rg_documento_id        UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS rg_em                  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rg_confirmado_por      UUID,
    ADD COLUMN IF NOT EXISTS rg_confirmado_em       TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.clientes.cpf IS
    'CPF as read off a document or typed by an operator, in whatever '
    'punctuation it arrived with. Compare via normalizar_documento(), never '
    'by raw equality.';
COMMENT ON COLUMN social_wiring.clientes.cpf_origem IS
    '''manual'' | ''cpf'' | ''rg'' | ''cnh'' | ''import'' — where this value '
    'came from. NULL alongside a non-null cpf means it predates 097.';
COMMENT ON COLUMN social_wiring.clientes.cpf_confirmado_por IS
    'Set when a human accepted a LOW-confidence read. NULL alongside a set '
    'cpf means the extractor wrote it unattended at high confidence.';
COMMENT ON COLUMN social_wiring.clientes.rg IS
    'RG number including its check digit, which can be the letter X. Compare '
    'via normalizar_documento().';
COMMENT ON COLUMN social_wiring.clientes.rg_orgao_expedidor IS
    'Issuing body and UF as printed — ''SSP/SP''. A contract qualifies a '
    'party by the number AND its issuer; the number alone does not identify '
    'the document.';

CREATE INDEX IF NOT EXISTS idx_sw_clientes_cpf_norm
    ON social_wiring.clientes (org_id, social_wiring.normalizar_documento(cpf))
    WHERE cpf IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sw_clientes_rg_norm
    ON social_wiring.clientes (org_id, social_wiring.normalizar_documento(rg))
    WHERE rg IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. Estado civil, regime de bens, cônjuge, nacionalidade
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS estado_civil       TEXT,
    ADD COLUMN IF NOT EXISTS regime_bens        TEXT,
    ADD COLUMN IF NOT EXISTS conjuge_cliente_id UUID
        REFERENCES social_wiring.clientes(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS nacionalidade      TEXT;

COMMENT ON COLUMN social_wiring.clientes.estado_civil IS
    'Solteiro | Casado | Divorciado | Viúvo | União estável | Separado. '
    'Unconstrained TEXT (see the migration header) — the vocabulary lives in '
    'the service beside the dropdown. Decides whether a spouse must sign.';
COMMENT ON COLUMN social_wiring.clientes.regime_bens IS
    'Only meaningful when estado_civil is a married state. NOT tied to it by '
    'a CHECK: an operator fills the card top-to-bottom and a constraint that '
    'rejects a half-filled form loses the rest of what they typed.';
COMMENT ON COLUMN social_wiring.clientes.conjuge_cliente_id IS
    'The spouse''s own clientes row — so the spouse gets the same checklist, '
    'uploads and extraction as any other signatory. A name in TEXT signs '
    'nothing.';

-- A person cannot be their own spouse. Same shape as the vinculo guard in 074.
ALTER TABLE social_wiring.clientes
    DROP CONSTRAINT IF EXISTS clientes_conjuge_nao_e_proprio;
ALTER TABLE social_wiring.clientes
    ADD CONSTRAINT clientes_conjuge_nao_e_proprio
    CHECK (conjuge_cliente_id IS NULL OR conjuge_cliente_id <> id);

CREATE INDEX IF NOT EXISTS idx_sw_clientes_conjuge
    ON social_wiring.clientes (org_id, conjuge_cliente_id)
    WHERE conjuge_cliente_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 4. Endereço
-- ----------------------------------------------------------------------------
-- Structured rather than one TEXT blob, matching `imoveis` (migration 040)
-- exactly — same column names, same nullability. A contract prints the parts
-- separately and a CEP lookup fills them separately; a single line would have
-- to be re-split by every consumer, differently.
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS endereco_cep         TEXT,
    ADD COLUMN IF NOT EXISTS endereco_logradouro  TEXT,
    ADD COLUMN IF NOT EXISTS endereco_numero      TEXT,
    ADD COLUMN IF NOT EXISTS endereco_complemento TEXT,
    ADD COLUMN IF NOT EXISTS endereco_bairro      TEXT,
    ADD COLUMN IF NOT EXISTS endereco_cidade      TEXT,
    ADD COLUMN IF NOT EXISTS endereco_uf          TEXT;

COMMENT ON COLUMN social_wiring.clientes.endereco_logradouro IS
    'Residential address of the PERSON — not of any imóvel. Column names '
    'mirror social_wiring.imoveis so the two read alike.';

-- ----------------------------------------------------------------------------
-- 5. The extractor's per-document readings for CPF and RG
-- ----------------------------------------------------------------------------
-- Held on the DOCUMENT row, not on the client, for the reason migration 073
-- gave when it added the gender triple: a low-confidence read needs somewhere
-- to sit without touching the person's record. A suggestion is not a fact.
ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_cpf           TEXT,
    ADD COLUMN IF NOT EXISTS extracao_cpf_confianca TEXT,
    ADD COLUMN IF NOT EXISTS extracao_cpf_rotulo    TEXT,
    ADD COLUMN IF NOT EXISTS extracao_rg            TEXT,
    ADD COLUMN IF NOT EXISTS extracao_rg_confianca  TEXT,
    ADD COLUMN IF NOT EXISTS extracao_rg_rotulo     TEXT,
    ADD COLUMN IF NOT EXISTS extracao_rg_orgao      TEXT;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_cpf IS
    'CPF as read off THIS document. Promoted to clientes.cpf only at high '
    'confidence, or after a human confirms — see identidade_extracao_service.';
COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_rg_orgao IS
    'Issuing body read alongside the RG number. Travels with it: an RG number '
    'promoted without its issuer produces an incomplete qualification.';

-- Pending-suggestion lookup, mirroring the nome index from 071.
CREATE INDEX IF NOT EXISTS idx_sw_cliente_documentos_sugestao_doc_pendente
    ON social_wiring.cliente_documentos (cliente_id, extracao_em DESC)
    WHERE deleted_at IS NULL
      AND extracao_descartada_em IS NULL
      AND (extracao_cpf IS NOT NULL OR extracao_rg IS NOT NULL);
