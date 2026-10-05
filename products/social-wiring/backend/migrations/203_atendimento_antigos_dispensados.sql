-- ============================================================================
-- Migration 203 · social_wiring: per-deal dispensation of the previous
-- owners' certidões (antigos proprietários)
--
-- Owner decision 2026-10-05 (backed by the 33-contract signed-corpus study):
-- previous owners stay REQUIRED when the imóvel's last transfer is < 5 years
-- old, but an operator may DISPENSE them for ONE deal ("antigos proprietários
-- não exigidos neste negócio"), with a reason and who/when — admin-gated like
-- `processo_legado` (migration 151). Readiness then turns the missing
-- previous-owner group from a `falta` into an `aviso`; never a silent skip.
--
-- Stored on `atendimentos` (the DEAL), not on a contract: the Certidões tab
-- group header where it is toggled belongs to the card, and every contract of
-- the deal answers the same previous-owner question.
--
-- `antigos_dispensados_em IS NOT NULL` IS the flag (one source of truth — no
-- redundant boolean to drift from the stamps). No CHECK/UNIQUE/trigger: the
-- motivo rule (3..500 chars) is enforced by the service + request model, same
-- posture as 151.
--
-- FORWARD-ONLY, IDEMPOTENT. 🔴 MIGRATION FILE ONLY — applying is the
-- tech-lead's + user's decision. See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.atendimentos
    ADD COLUMN IF NOT EXISTS antigos_dispensados_em     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS antigos_dispensados_por    UUID,
    ADD COLUMN IF NOT EXISTS antigos_dispensados_motivo TEXT;

COMMENT ON COLUMN social_wiring.atendimentos.antigos_dispensados_em IS
    'When an admin dispensed the previous owners'' certidões for this deal '
    '(owner decision 2026-10-05). NULL = not dispensed (the default: required '
    'when the last transfer is < 5 years old). Set only by PUT '
    '.../antigos-proprietarios/dispensa; cleared by DELETE.';
COMMENT ON COLUMN social_wiring.atendimentos.antigos_dispensados_por IS
    'Who dispensed (noctus user id), stamped with antigos_dispensados_em.';
COMMENT ON COLUMN social_wiring.atendimentos.antigos_dispensados_motivo IS
    'Operator''s reason (3..500 chars) — required whenever dispensed.';

-- Where a previous-owner party row came from: 'matricula' (auto-created from
-- the last transfer's sellers on the confirmed matrícula) or 'manual' (an
-- operator added it because the matrícula does not name them). NULL for every
-- other party. Plain TEXT validated by the service (no CHECK — the vocabulary
-- is two words and a migration cycle is slower than the business).
ALTER TABLE social_wiring.atendimento_partes
    ADD COLUMN IF NOT EXISTS origem TEXT;

COMMENT ON COLUMN social_wiring.atendimento_partes.origem IS
    'Provenance of an antigo_proprietario party: matricula | manual. NULL '
    'for parties that are not previous owners.';
