-- ============================================================================
-- 024_llm_provider_runtime.sql -- provider-neutral runtime (Lais slice A1,
-- contract products/social-wiring/projects/lais/specs/julia-agent-contract.md
-- section 2 + 10.2 B1).
--
-- 1. agents.agent_versions.provider ('anthropic' | 'openai', default
--    'anthropic' so every existing version -- Julia-academia's included -- is
--    unchanged) + a PROVIDER-KEYED model CHECK. OpenAI names are the chat
--    models the seed catalog lists (noctusai_lib.integrations.llm.models).
--    `provider` is a compiled setting: changing it on a draft clears the
--    judged hash, and it is frozen on a published row (guard re-declared from
--    017's with the column added); a draft copy carries it (create_agent_draft
--    re-declared from 012's with the column added).
-- 2. agents.agents.runtime CHECK gains 'llm' (agents runs the agent on the
--    provider-neutral tool loop; distinct from 'external', where ANOTHER
--    product runs it).
-- 3. agents.credentials -- the per-ORG, Fernet-encrypted store the seed
--    api-keys router writes (openai_api_key / anthropic_api_key). Same shape
--    as noctusai_lib.security.api_keys.credentials_table_ddl; no
--    authenticated/anon access at all (the ciphertext is service-role only).
--
-- Idempotent (DROP CONSTRAINT IF EXISTS + ADD, IF NOT EXISTS, OR REPLACE).
-- NOT applied to any database by this slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

ALTER TABLE agents.agent_versions
    ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'anthropic';

ALTER TABLE agents.agent_versions
    DROP CONSTRAINT IF EXISTS agent_versions_provider_check;
ALTER TABLE agents.agent_versions
    ADD CONSTRAINT agent_versions_provider_check
        CHECK (provider IN ('anthropic', 'openai'));

ALTER TABLE agents.agent_versions
    DROP CONSTRAINT IF EXISTS agent_versions_model_check;
ALTER TABLE agents.agent_versions
    ADD CONSTRAINT agent_versions_model_check
        CHECK (
            (provider = 'anthropic'
                AND model IN ('claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'))
            OR (provider = 'openai'
                AND model IN ('gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna'))
        );

ALTER TABLE agents.agents
    DROP CONSTRAINT IF EXISTS agents_runtime_check;
ALTER TABLE agents.agents
    ADD CONSTRAINT agents_runtime_check
        CHECK (runtime IN ('claude_sdk', 'external', 'llm'));

-- 017's guard re-declared with `provider` compiled (draft) + frozen (published).
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
            OR NEW.provider IS DISTINCT FROM OLD.provider
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
       OR NEW.provider IS DISTINCT FROM OLD.provider
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

-- 012's create_agent_draft re-declared so a copied draft keeps its provider.
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


-- ────────────────────────────────────────────────────────────────────────
-- agents.credentials -- per-org encrypted API keys (seed api-keys router)
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    provider TEXT NOT NULL,
    encrypted_tokens TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, provider)
);

ALTER TABLE agents.credentials ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON agents.credentials;
CREATE POLICY "service_role_bypass" ON agents.credentials FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON agents.credentials FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS idx_agents_credentials_org ON agents.credentials(org_id);
CREATE INDEX IF NOT EXISTS idx_agents_credentials_provider ON agents.credentials(provider);
