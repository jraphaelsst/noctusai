-- ============================================================================
-- 091_haiku_5_5_model.sql — widen the three model allowlists with
-- claude-haiku-5-5 (the seed catalog prices it; owner wants Julia on it).
--
-- Same pattern as 015: DROP CONSTRAINT IF EXISTS + ADD CONSTRAINT, idempotent,
-- under the names Postgres/earlier migrations already gave them. Changes no
-- default and no existing row. The `agent_versions` CHECK keeps 024's
-- provider-keyed shape (anthropic models | openai models).
-- Python mirrors: app/studio/models.py ANTHROPIC_MODELS / EVAL_RUN_MODEL_ALLOWLIST.
--
-- NOT applied to any database by this slice — the tech-lead applies it once.
-- ============================================================================

SET search_path = agents, public;

ALTER TABLE agents.agent_personas
    DROP CONSTRAINT IF EXISTS agent_personas_model_check;
ALTER TABLE agents.agent_personas
    ADD CONSTRAINT agent_personas_model_check
        CHECK (model IN ('claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5', 'claude-haiku-5-5'));

ALTER TABLE agents.agent_versions
    DROP CONSTRAINT IF EXISTS agent_versions_model_check;
ALTER TABLE agents.agent_versions
    ADD CONSTRAINT agent_versions_model_check
        CHECK (
            (provider = 'anthropic'
                AND model IN ('claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5', 'claude-haiku-5-5'))
            OR (provider = 'openai'
                AND model IN ('gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna'))
        );

ALTER TABLE agents.eval_runs
    DROP CONSTRAINT IF EXISTS eval_runs_modelo_geracao_check;
ALTER TABLE agents.eval_runs
    ADD CONSTRAINT eval_runs_modelo_geracao_check
        CHECK (modelo_geracao IS NULL
               OR modelo_geracao IN ('claude-sonnet-5', 'claude-haiku-4-5', 'claude-haiku-5-5'));
