-- ============================================================================
-- 012_agent_studio_definitions.sql — Agent Studio: versioned agent definitions
-- (contract §B1, `products/agents/projects/agent-studio-isaia/CONTRACT.md`)
--
-- An agent becomes a VERSIONED, UI-managed definition: prompt sections,
-- skills (+ attached reference files), model/limits/tool policy, and client
-- brains. A version is immutable once published (§A3); exactly one
-- `rascunho` and at most one `ativa` per agent (partial uniques below).
-- `compiled_prompts` stores the exact compiled text once per hash (§A7).
--
-- Julia is untouched: every existing agent row gets
-- `definition_mode='legacy'` by column default (§A2).
--
-- Conventions (identical to 006_agents.sql): common columns, RLS with an
-- org-scoped SELECT policy + the literal "service_role_bypass" policy,
-- `idx_agents_<table>_org`, the `agents.set_updated_at()` trigger. Routes use
-- the admin client — RLS is defence in depth, never the authorization
-- boundary.
--
-- IMMUTABILITY (§B1, §H3) — enforced HERE, not only in Python:
--   * agent_versions: once OLD.status <> 'rascunho' the only permitted
--     UPDATE is `ativa -> substituida` with every content column unchanged;
--     DELETE of a non-draft raises. A draft may never jump straight to
--     `substituida`.
--   * agent_prompt_sections / agent_skills / agent_skill_files: any
--     INSERT/UPDATE/DELETE whose parent version is not `rascunho` raises
--     `version_immutable`. A child row whose parent is already gone (the
--     FK cascade of `discard_agent_draft`) is allowed through — the parent
--     could only have been deleted as a draft (the version trigger above
--     refuses every other delete).
--   * compiled_prompts: write-once — every UPDATE raises.
-- Every trigger raises with the MESSAGE equal to the machine code
-- (`version_immutable` / `compiled_prompt_immutable`) so the store maps the
-- PostgREST error to the right 409 without parsing prose.
--
-- VERSION FUNCTIONS: `create_agent_draft` / `publish_agent_version` /
-- `discard_agent_draft` each run as ONE PostgREST `.rpc()` request = ONE
-- Postgres transaction (same rationale as `create_persona_version` in 006:
-- "assign versao = max+1 + deep-copy children" and "flip ativa ->
-- substituida + this -> ativa" must never interleave).
--
-- SECURITY DEFINER EXECUTE LOCKDOWN: every SECURITY DEFINER function below
-- (the three version functions AND the four trigger functions) is
-- immediately followed by `REVOKE ALL ... FROM PUBLIC, anon, authenticated`
-- + `GRANT EXECUTE ... TO service_role` — Postgres grants EXECUTE to PUBLIC
-- by default, and `/rpc/publish_agent_version` reachable by anon would let
-- anyone publish any org's draft (prompt injection into a live agent).
-- Trigger invocation is not a role's direct EXECUTE call, so the revoke
-- cannot stop the triggers from firing.
--
-- ANON LOCKDOWN (mirrors 011_anon_grant_lockdown.sql for tables created
-- after it): 011 revoked anon from the schema's DEFAULT PRIVILEGES, so these
-- tables should already be created without an anon grant. Each new table
-- still carries an explicit `REVOKE ALL ... FROM anon` — a no-op restatement
-- when the default holds, and the guard when the migration runs as a role
-- whose default privileges 011 did not touch.
--
-- Forward-only.
-- ============================================================================

SET search_path = agents, public;

-- ────────────────────────────────────────────────────────────────────────
-- agents.agents — studio columns
-- ────────────────────────────────────────────────────────────────────────

ALTER TABLE agents.agents
    ADD COLUMN definition_mode TEXT NOT NULL DEFAULT 'legacy'
        CHECK (definition_mode IN ('legacy', 'studio')),
    ADD COLUMN descricao TEXT NULL,
    ADD COLUMN publicacao_limiar NUMERIC(4,3) NOT NULL DEFAULT 0.800
        CHECK (publicacao_limiar >= 0 AND publicacao_limiar <= 1);


-- ────────────────────────────────────────────────────────────────────────
-- agent_versions
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    versao INT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('rascunho', 'ativa', 'substituida')),
    notas TEXT NULL,
    model TEXT NOT NULL CHECK (model IN ('claude-opus-5', 'claude-sonnet-5')),
    effort TEXT NOT NULL CHECK (effort IN ('low', 'medium', 'high', 'xhigh', 'max')),
    max_turns INT NOT NULL DEFAULT 40 CHECK (max_turns BETWEEN 1 AND 200),
    idioma TEXT NOT NULL DEFAULT 'pt-BR',
    tool_policy JSONB NOT NULL DEFAULT '{"web_search": true, "knowledge": true}'::jsonb,
    based_on_version_id UUID NULL REFERENCES agents.agent_versions(id),
    created_by UUID NOT NULL,
    published_by UUID NULL,
    published_at TIMESTAMPTZ NULL,
    -- Hash of the compile WITHOUT a client; refreshed on every draft save.
    compiled_hash TEXT NULL,
    -- The eval run that satisfied the gate (FK added in 013).
    eval_run_id UUID NULL,
    publish_override_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, versao)
);

ALTER TABLE agents.agent_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_versions_select_own_org" ON agents.agent_versions
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.agent_versions
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_agent_versions_org ON agents.agent_versions(org_id);

-- One ativa per agent; one rascunho per agent (§A3).
CREATE UNIQUE INDEX agent_versions_one_ativa_idx
    ON agents.agent_versions (agent_id) WHERE status = 'ativa';
CREATE UNIQUE INDEX agent_versions_one_rascunho_idx
    ON agents.agent_versions (agent_id) WHERE status = 'rascunho';

CREATE OR REPLACE TRIGGER set_updated_at_agent_versions
    BEFORE UPDATE ON agents.agent_versions
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

REVOKE ALL ON agents.agent_versions FROM anon;


-- ────────────────────────────────────────────────────────────────────────
-- agent_prompt_sections
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_prompt_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    chave TEXT NOT NULL CHECK (chave ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    titulo TEXT NOT NULL,
    ordem INT NOT NULL,
    conteudo TEXT NOT NULL DEFAULT '',
    ativo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, chave)
);

ALTER TABLE agents.agent_prompt_sections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_prompt_sections_select_own_org" ON agents.agent_prompt_sections
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.agent_prompt_sections
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_agent_prompt_sections_org ON agents.agent_prompt_sections(org_id);
CREATE INDEX idx_agents_agent_prompt_sections_version ON agents.agent_prompt_sections(version_id);

CREATE OR REPLACE TRIGGER set_updated_at_agent_prompt_sections
    BEFORE UPDATE ON agents.agent_prompt_sections
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

REVOKE ALL ON agents.agent_prompt_sections FROM anon;


-- ────────────────────────────────────────────────────────────────────────
-- agent_skills
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    nome TEXT NOT NULL CHECK (nome ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(nome) <= 64),
    descricao TEXT NOT NULL CHECK (length(descricao) BETWEEN 1 AND 1024),
    corpo TEXT NOT NULL DEFAULT '',
    ordem INT NOT NULL DEFAULT 0,
    ativo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, nome)
);

ALTER TABLE agents.agent_skills ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_skills_select_own_org" ON agents.agent_skills
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.agent_skills
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_agent_skills_org ON agents.agent_skills(org_id);
CREATE INDEX idx_agents_agent_skills_version ON agents.agent_skills(version_id);

CREATE OR REPLACE TRIGGER set_updated_at_agent_skills
    BEFORE UPDATE ON agents.agent_skills
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

REVOKE ALL ON agents.agent_skills FROM anon;


-- ────────────────────────────────────────────────────────────────────────
-- agent_skill_files
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_skill_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    skill_id UUID NOT NULL REFERENCES agents.agent_skills(id) ON DELETE CASCADE,
    caminho TEXT NOT NULL CHECK (caminho ~ '^[a-z0-9][a-z0-9._/-]*$' AND caminho !~ '\.\.'),
    titulo TEXT NULL,
    conteudo TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (skill_id, caminho)
);

ALTER TABLE agents.agent_skill_files ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_skill_files_select_own_org" ON agents.agent_skill_files
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.agent_skill_files
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_agent_skill_files_org ON agents.agent_skill_files(org_id);
CREATE INDEX idx_agents_agent_skill_files_skill ON agents.agent_skill_files(skill_id);

CREATE OR REPLACE TRIGGER set_updated_at_agent_skill_files
    BEFORE UPDATE ON agents.agent_skill_files
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

REVOKE ALL ON agents.agent_skill_files FROM anon;


-- ────────────────────────────────────────────────────────────────────────
-- agent_clients — the "client brain": per-client durable context
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    slug TEXT NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    nome TEXT NOT NULL,
    resumo TEXT NOT NULL DEFAULT '',
    ativo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, slug)
);

ALTER TABLE agents.agent_clients ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_clients_select_own_org" ON agents.agent_clients
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.agent_clients
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_agent_clients_org ON agents.agent_clients(org_id);

CREATE OR REPLACE TRIGGER set_updated_at_agent_clients
    BEFORE UPDATE ON agents.agent_clients
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

REVOKE ALL ON agents.agent_clients FROM anon;


-- ────────────────────────────────────────────────────────────────────────
-- agent_client_entries
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_client_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    client_id UUID NOT NULL REFERENCES agents.agent_clients(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL CHECK (tipo IN ('marca', 'publico', 'posicionamento', 'trava', 'decisao', 'aprendizado', 'evidencia', 'nota')),
    titulo TEXT NOT NULL,
    conteudo TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'arquivado')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.agent_client_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_client_entries_select_own_org" ON agents.agent_client_entries
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.agent_client_entries
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_agent_client_entries_org ON agents.agent_client_entries(org_id);
CREATE INDEX idx_agents_agent_client_entries_client ON agents.agent_client_entries(client_id);

CREATE OR REPLACE TRIGGER set_updated_at_agent_client_entries
    BEFORE UPDATE ON agents.agent_client_entries
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

REVOKE ALL ON agents.agent_client_entries FROM anon;


-- ────────────────────────────────────────────────────────────────────────
-- compiled_prompts — exact text per hash, write-once (§A7)
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.compiled_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    hash TEXT NOT NULL CHECK (hash ~ '^sha256:[0-9a-f]{64}$'),
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id),
    client_id UUID NULL REFERENCES agents.agent_clients(id),
    texto TEXT NOT NULL,
    manifest JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, hash)
);

ALTER TABLE agents.compiled_prompts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "compiled_prompts_select_own_org" ON agents.compiled_prompts
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.compiled_prompts
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_compiled_prompts_org ON agents.compiled_prompts(org_id);

CREATE OR REPLACE TRIGGER set_updated_at_compiled_prompts
    BEFORE UPDATE ON agents.compiled_prompts
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

REVOKE ALL ON agents.compiled_prompts FROM anon;


-- ────────────────────────────────────────────────────────────────────────
-- conversations / messages — proof-of-use columns (§A7, §D6)
-- ────────────────────────────────────────────────────────────────────────

ALTER TABLE agents.conversations
    ADD COLUMN version_id UUID NULL REFERENCES agents.agent_versions(id),
    ADD COLUMN client_id UUID NULL REFERENCES agents.agent_clients(id);

ALTER TABLE agents.messages
    ADD COLUMN version_id UUID NULL REFERENCES agents.agent_versions(id),
    ADD COLUMN compiled_hash TEXT NULL;


-- ────────────────────────────────────────────────────────────────────────
-- Immutability triggers (§B1, §H3)
-- ────────────────────────────────────────────────────────────────────────

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
        RETURN NEW;
    END IF;

    -- Published row: only ativa -> substituida, every content column frozen.
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
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_agent_version_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_agent_version_immutable() TO service_role;

CREATE OR REPLACE TRIGGER guard_agent_version_immutable
    BEFORE UPDATE OR DELETE ON agents.agent_versions
    FOR EACH ROW EXECUTE FUNCTION agents.guard_agent_version_immutable();


-- Children keyed directly by version_id (sections, skills).
CREATE OR REPLACE FUNCTION agents.guard_version_child_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_status TEXT;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT status INTO v_status FROM agents.agent_versions WHERE id = OLD.version_id;
        -- NULL = parent already gone (discard_agent_draft's cascade).
        IF v_status IS NOT NULL AND v_status <> 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT status INTO v_status FROM agents.agent_versions WHERE id = NEW.version_id;
        IF v_status IS DISTINCT FROM 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_version_child_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_version_child_immutable() TO service_role;

CREATE OR REPLACE TRIGGER guard_agent_prompt_sections_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.agent_prompt_sections
    FOR EACH ROW EXECUTE FUNCTION agents.guard_version_child_immutable();

CREATE OR REPLACE TRIGGER guard_agent_skills_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.agent_skills
    FOR EACH ROW EXECUTE FUNCTION agents.guard_version_child_immutable();


-- Skill files — parent version reached through agent_skills.
CREATE OR REPLACE FUNCTION agents.guard_skill_file_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_status TEXT;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT v.status INTO v_status
        FROM agents.agent_skills s JOIN agents.agent_versions v ON v.id = s.version_id
        WHERE s.id = OLD.skill_id;
        -- NULL = skill (or its version) already gone — cascade from a draft.
        IF v_status IS NOT NULL AND v_status <> 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT v.status INTO v_status
        FROM agents.agent_skills s JOIN agents.agent_versions v ON v.id = s.version_id
        WHERE s.id = NEW.skill_id;
        IF v_status IS DISTINCT FROM 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_skill_file_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_skill_file_immutable() TO service_role;

CREATE OR REPLACE TRIGGER guard_agent_skill_files_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.agent_skill_files
    FOR EACH ROW EXECUTE FUNCTION agents.guard_skill_file_immutable();


-- compiled_prompts — write-once.
CREATE OR REPLACE FUNCTION agents.guard_compiled_prompt_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    RAISE EXCEPTION 'compiled_prompt_immutable' USING ERRCODE = 'P0001';
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_compiled_prompt_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_compiled_prompt_immutable() TO service_role;

CREATE OR REPLACE TRIGGER guard_compiled_prompts_immutable
    BEFORE UPDATE ON agents.compiled_prompts
    FOR EACH ROW EXECUTE FUNCTION agents.guard_compiled_prompt_immutable();


-- ────────────────────────────────────────────────────────────────────────
-- Version functions (§B1) — one .rpc() = one transaction
-- ────────────────────────────────────────────────────────────────────────

-- New draft: empty (defaults) or a deep copy of p_source_version_id.
-- Raises `agent_not_found`, `version_not_found`, `draft_exists`.
CREATE OR REPLACE FUNCTION agents.create_agent_draft(
    p_org_id UUID,
    p_agent_id UUID,
    p_source_version_id UUID,
    p_created_by UUID
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_src agents.agent_versions;
    v_next_versao INT;
    v_new_id UUID;
    v_skill RECORD;
    v_new_skill_id UUID;
BEGIN
    PERFORM 1 FROM agents.agents WHERE id = p_agent_id AND org_id = p_org_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent_not_found' USING ERRCODE = 'P0001';
    END IF;

    -- Serialise concurrent draft creation for this agent (the partial
    -- unique index is the backstop; this makes the error the clean code).
    PERFORM 1 FROM agents.agents WHERE id = p_agent_id FOR UPDATE;

    PERFORM 1 FROM agents.agent_versions
    WHERE org_id = p_org_id AND agent_id = p_agent_id AND status = 'rascunho';
    IF FOUND THEN
        RAISE EXCEPTION 'draft_exists' USING ERRCODE = 'P0001';
    END IF;

    SELECT COALESCE(MAX(versao), 0) + 1 INTO v_next_versao
    FROM agents.agent_versions
    WHERE org_id = p_org_id AND agent_id = p_agent_id;

    IF p_source_version_id IS NULL THEN
        INSERT INTO agents.agent_versions (
            org_id, agent_id, versao, status, model, effort, max_turns, created_by
        ) VALUES (
            p_org_id, p_agent_id, v_next_versao, 'rascunho',
            'claude-opus-5', 'high', 40, p_created_by
        )
        RETURNING id INTO v_new_id;
        RETURN v_new_id;
    END IF;

    SELECT * INTO v_src FROM agents.agent_versions
    WHERE id = p_source_version_id AND org_id = p_org_id AND agent_id = p_agent_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;

    INSERT INTO agents.agent_versions (
        org_id, agent_id, versao, status, notas, model, effort, max_turns,
        idioma, tool_policy, based_on_version_id, created_by
    ) VALUES (
        p_org_id, p_agent_id, v_next_versao, 'rascunho', NULL, v_src.model,
        v_src.effort, v_src.max_turns, v_src.idioma, v_src.tool_policy,
        v_src.id, p_created_by
    )
    RETURNING id INTO v_new_id;

    INSERT INTO agents.agent_prompt_sections (
        org_id, version_id, chave, titulo, ordem, conteudo, ativo
    )
    SELECT p_org_id, v_new_id, chave, titulo, ordem, conteudo, ativo
    FROM agents.agent_prompt_sections
    WHERE version_id = v_src.id AND org_id = p_org_id;

    FOR v_skill IN
        SELECT * FROM agents.agent_skills
        WHERE version_id = v_src.id AND org_id = p_org_id
    LOOP
        INSERT INTO agents.agent_skills (
            org_id, version_id, nome, descricao, corpo, ordem, ativo
        ) VALUES (
            p_org_id, v_new_id, v_skill.nome, v_skill.descricao, v_skill.corpo,
            v_skill.ordem, v_skill.ativo
        )
        RETURNING id INTO v_new_skill_id;

        INSERT INTO agents.agent_skill_files (
            org_id, skill_id, caminho, titulo, conteudo
        )
        SELECT p_org_id, v_new_skill_id, caminho, titulo, conteudo
        FROM agents.agent_skill_files
        WHERE skill_id = v_skill.id AND org_id = p_org_id;
    END LOOP;

    RETURN v_new_id;
END;
$$;

REVOKE ALL ON FUNCTION agents.create_agent_draft(UUID, UUID, UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.create_agent_draft(UUID, UUID, UUID, UUID) TO service_role;


-- Publish a draft: current ativa -> substituida, this -> ativa. The eval
-- gate runs in Python BEFORE this call (§B1); this only enforces "is a
-- draft of this org". Raises `version_not_found`, `version_immutable`.
CREATE OR REPLACE FUNCTION agents.publish_agent_version(
    p_org_id UUID,
    p_version_id UUID,
    p_published_by UUID,
    p_eval_run_id UUID,
    p_override_reason TEXT
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_row agents.agent_versions;
BEGIN
    SELECT * INTO v_row FROM agents.agent_versions
    WHERE id = p_version_id AND org_id = p_org_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF v_row.status <> 'rascunho' THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;

    UPDATE agents.agent_versions
    SET status = 'substituida'
    WHERE org_id = p_org_id AND agent_id = v_row.agent_id AND status = 'ativa';

    UPDATE agents.agent_versions
    SET status = 'ativa',
        published_by = p_published_by,
        published_at = now(),
        eval_run_id = p_eval_run_id,
        publish_override_reason = p_override_reason
    WHERE id = p_version_id AND org_id = p_org_id;
END;
$$;

REVOKE ALL ON FUNCTION agents.publish_agent_version(UUID, UUID, UUID, UUID, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.publish_agent_version(UUID, UUID, UUID, UUID, TEXT) TO service_role;


-- Discard a draft (children cascade). Raises `version_not_found`,
-- `version_immutable`.
CREATE OR REPLACE FUNCTION agents.discard_agent_draft(
    p_org_id UUID,
    p_version_id UUID
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_status TEXT;
BEGIN
    SELECT status INTO v_status FROM agents.agent_versions
    WHERE id = p_version_id AND org_id = p_org_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF v_status <> 'rascunho' THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;

    DELETE FROM agents.agent_versions WHERE id = p_version_id AND org_id = p_org_id;
END;
$$;

REVOKE ALL ON FUNCTION agents.discard_agent_draft(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.discard_agent_draft(UUID, UUID) TO service_role;


-- ────────────────────────────────────────────────────────────────────────
-- status_pagina — the Agent Studio nav page (§G `/studio`)
-- ────────────────────────────────────────────────────────────────────────
-- Every nav-listed route needs a matching row, or `filterNavByPageStatus`
-- hides it from EVERYONE once any row exists ("unlisted pages are hidden",
-- KB § PATTERNS/frontend/status-pagina-dev-visibility.md). Seeded at
-- 'desenvolvimento' — visible to owner/dev/admin via the existing
-- `dev_veem_desenvolvimento` policy (005), same as 008/010.
INSERT INTO agents.status_pagina (nome_pagina, status) VALUES
    ('studio', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
