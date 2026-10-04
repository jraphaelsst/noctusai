-- ============================================================================
-- Migration 200 -- social_wiring: automatic resolution for the FOURTH
-- `*_campo_conflitos` table (`atendimento_campo_conflitos`, migration 171)
--
-- WHAT THIS IS
-- ------------
-- Migration 175 gave the cliente/imovel/empresa conflict tables a
-- `'resolvido_automatico'` status and a `motivo_resolucao` audit column, so
-- a divergence the SYSTEM settles is recorded auditably (rule + evidence,
-- `decidido_por` NULL) instead of being shown to a human as `pendente`.
-- `atendimento_campo_conflitos` (171, the deal-side surface: valor
-- negociado, the financiamento parcela, the financing record's fields) was
-- left out — it had no automatic writer at the time.
--
-- It has one now. P5 audit F1 (owner rule H1, 2026-10-03: "the first
-- document fills empty fields"): an unverified financing/ITBI document used
-- to open a PENDING conflict against an EMPTY field (`valor_anterior` NULL)
-- — a "divergence" with nothing, which blocked contract generation until a
-- human accepted the very value the document carried. The live apply now
-- fills; `negociacao_extracao_service.resolver_conflitos_vazios` repairs the
-- rows already open by applying the proposal and closing the row
-- `resolvido_automatico`, `motivo_resolucao = '[vazio_preenchido] ...
-- evidência: <documento>'` — the same audit contract migration 175 set for
-- the other three tables (`campo_conflitos.registrar_decisao_automatica`).
--
-- Plain literal ALTERs (not a dynamic loop) for the same reason 175 gives:
-- `noctusai_lib.testing.migration_parser` must see the column.
--
-- FORWARD-ONLY, IDEMPOTENT (CHECK drop+recreate is re-runnable; ADD COLUMN
-- IF NOT EXISTS). Postgres names 171's inline unnamed CHECK
-- `atendimento_campo_conflitos_status_check`.
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.atendimento_campo_conflitos
    DROP CONSTRAINT IF EXISTS atendimento_campo_conflitos_status_check;
ALTER TABLE social_wiring.atendimento_campo_conflitos
    ADD CONSTRAINT atendimento_campo_conflitos_status_check
    CHECK (status IN ('pendente', 'aceito', 'rejeitado', 'resolvido_automatico'));
ALTER TABLE social_wiring.atendimento_campo_conflitos
    ADD COLUMN IF NOT EXISTS motivo_resolucao TEXT;
COMMENT ON COLUMN social_wiring.atendimento_campo_conflitos.motivo_resolucao IS
    'Populated only when status=''resolvido_automatico'' -- the rule and the '
    'evidence (document ids) that decided it. Migration 200 (mirrors 175).';
