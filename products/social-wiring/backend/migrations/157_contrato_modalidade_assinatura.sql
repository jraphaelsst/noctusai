-- ============================================================================
-- Migration 157 -- social_wiring: how a contract gets signed -- digital OR
--                  física (printed, signed by hand)
--
-- WHAT THIS IS
-- ------------
-- Owner request, 2026-09-22: "the contract has no lines for manual signing."
-- Until now every contract was assumed to be signed through the e-signature
-- platform (migration 134): the generated instrument always carried the
-- "DA ASSINATURA DIGITAL" clause, closed with "assinam ... de forma digital"
-- and printed the signers' names with no line to sign on.
--
-- `modalidade_assinatura` is the GATE, per contract:
--   'digital' -> the existing e-signature envelope flow (`assinatura_service.
--                enviar`), exactly as before;
--   'fisica'  -> no e-mail, no envelope. The generated instrument drops the
--                digital-signature clause (clause numbering re-flows), closes
--                "em NN (extenso) vias ... na presença das testemunhas" and
--                prints a signature line above every signer and witness; a
--                human prints it, collects signatures, and closes the
--                contract out via `POST .../assinatura-fisica` (status
--                'assinado', stamped status_por/status_em, optional upload of
--                the scanned signed PDF as an `origem='assinado'` version).
--
-- DEFAULT 'digital' keeps every existing contract on its current behaviour --
-- no backfill, no row changes meaning.
--
-- `atendimento_contrato_versoes.modalidade_assinatura` records WHICH
-- modalidade a GENERATED version was rendered with, so "Baixar para
-- impressão" only ever offers a PDF that actually carries the signature
-- lines -- a version generated while the contract was still 'digital' is
-- never silently handed out as the print copy. NULL for upload/assinado
-- versions (they were never rendered by the generator) and for gerado rows
-- that predate this migration (rendered digital; the column simply did not
-- exist yet -- the FE treats NULL as "not a print copy").
--
-- The 409 rules (code, not this migration):
--   - `enviar` on a 'fisica' contract -> 409 CONTRATO_FISICO_SEM_ASSINATURA_DIGITAL;
--   - switching a contract to 'fisica' while an envelope is live
--     (pendente/parcial) -> 409 CONTRATO_COM_ASSINATURA_DIGITAL_EM_ANDAMENTO.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- The CHECK rides inline on the ADD COLUMN: `IF NOT EXISTS` skips the whole
-- column definition (constraint included) on a re-run, so the step stays
-- idempotent without a pg_constraint probe.
ALTER TABLE social_wiring.atendimento_contratos
    ADD COLUMN IF NOT EXISTS modalidade_assinatura TEXT NOT NULL DEFAULT 'digital'
        CHECK (modalidade_assinatura IN ('digital', 'fisica'));

COMMENT ON COLUMN social_wiring.atendimento_contratos.modalidade_assinatura IS
    'digital | fisica. digital = e-signature envelope (migration 134); '
    'fisica = printed and signed by hand -- no envelope may be sent, the '
    'generated instrument carries signature lines instead of the digital '
    'clause. Default digital keeps every pre-157 contract unchanged.';

ALTER TABLE social_wiring.atendimento_contrato_versoes
    ADD COLUMN IF NOT EXISTS modalidade_assinatura TEXT
        CHECK (modalidade_assinatura IS NULL
               OR modalidade_assinatura IN ('digital', 'fisica'));

COMMENT ON COLUMN social_wiring.atendimento_contrato_versoes.modalidade_assinatura IS
    'For origem=gerado: the contract modalidade this version was rendered '
    'with (digital | fisica). NULL for upload/assinado versions and for '
    'gerado rows that predate migration 157.';

NOTIFY pgrst, 'reload schema';
