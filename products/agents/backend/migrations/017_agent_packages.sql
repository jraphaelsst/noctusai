-- ============================================================================
-- 017_agent_packages.sql — Agent Packages (contract §D1, §G3, §H2, §I;
-- `products/agents/projects/agent-packages/CONTRACT.md`)
--
-- A dev-advisor agent is authored in git as a PACKAGE and imported into Agent
-- Studio like any other agent (same versions / sections / skills / knowledge /
-- evals / audit — one registry, A9). This migration adds what the package
-- flow needs on top of Studio (012/013):
--
--   * agents.kind  ('runtime' | 'dev-advisor'), default 'runtime' so Julia and
--     IsaIA (and every row that exists today) stay valid and unchanged. The
--     kind is IMMUTABLE once the row exists (`guard_agent_kind_immutable`) —
--     an import can never flip IsaIA/Julia into a dev-advisor, nor back.
--   * agent_versions.versao_semver / package_sha — the package identity the
--     importer records on the draft (§C4). Frozen on publish like every other
--     content column (`guard_agent_version_immutable` re-declared below with
--     the two columns added). A published semver is unique per agent.
--   * agent_package_trees — the materialised Claude Code tree (`dist/claude/`)
--     of a version, stored at import time so `GET /api/agent-packages/...`
--     (§I) serves EXACTLY what the build produced (it carries the package's
--     LEARNINGS.md + PACKAGE.json, which cannot be re-derived from the Studio
--     rows). Write-once per published version: INSERT/UPDATE/DELETE refused
--     unless the parent version is a `rascunho`.
--   * agent_project_sources (§G3) — the consumer-repo manifest synced on every
--     push; each row points at the knowledge document that carries its text
--     (collection `projeto-<slug>`, tag `PRJ`).
--   * agent_learnings (§H2) — learnings pushed by consumers, reviewed in the
--     Studio (`aceito` / `descartado`). Content columns are write-once; only
--     the review columns may change.
--
-- agents.api_tokens ALREADY carries `scopes TEXT[] NOT NULL DEFAULT '{}'`
-- (007_api_tokens.sql, created with every SEED-1 column) — §D1/§I's "gains a
-- scopes column" is satisfied by 007; this file does not re-add it. The scopes
-- the package routes honour are `packages:read`, `project-knowledge:write`,
-- `learnings:write`, `learnings:read`.
--
-- Conventions identical to 012/013: org-scoped SELECT policy + the literal
-- "service_role_bypass", `idx_agents_<table>_org`, the `agents.set_updated_at()`
-- trigger, anon + authenticated-write REVOKEs, SECURITY DEFINER functions
-- locked to service_role. Routes use the admin client — RLS is defence in
-- depth, never the authorization boundary.
--
-- Forward-only. Existing rows stay valid: every new column on an existing
-- table is defaulted or nullable.
-- ============================================================================

SET search_path = agents, public;

-- ────────────────────────────────────────────────────────────────────────
-- agents.kind
-- ────────────────────────────────────────────────────────────────────────

ALTER TABLE agents.agents
    ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'runtime';

ALTER TABLE agents.agents
    DROP CONSTRAINT IF EXISTS agents_kind_check;

ALTER TABLE agents.agents
    ADD CONSTRAINT agents_kind_check CHECK (kind IN ('runtime', 'dev-advisor'));

CREATE OR REPLACE FUNCTION agents.guard_agent_kind_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    IF NEW.kind IS DISTINCT FROM OLD.kind THEN
        RAISE EXCEPTION 'kind_immutable' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_agent_kind_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_agent_kind_immutable() TO service_role;

CREATE OR REPLACE TRIGGER guard_agent_kind_immutable
    BEFORE UPDATE ON agents.agents
    FOR EACH ROW EXECUTE FUNCTION agents.guard_agent_kind_immutable();


-- ────────────────────────────────────────────────────────────────────────
-- agent_versions — package identity (§C4)
-- ────────────────────────────────────────────────────────────────────────

ALTER TABLE agents.agent_versions
    ADD COLUMN IF NOT EXISTS versao_semver TEXT NULL,
    ADD COLUMN IF NOT EXISTS package_sha TEXT NULL;

ALTER TABLE agents.agent_versions
    DROP CONSTRAINT IF EXISTS agent_versions_versao_semver_check;
ALTER TABLE agents.agent_versions
    ADD CONSTRAINT agent_versions_versao_semver_check CHECK (
        versao_semver IS NULL
        OR versao_semver ~ '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$'
    );

ALTER TABLE agents.agent_versions
    DROP CONSTRAINT IF EXISTS agent_versions_package_sha_check;
ALTER TABLE agents.agent_versions
    ADD CONSTRAINT agent_versions_package_sha_check CHECK (
        package_sha IS NULL OR package_sha ~ '^[0-9a-f]{64}$'
    );

-- A published semver is unique per agent (drafts may re-import the same one
-- freely while it is being authored). Backstop for the importer's
-- `semver_published` refusal.
CREATE UNIQUE INDEX IF NOT EXISTS agent_versions_published_semver_idx
    ON agents.agent_versions (agent_id, versao_semver)
    WHERE versao_semver IS NOT NULL AND status <> 'rascunho';

-- 012's guard re-declared with the two new columns frozen on a published row.
CREATE OR REPLACE FUNCTION agents.guard_agent_version_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        RETURN OLD;
    END IF;

    IF OLD.status = 'rascunho' THEN
        -- A draft is freely editable, and may be published (-> ativa), but
        -- never jump straight to substituida.
        IF NEW.status = 'substituida' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        -- M1: a change of a compiled setting invalidates the judged hash.
        IF NEW.status = 'rascunho' AND (
               NEW.model IS DISTINCT FROM OLD.model
            OR NEW.effort IS DISTINCT FROM OLD.effort
            OR NEW.max_turns IS DISTINCT FROM OLD.max_turns
            OR NEW.idioma IS DISTINCT FROM OLD.idioma
            OR NEW.tool_policy IS DISTINCT FROM OLD.tool_policy
        ) THEN
            NEW.compiled_hash := NULL;
        END IF;
        RETURN NEW;
    END IF;

    -- Published row: only ativa -> substituida, every content column frozen.
    -- (`substituida -> ativa` is refused here too: OLD.status is not 'ativa'.)
    IF NOT (OLD.status = 'ativa' AND NEW.status = 'substituida') THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    IF NEW.org_id IS DISTINCT FROM OLD.org_id
       OR NEW.agent_id IS DISTINCT FROM OLD.agent_id
       OR NEW.versao IS DISTINCT FROM OLD.versao
       OR NEW.notas IS DISTINCT FROM OLD.notas
       OR NEW.model IS DISTINCT FROM OLD.model
       OR NEW.effort IS DISTINCT FROM OLD.effort
       OR NEW.max_turns IS DISTINCT FROM OLD.max_turns
       OR NEW.idioma IS DISTINCT FROM OLD.idioma
       OR NEW.tool_policy IS DISTINCT FROM OLD.tool_policy
       OR NEW.based_on_version_id IS DISTINCT FROM OLD.based_on_version_id
       OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.published_by IS DISTINCT FROM OLD.published_by
       OR NEW.published_at IS DISTINCT FROM OLD.published_at
       OR NEW.compiled_hash IS DISTINCT FROM OLD.compiled_hash
       OR NEW.eval_run_id IS DISTINCT FROM OLD.eval_run_id
       OR NEW.publish_override_reason IS DISTINCT FROM OLD.publish_override_reason
       OR NEW.limiar_aplicado IS DISTINCT FROM OLD.limiar_aplicado
       OR NEW.eval_score IS DISTINCT FROM OLD.eval_score
       OR NEW.versao_semver IS DISTINCT FROM OLD.versao_semver
       OR NEW.package_sha IS DISTINCT FROM OLD.package_sha
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_agent_version_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_agent_version_immutable() TO service_role;


-- ────────────────────────────────────────────────────────────────────────
-- agent_package_trees — the materialised Claude Code tree of a version
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_package_trees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    -- [{"caminho": "<posix path relative to the consumer repo root>", "conteudo": "<text>"}]
    files JSONB NOT NULL CHECK (jsonb_typeof(files) = 'array'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id)
);

ALTER TABLE agents.agent_package_trees ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_package_trees_select_own_org" ON agents.agent_package_trees
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.agent_package_trees
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_agent_package_trees_org ON agents.agent_package_trees(org_id);
CREATE INDEX idx_agents_agent_package_trees_agent ON agents.agent_package_trees(agent_id);

CREATE OR REPLACE TRIGGER set_updated_at_agent_package_trees
    BEFORE UPDATE ON agents.agent_package_trees
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

REVOKE ALL ON agents.agent_package_trees FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_package_trees FROM authenticated;

-- Write-once once the parent version is published: same lock-the-parent shape
-- as 012's `guard_version_child_immutable` (no compiled_hash side effect — the
-- tree is not a compile input).
CREATE OR REPLACE FUNCTION agents.guard_package_tree_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_status TEXT;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT status INTO v_status FROM agents.agent_versions WHERE id = OLD.version_id FOR UPDATE;
        -- NULL = parent already gone (discard_agent_draft's cascade).
        IF v_status IS NOT NULL AND v_status <> 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT status INTO v_status FROM agents.agent_versions WHERE id = NEW.version_id FOR UPDATE;
        IF v_status IS DISTINCT FROM 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_package_tree_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_package_tree_immutable() TO service_role;

CREATE OR REPLACE TRIGGER guard_agent_package_trees_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.agent_package_trees
    FOR EACH ROW EXECUTE FUNCTION agents.guard_package_tree_immutable();


-- ────────────────────────────────────────────────────────────────────────
-- agent_project_sources (§G3) — consumer-repo manifest, one row per path
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_project_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    project_slug TEXT NOT NULL CHECK (project_slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    path TEXT NOT NULL CHECK (length(path) BETWEEN 1 AND 500),
    sha256 TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    tipo TEXT NOT NULL CHECK (tipo IN ('doc', 'codigo', 'quadro')),
    -- The knowledge document carrying the text. SET NULL, never a cascade: a
    -- manually deleted document must not silently erase the sync ledger.
    document_id UUID NULL REFERENCES agents.knowledge_documents(id) ON DELETE SET NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, project_slug, path)
);

ALTER TABLE agents.agent_project_sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_project_sources_select_own_org" ON agents.agent_project_sources
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.agent_project_sources
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_agent_project_sources_org ON agents.agent_project_sources(org_id);
CREATE INDEX idx_agents_agent_project_sources_agent ON agents.agent_project_sources(agent_id, project_slug);

CREATE OR REPLACE TRIGGER set_updated_at_agent_project_sources
    BEFORE UPDATE ON agents.agent_project_sources
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

REVOKE ALL ON agents.agent_project_sources FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_project_sources FROM authenticated;


-- ────────────────────────────────────────────────────────────────────────
-- agent_learnings (§H2)
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_learnings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    project_slug TEXT NOT NULL CHECK (project_slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    -- §H1 identity: sha256 over (date, learning text), whitespace-normalised.
    row_sha TEXT NOT NULL CHECK (row_sha ~ '^[0-9a-f]{64}$'),
    data TEXT NOT NULL CHECK (length(data) BETWEEN 1 AND 40),
    tipo TEXT NOT NULL CHECK (tipo IN (
        'pitfall', 'armadilha', 'practice', 'pratica', 'prática', 'decision', 'decisao', 'decisão'
    )),
    texto TEXT NOT NULL CHECK (length(texto) BETWEEN 1 AND 8000),
    evidencia TEXT NOT NULL DEFAULT '' CHECK (length(evidencia) <= 4000),
    -- The row's own §H1 status in the consumer's LEARNINGS.md (informational).
    row_status TEXT NOT NULL DEFAULT 'novo' CHECK (row_status IN (
        'new', 'novo', 'absorbed', 'absorvido', 'promoted', 'promovido'
    )),
    -- The Studio review state (§H2/§H3): the promote tool pulls `aceito`.
    status TEXT NOT NULL DEFAULT 'novo' CHECK (status IN ('novo', 'aceito', 'descartado', 'promovido')),
    review_note TEXT NULL CHECK (review_note IS NULL OR length(review_note) <= 2000),
    reviewed_by UUID NULL,
    reviewed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, row_sha)
);

ALTER TABLE agents.agent_learnings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_learnings_select_own_org" ON agents.agent_learnings
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.agent_learnings
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_agent_learnings_org ON agents.agent_learnings(org_id);
CREATE INDEX idx_agents_agent_learnings_agent ON agents.agent_learnings(agent_id, project_slug, status);

CREATE OR REPLACE TRIGGER set_updated_at_agent_learnings
    BEFORE UPDATE ON agents.agent_learnings
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

REVOKE ALL ON agents.agent_learnings FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_learnings FROM authenticated;

-- A learning's content is write-once; only the review columns may move.
CREATE OR REPLACE FUNCTION agents.guard_agent_learning_content()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    IF NEW.org_id IS DISTINCT FROM OLD.org_id
       OR NEW.agent_id IS DISTINCT FROM OLD.agent_id
       OR NEW.project_slug IS DISTINCT FROM OLD.project_slug
       OR NEW.row_sha IS DISTINCT FROM OLD.row_sha
       OR NEW.data IS DISTINCT FROM OLD.data
       OR NEW.tipo IS DISTINCT FROM OLD.tipo
       OR NEW.texto IS DISTINCT FROM OLD.texto
       OR NEW.evidencia IS DISTINCT FROM OLD.evidencia
       OR NEW.row_status IS DISTINCT FROM OLD.row_status
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'learning_content_immutable' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_agent_learning_content() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_agent_learning_content() TO service_role;

CREATE OR REPLACE TRIGGER guard_agent_learning_content
    BEFORE UPDATE ON agents.agent_learnings
    FOR EACH ROW EXECUTE FUNCTION agents.guard_agent_learning_content();
