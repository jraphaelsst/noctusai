-- ============================================================================
-- 082_qualificacao_identificacao_desejada.sql -- a standard DECLARES which identity fields it desires
-- (owner decision 2026-11-10: derive them from the standard, in code). NULL = the version predates the key
-- (legacy: the engine keeps rg/email/nome on a logged branch); '[]' = declared, wants none.
-- Additive + idempotent. The draft-copy function carries the new column over, and keeps 080's `max_retomadas_seguidas` and 081's `catalogo` (each redefined it first; this redefinition must copy all three). Requires 080 and 081.
-- ============================================================================
SET search_path = agents, public;

ALTER TABLE agents.qualificacao_parametros
    ADD COLUMN IF NOT EXISTS identificacao_desejada JSONB NULL
    CHECK (identificacao_desejada IS NULL OR jsonb_typeof(identificacao_desejada) = 'array');

-- New draft of a standard, optionally copied from an existing version.
CREATE OR REPLACE FUNCTION agents.criar_rascunho_qualificacao(
    p_padrao_id UUID,
    p_notas TEXT,
    p_copiar_de UUID
) RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_novo UUID;
    v_num INT;
BEGIN
    PERFORM 1 FROM agents.qualificacao_padroes WHERE id = p_padrao_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM agents.qualificacao_versoes WHERE padrao_id = p_padrao_id AND status = 'rascunho') THEN
        RAISE EXCEPTION 'draft_exists' USING ERRCODE = 'P0001';
    END IF;
    IF p_copiar_de IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM agents.qualificacao_versoes WHERE id = p_copiar_de AND padrao_id = p_padrao_id
    ) THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;

    SELECT COALESCE(MAX(versao), 0) + 1 INTO v_num
      FROM agents.qualificacao_versoes WHERE padrao_id = p_padrao_id;
    INSERT INTO agents.qualificacao_versoes (padrao_id, versao, status, notas)
    VALUES (p_padrao_id, v_num, 'rascunho', p_notas)
    RETURNING id INTO v_novo;

    IF p_copiar_de IS NOT NULL THEN
        INSERT INTO agents.qualificacao_criterios
            (versao_id, chave, grupo, rotulo, descricao_modelo, tipo, opcoes, unidade, sensivel, pontuacao, ordem, ativo, eixo, escopo, validade_dias)
        SELECT v_novo, chave, grupo, rotulo, descricao_modelo, tipo, opcoes, unidade, sensivel, pontuacao, ordem, ativo, eixo, escopo, validade_dias
          FROM agents.qualificacao_criterios WHERE versao_id = p_copiar_de;
        INSERT INTO agents.qualificacao_estagios
            (versao_id, chave, rotulo, descricao, ordem, regra, conclusivo, terminal)
        SELECT v_novo, chave, rotulo, descricao, ordem, regra, conclusivo, terminal
          FROM agents.qualificacao_estagios WHERE versao_id = p_copiar_de;
        INSERT INTO agents.qualificacao_parametros
            (versao_id, minimo_para_ofertar, lote_ofertas, score_max, eixos, pedir_identificacao_quando,
             max_retomadas_seguidas, catalogo, identificacao_desejada)
        SELECT v_novo, minimo_para_ofertar, lote_ofertas, score_max, eixos, pedir_identificacao_quando,
               max_retomadas_seguidas, catalogo, identificacao_desejada
          FROM agents.qualificacao_parametros WHERE versao_id = p_copiar_de;
    END IF;
    RETURN v_novo;
END;
$$;

REVOKE ALL ON FUNCTION agents.criar_rascunho_qualificacao(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.criar_rascunho_qualificacao(UUID, TEXT, UUID) TO service_role;
