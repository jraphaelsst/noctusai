-- =====================================================================
-- ERP Imobiliário — Consolidated Schema Migration
-- Merged from 87 incremental migration files into a single idempotent script.
-- Run this once on a fresh Supabase project.
--
-- All ERP objects live in the `erp` schema. Core platform tables stay in `public`.
-- =====================================================================

-- ─────────────────────────────────────────────────────────────────────
-- 0. SCHEMA + PERMISSIONS
-- ─────────────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS erp;

GRANT USAGE ON SCHEMA erp TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA erp TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA erp TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA erp TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT USAGE ON SEQUENCES TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA erp TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;

-- ─────────────────────────────────────────────────────────────────────
-- 1. EXTENSIONS
-- ─────────────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

-- ─────────────────────────────────────────────────────────────────────
-- 2. ENUMS
-- ─────────────────────────────────────────────────────────────────────

CREATE TYPE erp.tipo_meta AS ENUM ('diaria', 'semanal', 'mensal', 'anual');

CREATE TYPE erp.status_meta AS ENUM ('aberta', 'concluida', 'atrasada', 'no_prazo', 'vence_amanha');

CREATE TYPE erp.app_role AS ENUM ('admin', 'corretor', 'coordenador', 'dev');

CREATE TYPE erp.categoria_meta AS ENUM (
  'captacao', 'visitas', 'contatos', 'propostas', 'fechamento',
  'captacao_imoveis', 'captacao_compradores', 'atualizacao_imoveis', 'outro'
);

CREATE TYPE erp.conclusao_prazo_meta AS ENUM ('no_prazo', 'atrasada');

CREATE TYPE erp.nivel_performance_meta AS ENUM ('baixo', 'regular', 'bom', 'excelente');

CREATE TYPE erp.etapa_funil AS ENUM ('qualificacao', 'visitas', 'proposta', 'negociacao', 'fechado');

CREATE TYPE erp.tipo_atividade AS ENUM ('ligacao', 'email', 'reuniao', 'whatsapp', 'visita', 'proposta', 'negociacao', 'outro');

CREATE TYPE erp.status_negociacao AS ENUM ('qualificacao', 'visitas', 'proposta', 'negociacao', 'fechado', 'cancelado');

CREATE TYPE erp.tipo_acao AS ENUM (
  'criar', 'editar', 'excluir', 'concluir',
  'arquivar', 'desarquivar', 'mover', 'login', 'logout'
);

CREATE TYPE erp.tipo_entidade AS ENUM (
  'meta', 'cliente', 'usuario', 'atividade', 'config_meta', 'auth',
  'negociacao', 'match', 'condominio', 'ativo'
);

CREATE TYPE erp.status_match AS ENUM ('pendente', 'aceito', 'rejeitado', 'expirado');

-- ─────────────────────────────────────────────────────────────────────
-- 3. SEQUENCES
-- ─────────────────────────────────────────────────────────────────────

CREATE SEQUENCE IF NOT EXISTS erp.metas_id_seq;
CREATE SEQUENCE IF NOT EXISTS erp.negociacoes_id_seq START WITH 1;

-- ─────────────────────────────────────────────────────────────────────
-- 4. UTILITY FUNCTIONS
-- ─────────────────────────────────────────────────────────────────────

-- Timestamp helpers (São Paulo timezone)
CREATE OR REPLACE FUNCTION erp.current_date_sao_paulo()
RETURNS DATE
LANGUAGE SQL STABLE
AS $$ SELECT (NOW() AT TIME ZONE 'America/Sao_Paulo')::DATE; $$;

CREATE OR REPLACE FUNCTION erp.now_sao_paulo()
RETURNS TIMESTAMP WITH TIME ZONE
LANGUAGE SQL STABLE
AS $$ SELECT NOW() AT TIME ZONE 'America/Sao_Paulo'; $$;

CREATE OR REPLACE FUNCTION erp.normalize_timestamp_sp(ts TIMESTAMP WITH TIME ZONE)
RETURNS TIMESTAMP WITH TIME ZONE
LANGUAGE SQL IMMUTABLE
AS $$ SELECT ts AT TIME ZONE 'America/Sao_Paulo'; $$;

-- Generic updated_at trigger
CREATE OR REPLACE FUNCTION erp.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

-- São Paulo timestamp trigger for created_at/updated_at
CREATE OR REPLACE FUNCTION erp.set_timestamps_sp()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE
  has_updated_at boolean;
BEGIN
  -- Check if the table has an updated_at column (safe for all tables)
  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = TG_TABLE_SCHEMA
      AND table_name = TG_TABLE_NAME
      AND column_name = 'updated_at'
  ) INTO has_updated_at;

  IF TG_OP = 'INSERT' THEN
    NEW.created_at := now_sao_paulo();
    IF has_updated_at THEN
      NEW.updated_at := now_sao_paulo();
    END IF;
  ELSIF TG_OP = 'UPDATE' THEN
    IF has_updated_at THEN
      NEW.updated_at := now_sao_paulo();
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

-- ID generators (sequence-based, concurrency-safe)
CREATE OR REPLACE FUNCTION erp.generate_meta_id()
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE next_number INTEGER; next_id TEXT;
BEGIN
  next_number := nextval('erp.metas_id_seq')::INTEGER;
  IF next_number <= 9999 THEN
    next_id := 'MT' || LPAD(next_number::TEXT, 4, '0');
  ELSE
    next_id := 'MT' || next_number::TEXT;
  END IF;
  RETURN next_id;
END;
$$;

CREATE OR REPLACE FUNCTION erp.generate_negociacao_id()
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE next_number INTEGER; next_id TEXT;
BEGIN
  next_number := nextval('erp.negociacoes_id_seq')::INTEGER;
  IF next_number <= 9999 THEN
    next_id := 'NG' || LPAD(next_number::TEXT, 4, '0');
  ELSE
    next_id := 'NG' || next_number::TEXT;
  END IF;
  RETURN next_id;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────
-- 5. TABLES
-- ─────────────────────────────────────────────────────────────────────

-- 5a. Profiles (linked to auth.users)
CREATE TABLE erp.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  email TEXT NOT NULL,
  telefone TEXT NOT NULL,
  avatar TEXT,
  last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5b. User roles
CREATE TABLE erp.user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  role app_role NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  UNIQUE (user_id, role)
);

-- Role check helper (stays in public — used by RLS policies and auth context)
CREATE OR REPLACE FUNCTION public.has_role(_user_id UUID, _role erp.app_role)
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT EXISTS (SELECT 1 FROM erp.user_roles WHERE user_id = _user_id AND role = _role); $$;

-- 5c. Metas (goals) — fully merged with all incremental columns
CREATE TABLE erp.metas (
  id TEXT PRIMARY KEY DEFAULT erp.generate_meta_id(),
  usuario_id UUID NOT NULL REFERENCES erp.profiles(id) ON DELETE CASCADE,
  tipo erp.tipo_meta NOT NULL,
  categoria erp.categoria_meta NOT NULL DEFAULT 'captacao',
  categoria_custom TEXT,
  nome TEXT,
  detalhes TEXT,
  meta_pretendida INTEGER NOT NULL,
  meta_realizada INTEGER DEFAULT 0,
  data_prazo DATE NOT NULL,
  status erp.status_meta DEFAULT 'aberta' NOT NULL,
  carry_in INTEGER NOT NULL DEFAULT 0,
  carry_out INTEGER NOT NULL DEFAULT 0,
  conclusao_prazo erp.conclusao_prazo_meta NOT NULL DEFAULT 'no_prazo',
  nivel_performance erp.nivel_performance_meta NOT NULL DEFAULT 'baixo',
  dias_restantes INTEGER,
  tem_impedimento BOOLEAN NOT NULL DEFAULT false,
  motivo_impedimento TEXT,
  criada_manualmente BOOLEAN NOT NULL DEFAULT false,
  finalizada_em TIMESTAMP WITH TIME ZONE,
  finalizada_no_prazo BOOLEAN,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT check_motivo_impedimento CHECK (
    (tem_impedimento = false) OR
    (tem_impedimento = true AND motivo_impedimento IS NOT NULL AND trim(motivo_impedimento) <> '')
  )
);

-- 5d. Metas config (monthly targets)
CREATE TABLE erp.metas_config (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  usuario_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tipo tipo_meta NOT NULL,
  categoria categoria_meta NOT NULL,
  categoria_custom TEXT,
  meta_pretendida INTEGER NOT NULL DEFAULT 0,
  ativo BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  UNIQUE(usuario_id, tipo, categoria)
);

-- 5e. Clientes (CRM)
CREATE TABLE erp.clientes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID NOT NULL REFERENCES erp.profiles(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  email TEXT UNIQUE,
  telefone TEXT,
  origem TEXT,
  interesse TEXT,
  observacoes TEXT,
  etapa_atual etapa_funil NOT NULL DEFAULT 'qualificacao',
  probabilidade INTEGER NOT NULL DEFAULT 10 CHECK (probabilidade >= 0 AND probabilidade <= 100),
  valor_estimado NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (valor_estimado >= 0),
  arquivado BOOLEAN NOT NULL DEFAULT false,
  kanban_pos INTEGER NOT NULL DEFAULT 0,
  lead_score INTEGER CHECK (lead_score >= 0 AND lead_score <= 100),
  lead_score_justificativa TEXT,
  lead_score_updated_at TIMESTAMPTZ,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5f. Funil movimentos (funnel history)
CREATE TABLE erp.funil_movimentos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id UUID NOT NULL REFERENCES erp.clientes(id) ON DELETE CASCADE,
  de_etapa etapa_funil,
  para_etapa etapa_funil NOT NULL,
  responsavel_id UUID NOT NULL REFERENCES erp.profiles(id),
  motivo TEXT,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5g. Atividades (activities)
CREATE TABLE erp.atividades (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id UUID NOT NULL REFERENCES erp.clientes(id) ON DELETE CASCADE,
  usuario_id UUID NOT NULL REFERENCES erp.profiles(id),
  tipo tipo_atividade NOT NULL DEFAULT 'outro',
  descricao TEXT NOT NULL,
  data_execucao TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5h. Password request codes (admin temporary passwords)
CREATE TABLE erp.password_request_codes (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  admin_user_id UUID NOT NULL,
  corretor_id UUID NOT NULL,
  code TEXT NOT NULL,
  temp_password TEXT NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5i. Status pagina (feature flags)
CREATE TABLE erp.status_pagina (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome_pagina TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento')),
  descricao TEXT,
  tipo_pagina TEXT NOT NULL DEFAULT 'geral',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5j. User actions log (audit trail)
CREATE TABLE erp.user_actions_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tipo_acao tipo_acao NOT NULL,
  tipo_entidade tipo_entidade NOT NULL,
  entidade_id TEXT,
  descricao TEXT NOT NULL,
  detalhes JSONB,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5k. Negociações (negotiations) — FK to ativos added after ativos table creation
CREATE TABLE erp.negociacoes (
  id TEXT PRIMARY KEY DEFAULT generate_negociacao_id(),
  owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  ativo_origem_id UUID NOT NULL,
  ativo_destino_id UUID NOT NULL,
  cliente_proprietario_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  cliente_ofertante_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  valor_imovel NUMERIC(12,2) NOT NULL,
  valor_permuta NUMERIC(12,2) NOT NULL,
  valor_complemento NUMERIC(12,2) DEFAULT 0,
  status_etapa status_negociacao NOT NULL DEFAULT 'qualificacao',
  timeline JSONB DEFAULT '[]'::JSONB,
  observacoes TEXT
);

-- 5l. Condominios
CREATE TABLE erp.condominios (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  endereco TEXT,
  bairro TEXT,
  cidade TEXT,
  estado TEXT,
  cep TEXT,
  valor_condominio NUMERIC DEFAULT 0,
  sindico TEXT,
  telefone_sindico TEXT,
  administradora TEXT,
  torres INTEGER,
  unidades_por_andar INTEGER,
  total_unidades INTEGER,
  possui_portaria BOOLEAN DEFAULT false,
  possui_piscina BOOLEAN DEFAULT false,
  possui_academia BOOLEAN DEFAULT false,
  possui_salao_festas BOOLEAN DEFAULT false,
  possui_playground BOOLEAN DEFAULT false,
  possui_churrasqueira BOOLEAN DEFAULT false,
  observacoes TEXT,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- 5l. Matches (computed matches between ativos)
CREATE TABLE erp.matches (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ativo_origem_id UUID NOT NULL,
  ativo_destino_id UUID NOT NULL,
  score INTEGER NOT NULL DEFAULT 0 CHECK (score >= 0 AND score <= 100),
  status status_match NOT NULL DEFAULT 'pendente',
  justificativa TEXT,
  detalhes JSONB DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  UNIQUE(ativo_origem_id, ativo_destino_id)
);

-- 5q. Ativos (unified assets: imóveis + permutas)
CREATE TABLE erp.ativos (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  natureza TEXT NOT NULL CHECK (natureza IN ('imovel', 'permuta_imovel', 'permuta_automovel')),
  -- Shared fields
  valor NUMERIC NOT NULL DEFAULT 0,
  status TEXT DEFAULT 'ativo',
  observacoes TEXT,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  -- Property fields (imovel + permuta_imovel)
  tipo_imovel TEXT,
  cep TEXT,
  logradouro TEXT,
  numero TEXT,
  complemento TEXT,
  bairro TEXT,
  cidade TEXT,
  estado TEXT,
  zona TEXT,
  condominio_id UUID REFERENCES condominios(id) ON DELETE SET NULL,
  condominio_nome TEXT,
  area_privativa NUMERIC,
  area_total NUMERIC,
  quartos INTEGER,
  suites INTEGER,
  banheiros INTEGER,
  vagas INTEGER,
  andar INTEGER,
  ano_construcao INTEGER,
  -- Imóvel-only fields
  ref TEXT,
  corretor TEXT,
  proprietario_id UUID REFERENCES clientes(id) ON DELETE SET NULL,
  aceita_permutas BOOLEAN DEFAULT false,
  finalidade TEXT DEFAULT 'venda',
  iptu NUMERIC,
  pronto_para_portais BOOLEAN DEFAULT false,
  titulo_anuncio TEXT,
  descricao_seo TEXT,
  fotos TEXT[],
  plantas TEXT[],
  palavras_chave TEXT[],
  pontos_de_interesse TEXT[],
  tour_virtual_url TEXT,
  latitude NUMERIC,
  longitude NUMERIC,
  lqs_score_hint TEXT,
  observacoes_negociacao TEXT,
  interesses JSONB DEFAULT '[]'::JSONB,
  -- Vehicle fields (permuta_automovel)
  tipo_veiculo TEXT,
  marca TEXT,
  modelo TEXT,
  motor TEXT,
  ano INTEGER,
  quilometragem INTEGER,
  -- Permuta flexibility fields
  faixa_preco_min NUMERIC,
  faixa_preco_max NUMERIC,
  regiao_preferida TEXT[],
  aceita_completar_diferenca BOOLEAN DEFAULT false,
  limite_complemento NUMERIC,
  metragem_min NUMERIC,
  metragem_max NUMERIC,
  quartos_min INTEGER,
  vagas_min INTEGER,
  ano_min INTEGER,
  ano_max INTEGER,
  quilometragem_max INTEGER
);

-- Add FK constraints from matches to ativos
ALTER TABLE erp.matches
  ADD CONSTRAINT matches_ativo_origem_id_fkey FOREIGN KEY (ativo_origem_id) REFERENCES erp.ativos(id) ON DELETE CASCADE,
  ADD CONSTRAINT matches_ativo_destino_id_fkey FOREIGN KEY (ativo_destino_id) REFERENCES erp.ativos(id) ON DELETE CASCADE;

-- Add FK constraints from negociacoes to ativos
ALTER TABLE erp.negociacoes
  ADD CONSTRAINT negociacoes_ativo_origem_id_fkey FOREIGN KEY (ativo_origem_id) REFERENCES erp.ativos(id) ON DELETE CASCADE,
  ADD CONSTRAINT negociacoes_ativo_destino_id_fkey FOREIGN KEY (ativo_destino_id) REFERENCES erp.ativos(id) ON DELETE CASCADE;

-- ─────────────────────────────────────────────────────────────────────
-- 6. INDEXES
-- ─────────────────────────────────────────────────────────────────────

-- Metas
CREATE INDEX idx_metas_usuario_tipo_data ON erp.metas(usuario_id, tipo, data_prazo);
CREATE INDEX idx_metas_usuario_tipo_categoria_data ON erp.metas(usuario_id, tipo, categoria, data_prazo);
CREATE INDEX idx_metas_categoria ON erp.metas(categoria);
CREATE INDEX idx_metas_categoria_custom ON erp.metas(categoria_custom);
CREATE INDEX idx_metas_tem_impedimento ON erp.metas(tem_impedimento) WHERE tem_impedimento = true;
CREATE INDEX idx_metas_nome ON erp.metas(nome);

-- Metas config
CREATE INDEX idx_metas_config_categoria_custom ON erp.metas_config(categoria_custom);

-- Profiles
CREATE INDEX idx_profiles_last_activity ON erp.profiles(last_activity_at);

-- Clientes
CREATE INDEX idx_clientes_etapa_pos ON erp.clientes(etapa_atual, kanban_pos);
CREATE INDEX idx_clientes_owner ON erp.clientes(usuario_id, arquivado);
CREATE INDEX idx_clientes_busca ON erp.clientes USING gin(to_tsvector('portuguese', nome || ' ' || COALESCE(email, '') || ' ' || COALESCE(telefone, '')));

-- Funil movimentos
CREATE INDEX idx_funil_movimentos_cliente ON erp.funil_movimentos(cliente_id, created_at DESC);

-- Atividades
CREATE INDEX idx_atividades_cliente ON erp.atividades(cliente_id, created_at DESC);

-- Password request codes
CREATE INDEX idx_password_request_codes_admin_corretor ON erp.password_request_codes(admin_user_id, corretor_id);

-- User actions log
CREATE INDEX idx_user_actions_log_usuario_id ON erp.user_actions_log(usuario_id);
CREATE INDEX idx_user_actions_log_created_at ON erp.user_actions_log(created_at DESC);
CREATE INDEX idx_user_actions_log_tipo_acao ON erp.user_actions_log(tipo_acao);
CREATE INDEX idx_user_actions_log_tipo_entidade ON erp.user_actions_log(tipo_entidade);

-- Negociações
CREATE INDEX idx_negociacoes_ativo_origem ON erp.negociacoes(ativo_origem_id);
CREATE INDEX idx_negociacoes_ativo_destino ON erp.negociacoes(ativo_destino_id);
CREATE INDEX idx_negociacoes_proprietario ON erp.negociacoes(cliente_proprietario_id);
CREATE INDEX idx_negociacoes_ofertante ON erp.negociacoes(cliente_ofertante_id);
CREATE INDEX idx_negociacoes_status ON erp.negociacoes(status_etapa);

-- Condominios
CREATE INDEX idx_condominios_owner_id ON erp.condominios(owner_id);
CREATE INDEX idx_condominios_cidade ON erp.condominios(cidade);

-- Matches
CREATE INDEX idx_matches_ativo_origem_id ON erp.matches(ativo_origem_id);
CREATE INDEX idx_matches_ativo_destino_id ON erp.matches(ativo_destino_id);
CREATE INDEX idx_matches_score_desc ON erp.matches(score DESC);
CREATE INDEX idx_matches_status ON erp.matches(status);

-- Ativos
CREATE INDEX idx_ativos_owner_id ON erp.ativos(owner_id);
CREATE INDEX idx_ativos_natureza ON erp.ativos(natureza);
CREATE INDEX idx_ativos_tipo_imovel ON erp.ativos(tipo_imovel);
CREATE INDEX idx_ativos_cidade ON erp.ativos(cidade);
CREATE INDEX idx_ativos_estado ON erp.ativos(estado);
CREATE INDEX idx_ativos_valor ON erp.ativos(valor);
CREATE INDEX idx_ativos_status ON erp.ativos(status);
CREATE INDEX idx_ativos_proprietario ON erp.ativos(proprietario_id);

-- ─────────────────────────────────────────────────────────────────────
-- 7. ROW LEVEL SECURITY
-- ─────────────────────────────────────────────────────────────────────

-- Enable RLS on all tables
ALTER TABLE erp.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.metas ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.metas_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.clientes ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.funil_movimentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.atividades ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.password_request_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.status_pagina ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.user_actions_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.negociacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.condominios ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.ativos ENABLE ROW LEVEL SECURITY;

-- ── Profiles ──
CREATE POLICY "Users can view their own profile" ON erp.profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Admins can view all profiles" ON erp.profiles FOR SELECT USING (public.has_role(auth.uid(), 'admin'::app_role));
CREATE POLICY "Users can update their own profile" ON erp.profiles FOR UPDATE TO authenticated USING (auth.uid() = id) WITH CHECK (auth.uid() = id);
CREATE POLICY "Users can insert their own profile" ON erp.profiles FOR INSERT TO authenticated WITH CHECK (auth.uid() = id);
CREATE POLICY "Admins can update all profiles" ON erp.profiles FOR UPDATE TO authenticated USING (public.has_role(auth.uid(), 'admin'::app_role));

-- ── User roles ──
CREATE POLICY "Admins can view all roles" ON erp.user_roles FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Users can view their own roles" ON erp.user_roles FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Admins can insert roles" ON erp.user_roles FOR INSERT TO authenticated WITH CHECK (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Admins can update roles" ON erp.user_roles FOR UPDATE TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Admins can delete roles" ON erp.user_roles FOR DELETE TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Deny unauthenticated access to user_roles" ON erp.user_roles FOR ALL TO anon USING (false);

-- ── Metas ──
CREATE POLICY "Users can view their own metas" ON erp.metas FOR SELECT TO authenticated USING (auth.uid() = usuario_id);
CREATE POLICY "Admins can view all metas" ON erp.metas FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Users can insert their own metas" ON erp.metas FOR INSERT TO authenticated WITH CHECK (usuario_id = auth.uid() AND usuario_id IS NOT NULL);
CREATE POLICY "Admins can insert metas for any user" ON erp.metas FOR INSERT TO authenticated WITH CHECK (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Users can update own daily incomplete metas" ON erp.metas FOR UPDATE TO authenticated USING (auth.uid() = usuario_id AND tipo = 'diaria' AND status != 'concluida') WITH CHECK (auth.uid() = usuario_id AND tipo = 'diaria' AND status != 'concluida');
CREATE POLICY "Admins can update monthly metas" ON erp.metas FOR UPDATE TO authenticated USING (public.has_role(auth.uid(), 'admin') AND tipo = 'mensal') WITH CHECK (public.has_role(auth.uid(), 'admin') AND tipo = 'mensal');
CREATE POLICY "Admins can update daily metas" ON erp.metas FOR UPDATE TO authenticated USING (public.has_role(auth.uid(), 'admin') AND tipo = 'diaria') WITH CHECK (public.has_role(auth.uid(), 'admin') AND tipo = 'diaria');
CREATE POLICY "Users can delete own daily incomplete metas" ON erp.metas FOR DELETE USING (auth.uid() = usuario_id AND tipo = 'diaria' AND status != 'concluida');
CREATE POLICY "Users can delete own aggregated metas" ON erp.metas FOR DELETE USING ((auth.uid() = usuario_id) AND (tipo IN ('semanal', 'mensal', 'anual')));
CREATE POLICY "Admins can delete completed metas" ON erp.metas FOR DELETE USING (public.has_role(auth.uid(), 'admin') AND status = 'concluida');
CREATE POLICY "Admins can delete aggregated metas" ON erp.metas FOR DELETE USING (public.has_role(auth.uid(), 'admin') AND tipo IN ('semanal', 'mensal', 'anual'));
CREATE POLICY "Admins can delete any daily incomplete meta" ON erp.metas FOR DELETE USING (public.has_role(auth.uid(), 'admin') AND tipo = 'diaria' AND status != 'concluida');

-- ── Metas config ──
CREATE POLICY "Usuários podem ver suas próprias configs" ON erp.metas_config FOR SELECT USING (auth.uid() = usuario_id);
CREATE POLICY "Usuários podem inserir suas próprias configs" ON erp.metas_config FOR INSERT WITH CHECK (auth.uid() = usuario_id);
CREATE POLICY "Usuários podem atualizar suas próprias configs" ON erp.metas_config FOR UPDATE USING (auth.uid() = usuario_id);
CREATE POLICY "Usuários podem deletar suas próprias configs" ON erp.metas_config FOR DELETE USING (auth.uid() = usuario_id);
CREATE POLICY "Admins podem ver todas as configs" ON erp.metas_config FOR SELECT USING (public.has_role(auth.uid(), 'admin'::app_role));

-- ── Clientes ──
CREATE POLICY "Usuários podem ver seus próprios clientes" ON erp.clientes FOR SELECT TO authenticated USING (auth.uid() = usuario_id);
CREATE POLICY "Admins podem ver todos os clientes" ON erp.clientes FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem criar seus próprios clientes" ON erp.clientes FOR INSERT TO authenticated WITH CHECK (auth.uid() = usuario_id);
CREATE POLICY "Usuários podem atualizar seus próprios clientes" ON erp.clientes FOR UPDATE TO authenticated USING (auth.uid() = usuario_id);
CREATE POLICY "Admins podem atualizar todos os clientes" ON erp.clientes FOR UPDATE TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem deletar seus próprios clientes" ON erp.clientes FOR DELETE TO authenticated USING (auth.uid() = usuario_id);
CREATE POLICY "Admins podem deletar todos os clientes" ON erp.clientes FOR DELETE TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- ── Funil movimentos ──
CREATE POLICY "Usuários podem ver movimentos de seus clientes" ON erp.funil_movimentos FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM erp.clientes WHERE clientes.id = funil_movimentos.cliente_id AND clientes.usuario_id = auth.uid()));
CREATE POLICY "Admins podem ver todos os movimentos" ON erp.funil_movimentos FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem criar movimentos para seus clientes" ON erp.funil_movimentos FOR INSERT TO authenticated WITH CHECK (EXISTS (SELECT 1 FROM erp.clientes WHERE clientes.id = funil_movimentos.cliente_id AND clientes.usuario_id = auth.uid()) AND responsavel_id = auth.uid());

-- ── Atividades ──
CREATE POLICY "Usuários podem ver atividades de seus clientes" ON erp.atividades FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM erp.clientes WHERE clientes.id = atividades.cliente_id AND clientes.usuario_id = auth.uid()));
CREATE POLICY "Admins podem ver todas as atividades" ON erp.atividades FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem criar atividades para seus clientes" ON erp.atividades FOR INSERT TO authenticated WITH CHECK (EXISTS (SELECT 1 FROM erp.clientes WHERE clientes.id = atividades.cliente_id AND clientes.usuario_id = auth.uid()) AND usuario_id = auth.uid());

-- ── Password request codes ──
CREATE POLICY "Admins can manage their own password request codes" ON erp.password_request_codes FOR ALL USING (auth.uid() = admin_user_id);
CREATE POLICY "Only admins can view password codes" ON erp.password_request_codes FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- ── Status pagina ──
CREATE POLICY "Todos podem ver páginas gerais em produção" ON erp.status_pagina FOR SELECT USING (status = 'producao' AND tipo_pagina = 'geral');
CREATE POLICY "Admins podem ver todas as páginas" ON erp.status_pagina FOR SELECT USING (public.has_role(auth.uid(), 'admin'::app_role));
CREATE POLICY "Devs podem ver páginas gerais em desenvolvimento" ON erp.status_pagina FOR SELECT USING (public.has_role(auth.uid(), 'dev'::app_role) AND tipo_pagina = 'geral');
CREATE POLICY "Apenas admins podem gerenciar páginas" ON erp.status_pagina FOR ALL USING (public.has_role(auth.uid(), 'admin'::app_role)) WITH CHECK (public.has_role(auth.uid(), 'admin'::app_role));

-- ── User actions log ──
CREATE POLICY "Admins podem ver todos os logs de ações" ON erp.user_actions_log FOR SELECT USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem ver seus próprios logs" ON erp.user_actions_log FOR SELECT USING (auth.uid() = usuario_id);
CREATE POLICY "Usuários podem inserir logs" ON erp.user_actions_log FOR INSERT WITH CHECK (auth.uid() = usuario_id);

-- ── Negociações ──
CREATE POLICY "Admins podem ver todas as negociações" ON erp.negociacoes FOR SELECT USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Proprietários podem ver suas negociações" ON erp.negociacoes FOR SELECT USING (auth.uid() = cliente_proprietario_id);
CREATE POLICY "Ofertantes podem ver suas negociações" ON erp.negociacoes FOR SELECT USING (auth.uid() = cliente_ofertante_id);
CREATE POLICY "Usuários podem criar negociações" ON erp.negociacoes FOR INSERT WITH CHECK (auth.uid() = owner_id);
CREATE POLICY "Proprietários podem atualizar suas negociações" ON erp.negociacoes FOR UPDATE USING (auth.uid() = cliente_proprietario_id OR auth.uid() = cliente_ofertante_id);
CREATE POLICY "Admins podem atualizar todas as negociações" ON erp.negociacoes FOR UPDATE USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem deletar negociações que criaram" ON erp.negociacoes FOR DELETE USING (auth.uid() = owner_id);
CREATE POLICY "Admins podem deletar todas as negociações" ON erp.negociacoes FOR DELETE USING (public.has_role(auth.uid(), 'admin'));

-- ── Condominios ──
CREATE POLICY "Users can view all condominios" ON erp.condominios FOR SELECT TO authenticated USING (true);
CREATE POLICY "Users can insert their own condominios" ON erp.condominios FOR INSERT TO authenticated WITH CHECK (auth.uid() = owner_id);
CREATE POLICY "Users can update their own condominios" ON erp.condominios FOR UPDATE TO authenticated USING (auth.uid() = owner_id);
CREATE POLICY "Users can delete their own condominios" ON erp.condominios FOR DELETE TO authenticated USING (auth.uid() = owner_id);

-- ── Matches ──
CREATE POLICY "Authenticated users can view matches" ON erp.matches FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can update match status" ON erp.matches FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated users can insert matches" ON erp.matches FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated users can delete matches" ON erp.matches FOR DELETE TO authenticated USING (true);

-- ── Ativos ──
CREATE POLICY "Users can view all active ativos" ON erp.ativos FOR SELECT TO authenticated USING (true);
CREATE POLICY "Users can insert their own ativos" ON erp.ativos FOR INSERT TO authenticated WITH CHECK (auth.uid() = owner_id);
CREATE POLICY "Users can update their own ativos" ON erp.ativos FOR UPDATE TO authenticated USING (auth.uid() = owner_id);
CREATE POLICY "Users can delete their own ativos" ON erp.ativos FOR DELETE TO authenticated USING (auth.uid() = owner_id);

-- ─────────────────────────────────────────────────────────────────────
-- 8. BUSINESS LOGIC FUNCTIONS
-- ─────────────────────────────────────────────────────────────────────

-- NOTE: has_role() is defined in section 5b (right after user_roles table)

-- Auth: Create profile on signup (stays in public — triggered by auth.users)
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
BEGIN
  INSERT INTO erp.profiles (id, nome, email, telefone)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'nome', NEW.email),
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'telefone', '')
  );
  RETURN NEW;
END;
$$;

-- Auth: Assign default corretor role on signup (stays in public — triggered by auth.users)
CREATE OR REPLACE FUNCTION public.assign_default_corretor_role()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO erp.user_roles (user_id, role)
  VALUES (NEW.id, 'corretor')
  ON CONFLICT (user_id, role) DO NOTHING;
  RETURN NEW;
END;
$$;

-- Period helpers
CREATE OR REPLACE FUNCTION erp.get_period_key(tipo_meta tipo_meta, data_ref date)
RETURNS TEXT LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  CASE tipo_meta
    WHEN 'diaria' THEN RETURN TO_CHAR(data_ref, 'YYYY-MM-DD');
    WHEN 'semanal' THEN RETURN TO_CHAR(data_ref, 'IYYY-IW');
    WHEN 'mensal' THEN RETURN TO_CHAR(data_ref, 'YYYY-MM');
    WHEN 'anual' THEN RETURN TO_CHAR(data_ref, 'YYYY');
  END CASE;
END;
$$;

CREATE OR REPLACE FUNCTION erp.period_end_date(tipo_meta tipo_meta, data_ref date)
RETURNS DATE LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  CASE tipo_meta
    WHEN 'diaria' THEN RETURN data_ref;
    WHEN 'semanal' THEN RETURN data_ref + (7 - EXTRACT(ISODOW FROM data_ref)::INTEGER);
    WHEN 'mensal' THEN RETURN (DATE_TRUNC('month', data_ref) + INTERVAL '1 month - 1 day')::DATE;
    WHEN 'anual' THEN RETURN (DATE_TRUNC('year', data_ref) + INTERVAL '1 year - 1 day')::DATE;
  END CASE;
END;
$$;

-- Working days calculations
CREATE OR REPLACE FUNCTION erp.dias_uteis_mes(p_data_ref date)
RETURNS integer LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE v_primeiro DATE; v_ultimo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_primeiro := DATE_TRUNC('month', p_data_ref)::DATE;
  v_ultimo := (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE;
  v_dia := v_primeiro;
  WHILE v_dia <= v_ultimo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION erp.semanas_mes(p_data_ref date)
RETURNS numeric LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE v_dias INTEGER;
BEGIN
  v_dias := EXTRACT(DAY FROM (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE);
  RETURN ROUND(v_dias::numeric / 7, 2);
END;
$$;

CREATE OR REPLACE FUNCTION erp.dias_uteis_restantes_semana(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$
DECLARE v_domingo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_domingo := p_data_ref + (7 - EXTRACT(ISODOW FROM p_data_ref)::INTEGER);
  v_dia := p_data_ref;
  WHILE v_dia <= v_domingo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION erp.dias_uteis_totais_semana(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$
DECLARE v_segunda DATE; v_domingo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_segunda := p_data_ref - (EXTRACT(ISODOW FROM p_data_ref)::INTEGER - 1);
  v_domingo := v_segunda + 6;
  v_dia := v_segunda;
  WHILE v_dia <= v_domingo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION erp.dias_uteis_restantes_mes(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$
DECLARE v_ultimo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_ultimo := (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE;
  v_dia := p_data_ref;
  WHILE v_dia <= v_ultimo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION erp.dias_uteis_totais_mes(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$ BEGIN RETURN dias_uteis_mes(p_data_ref); END; $$;

CREATE OR REPLACE FUNCTION erp.dias_uteis_restantes_ano(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$
DECLARE v_ultimo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_ultimo := (DATE_TRUNC('year', p_data_ref) + INTERVAL '1 year - 1 day')::DATE;
  v_dia := p_data_ref;
  WHILE v_dia <= v_ultimo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION erp.dias_uteis_totais_ano(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$
DECLARE v_primeiro DATE; v_ultimo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_primeiro := DATE_TRUNC('year', p_data_ref)::DATE;
  v_ultimo := (DATE_TRUNC('year', p_data_ref) + INTERVAL '1 year - 1 day')::DATE;
  v_dia := v_primeiro;
  WHILE v_dia <= v_ultimo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION erp.calcular_meta_proporcional(p_meta_mensal INTEGER, p_tipo tipo_meta, p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$
DECLARE v_total INTEGER; v_restantes INTEGER; v_diaria NUMERIC; v_resultado INTEGER;
BEGIN
  CASE p_tipo
    WHEN 'diaria' THEN
      v_total := dias_uteis_totais_mes(p_data_ref);
      v_resultado := CEIL(p_meta_mensal::NUMERIC / GREATEST(v_total, 1));
    WHEN 'semanal' THEN
      v_total := dias_uteis_totais_mes(p_data_ref);
      v_restantes := dias_uteis_restantes_semana(p_data_ref);
      v_diaria := p_meta_mensal::NUMERIC / GREATEST(v_total, 1);
      v_resultado := CEIL(v_diaria * v_restantes);
    WHEN 'mensal' THEN
      v_total := dias_uteis_totais_mes(p_data_ref);
      v_restantes := dias_uteis_restantes_mes(p_data_ref);
      v_resultado := CEIL(p_meta_mensal::NUMERIC * v_restantes::NUMERIC / GREATEST(v_total, 1));
    WHEN 'anual' THEN
      v_total := dias_uteis_totais_ano(p_data_ref);
      v_restantes := dias_uteis_restantes_ano(p_data_ref);
      v_resultado := CEIL((p_meta_mensal * 12)::NUMERIC * v_restantes::NUMERIC / GREATEST(v_total, 1));
  END CASE;
  RETURN GREATEST(v_resultado, 1);
END;
$$;

-- Scaffold meta (lookup-only, no auto-creation)
CREATE OR REPLACE FUNCTION erp.ensure_scaffold_meta(
  p_usuario_id uuid, p_tipo tipo_meta, p_categoria categoria_meta, p_data_ref date
)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE v_data_prazo DATE; v_meta_id TEXT;
BEGIN
  IF p_usuario_id != auth.uid() AND NOT public.has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: não é possível acessar metas para outros usuários';
  END IF;
  v_data_prazo := period_end_date(p_tipo, p_data_ref);
  SELECT id INTO v_meta_id FROM erp.metas
  WHERE usuario_id = p_usuario_id AND tipo = p_tipo AND categoria = p_categoria AND data_prazo = v_data_prazo
  ORDER BY created_at DESC LIMIT 1;
  RETURN v_meta_id;
END;
$$;

-- Rollup metas (aggregation with São Paulo timezone)
CREATE OR REPLACE FUNCTION erp.rollup_metas(p_usuario_id uuid, p_categoria categoria_meta, p_data_ref date)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE
  v_periodo_inicio DATE; v_periodo_fim DATE;
  v_real_bruta INTEGER; v_pretendida INTEGER; v_carry_in_prev INTEGER;
  v_acumulado INTEGER; v_real_cap INTEGER; v_carry_out_calc INTEGER;
  v_status status_meta; v_meta_id TEXT; v_data_prazo DATE; v_prev_data_prazo DATE;
  v_meta_mensal INTEGER; v_semanas NUMERIC; v_hoje DATE;
BEGIN
  IF p_usuario_id != auth.uid() AND NOT public.has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado';
  END IF;
  v_hoje := current_date_sao_paulo();
  SELECT meta_pretendida INTO v_meta_mensal FROM erp.metas_config
  WHERE usuario_id = p_usuario_id AND tipo = 'mensal' AND categoria = p_categoria AND ativo = true LIMIT 1;
  v_meta_mensal := COALESCE(v_meta_mensal, 0);

  -- Weekly
  v_data_prazo := period_end_date('semanal', p_data_ref);
  v_periodo_inicio := v_data_prazo - 6;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := period_end_date('semanal', v_periodo_inicio - 7);
  SELECT carry_out INTO v_carry_in_prev FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'semanal' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria AND data_prazo >= v_periodo_inicio AND data_prazo <= v_periodo_fim;
  v_semanas := semanas_mes(p_data_ref);
  v_pretendida := CASE WHEN v_semanas > 0 THEN CEIL(v_meta_mensal::numeric / v_semanas) ELSE v_meta_mensal END;
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  v_status := CASE WHEN v_real_cap >= v_pretendida THEN 'concluida' WHEN v_hoje > v_data_prazo THEN 'atrasada' ELSE 'no_prazo' END;
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'semanal', p_categoria, p_data_ref);
  IF v_meta_id IS NOT NULL THEN
    UPDATE erp.metas SET meta_pretendida = v_pretendida, meta_realizada = v_real_cap, carry_in = v_carry_in_prev, carry_out = v_carry_out_calc, status = v_status, updated_at = NOW() WHERE id = v_meta_id;
  END IF;

  -- Monthly
  v_data_prazo := period_end_date('mensal', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('month', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := period_end_date('mensal', v_periodo_inicio - 1);
  SELECT carry_out INTO v_carry_in_prev FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'mensal' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria AND data_prazo >= v_periodo_inicio AND data_prazo <= v_periodo_fim;
  v_pretendida := v_meta_mensal;
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  v_status := CASE WHEN v_real_cap >= v_pretendida THEN 'concluida' WHEN v_hoje > v_data_prazo THEN 'atrasada' ELSE 'no_prazo' END;
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'mensal', p_categoria, p_data_ref);
  IF v_meta_id IS NOT NULL THEN
    UPDATE erp.metas SET meta_pretendida = v_pretendida, meta_realizada = v_real_cap, carry_in = v_carry_in_prev, carry_out = v_carry_out_calc, status = v_status, updated_at = NOW() WHERE id = v_meta_id;
  END IF;

  -- Annual
  v_data_prazo := period_end_date('anual', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('year', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := period_end_date('anual', v_periodo_inicio - 1);
  SELECT carry_out INTO v_carry_in_prev FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'anual' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria AND data_prazo >= v_periodo_inicio AND data_prazo <= v_periodo_fim;
  v_pretendida := v_meta_mensal * 12;
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  v_status := CASE WHEN v_real_cap >= v_pretendida THEN 'concluida' WHEN v_hoje > v_data_prazo THEN 'atrasada' ELSE 'no_prazo' END;
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'anual', p_categoria, p_data_ref);
  IF v_meta_id IS NOT NULL THEN
    UPDATE erp.metas SET meta_pretendida = v_pretendida, meta_realizada = v_real_cap, carry_in = v_carry_in_prev, carry_out = v_carry_out_calc, status = v_status, updated_at = NOW() WHERE id = v_meta_id;
  END IF;
END;
$$;

-- Concluir meta agrupada (SP timezone)
CREATE OR REPLACE FUNCTION erp.concluir_meta_agrupada(p_meta_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE v_meta RECORD; v_no_prazo boolean; v_hoje DATE;
BEGIN
  v_hoje := current_date_sao_paulo();
  SELECT * INTO v_meta FROM erp.metas WHERE id = p_meta_id AND tipo IN ('semanal', 'mensal', 'anual') AND usuario_id = auth.uid();
  IF NOT FOUND THEN RETURN jsonb_build_object('success', false, 'error', 'Meta não encontrada ou sem permissão'); END IF;
  IF v_meta.meta_realizada < v_meta.meta_pretendida THEN
    RETURN jsonb_build_object('success', false, 'error', 'Meta não atingida. Realize: ' || v_meta.meta_realizada || '/' || v_meta.meta_pretendida);
  END IF;
  v_no_prazo := (v_hoje <= v_meta.data_prazo);
  UPDATE erp.metas SET status = 'concluida', finalizada_em = NOW(), finalizada_no_prazo = v_no_prazo,
    conclusao_prazo = CASE WHEN v_no_prazo THEN 'no_prazo' ELSE 'atrasada' END::erp.conclusao_prazo_meta, updated_at = NOW()
  WHERE id = p_meta_id;
  RETURN jsonb_build_object('success', true, 'message', 'Meta concluída com sucesso');
END;
$$;

-- Conclusao prazo trigger function
CREATE OR REPLACE FUNCTION erp.set_conclusao_prazo()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.status = 'concluida' AND (OLD.status IS DISTINCT FROM 'concluida') THEN
      IF NEW.finalizada_em IS NULL THEN NEW.finalizada_em := now(); END IF;
      NEW.finalizada_no_prazo := (NEW.finalizada_em::date <= NEW.data_prazo);
      NEW.conclusao_prazo := CASE WHEN NEW.finalizada_em::date <= NEW.data_prazo THEN 'no_prazo' ELSE 'atrasada' END;
    ELSE
      IF NEW.conclusao_prazo IS DISTINCT FROM OLD.conclusao_prazo THEN
        RAISE EXCEPTION 'conclusao_prazo é gerenciado pelo sistema e não pode ser alterado manualmente';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

-- Status update function (batch job)
CREATE OR REPLACE FUNCTION erp.atualizar_status_metas()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE v_count INTEGER := 0; v_tmp INTEGER; v_hoje DATE; v_amanha DATE;
BEGIN
  v_hoje := current_date_sao_paulo();
  v_amanha := v_hoje + 1;
  UPDATE erp.metas SET dias_restantes = data_prazo - v_hoje, updated_at = NOW() WHERE status NOT IN ('concluida');
  UPDATE erp.metas SET status = 'vence_amanha', updated_at = NOW() WHERE data_prazo = v_amanha AND status NOT IN ('concluida') AND status != 'vence_amanha';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  UPDATE erp.metas SET status = 'atrasada', updated_at = NOW() WHERE data_prazo < v_hoje AND status NOT IN ('concluida') AND status != 'atrasada';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  UPDATE erp.metas SET status = 'no_prazo', updated_at = NOW() WHERE data_prazo > v_amanha AND status NOT IN ('concluida') AND status != 'no_prazo';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  UPDATE erp.metas SET status = 'no_prazo', updated_at = NOW() WHERE data_prazo = v_hoje AND status NOT IN ('concluida', 'no_prazo') AND status != 'vence_amanha';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  RETURN jsonb_build_object('success', true, 'metas_atualizadas', v_count, 'timestamp', NOW());
END;
$$;

-- Performance level calculation
CREATE OR REPLACE FUNCTION erp.calcular_nivel_performance(p_realizada INTEGER, p_pretendida INTEGER)
RETURNS nivel_performance_meta LANGUAGE plpgsql IMMUTABLE
AS $$
DECLARE v_prog NUMERIC;
BEGIN
  IF p_pretendida = 0 THEN RETURN 'baixo'; END IF;
  v_prog := (p_realizada::NUMERIC / p_pretendida::NUMERIC) * 100;
  IF v_prog >= 100 THEN RETURN 'excelente';
  ELSIF v_prog >= 80 THEN RETURN 'bom';
  ELSIF v_prog >= 50 THEN RETURN 'regular';
  ELSE RETURN 'baixo'; END IF;
END;
$$;

-- Trigger functions for metas
CREATE OR REPLACE FUNCTION erp.atualizar_nivel_performance()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  NEW.nivel_performance := calcular_nivel_performance(COALESCE(NEW.meta_realizada, 0), NEW.meta_pretendida);
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION erp.atualizar_dias_restantes()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN NEW.dias_restantes := NEW.data_prazo - current_date_sao_paulo(); RETURN NEW; END;
$$;

CREATE OR REPLACE FUNCTION erp.validar_alteracao_status_meta()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = 'public'
AS $$
BEGIN
  IF public.has_role(auth.uid(), 'admin') THEN RETURN NEW; END IF;
  IF auth.uid() IS NULL THEN RETURN NEW; END IF;
  IF NEW.status = 'concluida' AND OLD.status != 'concluida' THEN RETURN NEW; END IF;
  IF OLD.status IS DISTINCT FROM NEW.status AND NEW.status != 'concluida' THEN
    RAISE EXCEPTION 'O status da meta é atualizado automaticamente pelo sistema';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION erp.validar_alteracao_nivel_performance()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = 'public'
AS $$
BEGIN
  IF public.has_role(auth.uid(), 'admin') THEN RETURN NEW; END IF;
  IF auth.uid() IS NULL THEN RETURN NEW; END IF;
  IF OLD.nivel_performance IS DISTINCT FROM NEW.nivel_performance THEN
    IF NEW.nivel_performance != calcular_nivel_performance(COALESCE(NEW.meta_realizada, 0), NEW.meta_pretendida) THEN
      RAISE EXCEPTION 'O nível de performance é calculado automaticamente';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION erp.prevent_date_change_on_daily_metas()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = 'public'
AS $$
BEGIN
  IF public.has_role(auth.uid(), 'admin') THEN RETURN NEW; END IF;
  IF OLD.tipo = 'diaria' AND NEW.data_prazo IS DISTINCT FROM OLD.data_prazo THEN
    RAISE EXCEPTION 'Apenas administradores podem alterar a data prazo de metas diárias';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION erp.recalcular_metas_on_mensal_change()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  IF NEW.tipo = 'mensal' AND OLD.meta_pretendida IS DISTINCT FROM NEW.meta_pretendida THEN
    PERFORM rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo);
    PERFORM rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo - INTERVAL '1 month');
    PERFORM rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo + INTERVAL '1 month');
  END IF;
  RETURN NEW;
END;
$$;

-- Timestamp normalization triggers
CREATE OR REPLACE FUNCTION erp.normalize_metas_finalizada_em()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$ BEGIN IF NEW.finalizada_em IS NOT NULL THEN NEW.finalizada_em := normalize_timestamp_sp(NEW.finalizada_em); END IF; RETURN NEW; END; $$;

CREATE OR REPLACE FUNCTION erp.normalize_atividades_data_execucao()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$ BEGIN IF NEW.data_execucao IS NOT NULL THEN NEW.data_execucao := normalize_timestamp_sp(NEW.data_execucao); ELSE NEW.data_execucao := now_sao_paulo(); END IF; RETURN NEW; END; $$;

CREATE OR REPLACE FUNCTION erp.normalize_profiles_last_activity()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$ BEGIN IF NEW.last_activity_at IS NOT NULL THEN NEW.last_activity_at := normalize_timestamp_sp(NEW.last_activity_at); ELSE NEW.last_activity_at := now_sao_paulo(); END IF; RETURN NEW; END; $$;

CREATE OR REPLACE FUNCTION erp.normalize_password_codes_expires()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$ BEGIN IF NEW.expires_at IS NOT NULL THEN NEW.expires_at := normalize_timestamp_sp(NEW.expires_at); END IF; RETURN NEW; END; $$;

-- Inactive users deactivation
CREATE OR REPLACE FUNCTION erp.desativar_metas_usuarios_inativos()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE v_users INTEGER := 0; v_configs INTEGER := 0;
BEGIN
  IF auth.uid() IS NOT NULL AND NOT public.has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: apenas administradores';
  END IF;
  WITH inativos AS (SELECT id FROM erp.profiles WHERE last_activity_at < NOW() - INTERVAL '20 days')
  UPDATE erp.metas_config SET ativo = false, updated_at = NOW()
  WHERE usuario_id IN (SELECT id FROM inativos) AND ativo = true;
  GET DIAGNOSTICS v_configs = ROW_COUNT;
  SELECT COUNT(DISTINCT usuario_id) INTO v_users FROM (SELECT usuario_id FROM erp.metas_config WHERE updated_at >= NOW() - INTERVAL '1 minute' AND ativo = false) t;
  RETURN jsonb_build_object('success', true, 'usuarios_afetados', v_users, 'configs_desativadas', v_configs, 'timestamp', NOW());
END;
$$;

-- Expired password codes cleanup
CREATE OR REPLACE FUNCTION erp.delete_expired_password_codes()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
AS $$ BEGIN DELETE FROM erp.password_request_codes WHERE expires_at < now(); END; $$;

-- Distribuir meta descendente (downward distribution from manual metas)
CREATE OR REPLACE FUNCTION erp.distribuir_meta_descendente()
RETURNS TRIGGER AS $$
DECLARE
  v_meta_diaria DECIMAL; v_meta_semanal DECIMAL; v_meta_mensal DECIMAL; v_meta_anual DECIMAL;
  v_data_atual DATE; v_data_fim DATE; v_data_temp DATE;
  v_dias_uteis INTEGER; v_semanas INTEGER; v_meses INTEGER; v_dia_semana INTEGER; v_existe_meta BOOLEAN;
BEGIN
  IF NOT NEW.criada_manualmente THEN RETURN NEW; END IF;
  CASE NEW.tipo
    WHEN 'anual' THEN
      v_meta_mensal := NEW.meta_pretendida / 12.0;
      FOR v_meses IN 0..11 LOOP
        v_data_atual := DATE_TRUNC('year', NEW.data_prazo) + (v_meses || ' months')::INTERVAL;
        v_data_fim := (v_data_atual + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
        v_semanas := CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0);
        v_meta_semanal := v_meta_mensal / v_semanas;
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'mensal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_mensal), v_data_fim, false, NEW.nome, NEW.detalhes);
        FOR v_semanas IN 1..CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0) LOOP
          v_data_temp := v_data_atual::DATE + ((v_semanas - 1) * 7);
          v_data_fim := LEAST(v_data_temp + 6, (DATE_TRUNC('month', v_data_temp) + INTERVAL '1 month' - INTERVAL '1 day')::DATE);
          v_dias_uteis := 0; v_data_temp := v_data_temp;
          WHILE v_data_temp <= v_data_fim LOOP
            IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN v_dias_uteis := v_dias_uteis + 1; END IF;
            v_data_temp := v_data_temp + 1;
          END LOOP;
          v_meta_diaria := v_meta_semanal / GREATEST(v_dias_uteis, 1);
          INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
          VALUES (NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_semanal), v_data_fim, false, NEW.nome, NEW.detalhes);
          v_data_temp := v_data_atual::DATE + ((v_semanas - 1) * 7);
          WHILE v_data_temp <= v_data_fim LOOP
            IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN
              INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
              VALUES (NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_diaria), v_data_temp, false, NEW.nome, NEW.detalhes);
            END IF;
            v_data_temp := v_data_temp + 1;
          END LOOP;
        END LOOP;
      END LOOP;
    WHEN 'mensal' THEN
      v_data_atual := DATE_TRUNC('month', NEW.data_prazo)::DATE;
      v_data_fim := (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
      v_semanas := CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0);
      v_meta_semanal := NEW.meta_pretendida / v_semanas;
      v_meta_anual := NEW.meta_pretendida * 12;
      SELECT EXISTS(SELECT 1 FROM erp.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'anual' AND categoria = NEW.categoria AND data_prazo = (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)) INTO v_existe_meta;
      IF NOT v_existe_meta THEN
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'anual', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_anual), (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE, false, NEW.nome, NEW.detalhes);
      END IF;
      FOR v_semanas IN 1..CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0) LOOP
        v_data_temp := v_data_atual + ((v_semanas - 1) * 7);
        v_data_fim := LEAST(v_data_temp + 6, (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE);
        v_dias_uteis := 0; v_data_temp := v_data_temp;
        WHILE v_data_temp <= v_data_fim LOOP IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN v_dias_uteis := v_dias_uteis + 1; END IF; v_data_temp := v_data_temp + 1; END LOOP;
        v_meta_diaria := v_meta_semanal / GREATEST(v_dias_uteis, 1);
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_semanal), v_data_fim, false, NEW.nome, NEW.detalhes);
        v_data_temp := v_data_atual + ((v_semanas - 1) * 7);
        WHILE v_data_temp <= v_data_fim LOOP
          IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN
            INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
            VALUES (NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_diaria), v_data_temp, false, NEW.nome, NEW.detalhes);
          END IF;
          v_data_temp := v_data_temp + 1;
        END LOOP;
      END LOOP;
    WHEN 'semanal' THEN
      v_data_atual := NEW.data_prazo - EXTRACT(DOW FROM NEW.data_prazo)::INTEGER + 1;
      IF EXTRACT(DOW FROM NEW.data_prazo) = 0 THEN v_data_atual := v_data_atual - 7; END IF;
      v_dias_uteis := 0; v_data_temp := v_data_atual;
      FOR i IN 0..6 LOOP IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN v_dias_uteis := v_dias_uteis + 1; END IF; v_data_temp := v_data_temp + 1; END LOOP;
      v_meta_diaria := NEW.meta_pretendida / GREATEST(v_dias_uteis, 1);
      v_meta_mensal := NEW.meta_pretendida * 4;
      SELECT EXISTS(SELECT 1 FROM erp.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'mensal' AND categoria = NEW.categoria AND data_prazo = (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)) INTO v_existe_meta;
      IF NOT v_existe_meta THEN
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'mensal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_mensal), (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE, false, NEW.nome, NEW.detalhes);
      END IF;
      v_meta_anual := v_meta_mensal * 12;
      SELECT EXISTS(SELECT 1 FROM erp.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'anual' AND categoria = NEW.categoria AND data_prazo = (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)) INTO v_existe_meta;
      IF NOT v_existe_meta THEN
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'anual', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_anual), (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE, false, NEW.nome, NEW.detalhes);
      END IF;
      v_data_temp := v_data_atual;
      FOR i IN 0..6 LOOP
        IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN
          INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
          VALUES (NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_diaria), v_data_temp, false, NEW.nome, NEW.detalhes);
        END IF;
        v_data_temp := v_data_temp + 1;
      END LOOP;
    ELSE NULL;
  END CASE;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ─────────────────────────────────────────────────────────────────────
-- 9. TRIGGERS
-- ─────────────────────────────────────────────────────────────────────

-- Auth triggers
CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
CREATE TRIGGER on_auth_user_created_assign_role AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.assign_default_corretor_role();

-- Timestamp triggers (São Paulo)
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.clientes FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.profiles FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.negociacoes FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.metas_config FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.atividades FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.funil_movimentos FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.user_actions_log FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.user_roles FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.password_request_codes FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();

-- Updated_at triggers (for tables not covered by set_timestamps_sp)
CREATE TRIGGER update_negociacoes_updated_at BEFORE UPDATE ON erp.negociacoes FOR EACH ROW EXECUTE FUNCTION erp.update_updated_at_column();
CREATE TRIGGER update_metas_config_updated_at BEFORE UPDATE ON erp.metas_config FOR EACH ROW EXECUTE FUNCTION erp.update_updated_at_column();

-- Metas-specific triggers
CREATE TRIGGER trg_set_conclusao_prazo BEFORE UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.set_conclusao_prazo();
CREATE TRIGGER trigger_atualizar_nivel_performance BEFORE INSERT OR UPDATE OF meta_realizada, meta_pretendida ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.atualizar_nivel_performance();
CREATE TRIGGER trigger_validar_nivel_performance BEFORE UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.validar_alteracao_nivel_performance();
CREATE TRIGGER trigger_atualizar_dias_restantes BEFORE INSERT OR UPDATE OF data_prazo ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.atualizar_dias_restantes();
CREATE TRIGGER trigger_validar_status_meta BEFORE UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.validar_alteracao_status_meta();
CREATE TRIGGER prevent_date_change_trigger BEFORE UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.prevent_date_change_on_daily_metas();
CREATE TRIGGER trigger_recalcular_metas_mensal AFTER UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.recalcular_metas_on_mensal_change();

-- Timestamp normalization triggers
CREATE TRIGGER normalize_metas_finalizada_em_trigger BEFORE INSERT OR UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.normalize_metas_finalizada_em();
CREATE TRIGGER normalize_atividades_data_execucao_trigger BEFORE INSERT ON erp.atividades FOR EACH ROW EXECUTE FUNCTION erp.normalize_atividades_data_execucao();
CREATE TRIGGER normalize_profiles_last_activity_trigger BEFORE INSERT OR UPDATE ON erp.profiles FOR EACH ROW EXECUTE FUNCTION erp.normalize_profiles_last_activity();
CREATE TRIGGER normalize_password_codes_expires_trigger BEFORE INSERT ON erp.password_request_codes FOR EACH ROW EXECUTE FUNCTION erp.normalize_password_codes_expires();

-- ─────────────────────────────────────────────────────────────────────
-- 9b. RPC ALIAS (used by backend: admin.rpc("get_data_sp"))
-- ─────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION erp.get_data_sp()
RETURNS DATE
LANGUAGE SQL STABLE
AS $$ SELECT (NOW() AT TIME ZONE 'America/Sao_Paulo')::DATE; $$;

-- ─────────────────────────────────────────────────────────────────────
-- 10. SEED DATA
-- ─────────────────────────────────────────────────────────────────────

INSERT INTO erp.status_pagina (nome_pagina, status, tipo_pagina) VALUES
  -- Principal
  ('dashboard', 'producao', 'geral'),
  ('funil', 'producao', 'geral'),
  ('clientes', 'producao', 'geral'),
  ('metas', 'producao', 'geral'),
  -- Comercial
  ('imoveis', 'producao', 'geral'),
  ('condominios', 'producao', 'geral'),
  ('permutas', 'producao', 'geral'),
  ('negociacoes', 'producao', 'geral'),
  ('propostas', 'producao', 'geral'),
  ('contratos', 'producao', 'geral'),
  ('locacoes', 'producao', 'geral'),
  ('comissoes', 'producao', 'geral'),
  -- Financeiro
  ('financeiro', 'producao', 'geral'),
  ('impostos', 'producao', 'geral'),
  ('banco', 'producao', 'geral'),
  ('analise-credito', 'producao', 'geral'),
  -- Operacional
  ('agenda', 'producao', 'geral'),
  ('vistorias', 'producao', 'geral'),
  ('manutencao', 'producao', 'geral'),
  ('chaves', 'producao', 'geral'),
  ('campo', 'producao', 'geral'),
  ('seguros', 'producao', 'geral'),
  -- Marketing & Comunicação
  ('marketing', 'producao', 'geral'),
  ('emails', 'producao', 'geral'),
  ('whatsapp', 'producao', 'geral'),
  ('meta-ads', 'producao', 'geral'),
  ('notificacoes', 'producao', 'geral'),
  -- Documentos
  ('documentos', 'producao', 'geral'),
  ('assinaturas', 'producao', 'geral'),
  ('dimob', 'producao', 'geral'),
  ('relatorios', 'producao', 'geral'),
  -- Portais & Site
  ('portal-cliente', 'producao', 'geral'),
  ('portal', 'producao', 'geral'),
  ('site', 'producao', 'geral'),
  -- Analytics & IA
  ('bi', 'producao', 'geral'),
  ('matching', 'producao', 'geral'),
  ('gamificacao', 'producao', 'geral'),
  -- Standalone
  ('distribuicao', 'producao', 'geral'),
  ('filiais', 'producao', 'geral'),
  ('configuracoes', 'producao', 'geral'),
  -- Painel de Controle (admin only)
  ('usuarios', 'producao', 'administrativa'),
  ('admin', 'producao', 'administrativa'),
  ('log-acoes', 'producao', 'administrativa')
ON CONFLICT (nome_pagina) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════
-- 11. MVP EXPANSION TABLES (inline from 004_mvp_expansion.sql)
-- ═══════════════════════════════════════════════════════════════════════
-- These tables support all 38 existing routers plus new features
-- (notifications, WAHA, Meta API).
-- ═══════════════════════════════════════════════════════════════════════

-- ── GROUP A: Sales & Proposals ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.propostas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  cliente_id uuid NOT NULL,
  corretor_id uuid NOT NULL,
  valor_proposta numeric NOT NULL,
  valor_contraproposta numeric,
  status text NOT NULL DEFAULT 'enviada'
    CHECK (status IN ('enviada','em_analise','contraproposta','aceita','recusada','expirada')),
  condicoes_pagamento text,
  prazo_validade date,
  observacoes text,
  historico jsonb NOT NULL DEFAULT '[]',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.contratos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('venda','locacao')),
  status text NOT NULL DEFAULT 'rascunho'
    CHECK (status IN ('rascunho','ativo','concluido','cancelado','distratado')),
  cliente_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  proposta_id uuid,
  valor_total numeric NOT NULL,
  valor_entrada numeric NOT NULL DEFAULT 0,
  num_parcelas integer NOT NULL DEFAULT 1,
  data_inicio date NOT NULL,
  data_fim date,
  data_assinatura date,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.parcelas_contrato (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  contrato_id uuid NOT NULL REFERENCES erp.contratos(id) ON DELETE CASCADE,
  numero integer NOT NULL,
  valor numeric NOT NULL,
  data_vencimento date NOT NULL,
  data_pagamento date,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','pago','atrasado','cancelado')),
  forma_pagamento text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP B: Financial ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.lancamentos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('receita','despesa')),
  categoria text NOT NULL,
  descricao text NOT NULL,
  valor numeric NOT NULL,
  data_vencimento date NOT NULL,
  data_pagamento date,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','pago','atrasado','cancelado')),
  forma_pagamento text,
  imovel_id uuid,
  cliente_id uuid,
  comissao_id uuid,
  recorrente boolean NOT NULL DEFAULT false,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.impostos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('iptu','itbi','txa_lixo','contribuicao_melhoria','outro')),
  ano integer NOT NULL,
  valor_total numeric NOT NULL,
  valor_pago numeric NOT NULL DEFAULT 0,
  num_parcelas integer NOT NULL DEFAULT 1,
  parcela_atual integer NOT NULL DEFAULT 0,
  desconto_cota_unica numeric NOT NULL DEFAULT 0,
  data_vencimento date NOT NULL,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','parcial','pago','atrasado','isento')),
  numero_guia text,
  comprovante_url text,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.extratos_bancarios (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  banco text NOT NULL,
  agencia text,
  conta text,
  data_importacao timestamptz NOT NULL DEFAULT now(),
  arquivo_nome text NOT NULL,
  periodo_inicio date,
  periodo_fim date,
  total_registros integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.movimentacoes_bancarias (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  extrato_id uuid NOT NULL REFERENCES erp.extratos_bancarios(id) ON DELETE CASCADE,
  data date NOT NULL,
  descricao text NOT NULL,
  valor numeric NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('credito','debito')),
  conciliado boolean NOT NULL DEFAULT false,
  lancamento_id uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP C: Commissions ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.comissoes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  venda_id uuid,
  imovel_id uuid,
  valor_venda numeric NOT NULL,
  percentual_comissao numeric NOT NULL DEFAULT 6.0,
  valor_comissao numeric NOT NULL,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','aprovada','paga','cancelada')),
  data_venda date,
  data_pagamento date,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.comissoes_splits (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  comissao_id uuid NOT NULL REFERENCES erp.comissoes(id) ON DELETE CASCADE,
  corretor_id uuid NOT NULL,
  corretor_nome text NOT NULL,
  percentual numeric NOT NULL,
  valor numeric NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP D: Rentals ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.contratos_locacao (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  locatario_id uuid NOT NULL,
  proprietario_id uuid,
  valor_aluguel numeric NOT NULL,
  dia_vencimento int NOT NULL DEFAULT 10,
  data_inicio date NOT NULL,
  data_fim date NOT NULL,
  indice_reajuste text NOT NULL DEFAULT 'IGPM'
    CHECK (indice_reajuste IN ('IGPM','IPCA','INPC','fixo')),
  percentual_reajuste numeric,
  status text NOT NULL DEFAULT 'ativo'
    CHECK (status IN ('ativo','encerrado','renovado','inadimplente')),
  taxa_administracao numeric NOT NULL DEFAULT 10.0,
  valor_caucao numeric,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP E: Calendar ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.eventos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  corretor_id uuid NOT NULL,
  titulo text NOT NULL,
  descricao text,
  tipo text NOT NULL
    CHECK (tipo IN ('visita','reuniao','ligacao','vistoria','assinatura','outro')),
  data_inicio timestamptz NOT NULL,
  data_fim timestamptz NOT NULL,
  local text,
  cliente_id uuid,
  imovel_id uuid,
  status text NOT NULL DEFAULT 'agendado'
    CHECK (status IN ('agendado','confirmado','realizado','cancelado')),
  cor text DEFAULT '#6366f1',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP F: Documents & Signatures ─────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.documentos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  nome text NOT NULL,
  tipo text NOT NULL
    CHECK (tipo IN ('contrato','procuracao','laudo','certidao','outro')),
  arquivo_url text,
  arquivo_path text,
  tamanho_bytes bigint,
  mime_type text,
  imovel_id uuid,
  cliente_id uuid,
  proposta_id uuid,
  template_id uuid,
  metadata jsonb NOT NULL DEFAULT '{}',
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.document_templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  nome text NOT NULL,
  tipo text NOT NULL,
  conteudo text NOT NULL,
  variaveis text[] NOT NULL DEFAULT '{}',
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.assinaturas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  documento_nome text NOT NULL,
  documento_url text,
  contrato_id uuid,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','enviado','assinado','recusado','expirado','cancelado')),
  provedor text NOT NULL DEFAULT 'interno'
    CHECK (provedor IN ('interno','clicksign','docusign','d4sign')),
  link_assinatura text,
  signatarios jsonb NOT NULL DEFAULT '[]',
  historico jsonb NOT NULL DEFAULT '[]',
  data_envio timestamptz,
  data_assinatura timestamptz,
  data_expiracao timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP G: Email & Marketing ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.emails (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  cliente_id uuid,
  remetente text NOT NULL,
  destinatario text NOT NULL,
  assunto text NOT NULL,
  corpo text NOT NULL,
  corpo_html text,
  direcao text NOT NULL CHECK (direcao IN ('enviado','recebido')),
  status text NOT NULL DEFAULT 'enviado'
    CHECK (status IN ('rascunho','enviado','entregue','aberto','erro')),
  template_id uuid,
  aberturas integer NOT NULL DEFAULT 0,
  cliques integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.email_templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  nome text NOT NULL,
  assunto text NOT NULL,
  corpo text NOT NULL,
  variaveis text[] NOT NULL DEFAULT '{}',
  ativo boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.campanhas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  nome text NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('email','whatsapp','alerta_imovel')),
  status text NOT NULL DEFAULT 'rascunho'
    CHECK (status IN ('rascunho','ativa','pausada','concluida')),
  template text NOT NULL,
  filtros jsonb NOT NULL DEFAULT '{}',
  total_enviados int NOT NULL DEFAULT 0,
  total_abertos int NOT NULL DEFAULT 0,
  total_cliques int NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.envios_email (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  campanha_id uuid NOT NULL REFERENCES erp.campanhas(id) ON DELETE CASCADE,
  cliente_id uuid NOT NULL,
  email text NOT NULL,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','enviado','aberto','clicado','erro')),
  enviado_at timestamptz,
  aberto_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP H: WhatsApp ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.whatsapp_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  cliente_id uuid,
  phone text NOT NULL,
  direction text NOT NULL CHECK (direction IN ('sent','received')),
  message text NOT NULL,
  message_type text NOT NULL DEFAULT 'text'
    CHECK (message_type IN ('text','property_card','image')),
  metadata jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'sent'
    CHECK (status IN ('sent','delivered','read','failed')),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP I: Inspections & Maintenance ──────────────────────────────

CREATE TABLE IF NOT EXISTS erp.vistorias (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('entrada','saida','periodica')),
  data_vistoria date NOT NULL,
  responsavel_id uuid NOT NULL,
  responsavel_nome text,
  status text NOT NULL DEFAULT 'agendada'
    CHECK (status IN ('agendada','em_andamento','concluida','cancelada')),
  checklist jsonb NOT NULL DEFAULT '[]',
  fotos text[] NOT NULL DEFAULT '{}',
  observacoes_gerais text,
  assinatura_locatario text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.checkins (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  corretor_id uuid NOT NULL,
  imovel_id uuid,
  latitude numeric NOT NULL,
  longitude numeric NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('visita','vistoria','captacao','reuniao')),
  observacoes text,
  fotos text[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.vistorias_rapidas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  corretor_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  checkin_id uuid REFERENCES erp.checkins(id),
  estado_geral text NOT NULL
    CHECK (estado_geral IN ('bom','regular','ruim','critico')),
  itens_checklist jsonb NOT NULL DEFAULT '{}',
  observacoes text,
  fotos text[] NOT NULL DEFAULT '{}',
  latitude numeric,
  longitude numeric,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.ordens_servico (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid,
  cliente_id uuid,
  titulo text NOT NULL,
  descricao text NOT NULL,
  tipo text NOT NULL
    CHECK (tipo IN ('preventiva','corretiva','emergencial','reforma')),
  prioridade text NOT NULL DEFAULT 'media'
    CHECK (prioridade IN ('baixa','media','alta','urgente')),
  status text NOT NULL DEFAULT 'aberto'
    CHECK (status IN ('aberto','em_andamento','aguardando','concluido','cancelado')),
  responsavel text,
  fornecedor text,
  custo_estimado numeric,
  custo_real numeric,
  data_abertura date NOT NULL,
  data_previsao date,
  data_conclusao date,
  fotos text[] NOT NULL DEFAULT '{}',
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP J: Insurance ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.seguros (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  cliente_id uuid,
  seguradora text NOT NULL,
  numero_apolice text,
  tipo_cobertura text NOT NULL
    CHECK (tipo_cobertura IN ('incendio','completo','responsabilidade_civil','vida','fianca_locaticia','outro')),
  valor_cobertura numeric NOT NULL,
  valor_premio numeric NOT NULL,
  data_inicio date NOT NULL,
  data_vencimento date NOT NULL,
  status text NOT NULL DEFAULT 'ativo'
    CHECK (status IN ('ativo','vencido','cancelado','renovado')),
  auto_renovar boolean NOT NULL DEFAULT false,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP K: Credit Analysis ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.analises_credito (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  cliente_id uuid,
  cpf text NOT NULL,
  nome text NOT NULL,
  score int,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','aprovado','reprovado','em_analise')),
  resultado jsonb NOT NULL DEFAULT '{}',
  fonte text NOT NULL DEFAULT 'manual'
    CHECK (fonte IN ('serasa','boa_vista','manual')),
  validade date,
  consultado_por uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP L: Key Management ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.chaves (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  codigo text NOT NULL,
  descricao text,
  status text NOT NULL DEFAULT 'disponivel'
    CHECK (status IN ('disponivel','emprestada','perdida')),
  ultima_retirada_por uuid,
  ultima_retirada_nome text,
  ultima_retirada_em timestamptz,
  ultima_devolucao_em timestamptz,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.chaves_historico (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  chave_id uuid NOT NULL REFERENCES erp.chaves(id) ON DELETE CASCADE,
  acao text NOT NULL CHECK (acao IN ('retirada','devolucao')),
  corretor_id uuid NOT NULL,
  corretor_nome text NOT NULL,
  motivo text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP M: Portals & Site ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.portal_acessos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  cliente_id uuid NOT NULL,
  token text NOT NULL UNIQUE,
  ativo boolean NOT NULL DEFAULT true,
  data_expiracao timestamptz,
  ultimo_acesso timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.chamados_portal (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  cliente_id uuid NOT NULL,
  portal_acesso_id uuid NOT NULL REFERENCES erp.portal_acessos(id) ON DELETE CASCADE,
  assunto text NOT NULL,
  descricao text NOT NULL,
  status text NOT NULL DEFAULT 'aberto'
    CHECK (status IN ('aberto','em_andamento','resolvido','fechado')),
  prioridade text NOT NULL DEFAULT 'media'
    CHECK (prioridade IN ('baixa','media','alta','urgente')),
  resposta text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.portal_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('proprietario','locatario')),
  pessoa_id uuid NOT NULL,
  token text UNIQUE NOT NULL,
  nome text NOT NULL,
  email text,
  expires_at timestamptz NOT NULL DEFAULT (now() + interval '90 days'),
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.site_config (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL UNIQUE,
  nome_site text NOT NULL,
  slug text UNIQUE NOT NULL,
  logo_url text,
  cor_primaria text NOT NULL DEFAULT '#6366f1',
  cor_secundaria text NOT NULL DEFAULT '#1a1a2e',
  telefone text,
  whatsapp text,
  email_contato text,
  sobre text,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP O: Gamification ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.pontuacoes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  user_id uuid NOT NULL,
  acao text NOT NULL,
  pontos int NOT NULL,
  referencia_id uuid,
  referencia_tipo text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.conquistas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  user_id uuid NOT NULL,
  tipo text NOT NULL,
  nome text NOT NULL,
  descricao text,
  icone text NOT NULL DEFAULT '🏆',
  desbloqueada_em timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP P: Distribution, Branches & Banking ───────────────────────

CREATE TABLE IF NOT EXISTS erp.distribuicao_config (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL UNIQUE,
  modo text NOT NULL DEFAULT 'manual'
    CHECK (modo IN ('manual','round_robin','por_regiao','por_especialidade')),
  corretores_ativos uuid[] NOT NULL DEFAULT '{}',
  proximo_corretor_idx int NOT NULL DEFAULT 0,
  regras jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.filiais (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  nome text NOT NULL,
  codigo text NOT NULL,
  endereco text,
  cidade text,
  estado text,
  telefone text,
  responsavel_id uuid,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.remessas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('cnab240','cnab400')),
  banco text NOT NULL,
  arquivo_nome text,
  total_titulos integer NOT NULL DEFAULT 0,
  valor_total numeric NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'gerado'
    CHECK (status IN ('gerado','enviado','processado','erro')),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── Notifications ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.notificacoes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  user_id uuid NOT NULL,
  tipo text NOT NULL,
  titulo text NOT NULL,
  mensagem text,
  is_read boolean NOT NULL DEFAULT false,
  link text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.notificacao_preferencias (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  user_id uuid NOT NULL,
  canal text NOT NULL DEFAULT 'app'
    CHECK (canal IN ('app','email','whatsapp')),
  tipo_evento text NOT NULL,
  ativo boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(user_id, canal, tipo_evento)
);

-- ── WAHA WhatsApp Config ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.whatsapp_config (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL UNIQUE,
  provider text NOT NULL DEFAULT 'meta'
    CHECK (provider IN ('meta','waha')),
  meta_api_token text,
  meta_phone_number_id text,
  meta_api_version text DEFAULT 'v18.0',
  waha_api_url text,
  waha_api_key text,
  waha_session_name text DEFAULT 'default',
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── Meta API (Facebook/Instagram) ───────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.meta_config (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL UNIQUE,
  page_id text,
  access_token text,
  ad_account_id text,
  webhook_verify_token text,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.meta_leads (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  lead_id text NOT NULL,
  form_id text,
  form_name text,
  campo_data jsonb NOT NULL DEFAULT '{}',
  cliente_id uuid,
  importado boolean NOT NULL DEFAULT false,
  importado_em timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.meta_campanhas_sync (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  campaign_id text NOT NULL,
  nome text,
  status text,
  spend numeric DEFAULT 0,
  impressions integer DEFAULT 0,
  clicks integer DEFAULT 0,
  leads integer DEFAULT 0,
  cpl numeric,
  last_sync timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- filial_id on existing tables
ALTER TABLE erp.ativos ADD COLUMN IF NOT EXISTS filial_id uuid;
ALTER TABLE erp.clientes ADD COLUMN IF NOT EXISTS filial_id uuid;

-- ── Indexes for expansion tables ────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_propostas_org ON erp.propostas(org_id);
CREATE INDEX IF NOT EXISTS idx_propostas_cliente ON erp.propostas(cliente_id);
CREATE INDEX IF NOT EXISTS idx_propostas_imovel ON erp.propostas(imovel_id);
CREATE INDEX IF NOT EXISTS idx_propostas_status ON erp.propostas(status);
CREATE INDEX IF NOT EXISTS idx_contratos_org ON erp.contratos(org_id);
CREATE INDEX IF NOT EXISTS idx_contratos_cliente ON erp.contratos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_contratos_status ON erp.contratos(status);
CREATE INDEX IF NOT EXISTS idx_parcelas_contrato_contrato ON erp.parcelas_contrato(contrato_id);
CREATE INDEX IF NOT EXISTS idx_lancamentos_org ON erp.lancamentos(org_id);
CREATE INDEX IF NOT EXISTS idx_lancamentos_status ON erp.lancamentos(status);
CREATE INDEX IF NOT EXISTS idx_lancamentos_vencimento ON erp.lancamentos(data_vencimento);
CREATE INDEX IF NOT EXISTS idx_impostos_org ON erp.impostos(org_id);
CREATE INDEX IF NOT EXISTS idx_impostos_imovel ON erp.impostos(imovel_id);
CREATE INDEX IF NOT EXISTS idx_extratos_org ON erp.extratos_bancarios(org_id);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_extrato ON erp.movimentacoes_bancarias(extrato_id);
CREATE INDEX IF NOT EXISTS idx_comissoes_org ON erp.comissoes(org_id);
CREATE INDEX IF NOT EXISTS idx_comissoes_status ON erp.comissoes(status);
CREATE INDEX IF NOT EXISTS idx_comissoes_splits_comissao ON erp.comissoes_splits(comissao_id);
CREATE INDEX IF NOT EXISTS idx_contratos_locacao_org ON erp.contratos_locacao(org_id);
CREATE INDEX IF NOT EXISTS idx_contratos_locacao_status ON erp.contratos_locacao(status);
CREATE INDEX IF NOT EXISTS idx_eventos_org ON erp.eventos(org_id);
CREATE INDEX IF NOT EXISTS idx_eventos_corretor ON erp.eventos(corretor_id);
CREATE INDEX IF NOT EXISTS idx_eventos_data ON erp.eventos(data_inicio);
CREATE INDEX IF NOT EXISTS idx_documentos_org ON erp.documentos(org_id);
CREATE INDEX IF NOT EXISTS idx_assinaturas_org ON erp.assinaturas(org_id);
CREATE INDEX IF NOT EXISTS idx_assinaturas_status ON erp.assinaturas(status);
CREATE INDEX IF NOT EXISTS idx_emails_org ON erp.emails(org_id);
CREATE INDEX IF NOT EXISTS idx_campanhas_org ON erp.campanhas(org_id);
CREATE INDEX IF NOT EXISTS idx_envios_email_campanha ON erp.envios_email(campanha_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_org ON erp.whatsapp_messages(org_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_phone ON erp.whatsapp_messages(phone);
CREATE INDEX IF NOT EXISTS idx_vistorias_org ON erp.vistorias(org_id);
CREATE INDEX IF NOT EXISTS idx_vistorias_imovel ON erp.vistorias(imovel_id);
CREATE INDEX IF NOT EXISTS idx_checkins_org ON erp.checkins(org_id);
CREATE INDEX IF NOT EXISTS idx_checkins_corretor ON erp.checkins(corretor_id);
CREATE INDEX IF NOT EXISTS idx_ordens_servico_org ON erp.ordens_servico(org_id);
CREATE INDEX IF NOT EXISTS idx_ordens_servico_status ON erp.ordens_servico(status);
CREATE INDEX IF NOT EXISTS idx_seguros_org ON erp.seguros(org_id);
CREATE INDEX IF NOT EXISTS idx_seguros_imovel ON erp.seguros(imovel_id);
CREATE INDEX IF NOT EXISTS idx_analises_credito_org ON erp.analises_credito(org_id);
CREATE INDEX IF NOT EXISTS idx_analises_credito_cpf ON erp.analises_credito(cpf);
CREATE INDEX IF NOT EXISTS idx_chaves_org ON erp.chaves(org_id);
CREATE INDEX IF NOT EXISTS idx_chaves_imovel ON erp.chaves(imovel_id);
CREATE INDEX IF NOT EXISTS idx_chaves_historico_chave ON erp.chaves_historico(chave_id);
CREATE INDEX IF NOT EXISTS idx_portal_acessos_org ON erp.portal_acessos(org_id);
CREATE INDEX IF NOT EXISTS idx_portal_acessos_token ON erp.portal_acessos(token);
CREATE INDEX IF NOT EXISTS idx_chamados_portal_org ON erp.chamados_portal(org_id);
CREATE INDEX IF NOT EXISTS idx_portal_tokens_org ON erp.portal_tokens(org_id);
CREATE INDEX IF NOT EXISTS idx_site_config_slug ON erp.site_config(slug);
CREATE INDEX IF NOT EXISTS idx_pontuacoes_org ON erp.pontuacoes(org_id);
CREATE INDEX IF NOT EXISTS idx_pontuacoes_user ON erp.pontuacoes(user_id);
CREATE INDEX IF NOT EXISTS idx_conquistas_user ON erp.conquistas(user_id);
CREATE INDEX IF NOT EXISTS idx_filiais_org ON erp.filiais(org_id);
CREATE INDEX IF NOT EXISTS idx_remessas_org ON erp.remessas(org_id);
CREATE INDEX IF NOT EXISTS idx_notificacoes_user ON erp.notificacoes(user_id);
CREATE INDEX IF NOT EXISTS idx_notificacoes_read ON erp.notificacoes(is_read);
CREATE INDEX IF NOT EXISTS idx_notificacoes_created ON erp.notificacoes(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_meta_leads_org ON erp.meta_leads(org_id);
CREATE INDEX IF NOT EXISTS idx_meta_leads_lead_id ON erp.meta_leads(lead_id);
CREATE INDEX IF NOT EXISTS idx_meta_campanhas_org ON erp.meta_campanhas_sync(org_id);
CREATE INDEX IF NOT EXISTS idx_ativos_filial ON erp.ativos(filial_id);
CREATE INDEX IF NOT EXISTS idx_clientes_filial ON erp.clientes(filial_id);

-- ── RLS for expansion tables ────────────────────────────────────────

DO $$
DECLARE
  tbl text;
BEGIN
  FOR tbl IN SELECT unnest(ARRAY[
    'propostas','contratos','parcelas_contrato',
    'lancamentos','impostos','extratos_bancarios','movimentacoes_bancarias',
    'comissoes','comissoes_splits',
    'contratos_locacao','eventos',
    'documentos','document_templates','assinaturas',
    'emails','email_templates','campanhas','envios_email',
    'whatsapp_messages',
    'vistorias','checkins','vistorias_rapidas','ordens_servico',
    'seguros','analises_credito',
    'chaves','chaves_historico',
    'portal_acessos','chamados_portal','portal_tokens','site_config',
    'pontuacoes','conquistas',
    'distribuicao_config','filiais','remessas',
    'notificacoes','notificacao_preferencias',
    'whatsapp_config','meta_config','meta_leads','meta_campanhas_sync'
  ])
  LOOP
    EXECUTE format('ALTER TABLE erp.%I ENABLE ROW LEVEL SECURITY', tbl);
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_select_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR SELECT TO authenticated USING (org_id = (auth.jwt() ->> ''org_id'')::uuid)',
      tbl || '_select_policy', tbl
    );
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_insert_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR INSERT TO authenticated WITH CHECK (org_id = (auth.jwt() ->> ''org_id'')::uuid)',
      tbl || '_insert_policy', tbl
    );
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_update_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR UPDATE TO authenticated USING (org_id = (auth.jwt() ->> ''org_id'')::uuid)',
      tbl || '_update_policy', tbl
    );
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_delete_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR DELETE TO authenticated USING (org_id = (auth.jwt() ->> ''org_id'')::uuid)',
      tbl || '_delete_policy', tbl
    );
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_service_role_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR ALL TO service_role USING (true)',
      tbl || '_service_role_policy', tbl
    );
  END LOOP;
END $$;

-- Public access for portals
DROP POLICY IF EXISTS site_config_anon_read ON erp.site_config;
CREATE POLICY site_config_anon_read ON erp.site_config
  FOR SELECT TO anon USING (is_active = true);
DROP POLICY IF EXISTS portal_tokens_anon_read ON erp.portal_tokens;
CREATE POLICY portal_tokens_anon_read ON erp.portal_tokens
  FOR SELECT TO anon USING (is_active = true AND expires_at > now());
DROP POLICY IF EXISTS portal_acessos_anon_read ON erp.portal_acessos;
CREATE POLICY portal_acessos_anon_read ON erp.portal_acessos
  FOR SELECT TO anon USING (ativo = true);

-- ── Timestamp triggers for expansion tables ─────────────────────────

DO $$
DECLARE
  tbl text;
BEGIN
  FOR tbl IN SELECT unnest(ARRAY[
    'propostas','contratos','lancamentos','impostos',
    'comissoes','contratos_locacao','eventos',
    'assinaturas','email_templates','campanhas',
    'vistorias','ordens_servico','seguros',
    'chamados_portal','distribuicao_config',
    'whatsapp_config','meta_config','meta_campanhas_sync'
  ])
  LOOP
    EXECUTE format(
      'CREATE TRIGGER IF NOT EXISTS set_timestamps_%I BEFORE INSERT OR UPDATE ON erp.%I FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp()',
      tbl, tbl
    );
  END LOOP;
END $$;

-- ─────────────────────────────────────────────────────────────────────
-- 12B. CERTIDÕES NEGATIVAS TABLES (inline from 007_certidoes_negativas.sql)
-- ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.certidao_consultas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid,
    created_by uuid NOT NULL,
    tipo_documento text NOT NULL CHECK (tipo_documento IN ('cpf', 'cnpj')),
    documento text NOT NULL,
    nome text NOT NULL,
    data_nascimento text,
    genero text CHECK (genero IS NULL OR genero IN ('M', 'F')),
    rg text,
    nome_mae text,
    nome_pai text,
    status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'processando', 'concluida', 'erro')),
    total_certidoes int NOT NULL DEFAULT 0,
    concluidas int NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.certidao_resultados (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    consulta_id uuid NOT NULL REFERENCES erp.certidao_consultas(id) ON DELETE CASCADE,
    org_id uuid,
    tipo text NOT NULL,
    nome_display text NOT NULL,
    ordem int NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'processando', 'sucesso', 'erro')),
    analise_ia text,
    arquivo_url text,
    arquivo_nome text,
    api_response jsonb,
    erro_mensagem text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_certidao_consultas_org ON erp.certidao_consultas(org_id);
CREATE INDEX IF NOT EXISTS idx_certidao_consultas_status ON erp.certidao_consultas(status);
CREATE INDEX IF NOT EXISTS idx_certidao_consultas_documento ON erp.certidao_consultas(documento);
CREATE INDEX IF NOT EXISTS idx_certidao_resultados_consulta ON erp.certidao_resultados(consulta_id);
CREATE INDEX IF NOT EXISTS idx_certidao_resultados_org ON erp.certidao_resultados(org_id);

ALTER TABLE erp.certidao_consultas ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.certidao_resultados ENABLE ROW LEVEL SECURITY;

CREATE POLICY certidao_consultas_select ON erp.certidao_consultas
    FOR SELECT TO authenticated USING (created_by = auth.uid());
CREATE POLICY certidao_consultas_insert ON erp.certidao_consultas
    FOR INSERT TO authenticated WITH CHECK (created_by = auth.uid());
CREATE POLICY certidao_consultas_update ON erp.certidao_consultas
    FOR UPDATE TO authenticated USING (created_by = auth.uid());
CREATE POLICY certidao_consultas_delete ON erp.certidao_consultas
    FOR DELETE TO authenticated USING (created_by = auth.uid());
CREATE POLICY certidao_consultas_service ON erp.certidao_consultas
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY certidao_resultados_select ON erp.certidao_resultados
    FOR SELECT TO authenticated USING (
        EXISTS (SELECT 1 FROM erp.certidao_consultas WHERE id = consulta_id AND created_by = auth.uid())
    );
CREATE POLICY certidao_resultados_insert ON erp.certidao_resultados
    FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY certidao_resultados_update ON erp.certidao_resultados
    FOR UPDATE TO authenticated USING (
        EXISTS (SELECT 1 FROM erp.certidao_consultas WHERE id = consulta_id AND created_by = auth.uid())
    );
CREATE POLICY certidao_resultados_delete ON erp.certidao_resultados
    FOR DELETE TO authenticated USING (
        EXISTS (SELECT 1 FROM erp.certidao_consultas WHERE id = consulta_id AND created_by = auth.uid())
    );
CREATE POLICY certidao_resultados_service ON erp.certidao_resultados
    FOR ALL USING (auth.role() = 'service_role');

CREATE TRIGGER set_certidao_consultas_updated
    BEFORE UPDATE ON erp.certidao_consultas FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_certidao_resultados_updated
    BEFORE UPDATE ON erp.certidao_resultados FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();

-- Seed sidebar entry
INSERT INTO erp.status_pagina (nome_pagina, status)
VALUES ('certidoes', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- 13. FINAL GRANTS (ensure all objects have correct permissions)
-- ─────────────────────────────────────────────────────────────────────

GRANT ALL ON ALL TABLES IN SCHEMA erp TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA erp TO anon, authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA erp TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA erp TO anon, authenticated, service_role;

-- ─────────────────────────────────────────────────────────────────────
-- DONE. Schema is fully set up.
-- ─────────────────────────────────────────────────────────────────────
