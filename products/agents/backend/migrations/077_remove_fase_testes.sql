-- ============================================================================
-- 077_remove_fase_testes.sql -- the "fase de testes" switch is retired (owner decision 2026-11-10): the agent no
-- longer tells a lead the service is in a testing phase, and nothing reads or writes the flag any more.
--
--   1. agents.set_agent_fase_testes(UUID, UUID, BOOLEAN, UUID) -- the audited writer 056 created.
--   2. agents.agents.fase_testes -- the per-org-instance flag 056 added.
--
-- Deploy order (expand/contract): ship the image that no longer selects `fase_testes` or calls the writer FIRST,
-- then apply this migration. An old image still selecting the column would 500 on the controle read once it is gone.
--
-- The audit CHECK keeps 'fase_testes_alterada' on purpose: rows written while the switch existed must stay valid.
-- Forward-only and idempotent: a second run finds nothing left. Applied migration 056 is untouched.
-- ============================================================================

SET search_path = agents, public;

DROP FUNCTION IF EXISTS agents.set_agent_fase_testes(UUID, UUID, BOOLEAN, UUID);

ALTER TABLE agents.agents DROP COLUMN IF EXISTS fase_testes;
