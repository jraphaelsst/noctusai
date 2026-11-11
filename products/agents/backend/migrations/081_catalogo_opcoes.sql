-- ============================================================================
-- 081_catalogo_opcoes.sql -- the OFFER CATALOGUE of an agent (owner 2026-11-10, sdr-base template).
--
-- The generic tools `oferecer_opcoes` / `detalhes_opcao` / `registrar_reacao_opcao` offer "options" from a catalogue
-- behind an adapter (app/catalogos). Two columns carry which one:
--
-- 1. agents.qualificacao_parametros.catalogo  -- the catalogue the standard's agents offer from (a key of
--    app.catalogos.CATALOGOS, validated by the app when the version is saved/published). NULL = none named: an agent
--    with `oferecer_opcoes` active then fails readiness (`catalogo_ausente`). Julia's rows stay NULL: her tools
--    (`oferecer_imoveis` ...) read the real-estate catalogue without naming it.
-- 2. agents.lead_imovel_eventos.catalogo      -- which catalogue an event's `codigo_imovel` belongs to, so the same
--    code in two catalogues is two options and the duplicate-offer rule is per catalogue. Existing rows are the
--    real-estate catalogue ('imoveis_sw'). There is no duplicate-offer UNIQUE index to extend: the rule lives in
--    QualificacaoService.registrar_evento_imovel (a unique index over history we never audited could fail the apply).
--
-- 3. agents.criar_rascunho_qualificacao copies the new column when it clones a version (and keeps 080's
--    max_retomadas_seguidas: this re-declaration replaces 080's, so it must carry every column 080 copies).
--
-- NOC-REMEDIATE[codigo-opcao-rename]: `lead_imovel_eventos` / `codigo_imovel` keep their real-estate names until the
-- imovel tools retire (expand -> migrate -> contract); the rename is the contract step -- 2026-11-11
--
-- DEPLOY ORDER: apply this migration BEFORE the image that carries the code (the standard's save writes `catalogo`).
-- Forward-only + idempotent.
-- ============================================================================

SET search_path = agents, public;

ALTER TABLE agents.qualificacao_parametros ADD COLUMN IF NOT EXISTS catalogo TEXT NULL;
ALTER TABLE agents.qualificacao_parametros DROP CONSTRAINT IF EXISTS qualificacao_parametros_catalogo_check;
ALTER TABLE agents.qualificacao_parametros ADD CONSTRAINT qualificacao_parametros_catalogo_check
    CHECK (catalogo IS NULL OR (btrim(catalogo) <> '' AND char_length(catalogo) <= 64));

ALTER TABLE agents.lead_imovel_eventos ADD COLUMN IF NOT EXISTS catalogo TEXT NOT NULL DEFAULT 'imoveis_sw';
ALTER TABLE agents.lead_imovel_eventos DROP CONSTRAINT IF EXISTS lead_imovel_eventos_catalogo_check;
ALTER TABLE agents.lead_imovel_eventos ADD CONSTRAINT lead_imovel_eventos_catalogo_check
    CHECK (btrim(catalogo) <> '' AND char_length(catalogo) <= 64);

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
             max_retomadas_seguidas, catalogo)
        SELECT v_novo, minimo_para_ofertar, lote_ofertas, score_max, eixos, pedir_identificacao_quando,
               max_retomadas_seguidas, catalogo
          FROM agents.qualificacao_parametros WHERE versao_id = p_copiar_de;
    END IF;
    RETURN v_novo;
END;
$$;

REVOKE ALL ON FUNCTION agents.criar_rascunho_qualificacao(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.criar_rascunho_qualificacao(UUID, TEXT, UUID) TO service_role;
