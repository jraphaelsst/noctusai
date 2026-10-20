-- ============================================================================
-- 041_julia_v2_skill_cas.sql -- Julia v2 A-polish (#11).
--
-- `update_draft_skill(p_org_id, p_skill_id, p_campos, p_expected_hash)`: the PATCH of a draft skill gets the SAME
-- atomic optimistic lock the replace-set PUTs got in 040 (`replace_draft_conteudo(..., p_expected_hash)`). The
-- parent version row is locked FOR UPDATE, its `compiled_hash` compared with what the caller last read, and only
-- then the skill updated -- one transaction, so two editors can never silently overwrite each other's skill body.
-- The content-mode hash covers the version's own skill bodies (A-polish #9), so any skill write moves the hash
-- and a writer holding the old one is refused (`conflito_de_versao`).
--
-- `p_campos` is the PATCH body (nome / descricao / corpo / ordem / ativo; any subset). An unknown key is
-- `invalid_payload`. The 012 child guard still runs on the UPDATE (draft-only + NULLs the parent hash).
-- `p_expected_hash` NULL = no check (the pre-041 behaviour; the store calls this function only with a hash).
--
-- Forward-only + idempotent. NOT applied by the slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

CREATE OR REPLACE FUNCTION agents.update_draft_skill(
    p_org_id UUID,
    p_skill_id UUID,
    p_campos JSONB,
    p_expected_hash TEXT DEFAULT NULL
) RETURNS SETOF agents.agent_skills
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_version UUID;
    v_status TEXT;
    v_hash TEXT;
BEGIN
    IF jsonb_typeof(p_campos) IS DISTINCT FROM 'object'
       OR EXISTS (
           SELECT 1 FROM jsonb_object_keys(p_campos) AS k
           WHERE k NOT IN ('nome', 'descricao', 'corpo', 'ordem', 'ativo')
       ) THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;

    SELECT s.version_id INTO v_version FROM agents.agent_skills s WHERE s.id = p_skill_id AND s.org_id = p_org_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;
    SELECT status, compiled_hash INTO v_status, v_hash FROM agents.agent_versions
    WHERE id = v_version AND org_id = p_org_id
    FOR UPDATE;
    IF v_status IS DISTINCT FROM 'rascunho' THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    IF p_expected_hash IS NOT NULL AND v_hash IS DISTINCT FROM p_expected_hash THEN
        RAISE EXCEPTION 'conflito_de_versao' USING ERRCODE = 'P0001';
    END IF;

    BEGIN
        RETURN QUERY
        UPDATE agents.agent_skills s SET
            nome = CASE WHEN p_campos ? 'nome' THEN p_campos ->> 'nome' ELSE s.nome END,
            descricao = CASE WHEN p_campos ? 'descricao' THEN p_campos ->> 'descricao' ELSE s.descricao END,
            corpo = CASE WHEN p_campos ? 'corpo' THEN p_campos ->> 'corpo' ELSE s.corpo END,
            ordem = CASE WHEN p_campos ? 'ordem' THEN (p_campos ->> 'ordem')::int ELSE s.ordem END,
            ativo = CASE WHEN p_campos ? 'ativo' THEN (p_campos ->> 'ativo')::boolean ELSE s.ativo END,
            updated_at = now()
        WHERE s.id = p_skill_id AND s.org_id = p_org_id
        RETURNING s.*;
    EXCEPTION WHEN unique_violation THEN
        RAISE EXCEPTION 'skill_exists' USING ERRCODE = 'P0001';
    END;
END;
$$;

REVOKE ALL ON FUNCTION agents.update_draft_skill(UUID, UUID, JSONB, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.update_draft_skill(UUID, UUID, JSONB, TEXT) TO service_role;
