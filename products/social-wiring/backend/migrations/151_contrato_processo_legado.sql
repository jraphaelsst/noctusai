-- ============================================================================
-- Migration 151 -- social_wiring: an explicit, admin-only, logged
--                  "processo anterior à plataforma" flag per contract
--
-- WHAT THIS IS
-- ------------
-- Owner directive, 2026-09-22: the contract gate's certidão TIME rules
-- (`CERTIDAO_EMISSAO_ANTIGA` / `CERTIDAO_VENCIDA` / `CERTIDAO_ESTADO_CIVIL_
-- ANTIGA`) "should be valid only for processes that are done via the
-- platform. So new sale processes come in correctly and 100% e2e. Those old
-- ones are okay to bypass the way they are now." Old = a deal that started
-- before the platform, whose certidões were legitimately issued outside it
-- (e.g. RODRIGO MORASCHI ENRIQUEZ's card: a federal CND 78 days old and a
-- 2022 certidão de estado civil) -- a real fact about how the deal began,
-- never a reason to relax the rule for a NEW deal.
--
-- 🔴 EXPLICIT, ADMIN-ONLY, LOGGED -- NEVER AN AUTOMATIC DATE HEURISTIC. A
-- contract row is flagged one at a time, by a human who read the deal and
-- decided it predates the platform (`PUT .../contratos/{id}/processo-
-- legado`, admin-only per `noctusai_lib.api.auth.session.is_org_admin` --
-- same trusted `noctus_users` row `router.decidir_conflito_route` reads,
-- never a spoofable JWT claim). There is no column here that infers this
-- from `created_at` or any other timestamp -- doing so would silently
-- misroute a genuinely NEW deal that happens to look old.
--
-- `_por` / `_em` mirror `atendimento_contratos.status_por` / `status_em`
-- (migration 106): the SAME "stamped only when it changes" provenance pair
-- this table already carries for its `status` column, extended to this
-- flag. `_motivo` is the admin's own account of why -- required by the
-- endpoint whenever `ativo=true` (3..500 chars, same shape every other
-- contract-mutation motivo in this schema already uses --
-- `remover_contrato` / `remover_versao` / `cancelar_assinatura`) -- and is
-- the audit entry itself: `_por` + `_em` + `_motivo` together are who,
-- when, and WHY, on the row the decision is about, the same place every
-- other admin decision in this schema (migration 138's `decidido_por` /
-- `decidido_em`) keeps its own.
--
-- WHAT CHANGES WHEN THIS IS TRUE (code, not this migration)
-- --------------------------------------------------------------------------
-- `contrato_gerador.derivacao._certidoes`: the three TIME rules above
-- become `av.avisa` (a warning) instead of `av.bloqueia` (a hard block).
-- `CERTIDAO_EMITIDA_APOS_ASSINATURA` is UNCHANGED -- always a block,
-- flagged or not -- because a certidão issued AFTER the signing date is a
-- data error, never a question of when the deal itself started.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.atendimento_contratos
    ADD COLUMN IF NOT EXISTS processo_legado         BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS processo_legado_por      UUID,
    ADD COLUMN IF NOT EXISTS processo_legado_em       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS processo_legado_motivo   TEXT;

COMMENT ON COLUMN social_wiring.atendimento_contratos.processo_legado IS
    'Explicit, admin-only flag (owner directive 2026-09-22): this deal '
    'started before the platform, so the contract gate''s certidão TIME '
    'rules (CERTIDAO_EMISSAO_ANTIGA / CERTIDAO_VENCIDA / '
    'CERTIDAO_ESTADO_CIVIL_ANTIGA) become warnings instead of blocks. '
    'NEVER inferred from a date -- set only by PUT .../processo-legado. '
    'CERTIDAO_EMITIDA_APOS_ASSINATURA stays a block regardless -- that is '
    'a data error, not an age rule.';
COMMENT ON COLUMN social_wiring.atendimento_contratos.processo_legado_por IS
    'Who set/cleared processo_legado -- stamped only when the flag '
    'CHANGES, same discipline as status_por/status_em (migration 106).';
COMMENT ON COLUMN social_wiring.atendimento_contratos.processo_legado_em IS
    'When processo_legado last changed. NULL while it has never been set.';
COMMENT ON COLUMN social_wiring.atendimento_contratos.processo_legado_motivo IS
    'The admin''s own account of why this deal predates the platform -- '
    'required (3..500 chars) whenever processo_legado is set to true; '
    'cleared when the flag is turned back off.';
