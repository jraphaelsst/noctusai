-- ============================================================================
-- Daily Life Product schema
-- Schema: daily_life
-- Description: Personal productivity hub — tasks, goals, habits, schedule,
--              notes, automations, and performance tracking.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS daily_life;

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA daily_life TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA daily_life TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA daily_life TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA daily_life GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA daily_life GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- Page status (feature flags)
-- ============================================================================

CREATE TABLE daily_life.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE daily_life.status_pagina ENABLE ROW LEVEL SECURITY;

CREATE POLICY "todos_veem_producao" ON daily_life.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- Invitations
-- ============================================================================

CREATE TABLE daily_life.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by UUID NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daily_life.invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "invitations_select_own_org" ON daily_life.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_dl_invitations_org ON daily_life.invitations(org_id);
CREATE INDEX idx_dl_invitations_token ON daily_life.invitations(token);


-- ============================================================================
-- Tasks (Tarefas)
-- ============================================================================

CREATE TABLE daily_life.tarefas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    descricao TEXT,
    prioridade TEXT NOT NULL DEFAULT 'media' CHECK (prioridade IN ('alta', 'media', 'baixa')),
    prioridade_ordem INT NOT NULL DEFAULT 2,
    categoria TEXT,
    data_vencimento DATE,
    status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'em_progresso', 'concluida', 'cancelada')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daily_life.tarefas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tarefas_select_own" ON daily_life.tarefas
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "tarefas_insert_own" ON daily_life.tarefas
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "tarefas_update_own" ON daily_life.tarefas
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "tarefas_delete_own" ON daily_life.tarefas
    FOR DELETE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_tarefas_user ON daily_life.tarefas(user_id);
CREATE INDEX idx_dl_tarefas_user_status ON daily_life.tarefas(user_id, status);
CREATE INDEX idx_dl_tarefas_org ON daily_life.tarefas(org_id);


-- ============================================================================
-- Goals & Habits (Metas)
-- ============================================================================

CREATE TABLE daily_life.metas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    descricao TEXT,
    tipo TEXT NOT NULL DEFAULT 'meta' CHECK (tipo IN ('meta', 'habito')),
    categoria TEXT,
    meta_valor NUMERIC,
    valor_atual NUMERIC DEFAULT 0,
    unidade TEXT,
    frequencia TEXT CHECK (frequencia IS NULL OR frequencia IN ('diario', 'semanal', 'mensal')),
    data_limite DATE,
    status TEXT NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'concluida', 'pausada', 'cancelada')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daily_life.metas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "metas_select_own" ON daily_life.metas
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "metas_insert_own" ON daily_life.metas
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "metas_update_own" ON daily_life.metas
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "metas_delete_own" ON daily_life.metas
    FOR DELETE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_metas_user ON daily_life.metas(user_id);
CREATE INDEX idx_dl_metas_user_tipo ON daily_life.metas(user_id, tipo);


-- ============================================================================
-- Habit Check-Ins
-- ============================================================================

CREATE TABLE daily_life.checkins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meta_id UUID NOT NULL REFERENCES daily_life.metas(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    data DATE NOT NULL,
    valor NUMERIC DEFAULT 1,
    nota TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(meta_id, data)
);

ALTER TABLE daily_life.checkins ENABLE ROW LEVEL SECURITY;

CREATE POLICY "checkins_select_own" ON daily_life.checkins
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "checkins_insert_own" ON daily_life.checkins
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_checkins_meta ON daily_life.checkins(meta_id);
CREATE INDEX idx_dl_checkins_user_data ON daily_life.checkins(user_id, data);


-- ============================================================================
-- Calendar Events (Eventos)
-- ============================================================================

CREATE TABLE daily_life.eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    descricao TEXT,
    categoria TEXT,
    data_inicio TIMESTAMPTZ NOT NULL,
    data_fim TIMESTAMPTZ,
    dia_inteiro BOOLEAN DEFAULT FALSE,
    local TEXT,
    lembrete_minutos INT,
    cor TEXT,
    status TEXT NOT NULL DEFAULT 'agendado' CHECK (status IN ('agendado', 'concluido', 'cancelado')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daily_life.eventos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "eventos_select_own" ON daily_life.eventos
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "eventos_insert_own" ON daily_life.eventos
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "eventos_update_own" ON daily_life.eventos
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "eventos_delete_own" ON daily_life.eventos
    FOR DELETE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_eventos_user ON daily_life.eventos(user_id);
CREATE INDEX idx_dl_eventos_user_data ON daily_life.eventos(user_id, data_inicio);
CREATE INDEX idx_dl_eventos_org ON daily_life.eventos(org_id);


-- ============================================================================
-- Notes (Notas)
-- ============================================================================

CREATE TABLE daily_life.notas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    conteudo TEXT,
    categoria TEXT,
    tags TEXT[] DEFAULT '{}',
    fixada BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daily_life.notas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "notas_select_own" ON daily_life.notas
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "notas_insert_own" ON daily_life.notas
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "notas_update_own" ON daily_life.notas
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "notas_delete_own" ON daily_life.notas
    FOR DELETE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_notas_user ON daily_life.notas(user_id);
CREATE INDEX idx_dl_notas_user_fixada ON daily_life.notas(user_id, fixada);


-- ============================================================================
-- Productivity Metrics (daily snapshots)
-- ============================================================================

CREATE TABLE daily_life.metricas_produtividade (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    data DATE NOT NULL,
    tarefas_concluidas INT DEFAULT 0,
    tarefas_criadas INT DEFAULT 0,
    checkins_realizados INT DEFAULT 0,
    eventos_do_dia INT DEFAULT 0,
    notas_criadas INT DEFAULT 0,
    score_produtividade NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, data)
);

ALTER TABLE daily_life.metricas_produtividade ENABLE ROW LEVEL SECURITY;

CREATE POLICY "metricas_select_own" ON daily_life.metricas_produtividade
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "metricas_insert_own" ON daily_life.metricas_produtividade
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "metricas_update_own" ON daily_life.metricas_produtividade
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_metricas_user_data ON daily_life.metricas_produtividade(user_id, data);


-- ============================================================================
-- Focus Sessions (Pomodoro / Deep Work)
-- ============================================================================

CREATE TABLE daily_life.sessoes_foco (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tarefa_id UUID REFERENCES daily_life.tarefas(id) ON DELETE SET NULL,
    tipo TEXT NOT NULL DEFAULT 'pomodoro' CHECK (tipo IN ('pomodoro', 'deep_work', 'livre')),
    duracao_minutos INT NOT NULL,
    inicio TIMESTAMPTZ NOT NULL,
    fim TIMESTAMPTZ,
    nota TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daily_life.sessoes_foco ENABLE ROW LEVEL SECURITY;

CREATE POLICY "sessoes_select_own" ON daily_life.sessoes_foco
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "sessoes_insert_own" ON daily_life.sessoes_foco
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "sessoes_update_own" ON daily_life.sessoes_foco
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_sessoes_user ON daily_life.sessoes_foco(user_id);
CREATE INDEX idx_dl_sessoes_user_inicio ON daily_life.sessoes_foco(user_id, inicio);


-- ============================================================================
-- Auto-update timestamps trigger
-- ============================================================================

CREATE OR REPLACE FUNCTION daily_life.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = daily_life
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER tarefas_updated_at BEFORE UPDATE ON daily_life.tarefas
    FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();

CREATE TRIGGER metas_updated_at BEFORE UPDATE ON daily_life.metas
    FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();

CREATE TRIGGER eventos_updated_at BEFORE UPDATE ON daily_life.eventos
    FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();

CREATE TRIGGER notas_updated_at BEFORE UPDATE ON daily_life.notas
    FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();


-- ============================================================================
-- Command knowledge tables (CLI learning system)
-- ============================================================================

CREATE TABLE daily_life.commands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('exact', 'pattern', 'alias')),
    handler TEXT NOT NULL,
    parameters JSONB DEFAULT '{}',
    description TEXT,
    category TEXT,
    examples TEXT[] DEFAULT '{}',
    enabled BOOLEAN DEFAULT TRUE,
    usage_count INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.commands ENABLE ROW LEVEL SECURITY;
CREATE POLICY "commands_service" ON daily_life.commands FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "commands_read" ON daily_life.commands FOR SELECT TO authenticated USING (true);
CREATE INDEX idx_dl_commands_type ON daily_life.commands(type);
CREATE INDEX idx_dl_commands_trigger ON daily_life.commands(trigger);

CREATE TABLE daily_life.intent_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern TEXT NOT NULL,
    pattern_type TEXT NOT NULL DEFAULT 'keyword' CHECK (pattern_type IN ('regex', 'keyword', 'fuzzy')),
    mapped_command_id UUID REFERENCES daily_life.commands(id) ON DELETE CASCADE,
    handler TEXT,
    parameter_extraction JSONB DEFAULT '{}',
    confidence_threshold NUMERIC DEFAULT 0.8,
    examples TEXT[] DEFAULT '{}',
    enabled BOOLEAN DEFAULT TRUE,
    usage_count INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.intent_patterns ENABLE ROW LEVEL SECURITY;
CREATE POLICY "patterns_service" ON daily_life.intent_patterns FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "patterns_read" ON daily_life.intent_patterns FOR SELECT TO authenticated USING (true);

CREATE TABLE daily_life.context_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    rule_type TEXT NOT NULL CHECK (rule_type IN ('contact', 'location', 'default', 'alias', 'preference')),
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.context_rules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "context_all" ON daily_life.context_rules FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));
CREATE INDEX idx_dl_context_user_type ON daily_life.context_rules(user_id, rule_type);

CREATE TABLE daily_life.command_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    raw_input TEXT NOT NULL,
    resolved_command TEXT,
    resolved_handler TEXT,
    tier_used TEXT NOT NULL CHECK (tier_used IN ('direct', 'pattern', 'llm', 'failed')),
    parameters JSONB DEFAULT '{}',
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    execution_time_ms INT,
    tokens_used INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.command_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY "history_all" ON daily_life.command_history FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));
CREATE INDEX idx_dl_history_user ON daily_life.command_history(user_id);
CREATE INDEX idx_dl_history_created ON daily_life.command_history(created_at);
CREATE INDEX idx_dl_history_tier ON daily_life.command_history(tier_used);

CREATE TABLE daily_life.learned_promotions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_history_id UUID REFERENCES daily_life.command_history(id) ON DELETE SET NULL,
    raw_input TEXT NOT NULL,
    extracted_intent TEXT NOT NULL,
    extracted_handler TEXT NOT NULL,
    extracted_parameters JSONB DEFAULT '{}',
    suggested_pattern TEXT,
    suggested_pattern_type TEXT DEFAULT 'keyword' CHECK (suggested_pattern_type IN ('regex', 'keyword', 'fuzzy')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'auto_approved')),
    occurrences INT DEFAULT 1,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_to_pattern_id UUID REFERENCES daily_life.intent_patterns(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.learned_promotions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "promotions_all" ON daily_life.learned_promotions FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));
CREATE INDEX idx_dl_promotions_user_status ON daily_life.learned_promotions(user_id, status);
CREATE INDEX idx_dl_promotions_intent ON daily_life.learned_promotions(extracted_intent);

CREATE TRIGGER commands_updated_at BEFORE UPDATE ON daily_life.commands FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();
CREATE TRIGGER context_updated_at BEFORE UPDATE ON daily_life.context_rules FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();


-- ============================================================================
-- Seed pages
-- ============================================================================

INSERT INTO daily_life.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('tarefas', 'producao'),
    ('metas', 'producao'),
    ('agenda', 'producao'),
    ('notas', 'producao'),
    ('foco', 'producao'),
    ('metricas', 'producao'),
    ('equipe', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
