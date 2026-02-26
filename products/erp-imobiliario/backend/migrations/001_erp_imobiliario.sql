-- =====================================================================
-- ERP Imobiliário — Consolidated Schema Migration
-- Merged from 87 incremental migration files into a single idempotent script.
-- Run this once on a fresh Supabase project.
-- =====================================================================

-- ─────────────────────────────────────────────────────────────────────
-- 1. EXTENSIONS
-- ─────────────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

-- ─────────────────────────────────────────────────────────────────────
-- 2. ENUMS
-- ─────────────────────────────────────────────────────────────────────

CREATE TYPE public.tipo_meta AS ENUM ('diaria', 'semanal', 'mensal', 'anual');

CREATE TYPE public.status_meta AS ENUM ('aberta', 'concluida', 'atrasada', 'no_prazo', 'vence_amanha');

CREATE TYPE public.app_role AS ENUM ('admin', 'corretor', 'coordenador', 'dev');

CREATE TYPE public.categoria_meta AS ENUM (
  'captacao', 'visitas', 'contatos', 'propostas', 'fechamento',
  'captacao_imoveis', 'captacao_compradores', 'atualizacao_imoveis', 'outro'
);

CREATE TYPE public.conclusao_prazo_meta AS ENUM ('no_prazo', 'atrasada');

CREATE TYPE public.nivel_performance_meta AS ENUM ('baixo', 'regular', 'bom', 'excelente');

CREATE TYPE public.etapa_funil AS ENUM ('qualificacao', 'visitas', 'proposta', 'negociacao', 'fechado');

CREATE TYPE public.tipo_atividade AS ENUM ('ligacao', 'email', 'reuniao', 'whatsapp', 'visita', 'proposta', 'negociacao', 'outro');

CREATE TYPE public.finalidade_imovel AS ENUM ('venda', 'aluguel');

CREATE TYPE public.tipo_imovel AS ENUM ('casa', 'apartamento', 'terreno', 'comercial', 'rural', 'outro');

CREATE TYPE public.categoria_permuta AS ENUM ('imovel', 'movel');

CREATE TYPE public.tipo_movel AS ENUM ('carro', 'moto');

CREATE TYPE public.status_negociacao AS ENUM ('qualificacao', 'visitas', 'proposta', 'negociacao', 'fechado', 'cancelado');

CREATE TYPE public.tipo_acao AS ENUM (
  'criar', 'editar', 'excluir', 'concluir',
  'arquivar', 'desarquivar', 'mover', 'login', 'logout'
);

CREATE TYPE public.tipo_entidade AS ENUM (
  'meta', 'cliente', 'usuario', 'atividade', 'config_meta', 'auth',
  'imovel', 'perfil_permuta', 'negociacao', 'match', 'condominio', 'ativo'
);

CREATE TYPE public.status_match AS ENUM ('pendente', 'aceito', 'rejeitado', 'expirado');

-- ─────────────────────────────────────────────────────────────────────
-- 3. SEQUENCES
-- ─────────────────────────────────────────────────────────────────────

CREATE SEQUENCE IF NOT EXISTS public.metas_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.imoveis_id_seq START WITH 1;
CREATE SEQUENCE IF NOT EXISTS public.perfis_permutas_id_seq START WITH 1;
CREATE SEQUENCE IF NOT EXISTS public.negociacoes_id_seq START WITH 1;

-- ─────────────────────────────────────────────────────────────────────
-- 4. UTILITY FUNCTIONS
-- ─────────────────────────────────────────────────────────────────────

-- Timestamp helpers (São Paulo timezone)
CREATE OR REPLACE FUNCTION public.current_date_sao_paulo()
RETURNS DATE
LANGUAGE SQL STABLE
AS $$ SELECT (NOW() AT TIME ZONE 'America/Sao_Paulo')::DATE; $$;

CREATE OR REPLACE FUNCTION public.now_sao_paulo()
RETURNS TIMESTAMP WITH TIME ZONE
LANGUAGE SQL STABLE
AS $$ SELECT NOW() AT TIME ZONE 'America/Sao_Paulo'; $$;

CREATE OR REPLACE FUNCTION public.normalize_timestamp_sp(ts TIMESTAMP WITH TIME ZONE)
RETURNS TIMESTAMP WITH TIME ZONE
LANGUAGE SQL IMMUTABLE
AS $$ SELECT ts AT TIME ZONE 'America/Sao_Paulo'; $$;

-- Generic updated_at trigger
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

-- São Paulo timestamp trigger for created_at/updated_at
CREATE OR REPLACE FUNCTION public.set_timestamps_sp()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    NEW.created_at := now_sao_paulo();
    IF TG_TABLE_NAME IN ('clientes', 'imoveis', 'profiles', 'negociacoes', 'metas', 'metas_config') THEN
      NEW.updated_at := now_sao_paulo();
    END IF;
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF TG_TABLE_NAME IN ('clientes', 'imoveis', 'profiles', 'negociacoes', 'metas', 'metas_config') THEN
      NEW.updated_at := now_sao_paulo();
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

-- ID generators (sequence-based, concurrency-safe)
CREATE OR REPLACE FUNCTION public.generate_meta_id()
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
DECLARE next_number INTEGER; next_id TEXT;
BEGIN
  next_number := nextval('public.metas_id_seq')::INTEGER;
  IF next_number <= 9999 THEN
    next_id := 'MT' || LPAD(next_number::TEXT, 4, '0');
  ELSE
    next_id := 'MT' || next_number::TEXT;
  END IF;
  RETURN next_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.generate_imovel_id()
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
DECLARE next_number INTEGER; next_id TEXT;
BEGIN
  next_number := nextval('public.imoveis_id_seq')::INTEGER;
  IF next_number <= 9999 THEN
    next_id := 'IM' || LPAD(next_number::TEXT, 4, '0');
  ELSE
    next_id := 'IM' || next_number::TEXT;
  END IF;
  RETURN next_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.generate_perfil_permuta_id()
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
DECLARE next_number INTEGER; next_id TEXT;
BEGIN
  next_number := nextval('public.perfis_permutas_id_seq')::INTEGER;
  IF next_number <= 9999 THEN
    next_id := 'PP' || LPAD(next_number::TEXT, 4, '0');
  ELSE
    next_id := 'PP' || next_number::TEXT;
  END IF;
  RETURN next_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.generate_negociacao_id()
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
DECLARE next_number INTEGER; next_id TEXT;
BEGIN
  next_number := nextval('public.negociacoes_id_seq')::INTEGER;
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
CREATE TABLE public.profiles (
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
CREATE TABLE public.user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  role app_role NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  UNIQUE (user_id, role)
);

-- Role check helper (must be here — after user_roles, before RLS policies)
CREATE OR REPLACE FUNCTION public.has_role(_user_id UUID, _role app_role)
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = _user_id AND role = _role); $$;

-- 5c. Metas (goals) — fully merged with all incremental columns
CREATE TABLE public.metas (
  id TEXT PRIMARY KEY DEFAULT public.generate_meta_id(),
  usuario_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  tipo public.tipo_meta NOT NULL,
  categoria public.categoria_meta NOT NULL DEFAULT 'captacao',
  categoria_custom TEXT,
  nome TEXT,
  detalhes TEXT,
  meta_pretendida INTEGER NOT NULL,
  meta_realizada INTEGER DEFAULT 0,
  data_prazo DATE NOT NULL,
  status public.status_meta DEFAULT 'aberta' NOT NULL,
  carry_in INTEGER NOT NULL DEFAULT 0,
  carry_out INTEGER NOT NULL DEFAULT 0,
  conclusao_prazo public.conclusao_prazo_meta NOT NULL DEFAULT 'no_prazo',
  nivel_performance public.nivel_performance_meta NOT NULL DEFAULT 'baixo',
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
CREATE TABLE public.metas_config (
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
CREATE TABLE public.clientes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
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
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5f. Funil movimentos (funnel history)
CREATE TABLE public.funil_movimentos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id UUID NOT NULL REFERENCES public.clientes(id) ON DELETE CASCADE,
  de_etapa etapa_funil,
  para_etapa etapa_funil NOT NULL,
  responsavel_id UUID NOT NULL REFERENCES public.profiles(id),
  motivo TEXT,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5g. Atividades (activities)
CREATE TABLE public.atividades (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id UUID NOT NULL REFERENCES public.clientes(id) ON DELETE CASCADE,
  usuario_id UUID NOT NULL REFERENCES public.profiles(id),
  tipo tipo_atividade NOT NULL DEFAULT 'outro',
  descricao TEXT NOT NULL,
  data_execucao TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5h. Password request codes (admin temporary passwords)
CREATE TABLE public.password_request_codes (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  admin_user_id UUID NOT NULL,
  corretor_id UUID NOT NULL,
  code TEXT NOT NULL,
  temp_password TEXT NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5i. Status pagina (feature flags)
CREATE TABLE public.status_pagina (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome_pagina TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento')),
  descricao TEXT,
  tipo_pagina TEXT NOT NULL DEFAULT 'geral',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5j. User actions log (audit trail)
CREATE TABLE public.user_actions_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tipo_acao tipo_acao NOT NULL,
  tipo_entidade tipo_entidade NOT NULL,
  entidade_id TEXT,
  descricao TEXT NOT NULL,
  detalhes JSONB,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5k. Imóveis (properties)
CREATE TABLE public.imoveis (
  id TEXT PRIMARY KEY DEFAULT generate_imovel_id(),
  owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'ativo',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  finalidade finalidade_imovel NOT NULL DEFAULT 'venda',
  preco_pedido NUMERIC(12,2) NOT NULL,
  aceita_permutas BOOLEAN NOT NULL DEFAULT false,
  observacoes_negociacao TEXT,
  cep TEXT NOT NULL,
  logradouro TEXT,
  numero TEXT,
  complemento TEXT,
  bairro TEXT,
  cidade TEXT,
  estado TEXT,
  latitude NUMERIC(10,8),
  longitude NUMERIC(11,8),
  tipo tipo_imovel NOT NULL,
  area_privativa NUMERIC(8,2),
  area_total NUMERIC(8,2),
  quartos INTEGER,
  suites INTEGER,
  banheiros INTEGER,
  vagas INTEGER,
  andar INTEGER,
  condominio NUMERIC(10,2),
  iptu NUMERIC(10,2),
  condominio_nome TEXT,
  ano_construcao INTEGER,
  fotos TEXT[] DEFAULT ARRAY[]::TEXT[],
  tour_virtual_url TEXT,
  plantas TEXT[] DEFAULT ARRAY[]::TEXT[],
  titulo_anuncio TEXT,
  descricao_seo TEXT,
  palavras_chave TEXT[] DEFAULT ARRAY[]::TEXT[],
  pontos_de_interesse TEXT[] DEFAULT ARRAY[]::TEXT[],
  pronto_para_portais BOOLEAN NOT NULL DEFAULT false,
  lqs_score_hint TEXT,
  condominio_id UUID, -- FK added after condominios table creation
  CONSTRAINT check_palavras_chave_max CHECK (array_length(palavras_chave, 1) IS NULL OR array_length(palavras_chave, 1) <= 4)
);

-- 5l. Perfis de permuta (exchange profiles)
CREATE TABLE public.perfis_permutas (
  id TEXT PRIMARY KEY DEFAULT generate_perfil_permuta_id(),
  cliente_ofertante_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'ativo',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  categoria categoria_permuta NOT NULL,
  tipo_imovel tipo_imovel,
  faixa_preco_min NUMERIC(12,2),
  faixa_preco_max NUMERIC(12,2),
  regiao_preferida TEXT[] DEFAULT ARRAY[]::TEXT[],
  metragem_min NUMERIC(8,2),
  metragem_max NUMERIC(8,2),
  quartos_min INTEGER,
  vagas_min INTEGER,
  tipo_movel tipo_movel,
  marca TEXT,
  modelo TEXT,
  ano_min INTEGER,
  ano_max INTEGER,
  quilometragem_max INTEGER,
  aceita_completar_diferenca BOOLEAN NOT NULL DEFAULT false,
  limite_complemento NUMERIC(12,2),
  observacoes TEXT,
  valor_estimado NUMERIC(12,2)
);

-- 5m. Imóveis ↔ Perfis permutas (N:N)
CREATE TABLE public.imoveis_perfis_permutas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  imovel_id TEXT NOT NULL REFERENCES public.imoveis(id) ON DELETE CASCADE,
  perfil_permuta_id TEXT NOT NULL REFERENCES public.perfis_permutas(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  UNIQUE(imovel_id, perfil_permuta_id)
);

-- 5n. Negociações (negotiations)
CREATE TABLE public.negociacoes (
  id TEXT PRIMARY KEY DEFAULT generate_negociacao_id(),
  owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  imovel_id TEXT NOT NULL REFERENCES public.imoveis(id) ON DELETE CASCADE,
  perfil_permuta_id TEXT NOT NULL REFERENCES public.perfis_permutas(id) ON DELETE CASCADE,
  cliente_proprietario_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  cliente_ofertante_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  valor_imovel NUMERIC(12,2) NOT NULL,
  valor_permuta NUMERIC(12,2) NOT NULL,
  valor_complemento NUMERIC(12,2) DEFAULT 0,
  status_etapa status_negociacao NOT NULL DEFAULT 'qualificacao',
  timeline JSONB DEFAULT '[]'::JSONB,
  observacoes TEXT
);

-- 5o. Condominios
CREATE TABLE public.condominios (
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

-- Add condominio FK to imoveis now that condominios table exists
ALTER TABLE public.imoveis
  ADD CONSTRAINT imoveis_condominio_id_fkey
  FOREIGN KEY (condominio_id) REFERENCES public.condominios(id) ON DELETE SET NULL;

-- 5p. Matches (computed matches between ativos)
CREATE TABLE public.matches (
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
CREATE TABLE public.ativos (
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
ALTER TABLE public.matches
  ADD CONSTRAINT matches_ativo_origem_id_fkey FOREIGN KEY (ativo_origem_id) REFERENCES public.ativos(id) ON DELETE CASCADE,
  ADD CONSTRAINT matches_ativo_destino_id_fkey FOREIGN KEY (ativo_destino_id) REFERENCES public.ativos(id) ON DELETE CASCADE;

-- ─────────────────────────────────────────────────────────────────────
-- 6. INDEXES
-- ─────────────────────────────────────────────────────────────────────

-- Metas
CREATE INDEX idx_metas_usuario_tipo_data ON public.metas(usuario_id, tipo, data_prazo);
CREATE INDEX idx_metas_usuario_tipo_categoria_data ON public.metas(usuario_id, tipo, categoria, data_prazo);
CREATE INDEX idx_metas_categoria ON public.metas(categoria);
CREATE INDEX idx_metas_categoria_custom ON public.metas(categoria_custom);
CREATE INDEX idx_metas_tem_impedimento ON public.metas(tem_impedimento) WHERE tem_impedimento = true;
CREATE INDEX idx_metas_nome ON public.metas(nome);

-- Metas config
CREATE INDEX idx_metas_config_categoria_custom ON public.metas_config(categoria_custom);

-- Profiles
CREATE INDEX idx_profiles_last_activity ON public.profiles(last_activity_at);

-- Clientes
CREATE INDEX idx_clientes_etapa_pos ON public.clientes(etapa_atual, kanban_pos);
CREATE INDEX idx_clientes_owner ON public.clientes(usuario_id, arquivado);
CREATE INDEX idx_clientes_busca ON public.clientes USING gin(to_tsvector('portuguese', nome || ' ' || COALESCE(email, '') || ' ' || COALESCE(telefone, '')));

-- Funil movimentos
CREATE INDEX idx_funil_movimentos_cliente ON public.funil_movimentos(cliente_id, created_at DESC);

-- Atividades
CREATE INDEX idx_atividades_cliente ON public.atividades(cliente_id, created_at DESC);

-- Password request codes
CREATE INDEX idx_password_request_codes_admin_corretor ON public.password_request_codes(admin_user_id, corretor_id);

-- User actions log
CREATE INDEX idx_user_actions_log_usuario_id ON public.user_actions_log(usuario_id);
CREATE INDEX idx_user_actions_log_created_at ON public.user_actions_log(created_at DESC);
CREATE INDEX idx_user_actions_log_tipo_acao ON public.user_actions_log(tipo_acao);
CREATE INDEX idx_user_actions_log_tipo_entidade ON public.user_actions_log(tipo_entidade);

-- Imóveis
CREATE INDEX idx_imoveis_owner ON public.imoveis(owner_id);
CREATE INDEX idx_imoveis_finalidade ON public.imoveis(finalidade);
CREATE INDEX idx_imoveis_tipo ON public.imoveis(tipo);
CREATE INDEX idx_imoveis_preco ON public.imoveis(preco_pedido);
CREATE INDEX idx_imoveis_aceita_permutas ON public.imoveis(aceita_permutas);
CREATE INDEX idx_imoveis_cep ON public.imoveis(cep);
CREATE INDEX idx_imoveis_cidade ON public.imoveis(cidade);
CREATE INDEX idx_imoveis_estado ON public.imoveis(estado);
CREATE INDEX idx_imoveis_status ON public.imoveis(status);

-- Perfis de permuta
CREATE INDEX idx_perfis_cliente ON public.perfis_permutas(cliente_ofertante_id);
CREATE INDEX idx_perfis_categoria ON public.perfis_permutas(categoria);
CREATE INDEX idx_perfis_tipo_imovel ON public.perfis_permutas(tipo_imovel);
CREATE INDEX idx_perfis_tipo_movel ON public.perfis_permutas(tipo_movel);
CREATE INDEX idx_perfis_status ON public.perfis_permutas(status);

-- Imoveis ↔ Perfis
CREATE INDEX idx_imoveis_perfis_imovel ON public.imoveis_perfis_permutas(imovel_id);
CREATE INDEX idx_imoveis_perfis_perfil ON public.imoveis_perfis_permutas(perfil_permuta_id);

-- Negociações
CREATE INDEX idx_negociacoes_imovel ON public.negociacoes(imovel_id);
CREATE INDEX idx_negociacoes_perfil ON public.negociacoes(perfil_permuta_id);
CREATE INDEX idx_negociacoes_proprietario ON public.negociacoes(cliente_proprietario_id);
CREATE INDEX idx_negociacoes_ofertante ON public.negociacoes(cliente_ofertante_id);
CREATE INDEX idx_negociacoes_status ON public.negociacoes(status_etapa);

-- Condominios
CREATE INDEX idx_condominios_owner_id ON public.condominios(owner_id);
CREATE INDEX idx_condominios_cidade ON public.condominios(cidade);

-- Matches
CREATE INDEX idx_matches_ativo_origem_id ON public.matches(ativo_origem_id);
CREATE INDEX idx_matches_ativo_destino_id ON public.matches(ativo_destino_id);
CREATE INDEX idx_matches_score_desc ON public.matches(score DESC);
CREATE INDEX idx_matches_status ON public.matches(status);

-- Ativos
CREATE INDEX idx_ativos_owner_id ON public.ativos(owner_id);
CREATE INDEX idx_ativos_natureza ON public.ativos(natureza);
CREATE INDEX idx_ativos_tipo_imovel ON public.ativos(tipo_imovel);
CREATE INDEX idx_ativos_cidade ON public.ativos(cidade);
CREATE INDEX idx_ativos_estado ON public.ativos(estado);
CREATE INDEX idx_ativos_valor ON public.ativos(valor);
CREATE INDEX idx_ativos_status ON public.ativos(status);
CREATE INDEX idx_ativos_proprietario ON public.ativos(proprietario_id);

-- ─────────────────────────────────────────────────────────────────────
-- 7. ROW LEVEL SECURITY
-- ─────────────────────────────────────────────────────────────────────

-- Enable RLS on all tables
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.metas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.metas_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.clientes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.funil_movimentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atividades ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.password_request_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.status_pagina ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_actions_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.imoveis ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.perfis_permutas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.imoveis_perfis_permutas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.negociacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.condominios ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ativos ENABLE ROW LEVEL SECURITY;

-- ── Profiles ──
CREATE POLICY "Users can view their own profile" ON public.profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Admins can view all profiles" ON public.profiles FOR SELECT USING (public.has_role(auth.uid(), 'admin'::app_role));
CREATE POLICY "Users can update their own profile" ON public.profiles FOR UPDATE TO authenticated USING (auth.uid() = id) WITH CHECK (auth.uid() = id);
CREATE POLICY "Users can insert their own profile" ON public.profiles FOR INSERT TO authenticated WITH CHECK (auth.uid() = id);
CREATE POLICY "Admins can update all profiles" ON public.profiles FOR UPDATE TO authenticated USING (public.has_role(auth.uid(), 'admin'::app_role));

-- ── User roles ──
CREATE POLICY "Admins can view all roles" ON public.user_roles FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Users can view their own roles" ON public.user_roles FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Admins can insert roles" ON public.user_roles FOR INSERT TO authenticated WITH CHECK (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Admins can update roles" ON public.user_roles FOR UPDATE TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Admins can delete roles" ON public.user_roles FOR DELETE TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Deny unauthenticated access to user_roles" ON public.user_roles FOR ALL TO anon USING (false);

-- ── Metas ──
CREATE POLICY "Users can view their own metas" ON public.metas FOR SELECT TO authenticated USING (auth.uid() = usuario_id);
CREATE POLICY "Admins can view all metas" ON public.metas FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Users can insert their own metas" ON public.metas FOR INSERT TO authenticated WITH CHECK (usuario_id = auth.uid() AND usuario_id IS NOT NULL);
CREATE POLICY "Admins can insert metas for any user" ON public.metas FOR INSERT TO authenticated WITH CHECK (has_role(auth.uid(), 'admin'));
CREATE POLICY "Users can update own daily incomplete metas" ON public.metas FOR UPDATE TO authenticated USING (auth.uid() = usuario_id AND tipo = 'diaria' AND status != 'concluida') WITH CHECK (auth.uid() = usuario_id AND tipo = 'diaria' AND status != 'concluida');
CREATE POLICY "Admins can update monthly metas" ON public.metas FOR UPDATE TO authenticated USING (has_role(auth.uid(), 'admin') AND tipo = 'mensal') WITH CHECK (has_role(auth.uid(), 'admin') AND tipo = 'mensal');
CREATE POLICY "Admins can update daily metas" ON public.metas FOR UPDATE TO authenticated USING (has_role(auth.uid(), 'admin') AND tipo = 'diaria') WITH CHECK (has_role(auth.uid(), 'admin') AND tipo = 'diaria');
CREATE POLICY "Users can delete own daily incomplete metas" ON public.metas FOR DELETE USING (auth.uid() = usuario_id AND tipo = 'diaria' AND status != 'concluida');
CREATE POLICY "Users can delete own aggregated metas" ON public.metas FOR DELETE USING ((auth.uid() = usuario_id) AND (tipo IN ('semanal', 'mensal', 'anual')));
CREATE POLICY "Admins can delete completed metas" ON public.metas FOR DELETE USING (has_role(auth.uid(), 'admin') AND status = 'concluida');
CREATE POLICY "Admins can delete aggregated metas" ON public.metas FOR DELETE USING (has_role(auth.uid(), 'admin') AND tipo IN ('semanal', 'mensal', 'anual'));
CREATE POLICY "Admins can delete any daily incomplete meta" ON public.metas FOR DELETE USING (has_role(auth.uid(), 'admin') AND tipo = 'diaria' AND status != 'concluida');

-- ── Metas config ──
CREATE POLICY "Usuários podem ver suas próprias configs" ON public.metas_config FOR SELECT USING (auth.uid() = usuario_id);
CREATE POLICY "Usuários podem inserir suas próprias configs" ON public.metas_config FOR INSERT WITH CHECK (auth.uid() = usuario_id);
CREATE POLICY "Usuários podem atualizar suas próprias configs" ON public.metas_config FOR UPDATE USING (auth.uid() = usuario_id);
CREATE POLICY "Usuários podem deletar suas próprias configs" ON public.metas_config FOR DELETE USING (auth.uid() = usuario_id);
CREATE POLICY "Admins podem ver todas as configs" ON public.metas_config FOR SELECT USING (has_role(auth.uid(), 'admin'::app_role));

-- ── Clientes ──
CREATE POLICY "Usuários podem ver seus próprios clientes" ON public.clientes FOR SELECT TO authenticated USING (auth.uid() = usuario_id);
CREATE POLICY "Admins podem ver todos os clientes" ON public.clientes FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem criar seus próprios clientes" ON public.clientes FOR INSERT TO authenticated WITH CHECK (auth.uid() = usuario_id);
CREATE POLICY "Usuários podem atualizar seus próprios clientes" ON public.clientes FOR UPDATE TO authenticated USING (auth.uid() = usuario_id);
CREATE POLICY "Admins podem atualizar todos os clientes" ON public.clientes FOR UPDATE TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem deletar seus próprios clientes" ON public.clientes FOR DELETE TO authenticated USING (auth.uid() = usuario_id);
CREATE POLICY "Admins podem deletar todos os clientes" ON public.clientes FOR DELETE TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- ── Funil movimentos ──
CREATE POLICY "Usuários podem ver movimentos de seus clientes" ON public.funil_movimentos FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM public.clientes WHERE clientes.id = funil_movimentos.cliente_id AND clientes.usuario_id = auth.uid()));
CREATE POLICY "Admins podem ver todos os movimentos" ON public.funil_movimentos FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem criar movimentos para seus clientes" ON public.funil_movimentos FOR INSERT TO authenticated WITH CHECK (EXISTS (SELECT 1 FROM public.clientes WHERE clientes.id = funil_movimentos.cliente_id AND clientes.usuario_id = auth.uid()) AND responsavel_id = auth.uid());

-- ── Atividades ──
CREATE POLICY "Usuários podem ver atividades de seus clientes" ON public.atividades FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM public.clientes WHERE clientes.id = atividades.cliente_id AND clientes.usuario_id = auth.uid()));
CREATE POLICY "Admins podem ver todas as atividades" ON public.atividades FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem criar atividades para seus clientes" ON public.atividades FOR INSERT TO authenticated WITH CHECK (EXISTS (SELECT 1 FROM public.clientes WHERE clientes.id = atividades.cliente_id AND clientes.usuario_id = auth.uid()) AND usuario_id = auth.uid());

-- ── Password request codes ──
CREATE POLICY "Admins can manage their own password request codes" ON public.password_request_codes FOR ALL USING (auth.uid() = admin_user_id);
CREATE POLICY "Only admins can view password codes" ON public.password_request_codes FOR SELECT TO authenticated USING (has_role(auth.uid(), 'admin'));

-- ── Status pagina ──
CREATE POLICY "Todos podem ver páginas gerais em produção" ON public.status_pagina FOR SELECT USING (status = 'producao' AND tipo_pagina = 'geral');
CREATE POLICY "Admins podem ver todas as páginas" ON public.status_pagina FOR SELECT USING (has_role(auth.uid(), 'admin'::app_role));
CREATE POLICY "Devs podem ver páginas gerais em desenvolvimento" ON public.status_pagina FOR SELECT USING (has_role(auth.uid(), 'dev'::app_role) AND tipo_pagina = 'geral');
CREATE POLICY "Apenas admins podem gerenciar páginas" ON public.status_pagina FOR ALL USING (has_role(auth.uid(), 'admin'::app_role)) WITH CHECK (has_role(auth.uid(), 'admin'::app_role));

-- ── User actions log ──
CREATE POLICY "Admins podem ver todos os logs de ações" ON public.user_actions_log FOR SELECT USING (has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem ver seus próprios logs" ON public.user_actions_log FOR SELECT USING (auth.uid() = usuario_id);
CREATE POLICY "Usuários podem inserir logs" ON public.user_actions_log FOR INSERT WITH CHECK (auth.uid() = usuario_id);

-- ── Imóveis ──
CREATE POLICY "Admins podem ver todos os imóveis" ON public.imoveis FOR SELECT USING (has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem ver seus próprios imóveis" ON public.imoveis FOR SELECT USING (auth.uid() = owner_id);
CREATE POLICY "Usuários podem criar seus próprios imóveis" ON public.imoveis FOR INSERT WITH CHECK (auth.uid() = owner_id);
CREATE POLICY "Usuários podem atualizar seus próprios imóveis" ON public.imoveis FOR UPDATE USING (auth.uid() = owner_id);
CREATE POLICY "Admins podem atualizar todos os imóveis" ON public.imoveis FOR UPDATE USING (has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem deletar seus próprios imóveis" ON public.imoveis FOR DELETE USING (auth.uid() = owner_id);
CREATE POLICY "Admins podem deletar todos os imóveis" ON public.imoveis FOR DELETE USING (has_role(auth.uid(), 'admin'));

-- ── Perfis de permuta ──
CREATE POLICY "Admins podem ver todos os perfis de permuta" ON public.perfis_permutas FOR SELECT USING (has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem ver seus próprios perfis" ON public.perfis_permutas FOR SELECT USING (auth.uid() = cliente_ofertante_id);
CREATE POLICY "Usuários podem criar seus próprios perfis" ON public.perfis_permutas FOR INSERT WITH CHECK (auth.uid() = cliente_ofertante_id);
CREATE POLICY "Usuários podem atualizar seus próprios perfis" ON public.perfis_permutas FOR UPDATE USING (auth.uid() = cliente_ofertante_id);
CREATE POLICY "Admins podem atualizar todos os perfis" ON public.perfis_permutas FOR UPDATE USING (has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem deletar seus próprios perfis" ON public.perfis_permutas FOR DELETE USING (auth.uid() = cliente_ofertante_id);
CREATE POLICY "Admins podem deletar todos os perfis" ON public.perfis_permutas FOR DELETE USING (has_role(auth.uid(), 'admin'));

-- ── Imoveis ↔ Perfis permutas ──
CREATE POLICY "Admins podem ver todos os relacionamentos" ON public.imoveis_perfis_permutas FOR SELECT USING (has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem ver relacionamentos de seus imóveis" ON public.imoveis_perfis_permutas FOR SELECT USING (EXISTS (SELECT 1 FROM public.imoveis WHERE imoveis.id = imoveis_perfis_permutas.imovel_id AND imoveis.owner_id = auth.uid()));
CREATE POLICY "Usuários podem criar relacionamentos de seus imóveis" ON public.imoveis_perfis_permutas FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM public.imoveis WHERE imoveis.id = imoveis_perfis_permutas.imovel_id AND imoveis.owner_id = auth.uid()));
CREATE POLICY "Usuários podem deletar relacionamentos de seus imóveis" ON public.imoveis_perfis_permutas FOR DELETE USING (EXISTS (SELECT 1 FROM public.imoveis WHERE imoveis.id = imoveis_perfis_permutas.imovel_id AND imoveis.owner_id = auth.uid()));
CREATE POLICY "Admins podem gerenciar todos os relacionamentos" ON public.imoveis_perfis_permutas FOR ALL USING (has_role(auth.uid(), 'admin'));

-- ── Negociações ──
CREATE POLICY "Admins podem ver todas as negociações" ON public.negociacoes FOR SELECT USING (has_role(auth.uid(), 'admin'));
CREATE POLICY "Proprietários podem ver suas negociações" ON public.negociacoes FOR SELECT USING (auth.uid() = cliente_proprietario_id);
CREATE POLICY "Ofertantes podem ver suas negociações" ON public.negociacoes FOR SELECT USING (auth.uid() = cliente_ofertante_id);
CREATE POLICY "Usuários podem criar negociações" ON public.negociacoes FOR INSERT WITH CHECK (auth.uid() = owner_id);
CREATE POLICY "Proprietários podem atualizar suas negociações" ON public.negociacoes FOR UPDATE USING (auth.uid() = cliente_proprietario_id OR auth.uid() = cliente_ofertante_id);
CREATE POLICY "Admins podem atualizar todas as negociações" ON public.negociacoes FOR UPDATE USING (has_role(auth.uid(), 'admin'));
CREATE POLICY "Usuários podem deletar negociações que criaram" ON public.negociacoes FOR DELETE USING (auth.uid() = owner_id);
CREATE POLICY "Admins podem deletar todas as negociações" ON public.negociacoes FOR DELETE USING (has_role(auth.uid(), 'admin'));

-- ── Condominios ──
CREATE POLICY "Users can view all condominios" ON public.condominios FOR SELECT TO authenticated USING (true);
CREATE POLICY "Users can insert their own condominios" ON public.condominios FOR INSERT TO authenticated WITH CHECK (auth.uid() = owner_id);
CREATE POLICY "Users can update their own condominios" ON public.condominios FOR UPDATE TO authenticated USING (auth.uid() = owner_id);
CREATE POLICY "Users can delete their own condominios" ON public.condominios FOR DELETE TO authenticated USING (auth.uid() = owner_id);

-- ── Matches ──
CREATE POLICY "Authenticated users can view matches" ON public.matches FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can update match status" ON public.matches FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated users can insert matches" ON public.matches FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated users can delete matches" ON public.matches FOR DELETE TO authenticated USING (true);

-- ── Ativos ──
CREATE POLICY "Users can view all active ativos" ON public.ativos FOR SELECT TO authenticated USING (true);
CREATE POLICY "Users can insert their own ativos" ON public.ativos FOR INSERT TO authenticated WITH CHECK (auth.uid() = owner_id);
CREATE POLICY "Users can update their own ativos" ON public.ativos FOR UPDATE TO authenticated USING (auth.uid() = owner_id);
CREATE POLICY "Users can delete their own ativos" ON public.ativos FOR DELETE TO authenticated USING (auth.uid() = owner_id);

-- ─────────────────────────────────────────────────────────────────────
-- 8. BUSINESS LOGIC FUNCTIONS
-- ─────────────────────────────────────────────────────────────────────

-- NOTE: has_role() is defined in section 5b (right after user_roles table)

-- Auth: Create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
BEGIN
  INSERT INTO public.profiles (id, nome, email, telefone)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'nome', NEW.email),
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'telefone', '')
  );
  RETURN NEW;
END;
$$;

-- Auth: Assign default corretor role on signup
CREATE OR REPLACE FUNCTION public.assign_default_corretor_role()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO public.user_roles (user_id, role)
  VALUES (NEW.id, 'corretor')
  ON CONFLICT (user_id, role) DO NOTHING;
  RETURN NEW;
END;
$$;

-- Period helpers
CREATE OR REPLACE FUNCTION public.get_period_key(tipo_meta tipo_meta, data_ref date)
RETURNS TEXT LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public
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

CREATE OR REPLACE FUNCTION public.period_end_date(tipo_meta tipo_meta, data_ref date)
RETURNS DATE LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public
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
CREATE OR REPLACE FUNCTION public.dias_uteis_mes(p_data_ref date)
RETURNS integer LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'public'
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

CREATE OR REPLACE FUNCTION public.semanas_mes(p_data_ref date)
RETURNS numeric LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'public'
AS $$
DECLARE v_dias INTEGER;
BEGIN
  v_dias := EXTRACT(DAY FROM (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE);
  RETURN ROUND(v_dias::numeric / 7, 2);
END;
$$;

CREATE OR REPLACE FUNCTION public.dias_uteis_restantes_semana(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'public'
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

CREATE OR REPLACE FUNCTION public.dias_uteis_totais_semana(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'public'
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

CREATE OR REPLACE FUNCTION public.dias_uteis_restantes_mes(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'public'
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

CREATE OR REPLACE FUNCTION public.dias_uteis_totais_mes(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'public'
AS $$ BEGIN RETURN dias_uteis_mes(p_data_ref); END; $$;

CREATE OR REPLACE FUNCTION public.dias_uteis_restantes_ano(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'public'
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

CREATE OR REPLACE FUNCTION public.dias_uteis_totais_ano(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'public'
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

CREATE OR REPLACE FUNCTION public.calcular_meta_proporcional(p_meta_mensal INTEGER, p_tipo tipo_meta, p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'public'
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
CREATE OR REPLACE FUNCTION public.ensure_scaffold_meta(
  p_usuario_id uuid, p_tipo tipo_meta, p_categoria categoria_meta, p_data_ref date
)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
DECLARE v_data_prazo DATE; v_meta_id TEXT;
BEGIN
  IF p_usuario_id != auth.uid() AND NOT has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: não é possível acessar metas para outros usuários';
  END IF;
  v_data_prazo := period_end_date(p_tipo, p_data_ref);
  SELECT id INTO v_meta_id FROM public.metas
  WHERE usuario_id = p_usuario_id AND tipo = p_tipo AND categoria = p_categoria AND data_prazo = v_data_prazo
  ORDER BY created_at DESC LIMIT 1;
  RETURN v_meta_id;
END;
$$;

-- Rollup metas (aggregation with São Paulo timezone)
CREATE OR REPLACE FUNCTION public.rollup_metas(p_usuario_id uuid, p_categoria categoria_meta, p_data_ref date)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
DECLARE
  v_periodo_inicio DATE; v_periodo_fim DATE;
  v_real_bruta INTEGER; v_pretendida INTEGER; v_carry_in_prev INTEGER;
  v_acumulado INTEGER; v_real_cap INTEGER; v_carry_out_calc INTEGER;
  v_status status_meta; v_meta_id TEXT; v_data_prazo DATE; v_prev_data_prazo DATE;
  v_meta_mensal INTEGER; v_semanas NUMERIC; v_hoje DATE;
BEGIN
  IF p_usuario_id != auth.uid() AND NOT has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado';
  END IF;
  v_hoje := current_date_sao_paulo();
  SELECT meta_pretendida INTO v_meta_mensal FROM public.metas_config
  WHERE usuario_id = p_usuario_id AND tipo = 'mensal' AND categoria = p_categoria AND ativo = true LIMIT 1;
  v_meta_mensal := COALESCE(v_meta_mensal, 0);

  -- Weekly
  v_data_prazo := period_end_date('semanal', p_data_ref);
  v_periodo_inicio := v_data_prazo - 6;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := period_end_date('semanal', v_periodo_inicio - 7);
  SELECT carry_out INTO v_carry_in_prev FROM public.metas WHERE usuario_id = p_usuario_id AND tipo = 'semanal' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta FROM public.metas WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria AND data_prazo >= v_periodo_inicio AND data_prazo <= v_periodo_fim;
  v_semanas := semanas_mes(p_data_ref);
  v_pretendida := CASE WHEN v_semanas > 0 THEN CEIL(v_meta_mensal::numeric / v_semanas) ELSE v_meta_mensal END;
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  v_status := CASE WHEN v_real_cap >= v_pretendida THEN 'concluida' WHEN v_hoje > v_data_prazo THEN 'atrasada' ELSE 'no_prazo' END;
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'semanal', p_categoria, p_data_ref);
  IF v_meta_id IS NOT NULL THEN
    UPDATE public.metas SET meta_pretendida = v_pretendida, meta_realizada = v_real_cap, carry_in = v_carry_in_prev, carry_out = v_carry_out_calc, status = v_status, updated_at = NOW() WHERE id = v_meta_id;
  END IF;

  -- Monthly
  v_data_prazo := period_end_date('mensal', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('month', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := period_end_date('mensal', v_periodo_inicio - 1);
  SELECT carry_out INTO v_carry_in_prev FROM public.metas WHERE usuario_id = p_usuario_id AND tipo = 'mensal' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta FROM public.metas WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria AND data_prazo >= v_periodo_inicio AND data_prazo <= v_periodo_fim;
  v_pretendida := v_meta_mensal;
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  v_status := CASE WHEN v_real_cap >= v_pretendida THEN 'concluida' WHEN v_hoje > v_data_prazo THEN 'atrasada' ELSE 'no_prazo' END;
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'mensal', p_categoria, p_data_ref);
  IF v_meta_id IS NOT NULL THEN
    UPDATE public.metas SET meta_pretendida = v_pretendida, meta_realizada = v_real_cap, carry_in = v_carry_in_prev, carry_out = v_carry_out_calc, status = v_status, updated_at = NOW() WHERE id = v_meta_id;
  END IF;

  -- Annual
  v_data_prazo := period_end_date('anual', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('year', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := period_end_date('anual', v_periodo_inicio - 1);
  SELECT carry_out INTO v_carry_in_prev FROM public.metas WHERE usuario_id = p_usuario_id AND tipo = 'anual' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta FROM public.metas WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria AND data_prazo >= v_periodo_inicio AND data_prazo <= v_periodo_fim;
  v_pretendida := v_meta_mensal * 12;
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  v_status := CASE WHEN v_real_cap >= v_pretendida THEN 'concluida' WHEN v_hoje > v_data_prazo THEN 'atrasada' ELSE 'no_prazo' END;
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'anual', p_categoria, p_data_ref);
  IF v_meta_id IS NOT NULL THEN
    UPDATE public.metas SET meta_pretendida = v_pretendida, meta_realizada = v_real_cap, carry_in = v_carry_in_prev, carry_out = v_carry_out_calc, status = v_status, updated_at = NOW() WHERE id = v_meta_id;
  END IF;
END;
$$;

-- Concluir meta agrupada (SP timezone)
CREATE OR REPLACE FUNCTION public.concluir_meta_agrupada(p_meta_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
DECLARE v_meta RECORD; v_no_prazo boolean; v_hoje DATE;
BEGIN
  v_hoje := current_date_sao_paulo();
  SELECT * INTO v_meta FROM public.metas WHERE id = p_meta_id AND tipo IN ('semanal', 'mensal', 'anual') AND usuario_id = auth.uid();
  IF NOT FOUND THEN RETURN jsonb_build_object('success', false, 'error', 'Meta não encontrada ou sem permissão'); END IF;
  IF v_meta.meta_realizada < v_meta.meta_pretendida THEN
    RETURN jsonb_build_object('success', false, 'error', 'Meta não atingida. Realize: ' || v_meta.meta_realizada || '/' || v_meta.meta_pretendida);
  END IF;
  v_no_prazo := (v_hoje <= v_meta.data_prazo);
  UPDATE public.metas SET status = 'concluida', finalizada_em = NOW(), finalizada_no_prazo = v_no_prazo,
    conclusao_prazo = CASE WHEN v_no_prazo THEN 'no_prazo' ELSE 'atrasada' END::public.conclusao_prazo_meta, updated_at = NOW()
  WHERE id = p_meta_id;
  RETURN jsonb_build_object('success', true, 'message', 'Meta concluída com sucesso');
END;
$$;

-- Conclusao prazo trigger function
CREATE OR REPLACE FUNCTION public.set_conclusao_prazo()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
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
CREATE OR REPLACE FUNCTION public.atualizar_status_metas()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
DECLARE v_count INTEGER := 0; v_tmp INTEGER; v_hoje DATE; v_amanha DATE;
BEGIN
  v_hoje := current_date_sao_paulo();
  v_amanha := v_hoje + 1;
  UPDATE public.metas SET dias_restantes = data_prazo - v_hoje, updated_at = NOW() WHERE status NOT IN ('concluida');
  UPDATE public.metas SET status = 'vence_amanha', updated_at = NOW() WHERE data_prazo = v_amanha AND status NOT IN ('concluida') AND status != 'vence_amanha';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  UPDATE public.metas SET status = 'atrasada', updated_at = NOW() WHERE data_prazo < v_hoje AND status NOT IN ('concluida') AND status != 'atrasada';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  UPDATE public.metas SET status = 'no_prazo', updated_at = NOW() WHERE data_prazo > v_amanha AND status NOT IN ('concluida') AND status != 'no_prazo';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  UPDATE public.metas SET status = 'no_prazo', updated_at = NOW() WHERE data_prazo = v_hoje AND status NOT IN ('concluida', 'no_prazo') AND status != 'vence_amanha';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  RETURN jsonb_build_object('success', true, 'metas_atualizadas', v_count, 'timestamp', NOW());
END;
$$;

-- Performance level calculation
CREATE OR REPLACE FUNCTION public.calcular_nivel_performance(p_realizada INTEGER, p_pretendida INTEGER)
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
CREATE OR REPLACE FUNCTION public.atualizar_nivel_performance()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  NEW.nivel_performance := calcular_nivel_performance(COALESCE(NEW.meta_realizada, 0), NEW.meta_pretendida);
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.atualizar_dias_restantes()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN NEW.dias_restantes := NEW.data_prazo - current_date_sao_paulo(); RETURN NEW; END;
$$;

CREATE OR REPLACE FUNCTION public.validar_alteracao_status_meta()
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

CREATE OR REPLACE FUNCTION public.validar_alteracao_nivel_performance()
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

CREATE OR REPLACE FUNCTION public.prevent_date_change_on_daily_metas()
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

CREATE OR REPLACE FUNCTION public.recalcular_metas_on_mensal_change()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
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
CREATE OR REPLACE FUNCTION public.normalize_metas_finalizada_em()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$ BEGIN IF NEW.finalizada_em IS NOT NULL THEN NEW.finalizada_em := normalize_timestamp_sp(NEW.finalizada_em); END IF; RETURN NEW; END; $$;

CREATE OR REPLACE FUNCTION public.normalize_atividades_data_execucao()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$ BEGIN IF NEW.data_execucao IS NOT NULL THEN NEW.data_execucao := normalize_timestamp_sp(NEW.data_execucao); ELSE NEW.data_execucao := now_sao_paulo(); END IF; RETURN NEW; END; $$;

CREATE OR REPLACE FUNCTION public.normalize_profiles_last_activity()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$ BEGIN IF NEW.last_activity_at IS NOT NULL THEN NEW.last_activity_at := normalize_timestamp_sp(NEW.last_activity_at); ELSE NEW.last_activity_at := now_sao_paulo(); END IF; RETURN NEW; END; $$;

CREATE OR REPLACE FUNCTION public.normalize_password_codes_expires()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$ BEGIN IF NEW.expires_at IS NOT NULL THEN NEW.expires_at := normalize_timestamp_sp(NEW.expires_at); END IF; RETURN NEW; END; $$;

-- Inactive users deactivation
CREATE OR REPLACE FUNCTION public.desativar_metas_usuarios_inativos()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
DECLARE v_users INTEGER := 0; v_configs INTEGER := 0;
BEGIN
  IF auth.uid() IS NOT NULL AND NOT has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: apenas administradores';
  END IF;
  WITH inativos AS (SELECT id FROM public.profiles WHERE last_activity_at < NOW() - INTERVAL '20 days')
  UPDATE public.metas_config SET ativo = false, updated_at = NOW()
  WHERE usuario_id IN (SELECT id FROM inativos) AND ativo = true;
  GET DIAGNOSTICS v_configs = ROW_COUNT;
  SELECT COUNT(DISTINCT usuario_id) INTO v_users FROM (SELECT usuario_id FROM public.metas_config WHERE updated_at >= NOW() - INTERVAL '1 minute' AND ativo = false) t;
  RETURN jsonb_build_object('success', true, 'usuarios_afetados', v_users, 'configs_desativadas', v_configs, 'timestamp', NOW());
END;
$$;

-- Expired password codes cleanup
CREATE OR REPLACE FUNCTION public.delete_expired_password_codes()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
AS $$ BEGIN DELETE FROM public.password_request_codes WHERE expires_at < now(); END; $$;

-- Distribuir meta descendente (downward distribution from manual metas)
CREATE OR REPLACE FUNCTION public.distribuir_meta_descendente()
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
        INSERT INTO public.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
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
          INSERT INTO public.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
          VALUES (NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_semanal), v_data_fim, false, NEW.nome, NEW.detalhes);
          v_data_temp := v_data_atual::DATE + ((v_semanas - 1) * 7);
          WHILE v_data_temp <= v_data_fim LOOP
            IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN
              INSERT INTO public.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
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
      SELECT EXISTS(SELECT 1 FROM public.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'anual' AND categoria = NEW.categoria AND data_prazo = (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)) INTO v_existe_meta;
      IF NOT v_existe_meta THEN
        INSERT INTO public.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'anual', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_anual), (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE, false, NEW.nome, NEW.detalhes);
      END IF;
      FOR v_semanas IN 1..CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0) LOOP
        v_data_temp := v_data_atual + ((v_semanas - 1) * 7);
        v_data_fim := LEAST(v_data_temp + 6, (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE);
        v_dias_uteis := 0; v_data_temp := v_data_temp;
        WHILE v_data_temp <= v_data_fim LOOP IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN v_dias_uteis := v_dias_uteis + 1; END IF; v_data_temp := v_data_temp + 1; END LOOP;
        v_meta_diaria := v_meta_semanal / GREATEST(v_dias_uteis, 1);
        INSERT INTO public.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_semanal), v_data_fim, false, NEW.nome, NEW.detalhes);
        v_data_temp := v_data_atual + ((v_semanas - 1) * 7);
        WHILE v_data_temp <= v_data_fim LOOP
          IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN
            INSERT INTO public.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
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
      SELECT EXISTS(SELECT 1 FROM public.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'mensal' AND categoria = NEW.categoria AND data_prazo = (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)) INTO v_existe_meta;
      IF NOT v_existe_meta THEN
        INSERT INTO public.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'mensal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_mensal), (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE, false, NEW.nome, NEW.detalhes);
      END IF;
      v_meta_anual := v_meta_mensal * 12;
      SELECT EXISTS(SELECT 1 FROM public.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'anual' AND categoria = NEW.categoria AND data_prazo = (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)) INTO v_existe_meta;
      IF NOT v_existe_meta THEN
        INSERT INTO public.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'anual', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_anual), (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE, false, NEW.nome, NEW.detalhes);
      END IF;
      v_data_temp := v_data_atual;
      FOR i IN 0..6 LOOP
        IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN
          INSERT INTO public.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
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
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON public.metas FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON public.clientes FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON public.imoveis FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON public.negociacoes FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON public.metas_config FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON public.atividades FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON public.funil_movimentos FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON public.user_actions_log FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON public.perfis_permutas FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON public.imoveis_perfis_permutas FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON public.user_roles FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON public.password_request_codes FOR EACH ROW EXECUTE FUNCTION public.set_timestamps_sp();

-- Updated_at triggers (for tables not covered by set_timestamps_sp)
CREATE TRIGGER update_perfis_permutas_updated_at BEFORE UPDATE ON public.perfis_permutas FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_negociacoes_updated_at BEFORE UPDATE ON public.negociacoes FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_metas_config_updated_at BEFORE UPDATE ON public.metas_config FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Metas-specific triggers
CREATE TRIGGER trg_set_conclusao_prazo BEFORE UPDATE ON public.metas FOR EACH ROW EXECUTE FUNCTION public.set_conclusao_prazo();
CREATE TRIGGER trigger_atualizar_nivel_performance BEFORE INSERT OR UPDATE OF meta_realizada, meta_pretendida ON public.metas FOR EACH ROW EXECUTE FUNCTION public.atualizar_nivel_performance();
CREATE TRIGGER trigger_validar_nivel_performance BEFORE UPDATE ON public.metas FOR EACH ROW EXECUTE FUNCTION public.validar_alteracao_nivel_performance();
CREATE TRIGGER trigger_atualizar_dias_restantes BEFORE INSERT OR UPDATE OF data_prazo ON public.metas FOR EACH ROW EXECUTE FUNCTION public.atualizar_dias_restantes();
CREATE TRIGGER trigger_validar_status_meta BEFORE UPDATE ON public.metas FOR EACH ROW EXECUTE FUNCTION public.validar_alteracao_status_meta();
CREATE TRIGGER prevent_date_change_trigger BEFORE UPDATE ON public.metas FOR EACH ROW EXECUTE FUNCTION public.prevent_date_change_on_daily_metas();
CREATE TRIGGER trigger_recalcular_metas_mensal AFTER UPDATE ON public.metas FOR EACH ROW EXECUTE FUNCTION public.recalcular_metas_on_mensal_change();

-- Timestamp normalization triggers
CREATE TRIGGER normalize_metas_finalizada_em_trigger BEFORE INSERT OR UPDATE ON public.metas FOR EACH ROW EXECUTE FUNCTION public.normalize_metas_finalizada_em();
CREATE TRIGGER normalize_atividades_data_execucao_trigger BEFORE INSERT ON public.atividades FOR EACH ROW EXECUTE FUNCTION public.normalize_atividades_data_execucao();
CREATE TRIGGER normalize_profiles_last_activity_trigger BEFORE INSERT OR UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.normalize_profiles_last_activity();
CREATE TRIGGER normalize_password_codes_expires_trigger BEFORE INSERT ON public.password_request_codes FOR EACH ROW EXECUTE FUNCTION public.normalize_password_codes_expires();

-- ─────────────────────────────────────────────────────────────────────
-- 10. SEED DATA
-- ─────────────────────────────────────────────────────────────────────

INSERT INTO public.status_pagina (nome_pagina, status, tipo_pagina) VALUES
  ('dashboard', 'producao', 'geral'),
  ('metas', 'producao', 'geral'),
  ('usuarios', 'producao', 'administrativa'),
  ('admin', 'producao', 'administrativa'),
  ('funil', 'desenvolvimento', 'geral'),
  ('clientes', 'desenvolvimento', 'geral'),
  ('condominios', 'producao', 'geral')
ON CONFLICT (nome_pagina) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- DONE. Schema is fully set up.
-- ─────────────────────────────────────────────────────────────────────
