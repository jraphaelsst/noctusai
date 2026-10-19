-- ============================================================================
-- 031_julia_v2_conteudo.sql -- Julia v2, slice A-CONT (projects/julia-v2/CONTRACT.md
-- section 2.2 + section 2.6 + owner answer Q2).
--
-- Every string a model reads lives in DB rows, versioned with the agent version
-- and covered by its compiled hash. CODE KEEPS STRUCTURE ONLY -- this migration
-- ships tables and constraints, NEVER content (D3): the first content is written
-- as data through the Studio API / the noctus.agents.content MCP tool.
--
--  1. agents.agents gets a DEFINITION SCOPE (Q2: "the SDR is one thing in the general
--     agents app, specified to each org's context"):
--       org         the existing shape -- this row owns its versions (dev-advisors,
--                   one-chat, bia, ...). The default; nothing existing changes.
--       plataforma  THE definition of the key (versions, sections, textos, tools,
--                   decisions, org-spec declarations). It lives in the platform org
--                   (organizations.is_platform), edited there by platform admins,
--                   published once, used by every org. At most one per key.
--       instancia   an org's instance of a plataforma definition: activation, LLM key,
--                   budget, tokens -- NO versions of its own; definition_agent_id
--                   points at the plataforma row.
--     conteudo_modo 'linhas' = the compiler reads every human-readable string from
--     rows (plataforma/instancia are always linhas); 'legado' = the pre-v2 compiler
--     strings, kept until the last legacy agent migrates (ratcheted by the keeper
--     check_agent_prompt_text_in_code).
--  2. Five version-scoped content tables (copied by every new draft, immutable once
--     published, a write NULLs the draft's compiled_hash): agent_version_textos,
--     agent_version_ferramentas, agent_version_decisoes, agent_version_specs (the
--     org-spec DECLARATIONS the definition's {{org.chave}} placeholders point at).
--  3. agents.textos_plataforma -- platform-wide texts (judge prompt, template content).
--  4. agents.agent_org_specs -- the per-org VALUES of the declared specs (live org data,
--     not versioned with the definition; rendered visibly in the compiled view per org).
--  5. decisao-* sections copied into decisoes rows (typed options are added later by the
--     content seed; the sections stay -- A-RT switches the reader, then they are dropped).
--  6. agent_audit_log.acao CHECK extended (this slice + the section 5.1 list, so the
--     parallel slices need not redefine the constraint and clobber each other).
--
-- Re-run safe. NOT applied to any database by this slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. definition scope ────────────────────────────────────────────────────

ALTER TABLE agents.agents
    ADD COLUMN IF NOT EXISTS definition_scope TEXT NOT NULL DEFAULT 'org',
    ADD COLUMN IF NOT EXISTS definition_agent_id UUID NULL REFERENCES agents.agents(id),
    ADD COLUMN IF NOT EXISTS conteudo_modo TEXT NOT NULL DEFAULT 'legado';

ALTER TABLE agents.agents DROP CONSTRAINT IF EXISTS agents_definition_scope_check;
ALTER TABLE agents.agents ADD CONSTRAINT agents_definition_scope_check
    CHECK (definition_scope IN ('org', 'plataforma', 'instancia'));

ALTER TABLE agents.agents DROP CONSTRAINT IF EXISTS agents_conteudo_modo_check;
ALTER TABLE agents.agents ADD CONSTRAINT agents_conteudo_modo_check
    CHECK (conteudo_modo IN ('legado', 'linhas'));

-- An instance names its definition; nothing else does.
ALTER TABLE agents.agents DROP CONSTRAINT IF EXISTS agents_definition_agent_scope;
ALTER TABLE agents.agents ADD CONSTRAINT agents_definition_agent_scope
    CHECK ((definition_scope = 'instancia') = (definition_agent_id IS NOT NULL));

-- A platform-defined agent is never in legacy content mode.
ALTER TABLE agents.agents DROP CONSTRAINT IF EXISTS agents_scope_conteudo;
ALTER TABLE agents.agents ADD CONSTRAINT agents_scope_conteudo
    CHECK (definition_scope = 'org' OR conteudo_modo = 'linhas');

-- ONE platform definition per key.
CREATE UNIQUE INDEX IF NOT EXISTS agents_one_plataforma_per_key
    ON agents.agents (key) WHERE definition_scope = 'plataforma';
CREATE INDEX IF NOT EXISTS idx_agents_agents_definition_agent
    ON agents.agents (definition_agent_id) WHERE definition_agent_id IS NOT NULL;

-- Scope integrity the CHECKs cannot see (they cannot read another row / table):
--   * a 'plataforma' row must belong to the platform org (organizations.is_platform);
--   * an 'instancia' row must point at a 'plataforma' row of the SAME key;
--   * scope and definition_agent_id never change after insert; conteudo_modo only
--     moves legado -> linhas (a published 'linhas' agent never drops back).
-- Raises definition_not_platform, definition_invalid, scope_immutable.
CREATE OR REPLACE FUNCTION agents.guard_agent_definition_scope()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_def agents.agents;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.definition_scope IS DISTINCT FROM OLD.definition_scope
           OR NEW.definition_agent_id IS DISTINCT FROM OLD.definition_agent_id
           OR (OLD.conteudo_modo = 'linhas' AND NEW.conteudo_modo <> 'linhas') THEN
            RAISE EXCEPTION 'scope_immutable' USING ERRCODE = 'P0001';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.definition_scope = 'plataforma' THEN
        PERFORM 1 FROM public.organizations o WHERE o.id = NEW.org_id AND o.is_platform;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'definition_not_platform' USING ERRCODE = 'P0001';
        END IF;
    ELSIF NEW.definition_scope = 'instancia' THEN
        SELECT * INTO v_def FROM agents.agents WHERE id = NEW.definition_agent_id;
        IF NOT FOUND OR v_def.definition_scope <> 'plataforma' OR v_def.key <> NEW.key THEN
            RAISE EXCEPTION 'definition_invalid' USING ERRCODE = 'P0001';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_agent_definition_scope() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_agent_definition_scope() TO service_role;

CREATE OR REPLACE TRIGGER guard_agent_definition_scope
    BEFORE INSERT OR UPDATE ON agents.agents
    FOR EACH ROW EXECUTE FUNCTION agents.guard_agent_definition_scope();


-- ── 2. version-scoped content tables ───────────────────────────────────────

-- Typed options of a decision: [] (a row moved from a decisao-* section, options still
-- to be set) or >= 1 object {valor, rotulo, padrao} with unique valores and EXACTLY ONE
-- padrao (the answer used when the asker cannot be served -- D13). The publish gate
-- (app code) additionally refuses an empty list.
CREATE OR REPLACE FUNCTION agents.decisao_opcoes_ok(p_opcoes JSONB)
RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE
AS $$
    SELECT CASE
        WHEN jsonb_typeof(p_opcoes) IS DISTINCT FROM 'array' THEN false
        WHEN jsonb_array_length(p_opcoes) = 0 THEN true
        ELSE (
            SELECT bool_and(
                       jsonb_typeof(o) = 'object'
                       AND jsonb_typeof(o -> 'valor') = 'string' AND length(o ->> 'valor') > 0
                       AND jsonb_typeof(o -> 'rotulo') = 'string'
                       AND jsonb_typeof(o -> 'padrao') = 'boolean'
                   )
               AND count(*) FILTER (WHERE o -> 'padrao' = 'true'::jsonb) = 1
               AND count(DISTINCT o ->> 'valor') = count(*)
            FROM jsonb_array_elements(p_opcoes) AS o
        )
    END
$$;

CREATE TABLE IF NOT EXISTS agents.agent_version_textos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    chave TEXT NOT NULL CHECK (chave ~ '^[a-z0-9]+(\.[a-z0-9_]+)+$'),
    conteudo TEXT NOT NULL DEFAULT '' CHECK (length(conteudo) <= 8000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, chave)
);

CREATE TABLE IF NOT EXISTS agents.agent_version_ferramentas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    ferramenta TEXT NOT NULL CHECK (ferramenta ~ '^[a-z][a-z0-9_]{1,63}$'),
    ativo BOOLEAN NOT NULL DEFAULT true,
    descricao TEXT NOT NULL CHECK (length(btrim(descricao)) BETWEEN 1 AND 2000),
    parametros JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(parametros) = 'object'),
    obrigatoria_skill TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, ferramenta)
);

CREATE TABLE IF NOT EXISTS agents.agent_version_decisoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    chave TEXT NOT NULL CHECK (chave ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    titulo TEXT NOT NULL,
    regra TEXT NOT NULL DEFAULT '' CHECK (length(regra) <= 8000),
    opcoes JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (agents.decisao_opcoes_ok(opcoes)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, chave)
);

-- The org-spec DECLARATIONS: which {{org.chave}} placeholders this definition version
-- uses, how to ask the org for each, and whether the instance may run without it.
CREATE TABLE IF NOT EXISTS agents.agent_version_specs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    chave TEXT NOT NULL CHECK (chave ~ '^[a-z][a-z0-9_]{1,63}$'),
    rotulo TEXT NOT NULL CHECK (length(btrim(rotulo)) > 0),
    descricao TEXT NOT NULL DEFAULT '' CHECK (length(descricao) <= 2000),
    tipo TEXT NOT NULL DEFAULT 'texto' CHECK (tipo IN ('texto', 'texto_longo')),
    obrigatoria BOOLEAN NOT NULL DEFAULT true,
    exemplo TEXT NULL CHECK (exemplo IS NULL OR length(exemplo) <= 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, chave)
);

-- ── decisao-* sections -> decisoes rows (BEFORE the immutability triggers exist, so the
-- frozen published versions get their rows too). Copy, not move: the legacy channel reader
-- still reads the section until A-RT switches it; the sections are dropped after.
INSERT INTO agents.agent_version_decisoes (org_id, version_id, chave, titulo, regra, opcoes)
SELECT s.org_id, s.version_id, substr(s.chave, length('decisao-') + 1), s.titulo, s.conteudo, '[]'::jsonb
FROM agents.agent_prompt_sections s
WHERE s.chave LIKE 'decisao-%' AND length(s.chave) > length('decisao-')
ON CONFLICT (version_id, chave) DO NOTHING;

-- RLS + grants + triggers for the four content tables (explicit statements: a DO block that
-- builds policies is invisible to the policy-rollout static walk).

ALTER TABLE agents.agent_version_textos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "agent_version_textos_select_own_org" ON agents.agent_version_textos;
CREATE POLICY "agent_version_textos_select_own_org" ON agents.agent_version_textos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('agents')));
DROP POLICY IF EXISTS "service_role_bypass" ON agents.agent_version_textos;
CREATE POLICY "service_role_bypass" ON agents.agent_version_textos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX IF NOT EXISTS idx_agents_agent_version_textos_org ON agents.agent_version_textos (org_id);
CREATE INDEX IF NOT EXISTS idx_agents_agent_version_textos_version ON agents.agent_version_textos (version_id);
REVOKE ALL ON agents.agent_version_textos FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_version_textos FROM authenticated;
CREATE OR REPLACE TRIGGER set_updated_at_agent_version_textos
    BEFORE UPDATE ON agents.agent_version_textos
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
-- 012's guard: locks the parent version, refuses a non-draft, NULLs the draft's compiled_hash
-- (every content write is hash-visible, M1).
CREATE OR REPLACE TRIGGER guard_agent_version_textos_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.agent_version_textos
    FOR EACH ROW EXECUTE FUNCTION agents.guard_version_child_immutable();

ALTER TABLE agents.agent_version_ferramentas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "agent_version_ferramentas_select_own_org" ON agents.agent_version_ferramentas;
CREATE POLICY "agent_version_ferramentas_select_own_org" ON agents.agent_version_ferramentas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('agents')));
DROP POLICY IF EXISTS "service_role_bypass" ON agents.agent_version_ferramentas;
CREATE POLICY "service_role_bypass" ON agents.agent_version_ferramentas
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX IF NOT EXISTS idx_agents_agent_version_ferramentas_org ON agents.agent_version_ferramentas (org_id);
CREATE INDEX IF NOT EXISTS idx_agents_agent_version_ferramentas_version ON agents.agent_version_ferramentas (version_id);
REVOKE ALL ON agents.agent_version_ferramentas FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_version_ferramentas FROM authenticated;
CREATE OR REPLACE TRIGGER set_updated_at_agent_version_ferramentas
    BEFORE UPDATE ON agents.agent_version_ferramentas
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
-- 012's guard: locks the parent version, refuses a non-draft, NULLs the draft's compiled_hash
-- (every content write is hash-visible, M1).
CREATE OR REPLACE TRIGGER guard_agent_version_ferramentas_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.agent_version_ferramentas
    FOR EACH ROW EXECUTE FUNCTION agents.guard_version_child_immutable();

ALTER TABLE agents.agent_version_decisoes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "agent_version_decisoes_select_own_org" ON agents.agent_version_decisoes;
CREATE POLICY "agent_version_decisoes_select_own_org" ON agents.agent_version_decisoes
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('agents')));
DROP POLICY IF EXISTS "service_role_bypass" ON agents.agent_version_decisoes;
CREATE POLICY "service_role_bypass" ON agents.agent_version_decisoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX IF NOT EXISTS idx_agents_agent_version_decisoes_org ON agents.agent_version_decisoes (org_id);
CREATE INDEX IF NOT EXISTS idx_agents_agent_version_decisoes_version ON agents.agent_version_decisoes (version_id);
REVOKE ALL ON agents.agent_version_decisoes FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_version_decisoes FROM authenticated;
CREATE OR REPLACE TRIGGER set_updated_at_agent_version_decisoes
    BEFORE UPDATE ON agents.agent_version_decisoes
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
-- 012's guard: locks the parent version, refuses a non-draft, NULLs the draft's compiled_hash
-- (every content write is hash-visible, M1).
CREATE OR REPLACE TRIGGER guard_agent_version_decisoes_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.agent_version_decisoes
    FOR EACH ROW EXECUTE FUNCTION agents.guard_version_child_immutable();

ALTER TABLE agents.agent_version_specs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "agent_version_specs_select_own_org" ON agents.agent_version_specs;
CREATE POLICY "agent_version_specs_select_own_org" ON agents.agent_version_specs
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('agents')));
DROP POLICY IF EXISTS "service_role_bypass" ON agents.agent_version_specs;
CREATE POLICY "service_role_bypass" ON agents.agent_version_specs
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX IF NOT EXISTS idx_agents_agent_version_specs_org ON agents.agent_version_specs (org_id);
CREATE INDEX IF NOT EXISTS idx_agents_agent_version_specs_version ON agents.agent_version_specs (version_id);
REVOKE ALL ON agents.agent_version_specs FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_version_specs FROM authenticated;
CREATE OR REPLACE TRIGGER set_updated_at_agent_version_specs
    BEFORE UPDATE ON agents.agent_version_specs
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
-- 012's guard: locks the parent version, refuses a non-draft, NULLs the draft's compiled_hash
-- (every content write is hash-visible, M1).
CREATE OR REPLACE TRIGGER guard_agent_version_specs_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.agent_version_specs
    FOR EACH ROW EXECUTE FUNCTION agents.guard_version_child_immutable();

-- A new draft based on a version carries that version's content tables. A TRIGGER rather
-- than a third redefinition of create_agent_draft (012 -> 024 -> here): the sibling slices
-- (qualification pin, threads) extend the draft the same way and none overwrites another.
CREATE OR REPLACE FUNCTION agents.copy_version_conteudo()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    IF NEW.based_on_version_id IS NULL OR NEW.status <> 'rascunho' THEN
        RETURN NEW;
    END IF;
    INSERT INTO agents.agent_version_textos (org_id, version_id, chave, conteudo)
    SELECT NEW.org_id, NEW.id, chave, conteudo
    FROM agents.agent_version_textos WHERE version_id = NEW.based_on_version_id;
    INSERT INTO agents.agent_version_ferramentas
        (org_id, version_id, ferramenta, ativo, descricao, parametros, obrigatoria_skill)
    SELECT NEW.org_id, NEW.id, ferramenta, ativo, descricao, parametros, obrigatoria_skill
    FROM agents.agent_version_ferramentas WHERE version_id = NEW.based_on_version_id;
    INSERT INTO agents.agent_version_decisoes (org_id, version_id, chave, titulo, regra, opcoes)
    SELECT NEW.org_id, NEW.id, chave, titulo, regra, opcoes
    FROM agents.agent_version_decisoes WHERE version_id = NEW.based_on_version_id;
    INSERT INTO agents.agent_version_specs
        (org_id, version_id, chave, rotulo, descricao, tipo, obrigatoria, exemplo)
    SELECT NEW.org_id, NEW.id, chave, rotulo, descricao, tipo, obrigatoria, exemplo
    FROM agents.agent_version_specs WHERE version_id = NEW.based_on_version_id;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.copy_version_conteudo() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.copy_version_conteudo() TO service_role;

CREATE OR REPLACE TRIGGER copy_version_conteudo
    AFTER INSERT ON agents.agent_versions
    FOR EACH ROW EXECUTE FUNCTION agents.copy_version_conteudo();

-- Replace-set writers: ONE .rpc() = one transaction; the whole set lands or nothing does.
-- Each raises version_not_found / version_immutable / invalid_payload / chave_conflict.
CREATE OR REPLACE FUNCTION agents.replace_draft_conteudo(
    p_org_id UUID,
    p_version_id UUID,
    p_tabela TEXT,
    p_itens JSONB
) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
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
    IF jsonb_typeof(p_itens) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;

    IF p_tabela = 'textos' THEN
        PERFORM 1 FROM jsonb_to_recordset(p_itens) AS x(chave TEXT) GROUP BY x.chave HAVING count(*) > 1;
        IF FOUND THEN RAISE EXCEPTION 'chave_conflict' USING ERRCODE = 'P0001'; END IF;
        DELETE FROM agents.agent_version_textos WHERE version_id = p_version_id AND org_id = p_org_id;
        INSERT INTO agents.agent_version_textos (org_id, version_id, chave, conteudo)
        SELECT p_org_id, p_version_id, x.chave, COALESCE(x.conteudo, '')
        FROM jsonb_to_recordset(p_itens) AS x(chave TEXT, conteudo TEXT);

    ELSIF p_tabela = 'ferramentas' THEN
        PERFORM 1 FROM jsonb_to_recordset(p_itens) AS x(ferramenta TEXT) GROUP BY x.ferramenta HAVING count(*) > 1;
        IF FOUND THEN RAISE EXCEPTION 'chave_conflict' USING ERRCODE = 'P0001'; END IF;
        DELETE FROM agents.agent_version_ferramentas WHERE version_id = p_version_id AND org_id = p_org_id;
        INSERT INTO agents.agent_version_ferramentas
            (org_id, version_id, ferramenta, ativo, descricao, parametros, obrigatoria_skill)
        SELECT p_org_id, p_version_id, x.ferramenta, COALESCE(x.ativo, true), x.descricao,
               COALESCE(x.parametros, '{}'::jsonb), x.obrigatoria_skill
        FROM jsonb_to_recordset(p_itens)
            AS x(ferramenta TEXT, ativo BOOLEAN, descricao TEXT, parametros JSONB, obrigatoria_skill TEXT);

    ELSIF p_tabela = 'decisoes' THEN
        PERFORM 1 FROM jsonb_to_recordset(p_itens) AS x(chave TEXT) GROUP BY x.chave HAVING count(*) > 1;
        IF FOUND THEN RAISE EXCEPTION 'chave_conflict' USING ERRCODE = 'P0001'; END IF;
        DELETE FROM agents.agent_version_decisoes WHERE version_id = p_version_id AND org_id = p_org_id;
        INSERT INTO agents.agent_version_decisoes (org_id, version_id, chave, titulo, regra, opcoes)
        SELECT p_org_id, p_version_id, x.chave, x.titulo, COALESCE(x.regra, ''), COALESCE(x.opcoes, '[]'::jsonb)
        FROM jsonb_to_recordset(p_itens) AS x(chave TEXT, titulo TEXT, regra TEXT, opcoes JSONB);

    ELSIF p_tabela = 'specs' THEN
        PERFORM 1 FROM jsonb_to_recordset(p_itens) AS x(chave TEXT) GROUP BY x.chave HAVING count(*) > 1;
        IF FOUND THEN RAISE EXCEPTION 'chave_conflict' USING ERRCODE = 'P0001'; END IF;
        DELETE FROM agents.agent_version_specs WHERE version_id = p_version_id AND org_id = p_org_id;
        INSERT INTO agents.agent_version_specs
            (org_id, version_id, chave, rotulo, descricao, tipo, obrigatoria, exemplo)
        SELECT p_org_id, p_version_id, x.chave, x.rotulo, COALESCE(x.descricao, ''),
               COALESCE(x.tipo, 'texto'), COALESCE(x.obrigatoria, true), x.exemplo
        FROM jsonb_to_recordset(p_itens)
            AS x(chave TEXT, rotulo TEXT, descricao TEXT, tipo TEXT, obrigatoria BOOLEAN, exemplo TEXT);

    ELSE
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
END;
$$;

REVOKE ALL ON FUNCTION agents.replace_draft_conteudo(UUID, UUID, TEXT, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.replace_draft_conteudo(UUID, UUID, TEXT, JSONB) TO service_role;


-- ── 3. platform-wide texts ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.textos_plataforma (
    chave TEXT PRIMARY KEY CHECK (chave ~ '^[a-z0-9]+(\.[a-z0-9_]+)+$'),
    conteudo TEXT NOT NULL DEFAULT '' CHECK (length(conteudo) <= 8000),
    updated_by UUID NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.textos_plataforma ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.textos_plataforma;
CREATE POLICY "service_role_bypass" ON agents.textos_plataforma
    FOR ALL TO service_role USING (true) WITH CHECK (true);
-- Platform text, not tenant data: no authenticated/anon read path at all (the API gates it).
REVOKE ALL ON agents.textos_plataforma FROM anon, authenticated;


-- ── 4. per-org spec values ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.agent_org_specs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_key TEXT NOT NULL CHECK (agent_key <> ''),
    chave TEXT NOT NULL CHECK (chave ~ '^[a-z][a-z0-9_]{1,63}$'),
    valor TEXT NOT NULL DEFAULT '' CHECK (length(valor) <= 20000),
    updated_by UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, agent_key, chave)
);

ALTER TABLE agents.agent_org_specs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "agent_org_specs_select_own_org" ON agents.agent_org_specs;
CREATE POLICY "agent_org_specs_select_own_org" ON agents.agent_org_specs
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('agents')));
DROP POLICY IF EXISTS "service_role_bypass" ON agents.agent_org_specs;
CREATE POLICY "service_role_bypass" ON agents.agent_org_specs
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX IF NOT EXISTS idx_agents_agent_org_specs_org ON agents.agent_org_specs (org_id, agent_key);
REVOKE ALL ON agents.agent_org_specs FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.agent_org_specs FROM authenticated;

CREATE OR REPLACE TRIGGER set_updated_at_agent_org_specs
    BEFORE UPDATE ON agents.agent_org_specs
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();


-- ── 5. audit actions ───────────────────────────────────────────────────────
-- 012's inline CHECK, re-declared once with this slice's actions AND the contract
-- section 5.1 list (modo_alterado, conversa_pausada, conversa_retomada, padrao_publicado),
-- so the controls / qualification slices never have to redefine it.
ALTER TABLE agents.agent_audit_log DROP CONSTRAINT IF EXISTS agent_audit_log_acao_check;
ALTER TABLE agents.agent_audit_log ADD CONSTRAINT agent_audit_log_acao_check
    CHECK (acao IN (
        'limiar_alterado', 'publicado', 'publicado_override', 'rascunho_descartado',
        'conteudo_editado_mcp', 'specs_org_editadas', 'definicao_lida',
        'modo_alterado', 'conversa_pausada', 'conversa_retomada', 'padrao_publicado'
    ));
