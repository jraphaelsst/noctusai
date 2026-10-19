-- ============================================================================
-- 039_julia_v2_skills_compartilhadas.sql -- Julia v2 shared, versioned SKILL
-- LIBRARY (products/agents/projects/julia-v2/CONTRACT.md D7, D8, sections 3.5 E2,
-- 4.2, 9).
--
-- Owner requirement: agents MUST use skills instead of their own judgement,
-- from ONE standardised library used the same way by every agent. Until now a
-- skill was a per-agent-version copy (agent_skills / agent_skill_files, 012).
--
-- 1. Library (platform-wide, like the qualification standard of 032 -- owner
--    decision Q2: one definition for every org, so NO org_id here):
--    skills_biblioteca (key + name), skill_versoes (the model-facing index
--    description + the body), skill_versao_arquivos (reference files). A
--    PUBLISHED skill version is immutable (triggers); a new version is a draft
--    copied from the last one.
-- 2. agent_version_skill_refs: an agent version PINS library versions
--    (obrigatoria_para = the tools that refuse until this skill was opened in
--    the thread). Hash-covered: any write NULLs the draft's compiled_hash through
--    012's guard_version_child_immutable. A new draft inherits its base version's
--    pins by an AFTER INSERT trigger (the pattern 031 established -- no third
--    redefinition of create_agent_draft).
-- 3. Two RPCs (one transaction each): criar_rascunho_skill / publicar_skill_versao.
--
-- IP RULE (CONTRACT 0.4): a skill body is platform IP. Every table is
-- SERVICE-ROLE ONLY -- RLS on, the single service_role_bypass policy, and NO
-- grant to authenticated / anon. The API is the only read path and it is
-- platform-admin only.
--
-- NO CONTENT is seeded here (D3): the skills' text arrives as DB data written
-- through the noctus.agents.content MCP tool.
--
-- Idempotent where it can be. NOT applied by this slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. library ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.skills_biblioteca (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- The name the model passes to abrir_skill (same shape as agent_skills.nome).
    chave TEXT NOT NULL CHECK (chave ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(chave) <= 64),
    -- Admin-facing label and note: NEVER sent to a model.
    nome TEXT NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
    descricao TEXT NULL CHECK (descricao IS NULL OR length(descricao) <= 1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_skills_biblioteca_chave UNIQUE (chave)
);

CREATE TABLE IF NOT EXISTS agents.skill_versoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id UUID NOT NULL REFERENCES agents.skills_biblioteca(id),
    versao INT NOT NULL CHECK (versao >= 1),
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'publicada', 'arquivada')),
    -- The one-line index entry the model sees ("when to open this skill").
    descricao_modelo TEXT NOT NULL DEFAULT '' CHECK (length(descricao_modelo) <= 1024),
    corpo TEXT NOT NULL DEFAULT '' CHECK (length(corpo) <= 60000),
    notas TEXT NULL CHECK (notas IS NULL OR length(notas) <= 2000),
    publicada_em TIMESTAMPTZ NULL,
    publicada_por UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_skill_versoes_skill_versao UNIQUE (skill_id, versao),
    CHECK (status = 'rascunho' OR (publicada_em IS NOT NULL AND publicada_por IS NOT NULL)),
    -- A published skill can always be opened and indexed: both texts are real.
    CHECK (status = 'rascunho' OR (btrim(corpo) <> '' AND btrim(descricao_modelo) <> ''))
);
-- One draft per skill.
CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_versoes_um_rascunho
    ON agents.skill_versoes (skill_id) WHERE status = 'rascunho';

CREATE TABLE IF NOT EXISTS agents.skill_versao_arquivos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_versao_id UUID NOT NULL REFERENCES agents.skill_versoes(id) ON DELETE CASCADE,
    caminho TEXT NOT NULL CHECK (caminho ~ '^[a-z0-9][a-z0-9._/-]*$' AND caminho !~ '\.\.'),
    titulo TEXT NULL CHECK (titulo IS NULL OR length(titulo) <= 200),
    conteudo TEXT NOT NULL DEFAULT '' CHECK (length(conteudo) <= 120000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (skill_versao_id, caminho)
);

CREATE INDEX IF NOT EXISTS idx_skill_versoes_skill ON agents.skill_versoes (skill_id, versao);
CREATE INDEX IF NOT EXISTS idx_skill_versao_arquivos_versao ON agents.skill_versao_arquivos (skill_versao_id);

CREATE OR REPLACE TRIGGER set_updated_at_skills_biblioteca
    BEFORE UPDATE ON agents.skills_biblioteca
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
CREATE OR REPLACE TRIGGER set_updated_at_skill_versoes
    BEFORE UPDATE ON agents.skill_versoes
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
CREATE OR REPLACE TRIGGER set_updated_at_skill_versao_arquivos
    BEFORE UPDATE ON agents.skill_versao_arquivos
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

-- ── immutability: a published version (and its files) never changes ────────

CREATE OR REPLACE FUNCTION agents.guard_skill_versao_immutable()
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
        -- A draft is editable and may be published; never archived directly.
        IF NEW.status = 'arquivada' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        RETURN NEW;
    END IF;
    -- Published: only publicada -> arquivada, every content column frozen.
    IF NOT (OLD.status = 'publicada' AND NEW.status = 'arquivada') THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    IF NEW.skill_id IS DISTINCT FROM OLD.skill_id
       OR NEW.versao IS DISTINCT FROM OLD.versao
       OR NEW.descricao_modelo IS DISTINCT FROM OLD.descricao_modelo
       OR NEW.corpo IS DISTINCT FROM OLD.corpo
       OR NEW.notas IS DISTINCT FROM OLD.notas
       OR NEW.publicada_em IS DISTINCT FROM OLD.publicada_em
       OR NEW.publicada_por IS DISTINCT FROM OLD.publicada_por
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_skill_versao_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_skill_versao_immutable() TO service_role;

CREATE OR REPLACE TRIGGER guard_skill_versao_immutable
    BEFORE UPDATE OR DELETE ON agents.skill_versoes
    FOR EACH ROW EXECUTE FUNCTION agents.guard_skill_versao_immutable();

-- Files keyed by skill_versao_id: the parent row is locked FOR UPDATE before its status is
-- read (serialises against a concurrent publish).
CREATE OR REPLACE FUNCTION agents.guard_skill_arquivo_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_status TEXT;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT status INTO v_status FROM agents.skill_versoes WHERE id = OLD.skill_versao_id FOR UPDATE;
        -- NULL = parent already gone (a cascade from a discarded draft).
        IF v_status IS NOT NULL AND v_status <> 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT status INTO v_status FROM agents.skill_versoes WHERE id = NEW.skill_versao_id FOR UPDATE;
        IF v_status IS DISTINCT FROM 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_skill_arquivo_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_skill_arquivo_immutable() TO service_role;

CREATE OR REPLACE TRIGGER guard_skill_versao_arquivos_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.skill_versao_arquivos
    FOR EACH ROW EXECUTE FUNCTION agents.guard_skill_arquivo_immutable();

-- ── RLS: service-role only (IP) ────────────────────────────────────────────

ALTER TABLE agents.skills_biblioteca ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.skills_biblioteca;
CREATE POLICY "service_role_bypass" ON agents.skills_biblioteca
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.skills_biblioteca FROM anon, authenticated;

ALTER TABLE agents.skill_versoes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.skill_versoes;
CREATE POLICY "service_role_bypass" ON agents.skill_versoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.skill_versoes FROM anon, authenticated;

ALTER TABLE agents.skill_versao_arquivos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.skill_versao_arquivos;
CREATE POLICY "service_role_bypass" ON agents.skill_versao_arquivos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.skill_versao_arquivos FROM anon, authenticated;

-- ── 2. library RPCs ────────────────────────────────────────────────────────

-- New draft of a skill, optionally copied from an existing version (its text and files).
CREATE OR REPLACE FUNCTION agents.criar_rascunho_skill(
    p_skill_id UUID,
    p_notas TEXT,
    p_copiar_de UUID
) RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_novo UUID;
    v_num INT;
BEGIN
    PERFORM 1 FROM agents.skills_biblioteca WHERE id = p_skill_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM agents.skill_versoes WHERE skill_id = p_skill_id AND status = 'rascunho') THEN
        RAISE EXCEPTION 'draft_exists' USING ERRCODE = 'P0001';
    END IF;
    IF p_copiar_de IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM agents.skill_versoes WHERE id = p_copiar_de AND skill_id = p_skill_id
    ) THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;

    SELECT COALESCE(MAX(versao), 0) + 1 INTO v_num FROM agents.skill_versoes WHERE skill_id = p_skill_id;
    INSERT INTO agents.skill_versoes (skill_id, versao, status, notas, descricao_modelo, corpo)
    SELECT p_skill_id, v_num, 'rascunho', p_notas,
           COALESCE((SELECT descricao_modelo FROM agents.skill_versoes WHERE id = p_copiar_de), ''),
           COALESCE((SELECT corpo FROM agents.skill_versoes WHERE id = p_copiar_de), '')
    RETURNING id INTO v_novo;

    IF p_copiar_de IS NOT NULL THEN
        INSERT INTO agents.skill_versao_arquivos (skill_versao_id, caminho, titulo, conteudo)
        SELECT v_novo, caminho, titulo, conteudo
          FROM agents.skill_versao_arquivos WHERE skill_versao_id = p_copiar_de;
    END IF;
    RETURN v_novo;
END;
$$;

-- Publish: the draft becomes `publicada`, the previous `publicada` is archived (pins of
-- agent versions keep pointing at the archived row -- it is immutable, which is the point).
CREATE OR REPLACE FUNCTION agents.publicar_skill_versao(
    p_versao_id UUID,
    p_user_id UUID
) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_status TEXT;
    v_skill UUID;
    v_corpo TEXT;
    v_desc TEXT;
BEGIN
    SELECT status, skill_id, corpo, descricao_modelo INTO v_status, v_skill, v_corpo, v_desc
      FROM agents.skill_versoes WHERE id = p_versao_id FOR UPDATE;
    IF v_status IS NULL THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF v_status <> 'rascunho' THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    IF btrim(v_corpo) = '' OR btrim(v_desc) = '' THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    UPDATE agents.skill_versoes SET status = 'arquivada'
     WHERE skill_id = v_skill AND status = 'publicada';
    UPDATE agents.skill_versoes
       SET status = 'publicada', publicada_em = now(), publicada_por = p_user_id
     WHERE id = p_versao_id;
END;
$$;

REVOKE ALL ON FUNCTION agents.criar_rascunho_skill(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.criar_rascunho_skill(UUID, TEXT, UUID) TO service_role;
REVOKE ALL ON FUNCTION agents.publicar_skill_versao(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.publicar_skill_versao(UUID, UUID) TO service_role;

-- ── 3. the pins on the agent version ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.agent_version_skill_refs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    -- Denormalised from skill_versao_id by the guard below: one pinned version PER skill.
    skill_id UUID NOT NULL REFERENCES agents.skills_biblioteca(id),
    skill_versao_id UUID NOT NULL REFERENCES agents.skill_versoes(id),
    -- Tool names that refuse until this skill was opened in the thread (D7). Shape-checked
    -- here, checked against the tool registry by the compiler.
    obrigatoria_para TEXT[] NOT NULL DEFAULT '{}'
        CHECK (cardinality(obrigatoria_para) <= 32
               AND array_to_string(obrigatoria_para, ',')
                   ~ '^([a-z][a-z0-9_]{1,63})?(,[a-z][a-z0-9_]{1,63})*$'),
    ordem INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, skill_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_version_skill_refs_org ON agents.agent_version_skill_refs (org_id);
CREATE INDEX IF NOT EXISTS idx_agent_version_skill_refs_version ON agents.agent_version_skill_refs (version_id);
CREATE INDEX IF NOT EXISTS idx_agent_version_skill_refs_skill_versao
    ON agents.agent_version_skill_refs (skill_versao_id);

ALTER TABLE agents.agent_version_skill_refs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.agent_version_skill_refs;
CREATE POLICY "service_role_bypass" ON agents.agent_version_skill_refs
    FOR ALL TO service_role USING (true) WITH CHECK (true);
-- Which library skill an agent pins is platform definition: no tenant read path at all.
REVOKE ALL ON agents.agent_version_skill_refs FROM anon, authenticated;

CREATE OR REPLACE TRIGGER set_updated_at_agent_version_skill_refs
    BEFORE UPDATE ON agents.agent_version_skill_refs
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

-- A pin must target a NON-draft skill version (a draft is mutable -- pinning it would defeat
-- immutability) and carries the skill id of it; the org must be the version's own.
CREATE OR REPLACE FUNCTION agents.guard_agent_version_skill_ref()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_status TEXT;
    v_skill UUID;
    v_org UUID;
BEGIN
    SELECT status, skill_id INTO v_status, v_skill FROM agents.skill_versoes WHERE id = NEW.skill_versao_id;
    IF v_status IS NULL OR v_status = 'rascunho' THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    NEW.skill_id := v_skill;
    SELECT org_id INTO v_org FROM agents.agent_versions WHERE id = NEW.version_id;
    IF v_org IS NULL OR v_org IS DISTINCT FROM NEW.org_id THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_agent_version_skill_ref() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_agent_version_skill_ref() TO service_role;

CREATE OR REPLACE TRIGGER guard_agent_version_skill_ref
    BEFORE INSERT OR UPDATE ON agents.agent_version_skill_refs
    FOR EACH ROW EXECUTE FUNCTION agents.guard_agent_version_skill_ref();

-- 012's guard: locks the parent version, refuses a non-draft, NULLs the draft's compiled_hash
-- (every pin change is hash-visible, M1).
CREATE OR REPLACE TRIGGER guard_agent_version_skill_refs_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.agent_version_skill_refs
    FOR EACH ROW EXECUTE FUNCTION agents.guard_version_child_immutable();

-- A new draft based on a version carries that version's pins (031's pattern: a trigger, not
-- another redefinition of create_agent_draft). A pin to an archived skill version is kept as is.
CREATE OR REPLACE FUNCTION agents.copy_version_skill_refs()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    IF NEW.based_on_version_id IS NULL OR NEW.status <> 'rascunho' THEN
        RETURN NEW;
    END IF;
    INSERT INTO agents.agent_version_skill_refs
        (org_id, version_id, skill_id, skill_versao_id, obrigatoria_para, ordem)
    SELECT NEW.org_id, NEW.id, skill_id, skill_versao_id, obrigatoria_para, ordem
    FROM agents.agent_version_skill_refs WHERE version_id = NEW.based_on_version_id;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.copy_version_skill_refs() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.copy_version_skill_refs() TO service_role;

CREATE OR REPLACE TRIGGER copy_version_skill_refs
    AFTER INSERT ON agents.agent_versions
    FOR EACH ROW EXECUTE FUNCTION agents.copy_version_skill_refs();
