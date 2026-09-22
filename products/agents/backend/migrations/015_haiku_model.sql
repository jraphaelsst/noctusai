-- ============================================================================
-- 015_haiku_model.sql — add claude-haiku-4-5 to the two model allowlists
-- (contract §E.1 `agent_personas.model`, §A10/§B1 `agent_versions.model`).
--
-- WHY: `claude-haiku-4-5` is the id the eval draft-model path already uses
-- (`agents.eval_runs.modelo_geracao`, migration 014's
-- `eval_runs_modelo_geracao_check`) and it was proven live against prod
-- today — but Julia's persona and Agent Studio's own version model were
-- never widened to OFFER it as a choice, so the UI could only ever propose
-- a value ('claude-haiku-4-5') the DB would reject for either table. This
-- migration ADDS the option; it changes no default and no existing row —
-- `agent_versions`' `DRAFT_DEFAULTS.model` stays `claude-opus-5`
-- (`app/stores/studio_definitions.py`).
--
-- 006/012 left both CHECKs UNNAMED (inline column-level `CHECK (...)`
-- inside `CREATE TABLE`), so Postgres auto-named them via its own
-- `<table>_<column>_check` convention: `agent_personas_model_check` and
-- `agent_versions_model_check`. This migration gives them those SAME names
-- explicitly (never renaming what is already live) so both are DROPped
-- and re-ADDed idempotently, matching 014's documented convention
-- (`DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT`, matching 009's
-- IDEMPOTENCY note) rather than editing 006/012 in place — those files are
-- already applied in prod and their migration-ledger hashes are recorded.
--
-- NOT applied to any database by this slice — the tech-lead applies it
-- once, with user consent (shared prod DB).
-- ============================================================================

SET search_path = agents, public;

-- ────────────────────────────────────────────────────────────────────────
-- agent_personas.model (006, contract §E.1) — Julia's persona.
-- ────────────────────────────────────────────────────────────────────────

ALTER TABLE agents.agent_personas
    DROP CONSTRAINT IF EXISTS agent_personas_model_check;

ALTER TABLE agents.agent_personas
    ADD CONSTRAINT agent_personas_model_check
        CHECK (model IN ('claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'));


-- ────────────────────────────────────────────────────────────────────────
-- agent_versions.model (012, contract §A10/§B1) — Agent Studio versions.
-- ────────────────────────────────────────────────────────────────────────

ALTER TABLE agents.agent_versions
    DROP CONSTRAINT IF EXISTS agent_versions_model_check;

ALTER TABLE agents.agent_versions
    ADD CONSTRAINT agent_versions_model_check
        CHECK (model IN ('claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'));
