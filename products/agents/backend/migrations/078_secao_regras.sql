-- 078 · agent_prompt_sections.regras: the rules a section declares (Q2, owner 2026-11-10).
--
-- Readiness verifies the respectful-disagreement RULE in the agent's effective sections instead of a section KEY: the
-- canonical template now has 15 sections and the rule lives inside `honestidade`. Forward-only, idempotent: re-running
-- adds nothing. The closed rule list is app/studio/regras_secao.py (the stores refuse an unknown rule with a 422).
-- Deploy order: apply this migration, THEN deploy the image (the new code selects/writes the column).

SET search_path = agents, public;

ALTER TABLE agents.agent_prompt_sections
    ADD COLUMN IF NOT EXISTS regras TEXT[] NOT NULL DEFAULT '{}';

-- Backfill: the old key-based check is replaced by the tag, so every section that carried the key is tagged. Published
-- versions are frozen by guard_agent_prompt_sections_immutable, so the guard is off for this one statement only (the
-- tag is metadata outside the compiled prompt; precedent 059) and back on right after, in the same transaction.
ALTER TABLE agents.agent_prompt_sections DISABLE TRIGGER guard_agent_prompt_sections_immutable;

UPDATE agents.agent_prompt_sections
SET regras = array_append(regras, 'discordar-com-respeito')
WHERE chave = 'discordar-com-respeito'
  AND NOT ('discordar-com-respeito' = ANY(regras));

ALTER TABLE agents.agent_prompt_sections ENABLE TRIGGER guard_agent_prompt_sections_immutable;

-- The Studio write paths carry the column (CREATE OR REPLACE: same signatures, same grants as 012).
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
        conteudo = COALESCE(x.conteudo, ''), ativo = COALESCE(x.ativo, true),
        regras = COALESCE(ARRAY(SELECT jsonb_array_elements_text(x.regras)), '{}')
    FROM jsonb_to_recordset(p_secoes)
        AS x(id UUID, chave TEXT, titulo TEXT, ordem INT, conteudo TEXT, ativo BOOLEAN, regras JSONB)
    WHERE s.id = x.id AND s.version_id = p_version_id AND s.org_id = p_org_id;

    INSERT INTO agents.agent_prompt_sections (org_id, version_id, chave, titulo, ordem, conteudo, ativo, regras)
    SELECT p_org_id, p_version_id, x.chave, x.titulo, x.ordem, COALESCE(x.conteudo, ''), COALESCE(x.ativo, true),
           COALESCE(ARRAY(SELECT jsonb_array_elements_text(x.regras)), '{}')
    FROM jsonb_to_recordset(p_secoes)
        AS x(id UUID, chave TEXT, titulo TEXT, ordem INT, conteudo TEXT, ativo BOOLEAN, regras JSONB)
    WHERE x.id IS NULL
       OR NOT EXISTS (
           SELECT 1 FROM agents.agent_prompt_sections s
           WHERE s.id = x.id AND s.version_id = p_version_id AND s.org_id = p_org_id
       );
END;
$$;

REVOKE ALL ON FUNCTION agents.replace_draft_sections(UUID, UUID, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.replace_draft_sections(UUID, UUID, JSONB) TO service_role;


-- A new draft copied from a version keeps each section's rules.
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
        org_id, agent_id, versao, status, notas, provider, model, effort, max_turns,
        idioma, tool_policy, based_on_version_id, created_by
    ) VALUES (
        p_org_id, p_agent_id, v_next_versao, 'rascunho', NULL, v_src.provider, v_src.model,
        v_src.effort, v_src.max_turns, v_src.idioma, v_src.tool_policy,
        v_src.id, p_created_by
    )
    RETURNING id INTO v_new_id;

    INSERT INTO agents.agent_prompt_sections (
        org_id, version_id, chave, titulo, ordem, conteudo, ativo, regras
    )
    SELECT p_org_id, v_new_id, chave, titulo, ordem, conteudo, ativo, regras
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

-- The importer's one-transaction write carries them too.
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

    INSERT INTO agents.agent_prompt_sections (org_id, version_id, chave, titulo, ordem, conteudo, ativo, regras)
    SELECT p_org_id, p_version_id, x.chave, x.titulo, x.ordem, COALESCE(x.conteudo, ''), COALESCE(x.ativo, true),
           COALESCE(ARRAY(SELECT jsonb_array_elements_text(x.regras)), '{}')
    FROM jsonb_to_recordset(p_secoes)
        AS x(chave TEXT, titulo TEXT, ordem INT, conteudo TEXT, ativo BOOLEAN, regras JSONB);

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
