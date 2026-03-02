-- =====================================================================
-- NoctusAI Personal Finance — Database Schema
-- Schema: "personal-finance"
-- =====================================================================

-- ===================== SCHEMA & PERMISSIONS =====================
CREATE SCHEMA IF NOT EXISTS "personal-finance";

GRANT USAGE ON SCHEMA "personal-finance" TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA "personal-finance" TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "personal-finance" TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA "personal-finance" GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA "personal-finance" GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA "personal-finance" TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA "personal-finance" GRANT USAGE ON SEQUENCES TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA "personal-finance" TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA "personal-finance" GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;

-- ===================== ORG ID HELPER =====================
CREATE OR REPLACE FUNCTION "personal-finance".user_org_id()
RETURNS UUID LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT org_id FROM public.noctus_users WHERE id = auth.uid() $$;

-- ===================== ACCOUNTS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".contas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN (
        'corrente','poupanca','cartao_credito','investimento',
        'carteira','emprestimo','outro'
    )),
    instituicao TEXT,
    saldo DECIMAL(14,2) DEFAULT 0,
    moeda TEXT DEFAULT 'BRL',
    cor TEXT DEFAULT '#6366f1',
    icone TEXT DEFAULT '🏦',
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== CATEGORIES =====================
CREATE TABLE IF NOT EXISTS "personal-finance".categorias (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID REFERENCES public.organizations(id),  -- NULL = system default
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('receita','despesa','transferencia')),
    categoria_pai_id UUID REFERENCES "personal-finance".categorias(id),
    icone TEXT,
    cor TEXT,
    tipo_orcamento TEXT CHECK (tipo_orcamento IN ('necessidade','desejo','poupanca')),
    is_sistema BOOLEAN DEFAULT false,
    ordem INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== TRANSACTIONS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".transacoes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    conta_id UUID NOT NULL REFERENCES "personal-finance".contas(id),
    conta_destino_id UUID REFERENCES "personal-finance".contas(id),
    categoria_id UUID REFERENCES "personal-finance".categorias(id),
    data DATE NOT NULL,
    valor DECIMAL(14,2) NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('receita','despesa','transferencia')),
    descricao TEXT,
    comerciante TEXT,
    notas TEXT,
    tags TEXT[] DEFAULT '{}',
    is_recorrente BOOLEAN DEFAULT false,
    recorrente_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== BUDGETS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".orcamentos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    nome TEXT NOT NULL,
    metodo TEXT DEFAULT 'zero_based' CHECK (metodo IN ('zero_based','envelope','50_30_20','personalizado')),
    periodo TEXT DEFAULT 'mensal' CHECK (periodo IN ('mensal','quinzenal','semanal')),
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "personal-finance".orcamento_itens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    orcamento_id UUID NOT NULL REFERENCES "personal-finance".orcamentos(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    categoria_id UUID NOT NULL REFERENCES "personal-finance".categorias(id),
    valor_planejado DECIMAL(14,2) NOT NULL,
    periodo_mes TEXT NOT NULL,  -- 'YYYY-MM'
    valor_gasto DECIMAL(14,2) DEFAULT 0,
    rollover DECIMAL(14,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== FINANCIAL GOALS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".metas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN (
        'poupanca','quitar_divida','investimento','fundo_emergencia','personalizado'
    )),
    valor_alvo DECIMAL(14,2) NOT NULL,
    valor_atual DECIMAL(14,2) DEFAULT 0,
    data_alvo DATE,
    conta_vinculada_id UUID REFERENCES "personal-finance".contas(id),
    prioridade TEXT DEFAULT 'media' CHECK (prioridade IN ('alta','media','baixa')),
    status TEXT DEFAULT 'ativa' CHECK (status IN ('ativa','concluida','pausada','cancelada')),
    icone TEXT DEFAULT '🎯',
    cor TEXT DEFAULT '#10b981',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "personal-finance".meta_contribuicoes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    meta_id UUID NOT NULL REFERENCES "personal-finance".metas(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    valor DECIMAL(14,2) NOT NULL,
    data DATE NOT NULL,
    fonte TEXT DEFAULT 'manual' CHECK (fonte IN ('manual','automatica','transacao')),
    transacao_id UUID REFERENCES "personal-finance".transacoes(id),
    notas TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== INVESTMENT PORTFOLIOS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".carteiras (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    nome TEXT NOT NULL,
    tipo TEXT DEFAULT 'geral' CHECK (tipo IN (
        'geral','acoes','renda_fixa','fundos','crypto','previdencia','outro'
    )),
    corretora TEXT,
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== HOLDINGS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".ativos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    carteira_id UUID NOT NULL REFERENCES "personal-finance".carteiras(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    ticker TEXT NOT NULL,
    nome TEXT,
    tipo TEXT NOT NULL CHECK (tipo IN (
        'acao','etf','fii','bdr','renda_fixa','tesouro_direto',
        'fundo','crypto','cdb','lci_lca','debenture','outro'
    )),
    quantidade DECIMAL(18,8) DEFAULT 0,
    preco_medio DECIMAL(14,4) DEFAULT 0,
    preco_atual DECIMAL(14,4) DEFAULT 0,
    valor_atual DECIMAL(14,2) DEFAULT 0,
    ganho_perda DECIMAL(14,2) DEFAULT 0,
    ganho_perda_pct DECIMAL(8,4) DEFAULT 0,
    setor TEXT,
    last_update TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== INVESTMENT TRANSACTIONS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".operacoes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    carteira_id UUID NOT NULL REFERENCES "personal-finance".carteiras(id),
    ativo_id UUID REFERENCES "personal-finance".ativos(id),
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    ticker TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN (
        'compra','venda','dividendo','jcp','rendimento',
        'split','bonificacao','amortizacao','transferencia'
    )),
    data DATE NOT NULL,
    quantidade DECIMAL(18,8),
    preco_unitario DECIMAL(14,4),
    taxas DECIMAL(14,2) DEFAULT 0,
    valor_total DECIMAL(14,2) NOT NULL,
    notas TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== WATCHLISTS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".watchlists (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    nome TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "personal-finance".watchlist_itens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    watchlist_id UUID NOT NULL REFERENCES "personal-finance".watchlists(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    ticker TEXT NOT NULL,
    nome TEXT,
    alerta_preco_acima DECIMAL(14,4),
    alerta_preco_abaixo DECIMAL(14,4),
    notas TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== RECURRING TRANSACTIONS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".recorrentes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    conta_id UUID REFERENCES "personal-finance".contas(id),
    nome TEXT NOT NULL,
    valor DECIMAL(14,2) NOT NULL,
    categoria_id UUID REFERENCES "personal-finance".categorias(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('receita','despesa')),
    frequencia TEXT NOT NULL CHECK (frequencia IN (
        'semanal','quinzenal','mensal','bimestral','trimestral','semestral','anual'
    )),
    dia_vencimento INT,
    proxima_data DATE,
    is_automatico BOOLEAN DEFAULT false,
    comerciante TEXT,
    lembrete_dias INT DEFAULT 3,
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== NET WORTH SNAPSHOTS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".patrimonio_snapshots (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    data DATE NOT NULL,
    total_ativos DECIMAL(14,2) DEFAULT 0,
    total_passivos DECIMAL(14,2) DEFAULT 0,
    patrimonio_liquido DECIMAL(14,2) DEFAULT 0,
    detalhamento JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== MONTHLY SUMMARIES =====================
CREATE TABLE IF NOT EXISTS "personal-finance".resumos_mensais (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    mes TEXT NOT NULL,  -- 'YYYY-MM'
    receita_total DECIMAL(14,2) DEFAULT 0,
    despesa_total DECIMAL(14,2) DEFAULT 0,
    fluxo_liquido DECIMAL(14,2) DEFAULT 0,
    taxa_poupanca DECIMAL(8,4) DEFAULT 0,
    top_categorias JSONB DEFAULT '[]',
    retorno_investimentos DECIMAL(14,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, mes)
);

-- ===================== TARGET ALLOCATIONS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".alocacao_alvo (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    carteira_id UUID NOT NULL REFERENCES "personal-finance".carteiras(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id),
    classe_ativo TEXT NOT NULL,
    percentual_alvo DECIMAL(8,4) NOT NULL,
    percentual_atual DECIMAL(8,4) DEFAULT 0,
    limite_desvio DECIMAL(8,4) DEFAULT 5.0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== RLS POLICIES =====================
ALTER TABLE "personal-finance".contas ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".categorias ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".transacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".orcamentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".orcamento_itens ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".metas ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".meta_contribuicoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".carteiras ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".ativos ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".operacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".watchlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".watchlist_itens ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".recorrentes ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".patrimonio_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".resumos_mensais ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".alocacao_alvo ENABLE ROW LEVEL SECURITY;

CREATE POLICY "contas_org" ON "personal-finance".contas
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "categorias_org" ON "personal-finance".categorias
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id() OR org_id IS NULL);
CREATE POLICY "transacoes_org" ON "personal-finance".transacoes
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "orcamentos_org" ON "personal-finance".orcamentos
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "orcamento_itens_org" ON "personal-finance".orcamento_itens
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "metas_org" ON "personal-finance".metas
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "meta_contribuicoes_org" ON "personal-finance".meta_contribuicoes
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "carteiras_org" ON "personal-finance".carteiras
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "ativos_org" ON "personal-finance".ativos
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "operacoes_org" ON "personal-finance".operacoes
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "watchlists_org" ON "personal-finance".watchlists
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "watchlist_itens_org" ON "personal-finance".watchlist_itens
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "recorrentes_org" ON "personal-finance".recorrentes
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "patrimonio_org" ON "personal-finance".patrimonio_snapshots
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "resumos_org" ON "personal-finance".resumos_mensais
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());
CREATE POLICY "alocacao_org" ON "personal-finance".alocacao_alvo
    FOR ALL TO authenticated USING (org_id = "personal-finance".user_org_id());

-- ===================== SEED DEFAULT CATEGORIES =====================
INSERT INTO "personal-finance".categorias (nome, tipo, icone, cor, tipo_orcamento, is_sistema, ordem) VALUES
-- Income
('Salario', 'receita', '💰', '#10b981', NULL, true, 1),
('Freelance', 'receita', '💻', '#3b82f6', NULL, true, 2),
('Investimentos', 'receita', '📈', '#8b5cf6', NULL, true, 3),
('Outros Rendimentos', 'receita', '💵', '#6b7280', NULL, true, 4),
-- Essential expenses (needs)
('Moradia', 'despesa', '🏠', '#ef4444', 'necessidade', true, 10),
('Alimentacao', 'despesa', '🛒', '#f59e0b', 'necessidade', true, 11),
('Transporte', 'despesa', '🚗', '#3b82f6', 'necessidade', true, 12),
('Saude', 'despesa', '🏥', '#10b981', 'necessidade', true, 13),
('Educacao', 'despesa', '📚', '#8b5cf6', 'necessidade', true, 14),
('Contas e Utilidades', 'despesa', '💡', '#6366f1', 'necessidade', true, 15),
('Seguros', 'despesa', '🛡️', '#64748b', 'necessidade', true, 16),
-- Wants
('Lazer', 'despesa', '🎬', '#ec4899', 'desejo', true, 20),
('Restaurantes', 'despesa', '🍽️', '#f97316', 'desejo', true, 21),
('Compras', 'despesa', '🛍️', '#a855f7', 'desejo', true, 22),
('Assinaturas', 'despesa', '📱', '#0ea5e9', 'desejo', true, 23),
('Viagens', 'despesa', '✈️', '#14b8a6', 'desejo', true, 24),
-- Savings
('Poupanca', 'despesa', '🏦', '#22c55e', 'poupanca', true, 30),
('Investimentos Aporte', 'despesa', '📊', '#6366f1', 'poupanca', true, 31),
-- Transfers
('Transferencia', 'transferencia', '🔄', '#94a3b8', NULL, true, 40)
ON CONFLICT DO NOTHING;

-- ===================== INDEXES =====================
CREATE INDEX IF NOT EXISTS idx_transacoes_org_data ON "personal-finance".transacoes(org_id, data DESC);
CREATE INDEX IF NOT EXISTS idx_transacoes_conta ON "personal-finance".transacoes(conta_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_categoria ON "personal-finance".transacoes(categoria_id);
CREATE INDEX IF NOT EXISTS idx_ativos_carteira ON "personal-finance".ativos(carteira_id);
CREATE INDEX IF NOT EXISTS idx_operacoes_carteira ON "personal-finance".operacoes(carteira_id);
CREATE INDEX IF NOT EXISTS idx_operacoes_ticker ON "personal-finance".operacoes(ticker);
CREATE INDEX IF NOT EXISTS idx_patrimonio_org_data ON "personal-finance".patrimonio_snapshots(org_id, data DESC);

-- ===================== TIMESTAMPS TRIGGER =====================
CREATE OR REPLACE FUNCTION "personal-finance".set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_contas_updated_at BEFORE UPDATE ON "personal-finance".contas
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
CREATE TRIGGER set_transacoes_updated_at BEFORE UPDATE ON "personal-finance".transacoes
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
CREATE TRIGGER set_ativos_updated_at BEFORE UPDATE ON "personal-finance".ativos
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
CREATE TRIGGER set_carteiras_updated_at BEFORE UPDATE ON "personal-finance".carteiras
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
CREATE TRIGGER set_metas_updated_at BEFORE UPDATE ON "personal-finance".metas
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
CREATE TRIGGER set_recorrentes_updated_at BEFORE UPDATE ON "personal-finance".recorrentes
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
CREATE TRIGGER set_orcamento_itens_updated_at BEFORE UPDATE ON "personal-finance".orcamento_itens
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
