-- ============================================================================
-- Migration 153 -- social_wiring: identity extraction feeds the contract (D1)
--
-- Roadmap: project-history/roadmaps/sw-extraction-contract-gate-2026-09.md
-- (owner decisions D1/D3, 2026-09-22; this is the `identity` slice).
--
-- D1 WRITE POLICY. Extraction writes a parsed value (any confidence) straight
-- into an EMPTY contract column, with provenance, and never overwrites: a
-- value already there -- typed by a human or written by an earlier extraction
-- -- opens a `cliente_campo_conflitos` row and notifies an admin. A value is
-- "machine-pending" (the validation gate's question) iff
-- `<campo>_origem IS NOT NULL AND <campo>_origem <> 'manual' AND
-- <campo>_confirmado_em IS NULL`. Every contract-feeding `clientes` field
-- therefore needs the provenance quintet; this migration adds the ones that
-- were still missing:
--
--   * rg_orgao_expedidor  -- used to RIDE WITH `rg` under the RG's decision,
--                            with no provenance of its own. The contract gate
--                            needs to know whether a human has seen it.
--   * endereco_*          -- ONE quintet for the seven parts: an address is
--                            written, confirmed and rejected as a group (a
--                            CEP from one bill with a street from another is
--                            an address nobody lives at).
--   * conjuge_cliente_id  -- the spouse link a certidão de casamento now sets.
--   * certidao_estado_civil_emitida_em -- had `_origem`/`_em` (148); gains
--                            `_confirmado_por/_em` so the gate can accept it.
--
-- Plus the per-DOCUMENT readings the new parsers produce (profissão, the
-- comprovante's address + its printed holder, the RG issuer's confidence, and
-- both spouses of a certidão), held on `cliente_documentos` exactly like
-- every earlier `extracao_*` triple: the reading survives on its document
-- whatever happens to the client record.
--
-- And a data fix: `clientes.genero` holds the words 'Masculino'/'Feminino'
-- (the card dropdown, the identity extractor). Matrícula qualificação
-- confirmations (137) wrote the codes 'm'/'f' verbatim, which then read as a
-- disagreement with every later RG/CIN reading of the same fact.
--
-- Additive + idempotent (IF NOT EXISTS; the UPDATE is a no-op on re-run).
-- ============================================================================


-- ============================================================
-- Schema lock — pin name resolution to social_wiring, public
-- WHY:
--   * RLS isolation: every product's tables live in its own
--     schema; un-locked search_path leaks resolution to
--     whatever the caller's session set.
--   * Cross-product safety: prevents accidental shadowing
--     when two products define identically-named helpers
--     (e.g. `current_org_id()`) in different schemas.
-- IDEMPOTENT: session-level setting; no DDL emitted.
-- ============================================================
SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. clientes -- the provenance quintets D1 needs
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS rg_orgao_expedidor_origem          TEXT,
    ADD COLUMN IF NOT EXISTS rg_orgao_expedidor_documento_id    UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS rg_orgao_expedidor_em              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rg_orgao_expedidor_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS rg_orgao_expedidor_confirmado_em   TIMESTAMPTZ,

    ADD COLUMN IF NOT EXISTS endereco_origem                    TEXT,
    ADD COLUMN IF NOT EXISTS endereco_documento_id              UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS endereco_em                        TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS endereco_confirmado_por            UUID,
    ADD COLUMN IF NOT EXISTS endereco_confirmado_em             TIMESTAMPTZ,

    ADD COLUMN IF NOT EXISTS conjuge_origem                     TEXT,
    ADD COLUMN IF NOT EXISTS conjuge_documento_id               UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS conjuge_em                         TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS conjuge_confirmado_por             UUID,
    ADD COLUMN IF NOT EXISTS conjuge_confirmado_em              TIMESTAMPTZ,

    ADD COLUMN IF NOT EXISTS certidao_estado_civil_emitida_em_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS certidao_estado_civil_emitida_em_confirmado_em  TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.clientes.rg_orgao_expedidor_origem IS
    '''manual'' | a tipo_documento (''rg'', ''cnh'', ...) | ''matricula'' -- '
    'where the CURRENT rg_orgao_expedidor came from (migration 153). Written '
    'by extraction only when the RG on file is the one the issuer was read '
    'beside.';
COMMENT ON COLUMN social_wiring.clientes.endereco_origem IS
    'Provenance of the WHOLE endereco_* group (153): ''manual'' | '
    '''comprovante_endereco'' | ... The seven parts are filled, confirmed and '
    'rejected together, never one at a time.';
COMMENT ON COLUMN social_wiring.clientes.conjuge_origem IS
    'Provenance of conjuge_cliente_id (153): ''manual'' | '
    '''certidao_casamento'' (both spouses identified on one certidão, linked '
    'reciprocally).';

-- ----------------------------------------------------------------------------
-- 2. cliente_documentos -- the new per-document readings
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_rg_orgao_confianca    TEXT,
    ADD COLUMN IF NOT EXISTS extracao_rg_orgao_rotulo       TEXT,

    ADD COLUMN IF NOT EXISTS extracao_profissao             TEXT,
    ADD COLUMN IF NOT EXISTS extracao_profissao_confianca   TEXT,
    ADD COLUMN IF NOT EXISTS extracao_profissao_rotulo      TEXT,

    ADD COLUMN IF NOT EXISTS extracao_endereco_cep          TEXT,
    ADD COLUMN IF NOT EXISTS extracao_endereco_logradouro   TEXT,
    ADD COLUMN IF NOT EXISTS extracao_endereco_numero       TEXT,
    ADD COLUMN IF NOT EXISTS extracao_endereco_complemento  TEXT,
    ADD COLUMN IF NOT EXISTS extracao_endereco_bairro       TEXT,
    ADD COLUMN IF NOT EXISTS extracao_endereco_cidade       TEXT,
    ADD COLUMN IF NOT EXISTS extracao_endereco_uf           TEXT,
    ADD COLUMN IF NOT EXISTS extracao_endereco_titular      TEXT,
    ADD COLUMN IF NOT EXISTS extracao_endereco_confianca    TEXT,
    ADD COLUMN IF NOT EXISTS extracao_endereco_rotulo       TEXT,

    ADD COLUMN IF NOT EXISTS extracao_conjuges              JSONB;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_endereco_titular IS
    'The holder name the comprovante PRINTS. Checked against the cliente before '
    'the address is filled: a bill in a relative''s name opens a conflict '
    'instead of silently becoming this person''s address.';
COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_conjuges IS
    'Both spouses read off a certidão de casamento: [{nome, cpf, '
    'data_nascimento, nacionalidade, profissao, genero, titular, cliente_id}]. '
    'cliente_id is the record each spouse was applied to, NULL when no '
    'existing cliente matched -- recorded, never invented.';

-- ----------------------------------------------------------------------------
-- 3. Backfill -- an issuer written before 153 rode with its RG
-- ----------------------------------------------------------------------------
-- Until this migration `rg_orgao_expedidor` was written together with `rg`,
-- under the RG's decision, so the RG's provenance IS the issuer's. Copying it
-- keeps a human-typed issuer 'manual' and a document-read one attributable,
-- instead of leaving every existing issuer looking like it came from nowhere.
UPDATE social_wiring.clientes
   SET rg_orgao_expedidor_origem       = rg_origem,
       rg_orgao_expedidor_documento_id = rg_documento_id,
       rg_orgao_expedidor_em           = rg_em,
       rg_orgao_expedidor_confirmado_por = rg_confirmado_por,
       rg_orgao_expedidor_confirmado_em  = rg_confirmado_em
 WHERE rg_orgao_expedidor IS NOT NULL
   AND rg_orgao_expedidor_origem IS NULL
   AND rg_origem IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 4. Data fix -- genero codes written by matrícula confirmations
-- ----------------------------------------------------------------------------
UPDATE social_wiring.clientes
   SET genero = CASE lower(genero) WHEN 'm' THEN 'Masculino' ELSE 'Feminino' END
 WHERE lower(genero) IN ('m', 'f');
