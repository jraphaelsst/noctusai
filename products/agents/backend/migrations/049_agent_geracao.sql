-- ============================================================================
-- 049_agent_geracao.sql -- S3a: AI-generated first drafts + data-driven platform definitions.
--
-- 1. A platform definition is ANY `definition_scope='plataforma'` row. What the old code registry
--    (`app.studio.plataforma._registro`) carried per key becomes COLUMNS on that row, written through the
--    Studio API (platform admin / content token) and read by every mechanism (runtime, compile,
--    qualification, org-instance creation, publish):
--      * escopo_qualificacao / padrao_qualificacao -- the qualification scope + standard the agent works;
--      * rascunho_padrao  -- JSON object of the settings the definition's FIRST draft starts with
--                            (provider / model / effort / max_turns / idioma / tool_policy);
--      * papel            -- the platform role the definition plays for a MECHANISM: 'gerador' (the agent whose
--                            published version drives AI draft generation) | 'exemplar' (a structure the generator
--                            imitates). Mechanisms find these by role, never by key;
--      * instanciavel     -- whether a published definition is instantiated in every org (default TRUE so every
--                            definition that exists today keeps behaving; a NEW definition opts in explicitly --
--                            an internal agent such as the draft generator must not appear in every org).
--    NO key-specific backfill: existing rows keep NULL and are configured through the API.
--
-- 2. agents.geracoes / agents.geracao_areas -- one AI generation run per agent (`pendente|executando` at most one
--    per agent) and one row per requested area, with the raw output, the per-item hashes (the "gerado vs editado"
--    signal) and the cost in the 014 column shape. `limite_usd` is capped at 5.00 by the DB.
--
-- 3. `agent_audit_log.acao` admits 'agente_gerado' (kept in lockstep with AUDIT_ACOES by
--    tests/test_migration_audit_acao_check.py).
--
-- Forward-only + idempotent. Service-role only (the 036 posture): RLS on, no policy for anon/authenticated.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. data-driven platform definition attributes ───────────────────────────────

ALTER TABLE agents.agents
    ADD COLUMN IF NOT EXISTS escopo_qualificacao TEXT NULL,
    ADD COLUMN IF NOT EXISTS padrao_qualificacao TEXT NULL,
    ADD COLUMN IF NOT EXISTS rascunho_padrao JSONB NULL,
    ADD COLUMN IF NOT EXISTS papel TEXT NULL,
    ADD COLUMN IF NOT EXISTS instanciavel BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE agents.agents DROP CONSTRAINT IF EXISTS agents_definicao_atributos_check;
ALTER TABLE agents.agents ADD CONSTRAINT agents_definicao_atributos_check
    CHECK (
        (escopo_qualificacao IS NULL OR escopo_qualificacao ~ '^[a-z0-9][a-z0-9_-]{0,62}$')
        AND (padrao_qualificacao IS NULL OR padrao_qualificacao ~ '^[a-z0-9][a-z0-9_-]{0,62}$')
        AND (rascunho_padrao IS NULL OR jsonb_typeof(rascunho_padrao) = 'object')
        AND (papel IS NULL OR papel IN ('gerador', 'exemplar'))
        AND (definition_scope = 'plataforma'
             OR (escopo_qualificacao IS NULL AND padrao_qualificacao IS NULL AND rascunho_padrao IS NULL
                 AND papel IS NULL))
    );

-- ── 2. generation runs ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.geracoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('pendente', 'executando', 'concluida', 'parcial', 'falhou', 'cancelada')),
    briefing JSONB NOT NULL,
    areas_solicitadas TEXT[] NOT NULL,
    forcar BOOLEAN NOT NULL DEFAULT FALSE,
    versao_gerador INT NULL,
    modelo TEXT NOT NULL,
    provider TEXT NOT NULL,
    plano JSONB NULL,
    custo_usd NUMERIC(10, 4) NOT NULL DEFAULT 0,
    limite_usd NUMERIC(10, 2) NOT NULL,
    erro TEXT NULL,
    aprendizado JSONB NULL,
    criado_por UUID NOT NULL,
    iniciado_em TIMESTAMPTZ NULL,
    concluido_em TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT geracoes_limite_check CHECK (limite_usd > 0 AND limite_usd <= 5.00)
);

-- at most one run in flight per agent (the store maps the violation to 409 geracao_em_andamento)
CREATE UNIQUE INDEX IF NOT EXISTS geracoes_one_active_idx
    ON agents.geracoes (agent_id) WHERE status IN ('pendente', 'executando');
CREATE INDEX IF NOT EXISTS idx_agents_geracoes_agent ON agents.geracoes (agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agents_geracoes_org ON agents.geracoes (org_id);

CREATE TABLE IF NOT EXISTS agents.geracao_areas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    geracao_id UUID NOT NULL REFERENCES agents.geracoes(id) ON DELETE CASCADE,
    area TEXT NOT NULL
        CHECK (area IN ('secoes', 'textos', 'ferramentas', 'decisoes', 'specs', 'skills', 'configuracoes')),
    status TEXT NOT NULL CHECK (status IN ('pendente', 'executando', 'concluida', 'falhou', 'pulado', 'cancelada')),
    erro TEXT NULL,
    custo_usd NUMERIC(10, 4) NOT NULL DEFAULT 0,
    tokens_entrada INT NULL,
    tokens_saida INT NULL,
    saida JSONB NULL,
    itens JSONB NOT NULL DEFAULT '[]'::jsonb,
    lacunas JSONB NOT NULL DEFAULT '[]'::jsonb,
    concluido_em TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (geracao_id, area)
);
CREATE INDEX IF NOT EXISTS idx_agents_geracao_areas_org ON agents.geracao_areas (org_id);

CREATE OR REPLACE TRIGGER set_updated_at_geracoes
    BEFORE UPDATE ON agents.geracoes FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
CREATE OR REPLACE TRIGGER set_updated_at_geracao_areas
    BEFORE UPDATE ON agents.geracao_areas FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

ALTER TABLE agents.geracoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.geracao_areas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.geracoes;
CREATE POLICY "service_role_bypass" ON agents.geracoes FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.geracao_areas;
CREATE POLICY "service_role_bypass" ON agents.geracao_areas FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.geracoes FROM PUBLIC, anon, authenticated;
REVOKE ALL ON agents.geracao_areas FROM PUBLIC, anon, authenticated;

-- ── 3. audit action ──────────────────────────────────────────────────────────────

DO $$
DECLARE
    v_con TEXT;
BEGIN
    FOR v_con IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'agents.agent_audit_log'::regclass
           AND contype = 'c'
           AND pg_get_constraintdef(oid) ILIKE '%acao%'
    LOOP
        EXECUTE format('ALTER TABLE agents.agent_audit_log DROP CONSTRAINT %I', v_con);
    END LOOP;
END
$$;

ALTER TABLE agents.agent_audit_log
    ADD CONSTRAINT agent_audit_log_acao_check
        CHECK (acao IN (
            'limiar_alterado', 'publicado', 'publicado_override', 'rascunho_descartado',
            'conteudo_editado_mcp', 'specs_org_editadas', 'definicao_lida',
            'modo_alterado', 'conversa_pausada', 'conversa_retomada', 'padrao_publicado',
            'agente_excluido', 'agente_criado', 'agente_gerado'
        ));
