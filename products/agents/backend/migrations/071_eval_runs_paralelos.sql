-- 071_eval_runs_paralelos.sql — several eval runs of the SAME version may execute at once.
--
-- 013 (`eval_runs_one_active_per_version_idx`) and 038 (`uq_eval_mecanismo_runs_um_em_execucao`)
-- allowed one in-flight run per version, so a second "Rodar avaliação completa" / "Rodar suíte de
-- mecanismo" was refused with `run_in_progress`. The owner runs the suites repeatedly to read
-- variance (an LLM agent passes or fails a case by chance), and batch evals will fan runs out in
-- parallel: queueing them only costs wall-clock. Every run is self-contained — its own results /
-- execucoes rows, its own `limite_usd` cap, its own status transitions keyed by run id — so no
-- state is shared between two runs of one version.
--
-- Spend stays bounded per run (`limite_usd`); the startup sweeps still fail orphaned runs by
-- `started_at`, regardless of how many share a version. Forward-only + idempotent.

SET search_path = agents, public;

DROP INDEX IF EXISTS agents.eval_runs_one_active_per_version_idx;
DROP INDEX IF EXISTS agents.uq_eval_mecanismo_runs_um_em_execucao;

-- Prontidão and the screens read "runs of this version"; keep that lookup indexed for both suites.
CREATE INDEX IF NOT EXISTS idx_agents_eval_runs_version_status
    ON agents.eval_runs (version_id, status);
CREATE INDEX IF NOT EXISTS idx_agents_eval_mecanismo_runs_version_status
    ON agents.eval_mecanismo_runs (version_id, status);
