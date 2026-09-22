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
--   * compiled_prompts: write-once — every UPDATE raises, and so does
--     every DELETE except inside `agents.erase_compiled_prompts` (the ONE
--     sanctioned deletion path — LGPD erasure of a client's prompts).
--   * agent_audit_log: append-only — every UPDATE/DELETE raises.
-- Every trigger raises with the MESSAGE equal to the machine code
-- (`version_immutable` / `compiled_prompt_immutable` / ...) so the store
-- maps the PostgREST error to the right 409 without parsing prose.
--
-- PUBLISH RACE (wave-1 security review M1): `compiled_hash` is the hash the
-- eval gate judged. Any content change of a draft — a child row
-- (section / skill / skill file) INSERT/UPDATE/DELETE, or a change of a
-- compiled setting on the version row itself — sets the draft's
-- `compiled_hash` back to NULL, row-locking the parent version first. The
-- app re-stamps the hash after its own writes (compare-and-set on
-- `updated_at`), and `publish_agent_version` refuses (`draft_changed`)
-- unless the caller's gate-checked hash is STILL the row's hash. A write
-- that lands between the gate check and the publish therefore can never be
-- published under a verdict that judged other content.
--
-- EVAL GATE IN THE DATABASE (H1/H2): `publish_agent_version` re-validates
-- the gate itself — the run must be this version's, `concluida`,
-- `completa` (covered every active case), non-empty, stamped with the
-- expected hash, and score >= the agent's CURRENT `publicacao_limiar`; the
-- agent must still have >= 1 active case. It snapshots `limiar_aplicado` +
-- `eval_score` onto the version and appends to `agent_audit_log`. The Python
-- gate stays (it produces the rich 409 body); this is the backstop.
--
-- VERSION FUNCTIONS: `create_agent_draft` / `publish_agent_version` /
-- `discard_agent_draft` / `replace_draft_sections` / `replace_draft_bundle` /
-- `set_agent_publicacao_limiar` / `erase_compiled_prompts` each run as ONE
-- PostgREST `.rpc()` request = ONE Postgres transaction (same rationale as
-- `create_persona_version` in 006: "assign versao = max+1 + deep-copy
-- children", "flip ativa -> substituida + this -> ativa" and "replace every
-- section/skill of a draft" must never interleave or half-apply).
--
-- SECURITY DEFINER EXECUTE LOCKDOWN: every SECURITY DEFINER function below
-- (the RPC functions AND the trigger functions) is immediately followed by
-- `REVOKE ALL ... FROM PUBLIC, anon, authenticated`
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
-- AUTHENTICATED WRITE LOCKDOWN (M5, mirrors 009/010): `authenticated` keeps
-- SELECT (the org-scoped read policy) but every studio table REVOKEs its
-- INSERT/UPDATE/DELETE/TRUNCATE grant explicitly — RLS having no write
-- policy is one layer; the missing grant is the second, so a future
-- permissive policy cannot silently open writes.
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
    ADD COLUMN publicacao_limiar NUMERIC(4,3) NOT NULL DEFAULT 0.800,
    -- H2: a floor, so the gate can never be made decorative (0.1 = "anything
    -- passes"). Every change of the value is audited (trigger below).
    ADD CONSTRAINT agents_publicacao_limiar_floor
        CHECK (publicacao_limiar >= 0.5 AND publicacao_limiar <= 1);


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
    -- H2: snapshots taken INSIDE publish_agent_version — the threshold in
    -- force and the gating run's score at the moment of publication.
    limiar_aplicado NUMERIC(4,3) NULL,
    eval_score NUMERIC(4,3) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, versao),
    -- L1: an override must carry a real reason (>= 20 chars once trimmed).
    CONSTRAINT agent_versions_override_reason_len CHECK (
        publish_override_reason IS NULL
        OR length(btrim(publish_override_reason, E' \t\r\n')) >= 20
    )
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
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_versions FROM authenticated;


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
    conteudo TEXT NOT NULL DEFAULT '' CHECK (length(conteudo) <= 40000),
    ativo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- DEFERRABLE so `replace_draft_sections` can swap two kept rows' chaves
    -- inside one statement set (checked at commit, never skipped).
    CONSTRAINT agent_prompt_sections_version_chave_key
        UNIQUE (version_id, chave) DEFERRABLE INITIALLY IMMEDIATE
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
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_prompt_sections FROM authenticated;


-- ────────────────────────────────────────────────────────────────────────
-- agent_skills
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    nome TEXT NOT NULL CHECK (nome ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(nome) <= 64),
    descricao TEXT NOT NULL CHECK (length(descricao) BETWEEN 1 AND 1024),
    corpo TEXT NOT NULL DEFAULT '' CHECK (length(corpo) <= 60000),
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
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_skills FROM authenticated;


-- ────────────────────────────────────────────────────────────────────────
-- agent_skill_files
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_skill_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    skill_id UUID NOT NULL REFERENCES agents.agent_skills(id) ON DELETE CASCADE,
    caminho TEXT NOT NULL CHECK (caminho ~ '^[a-z0-9][a-z0-9._/-]*$' AND caminho !~ '\.\.'),
    titulo TEXT NULL,
    conteudo TEXT NOT NULL DEFAULT '' CHECK (length(conteudo) <= 120000),
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
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_skill_files FROM authenticated;


-- ────────────────────────────────────────────────────────────────────────
-- agent_clients — the "client brain": per-client durable context
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    slug TEXT NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    nome TEXT NOT NULL,
    -- M3: the client brain is a LIVE prompt input (compiled into every turn
    -- bound to the client, never behind the eval gate) — capped.
    resumo TEXT NOT NULL DEFAULT '' CHECK (length(resumo) <= 8000),
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
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_clients FROM authenticated;


-- ────────────────────────────────────────────────────────────────────────
-- agent_client_entries
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_client_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    client_id UUID NOT NULL REFERENCES agents.agent_clients(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL CHECK (tipo IN ('marca', 'publico', 'posicionamento', 'trava', 'decisao', 'aprendizado', 'evidencia', 'nota')),
    titulo TEXT NOT NULL CHECK (length(titulo) <= 200),
    conteudo TEXT NOT NULL DEFAULT '' CHECK (length(conteudo) <= 4000),
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
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_client_entries FROM authenticated;


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
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.compiled_prompts FROM authenticated;


-- ────────────────────────────────────────────────────────────────────────
-- agent_audit_log — append-only record of every governance decision
-- (wave-1 security review H2): threshold changes (`limiar_alterado`, written
-- by a trigger so NO write path can skip it), publishes (`publicado` /
-- `publicado_override`) and draft discards (`rascunho_descartado`), the
-- latter two written inside their version functions (same transaction as
-- the change). `antes`/`depois` are the before/after snapshots.
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    actor UUID NULL,
    acao TEXT NOT NULL CHECK (acao IN ('limiar_alterado', 'publicado', 'publicado_override', 'rascunho_descartado')),
    antes JSONB NULL,
    depois JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.agent_audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_audit_log_select_own_org" ON agents.agent_audit_log
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.agent_audit_log
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_agent_audit_log_org ON agents.agent_audit_log(org_id);
CREATE INDEX idx_agents_agent_audit_log_agent ON agents.agent_audit_log(agent_id, created_at);

-- Convention parity only: the append-only guard below refuses every UPDATE
-- before this trigger could matter.
CREATE OR REPLACE TRIGGER set_updated_at_agent_audit_log
    BEFORE UPDATE ON agents.agent_audit_log
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

REVOKE ALL ON agents.agent_audit_log FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_audit_log FROM authenticated;


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
-- Immutability triggers (§B1, §H3) + draft-hash invalidation (M1)
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


-- Children keyed directly by version_id (sections, skills). The parent row
-- is locked FOR UPDATE before its status is read — serialises against a
-- concurrent `publish_agent_version` (which locks the same row), so a child
-- write can never slip into a version while it is being published. On a
-- draft parent the write then NULLs the parent's `compiled_hash` (M1).
CREATE OR REPLACE FUNCTION agents.guard_version_child_immutable()
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
        IF v_status = 'rascunho' THEN
            UPDATE agents.agent_versions SET compiled_hash = NULL WHERE id = OLD.version_id;
        END IF;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT status INTO v_status FROM agents.agent_versions WHERE id = NEW.version_id FOR UPDATE;
        IF v_status IS DISTINCT FROM 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        UPDATE agents.agent_versions SET compiled_hash = NULL WHERE id = NEW.version_id;
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


-- Skill files — parent version reached through agent_skills (same lock +
-- invalidation as above).
CREATE OR REPLACE FUNCTION agents.guard_skill_file_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_status TEXT;
    v_version UUID;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT v.id, v.status INTO v_version, v_status
        FROM agents.agent_skills s JOIN agents.agent_versions v ON v.id = s.version_id
        WHERE s.id = OLD.skill_id
        FOR UPDATE OF v;
        -- NULL = skill (or its version) already gone — cascade from a draft.
        IF v_status IS NOT NULL AND v_status <> 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        IF v_status = 'rascunho' THEN
            UPDATE agents.agent_versions SET compiled_hash = NULL WHERE id = v_version;
        END IF;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT v.id, v.status INTO v_version, v_status
        FROM agents.agent_skills s JOIN agents.agent_versions v ON v.id = s.version_id
        WHERE s.id = NEW.skill_id
        FOR UPDATE OF v;
        IF v_status IS DISTINCT FROM 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        UPDATE agents.agent_versions SET compiled_hash = NULL WHERE id = v_version;
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


-- compiled_prompts — write-once (L2). UPDATE always raises; DELETE raises
-- unless the transaction-local flag `agents.compiled_prompt_erasure` is on,
-- which ONLY `agents.erase_compiled_prompts` (service_role) sets.
CREATE OR REPLACE FUNCTION agents.guard_compiled_prompt_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('agents.compiled_prompt_erasure', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'compiled_prompt_immutable' USING ERRCODE = 'P0001';
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_compiled_prompt_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_compiled_prompt_immutable() TO service_role;

CREATE OR REPLACE TRIGGER guard_compiled_prompts_immutable
    BEFORE UPDATE OR DELETE ON agents.compiled_prompts
    FOR EACH ROW EXECUTE FUNCTION agents.guard_compiled_prompt_immutable();


-- agent_audit_log — append-only.
CREATE OR REPLACE FUNCTION agents.guard_audit_log_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    RAISE EXCEPTION 'audit_log_append_only' USING ERRCODE = 'P0001';
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_audit_log_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_audit_log_append_only() TO service_role;

CREATE OR REPLACE TRIGGER guard_agent_audit_log_append_only
    BEFORE UPDATE OR DELETE ON agents.agent_audit_log
    FOR EACH ROW EXECUTE FUNCTION agents.guard_audit_log_append_only();


-- Client brain entry cap (M3): at most 200 `ativo` entries per client — the
-- brain is compiled into every bound turn. The client row is locked first so
-- two concurrent inserts cannot both see 199.
CREATE OR REPLACE FUNCTION agents.guard_client_entry_cap()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_ativas INT;
BEGIN
    IF NEW.status <> 'ativo' THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = 'ativo' AND OLD.client_id = NEW.client_id THEN
        RETURN NEW;
    END IF;
    PERFORM 1 FROM agents.agent_clients WHERE id = NEW.client_id FOR UPDATE;
    SELECT count(*) INTO v_ativas FROM agents.agent_client_entries
    WHERE client_id = NEW.client_id AND status = 'ativo' AND id <> NEW.id;
    IF v_ativas >= 200 THEN
        RAISE EXCEPTION 'client_entries_cap' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_client_entry_cap() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_client_entry_cap() TO service_role;

CREATE OR REPLACE TRIGGER guard_agent_client_entries_cap
    BEFORE INSERT OR UPDATE ON agents.agent_client_entries
    FOR EACH ROW EXECUTE FUNCTION agents.guard_client_entry_cap();


-- Threshold audit (H2): EVERY change of `publicacao_limiar` — whatever the
-- write path — lands in agent_audit_log. The actor comes from the
-- transaction-local `agents.audit_actor` setting that
-- `set_agent_publicacao_limiar` sets (NULL for any other path — still logged).
CREATE OR REPLACE FUNCTION agents.audit_agent_limiar_change()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
    VALUES (
        NEW.org_id, NEW.id,
        NULLIF(current_setting('agents.audit_actor', true), '')::UUID,
        'limiar_alterado',
        jsonb_build_object('publicacao_limiar', OLD.publicacao_limiar),
        jsonb_build_object('publicacao_limiar', NEW.publicacao_limiar)
    );
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.audit_agent_limiar_change() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.audit_agent_limiar_change() TO service_role;

CREATE OR REPLACE TRIGGER audit_agent_limiar_change
    AFTER UPDATE OF publicacao_limiar ON agents.agents
    FOR EACH ROW
    WHEN (OLD.publicacao_limiar IS DISTINCT FROM NEW.publicacao_limiar)
    EXECUTE FUNCTION agents.audit_agent_limiar_change();


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


-- Publish a draft: current ativa -> substituida, this -> ativa.
-- The Python gate runs first (it builds the rich 409 body); THIS function is
-- the backstop that cannot be skipped:
--   * M1 — `p_expected_hash` must equal the row's `compiled_hash` (any
--     content write since the gate check NULLed/changed it) → `draft_changed`;
--   * H1/H2 — with a run: it must be this version's, `concluida`, `completa`,
--     non-empty, stamped `p_expected_hash`, score >= the agent's CURRENT
--     threshold, and the agent must still have >= 1 active case; without a
--     run: an override reason with >= 20 non-whitespace chars. Otherwise
--     `eval_required`.
-- Stores the proof-of-use `compiled_prompts` row (`p_texto`/`p_manifest`
-- under `p_expected_hash`, idempotent by hash), snapshots `limiar_aplicado` +
-- `eval_score` and appends the audit row — all in the same transaction, so a
-- version can never become `ativa` without its exact text on record, and a
-- failed publish never leaves a prompt row pinning the draft. Raises `version_not_found`, `version_immutable`,
-- `draft_changed`, `eval_required`.
--
-- `eval_runs`/`eval_cases` are created by 013: PL/pgSQL resolves the table
-- references at first execution (never at CREATE), and the only row-typed
-- variables below are of 012's own `agent_versions`.
CREATE OR REPLACE FUNCTION agents.publish_agent_version(
    p_org_id UUID,
    p_version_id UUID,
    p_published_by UUID,
    p_eval_run_id UUID,
    p_override_reason TEXT,
    p_expected_hash TEXT,
    p_texto TEXT,
    p_manifest JSONB
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_row agents.agent_versions;
    v_prev agents.agent_versions;
    v_limiar NUMERIC(4,3);
    v_score NUMERIC(4,3);
    v_reason TEXT := NULLIF(btrim(p_override_reason, E' \t\r\n'), '');
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
    IF p_expected_hash IS NULL OR v_row.compiled_hash IS DISTINCT FROM p_expected_hash THEN
        RAISE EXCEPTION 'draft_changed' USING ERRCODE = 'P0001';
    END IF;

    -- FOR SHARE: a concurrent threshold change waits for this publish, so
    -- the snapshot is the threshold the gate was actually held to.
    SELECT publicacao_limiar INTO v_limiar FROM agents.agents
    WHERE id = v_row.agent_id AND org_id = p_org_id
    FOR SHARE;

    IF p_eval_run_id IS NOT NULL THEN
        SELECT r.score INTO v_score FROM agents.eval_runs r
        WHERE r.id = p_eval_run_id
          AND r.org_id = p_org_id
          AND r.version_id = p_version_id
          AND r.status = 'concluida'
          AND r.completa
          AND r.total >= 1
          AND r.compiled_hash = p_expected_hash
          AND r.score IS NOT NULL
          AND r.score >= v_limiar;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'eval_required' USING ERRCODE = 'P0001';
        END IF;
        PERFORM 1 FROM agents.eval_cases c
        WHERE c.org_id = p_org_id AND c.agent_id = v_row.agent_id AND c.ativo;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'eval_required' USING ERRCODE = 'P0001';
        END IF;
        v_reason := NULL;
    ELSIF v_reason IS NULL OR length(regexp_replace(v_reason, '\s', '', 'g')) < 20 THEN
        RAISE EXCEPTION 'eval_required' USING ERRCODE = 'P0001';
    END IF;

    IF p_texto IS NULL OR p_manifest IS NULL THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO agents.compiled_prompts (org_id, hash, version_id, client_id, texto, manifest)
    VALUES (p_org_id, p_expected_hash, p_version_id, NULL, p_texto, p_manifest)
    ON CONFLICT (org_id, hash) DO NOTHING;

    SELECT * INTO v_prev FROM agents.agent_versions
    WHERE org_id = p_org_id AND agent_id = v_row.agent_id AND status = 'ativa'
    FOR UPDATE;

    UPDATE agents.agent_versions
    SET status = 'substituida'
    WHERE org_id = p_org_id AND agent_id = v_row.agent_id AND status = 'ativa';

    UPDATE agents.agent_versions
    SET status = 'ativa',
        published_by = p_published_by,
        published_at = now(),
        eval_run_id = p_eval_run_id,
        publish_override_reason = v_reason,
        limiar_aplicado = v_limiar,
        eval_score = v_score
    WHERE id = p_version_id AND org_id = p_org_id;

    INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
    VALUES (
        p_org_id, v_row.agent_id, p_published_by,
        CASE WHEN p_eval_run_id IS NULL THEN 'publicado_override' ELSE 'publicado' END,
        CASE WHEN v_prev.id IS NULL THEN NULL
             ELSE jsonb_build_object('version_id', v_prev.id, 'versao', v_prev.versao) END,
        jsonb_build_object(
            'version_id', v_row.id, 'versao', v_row.versao, 'compiled_hash', v_row.compiled_hash,
            'eval_run_id', p_eval_run_id, 'eval_score', v_score, 'limiar_aplicado', v_limiar,
            'override_reason', v_reason
        )
    );
END;
$$;

REVOKE ALL ON FUNCTION agents.publish_agent_version(UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.publish_agent_version(UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, JSONB) TO service_role;


-- Discard a draft (children cascade; so do its eval runs — 013's
-- `eval_runs.version_id ON DELETE CASCADE`). A draft referenced by a stored
-- compiled prompt still refuses (FK, no cascade → the store's
-- `draft_referenced`). Audited. Raises `version_not_found`,
-- `version_immutable`.
CREATE OR REPLACE FUNCTION agents.discard_agent_draft(
    p_org_id UUID,
    p_version_id UUID,
    p_actor UUID
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

    DELETE FROM agents.agent_versions WHERE id = p_version_id AND org_id = p_org_id;

    INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
    VALUES (
        p_org_id, v_row.agent_id, p_actor, 'rascunho_descartado',
        jsonb_build_object('version_id', v_row.id, 'versao', v_row.versao, 'compiled_hash', v_row.compiled_hash),
        NULL
    );
END;
$$;

REVOKE ALL ON FUNCTION agents.discard_agent_draft(UUID, UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.discard_agent_draft(UUID, UUID, UUID) TO service_role;


-- Change the publish threshold with an attributed audit row (H2). The audit
-- row itself is written by the `audit_agent_limiar_change` trigger; this
-- function only makes the actor known to it. Raises `agent_not_found`.
CREATE OR REPLACE FUNCTION agents.set_agent_publicacao_limiar(
    p_org_id UUID,
    p_agent_id UUID,
    p_limiar NUMERIC,
    p_actor UUID
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
BEGIN
    PERFORM set_config('agents.audit_actor', COALESCE(p_actor::TEXT, ''), true);
    UPDATE agents.agents SET publicacao_limiar = p_limiar
    WHERE id = p_agent_id AND org_id = p_org_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent_not_found' USING ERRCODE = 'P0001';
    END IF;
    PERFORM set_config('agents.audit_actor', '', true);
END;
$$;

REVOKE ALL ON FUNCTION agents.set_agent_publicacao_limiar(UUID, UUID, NUMERIC, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.set_agent_publicacao_limiar(UUID, UUID, NUMERIC, UUID) TO service_role;


-- Full replace of a draft's sections in ONE transaction (`PUT
-- .../draft/sections`). `p_secoes` = [{id?, chave, titulo, ordem, conteudo,
-- ativo}]: an `id` of an existing section of THIS version keeps that row;
-- every other element becomes a new row; sections not named are deleted.
-- The chave unique is deferred for the statement set so two kept rows may
-- swap chaves. Raises `version_not_found`, `version_immutable`,
-- `chave_conflict`, `invalid_payload`.
CREATE OR REPLACE FUNCTION agents.replace_draft_sections(
    p_org_id UUID,
    p_version_id UUID,
    p_secoes JSONB
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
    IF jsonb_typeof(p_secoes) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    PERFORM 1 FROM jsonb_to_recordset(p_secoes) AS x(chave TEXT)
    GROUP BY x.chave HAVING count(*) > 1;
    IF FOUND THEN
        RAISE EXCEPTION 'chave_conflict' USING ERRCODE = 'P0001';
    END IF;

    SET CONSTRAINTS agents.agent_prompt_sections_version_chave_key DEFERRED;

    DELETE FROM agents.agent_prompt_sections s
    WHERE s.version_id = p_version_id AND s.org_id = p_org_id
      AND s.id NOT IN (
          SELECT x.id FROM jsonb_to_recordset(p_secoes) AS x(id UUID) WHERE x.id IS NOT NULL
      );

    UPDATE agents.agent_prompt_sections s
    SET chave = x.chave, titulo = x.titulo, ordem = x.ordem,
        conteudo = COALESCE(x.conteudo, ''), ativo = COALESCE(x.ativo, true)
    FROM jsonb_to_recordset(p_secoes)
        AS x(id UUID, chave TEXT, titulo TEXT, ordem INT, conteudo TEXT, ativo BOOLEAN)
    WHERE s.id = x.id AND s.version_id = p_version_id AND s.org_id = p_org_id;

    INSERT INTO agents.agent_prompt_sections (org_id, version_id, chave, titulo, ordem, conteudo, ativo)
    SELECT p_org_id, p_version_id, x.chave, x.titulo, x.ordem, COALESCE(x.conteudo, ''), COALESCE(x.ativo, true)
    FROM jsonb_to_recordset(p_secoes)
        AS x(id UUID, chave TEXT, titulo TEXT, ordem INT, conteudo TEXT, ativo BOOLEAN)
    WHERE x.id IS NULL
       OR NOT EXISTS (
           SELECT 1 FROM agents.agent_prompt_sections s
           WHERE s.id = x.id AND s.version_id = p_version_id AND s.org_id = p_org_id
       );
END;
$$;

REVOKE ALL ON FUNCTION agents.replace_draft_sections(UUID, UUID, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.replace_draft_sections(UUID, UUID, JSONB) TO service_role;


-- Replace a draft's sections AND skills (+ their files) in ONE transaction —
-- the importer's write (§D5 "replaces the draft's sections + skills"). Either
-- the whole bundle lands or nothing does. `p_secoes` as above (ids ignored —
-- every row is new); `p_skills` = [{nome, descricao, corpo, ordem, ativo,
-- arquivos: [{caminho, titulo, conteudo}]}]. Raises `version_not_found`,
-- `version_immutable`, `chave_conflict`, `skill_exists`, `invalid_payload`.
CREATE OR REPLACE FUNCTION agents.replace_draft_bundle(
    p_org_id UUID,
    p_version_id UUID,
    p_secoes JSONB,
    p_skills JSONB
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_status TEXT;
    v_skill JSONB;
    v_skill_id UUID;
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
    IF jsonb_typeof(p_secoes) IS DISTINCT FROM 'array' OR jsonb_typeof(p_skills) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    PERFORM 1 FROM jsonb_to_recordset(p_secoes) AS x(chave TEXT)
    GROUP BY x.chave HAVING count(*) > 1;
    IF FOUND THEN
        RAISE EXCEPTION 'chave_conflict' USING ERRCODE = 'P0001';
    END IF;
    PERFORM 1 FROM jsonb_to_recordset(p_skills) AS x(nome TEXT)
    GROUP BY x.nome HAVING count(*) > 1;
    IF FOUND THEN
        RAISE EXCEPTION 'skill_exists' USING ERRCODE = 'P0001';
    END IF;

    DELETE FROM agents.agent_prompt_sections WHERE version_id = p_version_id AND org_id = p_org_id;
    DELETE FROM agents.agent_skills WHERE version_id = p_version_id AND org_id = p_org_id;

    INSERT INTO agents.agent_prompt_sections (org_id, version_id, chave, titulo, ordem, conteudo, ativo)
    SELECT p_org_id, p_version_id, x.chave, x.titulo, x.ordem, COALESCE(x.conteudo, ''), COALESCE(x.ativo, true)
    FROM jsonb_to_recordset(p_secoes)
        AS x(chave TEXT, titulo TEXT, ordem INT, conteudo TEXT, ativo BOOLEAN);

    FOR v_skill IN SELECT value FROM jsonb_array_elements(p_skills)
    LOOP
        INSERT INTO agents.agent_skills (org_id, version_id, nome, descricao, corpo, ordem, ativo)
        VALUES (
            p_org_id, p_version_id, v_skill ->> 'nome', v_skill ->> 'descricao',
            COALESCE(v_skill ->> 'corpo', ''), COALESCE((v_skill ->> 'ordem')::INT, 0),
            COALESCE((v_skill ->> 'ativo')::BOOLEAN, true)
        )
        RETURNING id INTO v_skill_id;

        INSERT INTO agents.agent_skill_files (org_id, skill_id, caminho, titulo, conteudo)
        SELECT p_org_id, v_skill_id, f.caminho, f.titulo, COALESCE(f.conteudo, '')
        FROM jsonb_to_recordset(COALESCE(v_skill -> 'arquivos', '[]'::JSONB))
            AS f(caminho TEXT, titulo TEXT, conteudo TEXT);
    END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION agents.replace_draft_bundle(UUID, UUID, JSONB, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.replace_draft_bundle(UUID, UUID, JSONB, JSONB) TO service_role;


-- LGPD erasure (L2): the ONLY path that may delete compiled prompts —
-- every prompt compiled for one client of one org. Opens the
-- `guard_compiled_prompt_immutable` DELETE gate for this transaction only.
-- Returns the number of rows erased. Raises `client_required`.
CREATE OR REPLACE FUNCTION agents.erase_compiled_prompts(
    p_org_id UUID,
    p_client_id UUID
) RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_count INT;
BEGIN
    IF p_org_id IS NULL OR p_client_id IS NULL THEN
        RAISE EXCEPTION 'client_required' USING ERRCODE = 'P0001';
    END IF;
    PERFORM set_config('agents.compiled_prompt_erasure', 'on', true);
    DELETE FROM agents.compiled_prompts WHERE org_id = p_org_id AND client_id = p_client_id;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    PERFORM set_config('agents.compiled_prompt_erasure', 'off', true);
    RETURN v_count;
END;
$$;

REVOKE ALL ON FUNCTION agents.erase_compiled_prompts(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.erase_compiled_prompts(UUID, UUID) TO service_role;


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
