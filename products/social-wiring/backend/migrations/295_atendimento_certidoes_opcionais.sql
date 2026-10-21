-- ============================================================================
-- Migration 295 · social_wiring: per-deal opt-in for the OPTIONAL certidões
--
-- Owner decision 2026-10-21: the certidões of the PREVIOUS OWNERS (last
-- onerous transfer under 5 years) and the company FGTS regularity certificate
-- (matriz row 5.13, "Regularidade do FGTS (empresas)") "are not required by
-- default, it depends on the case". The default flips from required to
-- optional: readiness names an `aviso` instead of a `falta`, and the grid
-- shows the cells as "Opcional". A deal opts IN with these two switches (the
-- Certidões tab header); ON restores the previous required behaviour.
--
-- Stored on `atendimentos` (the DEAL), next to `antigos_dispensados_*`
-- (migration 203): every contract of the deal answers the same question.
-- Plain booleans, NOT NULL DEFAULT false — existing deals become "optional".
--
-- FORWARD-ONLY, IDEMPOTENT. 🔴 MIGRATION FILE ONLY — applying is the
-- tech-lead's + user's decision. See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.atendimentos
    ADD COLUMN IF NOT EXISTS exigir_certidoes_antigos BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS exigir_crf_fgts          BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN social_wiring.atendimentos.exigir_certidoes_antigos IS
    'Owner decision 2026-10-21: require the previous owners'' certidões for this '
    'deal (last transfer < 5 years). false (default) = optional: readiness warns, '
    'the contract omits them, no automatic emission.';
COMMENT ON COLUMN social_wiring.atendimentos.exigir_crf_fgts IS
    'Owner decision 2026-10-21: require the company FGTS regularity certificate '
    '(CRF) for this deal. false (default) = optional: the grid shows "Opcional"; '
    'a CRF already on file is still printed.';
