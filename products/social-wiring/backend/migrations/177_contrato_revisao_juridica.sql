-- ============================================================================
-- 177 — one final legal review per generated contract version (replaces the
--       per-field extraction validation of migration 156 as the default)
-- ============================================================================
--
-- WHY
-- ---
-- Owner decision (2026-09-30, verbatim): asked "replace the per-field
-- confirmations with one final review of the finished contract by the legal
-- team?" → "yes". Standing directive: "Human reviews are meant to be the
-- exception, not the rule. The system must work by itself and humans
-- intervene only when the system actually can't resolve."
--
-- Until now (D2, migration 156) `contrato_gerador.service.gerar` refused with
-- 409 EXTRACAO_PENDENTE_VALIDACAO while ANY machine-extracted value the
-- contract prints lacked a per-field human accept/reject. With
-- `Politica.revisao_final_unica = True` it generates anyway, and the VERSION
-- remembers which values were machine-derived and not yet human-validated.
-- One contract-level "Aprovar revisão jurídica" then:
--   1. confirms each of those values on its own row (`<campo>_confirmado_por/
--      _em`, same write the per-field accept makes) and logs one
--      `extracao_validacoes` row per value, tagged with THIS version — so the
--      provenance stays truthful ("confirmed by X, via the legal review of
--      version N"), and
--   2. stamps `revisado_por/_em` on the version.
-- Sending the version for signature (`assinatura_service.enviar`), "Baixar
-- para impressão" and marking a física contract signed require that stamp
-- whenever the list is non-empty.
--
-- WHY ON THE VERSION (not the contract)
-- -------------------------------------
-- The signature flow sends ONE version (`atendimento_contrato_assinaturas.
-- versao_id`), and the reviewer reads one PDF. A later regeneration is a NEW
-- rendering the reviewer has not seen — review state that lived on the
-- contract would silently carry an approval over to bytes nobody read.
--
-- COLUMNS (atendimento_contrato_versoes)
-- --------------------------------------
-- `revisao_juridica_campos` JSONB NOT NULL DEFAULT '[]' — the machine-derived,
--     not-yet-validated values this rendering relied on: one object per value
--     `{chave, entidade, entidade_id, campo, rotulo, grupo, origem,
--       fonte_documento_id, fonte_nome, confianca, valor_sha256}`.
--     `valor_sha256` (never the value itself — the PDF already carries it; no
--     second copy of a CPF in a JSON blob) lets the approval refuse when the
--     value changed after this rendering. '[]' = nothing to review: every
--     upload/assinado version, every pre-177 gerado version (it passed the
--     per-field gate), and every version generated in per-field mode.
-- `revisado_por` UUID / `revisado_em` TIMESTAMPTZ — who approved, when. Both
--     NULL or `revisado_em` set (a CHECK).
--
-- COLUMN (extracao_validacoes)
-- ----------------------------
-- `revisao_versao_id` UUID → atendimento_contrato_versoes(id) ON DELETE SET
--     NULL — set on the ledger rows the legal review wrote; NULL on a
--     per-field decision. Distinguishes "accepted on its own" from "vouched
--     for by the review of version N".
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — apply via `noctus.dev.migrate_product` after the
-- tech-lead's go-ahead; record it in `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.atendimento_contrato_versoes
    ADD COLUMN IF NOT EXISTS revisao_juridica_campos JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE social_wiring.atendimento_contrato_versoes
    ADD COLUMN IF NOT EXISTS revisado_por UUID;

ALTER TABLE social_wiring.atendimento_contrato_versoes
    ADD COLUMN IF NOT EXISTS revisado_em TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'atendimento_contrato_versoes_revisao_juridica_campos_array'
    ) THEN
        ALTER TABLE social_wiring.atendimento_contrato_versoes
            ADD CONSTRAINT atendimento_contrato_versoes_revisao_juridica_campos_array
            CHECK (jsonb_typeof(revisao_juridica_campos) = 'array');
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'atendimento_contrato_versoes_revisado_par'
    ) THEN
        ALTER TABLE social_wiring.atendimento_contrato_versoes
            ADD CONSTRAINT atendimento_contrato_versoes_revisado_par
            CHECK (revisado_por IS NULL OR revisado_em IS NOT NULL);
    END IF;
END $$;

COMMENT ON COLUMN social_wiring.atendimento_contrato_versoes.revisao_juridica_campos IS
    'Machine-derived, not-yet-human-validated contract values this generated '
    'rendering relied on (migration 177) — [{chave, entidade, entidade_id, '
    'campo, rotulo, grupo, origem, fonte_documento_id, fonte_nome, confianca, '
    'valor_sha256}]. Non-empty ⇒ the version awaits the legal review before '
    'signature/print. [] for uploads, signed copies and pre-177 versions.';
COMMENT ON COLUMN social_wiring.atendimento_contrato_versoes.revisado_por IS
    'Who approved the legal review of this version (migration 177).';
COMMENT ON COLUMN social_wiring.atendimento_contrato_versoes.revisado_em IS
    'When the legal review of this version was approved (migration 177).';

ALTER TABLE social_wiring.extracao_validacoes
    ADD COLUMN IF NOT EXISTS revisao_versao_id UUID
        REFERENCES social_wiring.atendimento_contrato_versoes(id) ON DELETE SET NULL;

COMMENT ON COLUMN social_wiring.extracao_validacoes.revisao_versao_id IS
    'Set when the decision was made by the contract-level legal review of this '
    'version (migration 177); NULL for a per-field decision (migration 156).';

NOTIFY pgrst, 'reload schema';
