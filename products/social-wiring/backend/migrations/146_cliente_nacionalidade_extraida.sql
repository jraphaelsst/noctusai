-- ============================================================================
-- Migration 146 -- social_wiring: nacionalidade provenance + extraction
--
-- WHAT THIS IS
-- ------------
-- Resolves `NOC-REMEDIATE[nacionalidade-identity-parser]`
-- (`noctusai_lib.integrations.documents.types`, 2026-09-21): the contract
-- generator's readiness gate (`documento_checklist_service.
-- _CAMPOS_QUALIFICACAO_CONTRATO`, migration 097) has hard-required
-- `nacionalidade` for every party since 097, but nothing ever read it off a
-- document -- a new-model CNH prints it ("NACIONALIDADE\nBRASILEIRO") and a
-- certidão de casamento/nascimento states it for every person named on it
-- ("de nacionalidade brasileira"), and both went unread.
--
-- `clientes.nacionalidade` itself already exists (097) as a plain,
-- operator-fillable TEXT column. This is the SAME shape 073 gave `genero`
-- when a pre-existing plain column became ALSO derivable from a document:
-- the provenance quintet, plus the document-side extraction triple, plus
-- the pending-suggestion index widened to notice it. No new table.
--
-- 🔴 `sobrescreve=False` -- A REGISTRATION FIELD, NOT A DOCUMENT-OWNED ONE
-- --------------------------------------------------------------------------
-- Same posture `genero` / `estado_civil` / `data_casamento` all take, for
-- the same reason: there is no second column holding an operator's own
-- spelling the way `nome_completo` holds one beside `nome_oficial`, so a
-- typed value must outrank every later document reading rather than being
-- silently overwritten by it -- see `identidade_extracao_service.CAMPOS`.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. clientes -- the provenance quintet beside the pre-existing bare column.
--    ORDER MATTERS the same way 117's header warns: these columns land
--    BEFORE the index rebuild in section 3, whose predicate names
--    `extracao_nacionalidade` (a column added in section 2, not this one --
--    but the same discipline applies: columns before the index that names
--    them, never after).
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS nacionalidade_origem          TEXT,
    ADD COLUMN IF NOT EXISTS nacionalidade_documento_id    UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS nacionalidade_em              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS nacionalidade_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS nacionalidade_confirmado_em   TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.clientes.nacionalidade IS
    'Nationality (gentílico), e.g. "brasileiro". Operator-entered as free '
    'text since 097, or read off an identity document / certidão when the '
    'extractor is confident (noctusai_lib.integrations.documents.'
    'nacionalidade.find_nacionalidade) -- always the CANONICAL MASCULINE '
    'spelling when machine-read; the contract generator (frases.'
    'nacionalidade_flex) re-genders it for display. Deliberately '
    'unconstrained TEXT, like estado_civil/regime_bens -- the taxonomy '
    'lives in the extractor, not in a database CHECK.';
COMMENT ON COLUMN social_wiring.clientes.nacionalidade_origem IS
    '''manual'' | ''rg'' | ''cpf'' | ''cnh'' | ''certidao_casamento'' | '
    '''certidao_nascimento'' -- where the CURRENT nacionalidade value came '
    'from. NULL alongside a non-null nacionalidade means it predates 145.';
COMMENT ON COLUMN social_wiring.clientes.nacionalidade_confirmado_por IS
    'Set when a human accepted a LOW-confidence read. NULL alongside a set '
    'nacionalidade means the extractor wrote it unattended at high '
    'confidence, or an operator typed it directly (origem=''manual'').';

-- ----------------------------------------------------------------------------
-- 2. cliente_documentos -- what THIS document read, how sure, off which label.
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_nacionalidade            TEXT,
    ADD COLUMN IF NOT EXISTS extracao_nacionalidade_confianca  TEXT,
    ADD COLUMN IF NOT EXISTS extracao_nacionalidade_rotulo     TEXT;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_nacionalidade IS
    'Nationality as read off THIS document -- the canonical masculine '
    'gentílico regardless of which grammatical gender the document '
    'printed (see nacionalidade.find_nacionalidade''s module docstring). '
    'Held on the document row so a low-confidence read has somewhere to '
    'sit without touching the client record -- a suggestion is not a fact.';

-- ----------------------------------------------------------------------------
-- 3. Pending-suggestion lookup, widened to also catch nacionalidade reads --
--    same predicate 110/117 built for estado_civil/regime_bens/
--    data_casamento, same index. Rebuilt HERE, after both ALTERs above,
--    same "columns before the index that names them" discipline 117's
--    header states.
-- ----------------------------------------------------------------------------
DROP INDEX IF EXISTS social_wiring.idx_sw_cliente_documentos_sugestao_doc_pendente;
CREATE INDEX IF NOT EXISTS idx_sw_cliente_documentos_sugestao_doc_pendente
    ON social_wiring.cliente_documentos (cliente_id, extracao_em DESC)
    WHERE deleted_at IS NULL
      AND extracao_descartada_em IS NULL
      AND (
          extracao_cpf IS NOT NULL
          OR extracao_rg IS NOT NULL
          OR extracao_estado_civil IS NOT NULL
          OR extracao_regime_bens IS NOT NULL
          OR extracao_data_casamento IS NOT NULL
          OR extracao_nacionalidade IS NOT NULL
      );
