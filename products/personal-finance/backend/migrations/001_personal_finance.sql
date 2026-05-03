-- =====================================================================
-- NoctusAI Personal Finance — Database Schema
-- Schema: "personal-finance"
--
-- **Rewritten 2026-05-03 by `pf-org-scoping-migration` Phase 6** to reflect
-- deployed truth. Pre-rewrite this file declared a fictional `user_org_id()`
-- helper + an org-scoped shape that was never actually applied; live state
-- was user-scoped (per the `pf-schema-drift-reconciliation` audit, 2026-04-27).
-- This rewrite makes the migration accurately describe the deployed schema:
-- org-scoped via `public.current_org_id()`, `created_by uuid NULL` audit
-- field, no `user_org_id` schema-local helper, uniform RLS shape.
--
-- Migration 008 still exists on disk and was the transition vehicle that
-- flipped the live DB from user-scoped to org-scoped. On fresh clones it is
-- a near-no-op: 001 already declares truth, and 008's idempotent guards
-- short-circuit the column-rename steps when user_id no longer exists.
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

-- ===================== ORG SCOPING =====================
-- RLS reads the platform-level `public.current_org_id()` helper (defined in
-- core; reads the JWT `org_id` claim). No PF-local org helper.

-- ===================== ACCOUNTS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".contas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
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
-- §7.2=B: per-org seeded copies. RLS is uniform `org_id = current_org_id()`
-- with no NULL branch; defaults are seeded per-org by
-- `app/services/onboarding_service.seed_default_categories`.
CREATE TABLE IF NOT EXISTS "personal-finance".categorias (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
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
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
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
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    nome TEXT NOT NULL,
    metodo TEXT DEFAULT 'zero_based' CHECK (metodo IN ('zero_based','50_30_20','custom')),
    periodo TEXT DEFAULT 'mensal' CHECK (periodo IN ('mensal','quinzenal','semanal')),
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "personal-finance".orcamento_itens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    orcamento_id UUID NOT NULL REFERENCES "personal-finance".orcamentos(id) ON DELETE CASCADE,
    categoria_id UUID NOT NULL REFERENCES "personal-finance".categorias(id),
    valor_planejado DECIMAL(14,2) NOT NULL,
    periodo_mes TEXT NOT NULL,
    valor_gasto DECIMAL(14,2) DEFAULT 0,
    rollover DECIMAL(14,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== GOALS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".metas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('reserva_emergencia','aposentadoria','viagem','imovel','educacao','outro')),
    valor_alvo DECIMAL(14,2) NOT NULL,
    valor_atual DECIMAL(14,2) DEFAULT 0,
    data_alvo DATE,
    conta_vinculada_id UUID REFERENCES "personal-finance".contas(id),
    prioridade TEXT DEFAULT 'media' CHECK (prioridade IN ('alta','media','baixa')),
    status TEXT DEFAULT 'ativa' CHECK (status IN ('ativa','pausada','concluida','cancelada')),
    icone TEXT DEFAULT '🎯',
    cor TEXT DEFAULT '#10b981',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "personal-finance".meta_contribuicoes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    meta_id UUID NOT NULL REFERENCES "personal-finance".metas(id) ON DELETE CASCADE,
    valor DECIMAL(14,2) NOT NULL,
    data DATE NOT NULL,
    fonte TEXT DEFAULT 'manual' CHECK (fonte IN ('manual','automatica','transacao')),
    transacao_id UUID REFERENCES "personal-finance".transacoes(id),
    notas TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== PORTFOLIOS / INVESTMENTS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".carteiras (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    nome TEXT NOT NULL,
    tipo TEXT DEFAULT 'geral' CHECK (tipo IN ('geral','renda_fixa','renda_variavel','cripto','internacional')),
    corretora TEXT,
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "personal-finance".ativos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    carteira_id UUID NOT NULL REFERENCES "personal-finance".carteiras(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    nome TEXT,
    tipo TEXT NOT NULL CHECK (tipo IN ('acao','fii','etf','cripto','renda_fixa','outro')),
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

CREATE TABLE IF NOT EXISTS "personal-finance".operacoes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    carteira_id UUID NOT NULL REFERENCES "personal-finance".carteiras(id) ON DELETE CASCADE,
    ativo_id UUID REFERENCES "personal-finance".ativos(id),
    ticker TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('compra','venda','dividendo','jcp','desdobramento','grupamento')),
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
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    nome TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "personal-finance".watchlist_itens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    watchlist_id UUID NOT NULL REFERENCES "personal-finance".watchlists(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    nome TEXT,
    alerta_preco_acima DECIMAL(14,4),
    alerta_preco_abaixo DECIMAL(14,4),
    notas TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== RECURRING =====================
CREATE TABLE IF NOT EXISTS "personal-finance".recorrentes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    conta_id UUID REFERENCES "personal-finance".contas(id),
    nome TEXT NOT NULL,
    valor DECIMAL(14,2) NOT NULL,
    categoria_id UUID REFERENCES "personal-finance".categorias(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('receita','despesa')),
    frequencia TEXT NOT NULL CHECK (frequencia IN ('diario','semanal','quinzenal','mensal','bimestral','trimestral','semestral','anual')),
    dia_vencimento INT,
    proxima_data DATE,
    is_automatico BOOLEAN DEFAULT false,
    comerciante TEXT,
    lembrete_dias INT DEFAULT 3,
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== PATRIMONY SNAPSHOTS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".patrimonio_snapshots (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
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
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    mes TEXT NOT NULL,
    receita_total DECIMAL(14,2) DEFAULT 0,
    despesa_total DECIMAL(14,2) DEFAULT 0,
    fluxo_liquido DECIMAL(14,2) DEFAULT 0,
    taxa_poupanca DECIMAL(6,2) DEFAULT 0,
    top_categorias JSONB DEFAULT '[]',
    retorno_investimentos DECIMAL(14,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT resumos_mensais_org_id_mes_key UNIQUE (org_id, mes)
);

-- ===================== ALOCACAO ALVO =====================
CREATE TABLE IF NOT EXISTS "personal-finance".alocacao_alvo (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    carteira_id UUID NOT NULL REFERENCES "personal-finance".carteiras(id) ON DELETE CASCADE,
    classe_ativo TEXT NOT NULL,
    percentual_alvo DECIMAL(5,2) NOT NULL,
    percentual_atual DECIMAL(5,2) DEFAULT 0,
    limite_desvio DECIMAL(5,2) DEFAULT 5.0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== ROW LEVEL SECURITY =====================
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

-- All policies use the platform-level `public.current_org_id()` helper.
-- Parent tables filter directly on `org_id`; child tables traverse to parent.

CREATE POLICY contas_org_scoped ON "personal-finance".contas
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY categorias_org_scoped ON "personal-finance".categorias
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY transacoes_org_scoped ON "personal-finance".transacoes
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY orcamentos_org_scoped ON "personal-finance".orcamentos
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY orcamento_itens_org_scoped ON "personal-finance".orcamento_itens
    FOR ALL TO authenticated
    USING (orcamento_id IN (SELECT id FROM "personal-finance".orcamentos WHERE org_id = public.current_org_id()))
    WITH CHECK (orcamento_id IN (SELECT id FROM "personal-finance".orcamentos WHERE org_id = public.current_org_id()));

CREATE POLICY metas_org_scoped ON "personal-finance".metas
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY meta_contribuicoes_org_scoped ON "personal-finance".meta_contribuicoes
    FOR ALL TO authenticated
    USING (meta_id IN (SELECT id FROM "personal-finance".metas WHERE org_id = public.current_org_id()))
    WITH CHECK (meta_id IN (SELECT id FROM "personal-finance".metas WHERE org_id = public.current_org_id()));

CREATE POLICY carteiras_org_scoped ON "personal-finance".carteiras
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY ativos_org_scoped ON "personal-finance".ativos
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY operacoes_org_scoped ON "personal-finance".operacoes
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY watchlists_org_scoped ON "personal-finance".watchlists
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY watchlist_itens_org_scoped ON "personal-finance".watchlist_itens
    FOR ALL TO authenticated
    USING (watchlist_id IN (SELECT id FROM "personal-finance".watchlists WHERE org_id = public.current_org_id()))
    WITH CHECK (watchlist_id IN (SELECT id FROM "personal-finance".watchlists WHERE org_id = public.current_org_id()));

CREATE POLICY recorrentes_org_scoped ON "personal-finance".recorrentes
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY patrimonio_org_scoped ON "personal-finance".patrimonio_snapshots
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY resumos_org_scoped ON "personal-finance".resumos_mensais
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY alocacao_org_scoped ON "personal-finance".alocacao_alvo
    FOR ALL TO authenticated
    USING (carteira_id IN (SELECT id FROM "personal-finance".carteiras WHERE org_id = public.current_org_id()))
    WITH CHECK (carteira_id IN (SELECT id FROM "personal-finance".carteiras WHERE org_id = public.current_org_id()));

-- ===================== INDEXES =====================
-- org_id (one per parent table) + business-relevant composites.
CREATE INDEX IF NOT EXISTS idx_contas_org_id ON "personal-finance".contas(org_id);
CREATE INDEX IF NOT EXISTS idx_categorias_org_id ON "personal-finance".categorias(org_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_org_id ON "personal-finance".transacoes(org_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_org_data ON "personal-finance".transacoes(org_id, data DESC);
CREATE INDEX IF NOT EXISTS idx_orcamentos_org_id ON "personal-finance".orcamentos(org_id);
CREATE INDEX IF NOT EXISTS idx_metas_org_id ON "personal-finance".metas(org_id);
CREATE INDEX IF NOT EXISTS idx_carteiras_org_id ON "personal-finance".carteiras(org_id);
CREATE INDEX IF NOT EXISTS idx_ativos_org_id ON "personal-finance".ativos(org_id);
CREATE INDEX IF NOT EXISTS idx_operacoes_org_id ON "personal-finance".operacoes(org_id);
CREATE INDEX IF NOT EXISTS idx_watchlists_org_id ON "personal-finance".watchlists(org_id);
CREATE INDEX IF NOT EXISTS idx_recorrentes_org_id ON "personal-finance".recorrentes(org_id);
CREATE INDEX IF NOT EXISTS idx_patrimonio_snapshots_org_id ON "personal-finance".patrimonio_snapshots(org_id);
CREATE INDEX IF NOT EXISTS idx_patrimonio_org_data ON "personal-finance".patrimonio_snapshots(org_id, data DESC);
CREATE INDEX IF NOT EXISTS idx_resumos_mensais_org_id ON "personal-finance".resumos_mensais(org_id);

-- FK indexes (child tables + cross-references)
CREATE INDEX IF NOT EXISTS idx_alocacao_alvo_carteira_id ON "personal-finance".alocacao_alvo(carteira_id);
CREATE INDEX IF NOT EXISTS idx_categorias_categoria_pai_id ON "personal-finance".categorias(categoria_pai_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_conta ON "personal-finance".transacoes(conta_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_conta_destino_id ON "personal-finance".transacoes(conta_destino_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_categoria ON "personal-finance".transacoes(categoria_id);
CREATE INDEX IF NOT EXISTS idx_meta_contribuicoes_meta_id ON "personal-finance".meta_contribuicoes(meta_id);
CREATE INDEX IF NOT EXISTS idx_meta_contribuicoes_transacao_id ON "personal-finance".meta_contribuicoes(transacao_id);
CREATE INDEX IF NOT EXISTS idx_metas_conta_vinculada_id ON "personal-finance".metas(conta_vinculada_id);
CREATE INDEX IF NOT EXISTS idx_operacoes_ativo_id ON "personal-finance".operacoes(ativo_id);
CREATE INDEX IF NOT EXISTS idx_orcamento_itens_orcamento_id ON "personal-finance".orcamento_itens(orcamento_id);
CREATE INDEX IF NOT EXISTS idx_orcamento_itens_categoria_id ON "personal-finance".orcamento_itens(categoria_id);
CREATE INDEX IF NOT EXISTS idx_recorrentes_conta_id ON "personal-finance".recorrentes(conta_id);
CREATE INDEX IF NOT EXISTS idx_recorrentes_categoria_id ON "personal-finance".recorrentes(categoria_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_itens_watchlist_id ON "personal-finance".watchlist_itens(watchlist_id);

-- ===================== TIMESTAMPS TRIGGER =====================
CREATE OR REPLACE FUNCTION "personal-finance".set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = "personal-finance", public;

DROP TRIGGER IF EXISTS set_contas_updated_at ON "personal-finance".contas;
CREATE TRIGGER set_contas_updated_at BEFORE UPDATE ON "personal-finance".contas
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
DROP TRIGGER IF EXISTS set_transacoes_updated_at ON "personal-finance".transacoes;
CREATE TRIGGER set_transacoes_updated_at BEFORE UPDATE ON "personal-finance".transacoes
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
DROP TRIGGER IF EXISTS set_ativos_updated_at ON "personal-finance".ativos;
CREATE TRIGGER set_ativos_updated_at BEFORE UPDATE ON "personal-finance".ativos
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
DROP TRIGGER IF EXISTS set_carteiras_updated_at ON "personal-finance".carteiras;
CREATE TRIGGER set_carteiras_updated_at BEFORE UPDATE ON "personal-finance".carteiras
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
DROP TRIGGER IF EXISTS set_metas_updated_at ON "personal-finance".metas;
CREATE TRIGGER set_metas_updated_at BEFORE UPDATE ON "personal-finance".metas
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
DROP TRIGGER IF EXISTS set_recorrentes_updated_at ON "personal-finance".recorrentes;
CREATE TRIGGER set_recorrentes_updated_at BEFORE UPDATE ON "personal-finance".recorrentes
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
DROP TRIGGER IF EXISTS set_orcamento_itens_updated_at ON "personal-finance".orcamento_itens;
CREATE TRIGGER set_orcamento_itens_updated_at BEFORE UPDATE ON "personal-finance".orcamento_itens
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
