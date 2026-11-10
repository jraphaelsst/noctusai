-- 080_retomada_limite.sql -- the follow-up cap: at most N retomadas (re-engagement messages) in a row with no reply
-- from the lead, enforced in code by agents (owner rule 2026-11-10; design sdr-base section 2).
--
-- * `agents.thread_retomada_eventos`: APPEND-ONLY, one row per re-engagement outcome (enviada | recusada_limite |
--   ignorada). The count of consecutive follow-ups is the `enviada` rows after the lead's last message (a lead reply
--   resets it with no write).
-- * `qualificacao_parametros.max_retomadas_seguidas` (default 2, 0..10): the limit is DATA of the standard. Published
--   versions are immutable (trigger) and keep the default via the column default (no row update); a new draft copies it,
--   hence `criar_rascunho_qualificacao` is re-declared with the extra column.
--
-- Tier: `tier:org` data written only by the service (RLS on, service_role only, no grant to anon / authenticated), like
-- the sibling thread tables. Forward-only + idempotent. 077-079 belong to queued branches.

SET search_path = agents, public;

CREATE TABLE IF NOT EXISTS agents.thread_retomada_eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    thread_id UUID NOT NULL REFERENCES agents.conversations(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents.agents(id) ON DELETE CASCADE,
    tier TEXT NULL CHECK (tier IS NULL OR tier IN ('minutos', 'horas', 'regua')),
    resultado TEXT NOT NULL CHECK (resultado IN ('enviada', 'recusada_limite', 'ignorada')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agents_thread_retomada_eventos_conta
    ON agents.thread_retomada_eventos (thread_id, agent_id, created_at DESC) WHERE resultado = 'enviada';
CREATE INDEX IF NOT EXISTS idx_agents_thread_retomada_eventos_org ON agents.thread_retomada_eventos (org_id, created_at);

CREATE OR REPLACE FUNCTION agents.thread_retomada_eventos_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = agents, public AS $$
BEGIN
    RAISE EXCEPTION 'thread_retomada_eventos is append-only' USING ERRCODE = 'P0001';
END;
$$;
DROP TRIGGER IF EXISTS thread_retomada_eventos_append_only ON agents.thread_retomada_eventos;
CREATE TRIGGER thread_retomada_eventos_append_only
    BEFORE UPDATE ON agents.thread_retomada_eventos
    FOR EACH ROW EXECUTE FUNCTION agents.thread_retomada_eventos_append_only();

COMMENT ON TABLE agents.thread_retomada_eventos IS 'tier:org';
ALTER TABLE agents.thread_retomada_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.thread_retomada_eventos;
CREATE POLICY "service_role_bypass" ON agents.thread_retomada_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.thread_retomada_eventos FROM anon, authenticated;

ALTER TABLE agents.qualificacao_parametros
    ADD COLUMN IF NOT EXISTS max_retomadas_seguidas INT NOT NULL DEFAULT 2
        CONSTRAINT qualificacao_parametros_max_retomadas_check CHECK (max_retomadas_seguidas BETWEEN 0 AND 10);

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
            (versao_id, minimo_para_ofertar, lote_ofertas, score_max, eixos, pedir_identificacao_quando, max_retomadas_seguidas)
        SELECT v_novo, minimo_para_ofertar, lote_ofertas, score_max, eixos, pedir_identificacao_quando, max_retomadas_seguidas
          FROM agents.qualificacao_parametros WHERE versao_id = p_copiar_de;
    END IF;
    RETURN v_novo;
END;
$$;

-- CREATE OR REPLACE keeps the existing grants; restated here so the file is self-evidently locked down.
REVOKE ALL ON FUNCTION agents.criar_rascunho_qualificacao(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.criar_rascunho_qualificacao(UUID, TEXT, UUID) TO service_role;
