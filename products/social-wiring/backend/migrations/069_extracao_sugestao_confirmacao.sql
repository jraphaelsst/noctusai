-- ============================================================================
-- Migration 069 · social_wiring: confirming (or discarding) a low-confidence
-- birthdate read.
--
-- WHY THIS EXISTS
-- ---------------
-- Migration 068 shipped the rule that only a HIGH-confidence, label-anchored
-- read is written to a client record unattended. A low-confidence read — a
-- photographed RG where the vision pass produced a plausible date it cannot
-- vouch for — is kept on the document row instead
-- (`extracao_data_nascimento` + `extracao_confianca`), deliberately never
-- reaching `clientes`.
--
-- That was the right place to stop, and it left the value stranded: correct,
-- possibly useful, and invisible. This migration adds the two things that turn
-- a stranded read into a decision a human can actually make.
--
-- 1. A WAY TO SAY NO. Without a discard, a suggestion the operator has already
--    judged wrong reappears on every visit to the card, forever. A prompt that
--    cannot be dismissed stops being read — and the one that finally matters
--    gets dismissed by reflex along with the noise.
--
-- 2. A RECORD OF WHO SAID YES. Confirming an OCR-derived birthdate is a person
--    taking responsibility for a machine's reading. `data_nascimento_origem`
--    already says WHERE a value came from (which document type); it cannot
--    also say who vouched for it. Those are different questions and a single
--    column answering both would answer neither: 'rg' would be ambiguous
--    between "high-confidence, applied automatically" and "low-confidence, a
--    human checked it", which are exactly the two cases an auditor needs to
--    tell apart.
--
-- 🔴 STILL NOT DONE HERE: `cliente_documento_tipos` continues to seed 'rg' and
-- 'cpf' with `ativo = false` (migration 057). No identity document can be
-- uploaded, so nothing in this file is reachable in production. Enabling those
-- types remains a data change a human makes after the LGPD intake resolves —
-- see LGPD-WARNINGS.md, whose scope 068 widened to cover birthdate derivation.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the row
-- counts this will touch and the user has given an explicit go-ahead.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. cliente_documentos — a suggestion can be turned down
-- ----------------------------------------------------------------------------
-- Discarded, not deleted: the extraction result stays on the row. Clearing
-- `extracao_data_nascimento` on discard would destroy the evidence of what the
-- extractor actually read, which is the only way to later tell a bad OCR pass
-- from a bad decision about a good one.
ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_descartada_em  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS extracao_descartada_por UUID;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_descartada_em IS
    'Set when a human turned down this document''s extracted suggestion. The '
    'extracted value itself is KEPT — discarding records a judgement about the '
    'read, it does not erase what was read.';

-- The card''s suggestion lookup: every identity document holding a value that
-- is still awaiting a human decision.
CREATE INDEX IF NOT EXISTS idx_sw_cliente_documentos_sugestao_pendente
    ON social_wiring.cliente_documentos (cliente_id, extracao_em DESC)
    WHERE deleted_at IS NULL
      AND extracao_descartada_em IS NULL
      AND extracao_data_nascimento IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 2. clientes — who vouched for a machine-read birthdate
-- ----------------------------------------------------------------------------
-- Only ever set for a value a human CONFIRMED off a document. A high-confidence
-- read applied automatically leaves it NULL, and so does a hand-typed value
-- (that one is already identified by `data_nascimento_origem = 'manual'`).
-- Three distinguishable states, which is the point:
--
--   origem='rg',     confirmado_por IS NULL      → machine read, high confidence
--   origem='rg',     confirmado_por = <user>     → machine read, human vouched
--   origem='manual', confirmado_por IS NULL      → typed by a person
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS data_nascimento_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS data_nascimento_confirmado_em  TIMESTAMPTZ;
