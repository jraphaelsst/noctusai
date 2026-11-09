-- 070 · DB-source agents + the dev-executor kind (Agent Packages CONTRACT A11, A12, §M — owner decisions 2026-11-08)
--
-- A DB-source agent is authored in Agents Studio: the DB is the source of truth and git holds only a GENERATED
-- mirror (`.claude/agents/<key>.md` + `agents/<key>/`), rendered from the published version at publish time and
-- stored in the existing 017 `agent_package_trees` (so `GET /api/agent-packages/{key}/{versao}` serves it unchanged).
--
--   * agents.fonte              'git' (a package built from products/agents/packages/<key>/, A1) | 'db' (A11).
--                               Immutable once set, like kind: flipping the source would orphan one of the two.
--   * agents.kind               adds 'dev-executor' (A12): a dev agent that MAY carry write tools on the Claude Code
--                               surface. 'dev-advisor' keeps A10 (read-only tools).
--   * agents.superficie_claude  the Claude Code surface settings of a DB-source agent: {tools, model, owns_kb}.
--                               Validated by the API (dev-advisor => A10 tools only). The tree snapshot taken at
--                               publish freezes what each version shipped with.
--
-- Additive only; every existing row keeps fonte='git' (packages) or is a runtime agent (the column is then inert).

ALTER TABLE agents.agents
    ADD COLUMN IF NOT EXISTS fonte TEXT NOT NULL DEFAULT 'git';

ALTER TABLE agents.agents
    DROP CONSTRAINT IF EXISTS agents_fonte_check;

ALTER TABLE agents.agents
    ADD CONSTRAINT agents_fonte_check CHECK (fonte IN ('git', 'db'));

ALTER TABLE agents.agents
    ADD COLUMN IF NOT EXISTS superficie_claude JSONB NULL;

ALTER TABLE agents.agents
    DROP CONSTRAINT IF EXISTS agents_superficie_claude_check;

ALTER TABLE agents.agents
    ADD CONSTRAINT agents_superficie_claude_check
    CHECK (superficie_claude IS NULL OR jsonb_typeof(superficie_claude) = 'object');

ALTER TABLE agents.agents
    DROP CONSTRAINT IF EXISTS agents_kind_check;

ALTER TABLE agents.agents
    ADD CONSTRAINT agents_kind_check CHECK (kind IN ('runtime', 'dev-advisor', 'dev-executor'));

CREATE OR REPLACE FUNCTION agents.guard_agent_fonte_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    IF NEW.fonte IS DISTINCT FROM OLD.fonte THEN
        RAISE EXCEPTION 'fonte_immutable' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_agent_fonte_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_agent_fonte_immutable() TO service_role;

DROP TRIGGER IF EXISTS agents_fonte_immutable ON agents.agents;
CREATE TRIGGER agents_fonte_immutable
    BEFORE UPDATE OF fonte ON agents.agents
    FOR EACH ROW EXECUTE FUNCTION agents.guard_agent_fonte_immutable();
