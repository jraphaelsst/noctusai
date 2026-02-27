-- =============================================================================
-- Migration 004: MVP Expansion — All Missing Tables
-- =============================================================================
-- Creates 36 tables for existing routers + 6 tables for new features
-- (notifications, WAHA config, Meta API integration).
--
-- Prerequisites: 001_erp_imobiliario.sql, 002_ai_matching.sql applied.
-- All objects are created in the `erp` schema.
-- =============================================================================

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 0: Ensure schema and permissions
-- ─────────────────────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS erp;
GRANT USAGE ON SCHEMA erp TO postgres, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT SELECT ON TABLES TO anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT USAGE, SELECT ON SEQUENCES TO authenticated, service_role;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 1: Helper — reusable timestamp trigger (idempotent)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION erp.set_timestamps_sp()
RETURNS TRIGGER AS $$
DECLARE
  has_updated_at boolean;
BEGIN
  -- Check if the table has an updated_at column
  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = TG_TABLE_SCHEMA
      AND table_name = TG_TABLE_NAME
      AND column_name = 'updated_at'
  ) INTO has_updated_at;

  IF TG_OP = 'INSERT' THEN
    NEW.created_at := COALESCE(NEW.created_at, now() AT TIME ZONE 'America/Sao_Paulo');
    IF has_updated_at THEN
      NEW.updated_at := NEW.created_at;
    END IF;
  ELSIF TG_OP = 'UPDATE' THEN
    IF has_updated_at THEN
      NEW.updated_at := now() AT TIME ZONE 'America/Sao_Paulo';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 2: GROUP A — Sales & Proposals
-- ─────────────────────────────────────────────────────────────────────────────

-- A1: propostas
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

-- A2: contratos
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

-- A3: parcelas_contrato
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 3: GROUP B — Financial
-- ─────────────────────────────────────────────────────────────────────────────

-- B1: lancamentos
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

-- B2: impostos
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

-- B3: extratos_bancarios
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

-- B4: movimentacoes_bancarias
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 4: GROUP C — Commissions
-- ─────────────────────────────────────────────────────────────────────────────

-- C1: comissoes
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

-- C2: comissoes_splits
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 5: GROUP D — Rentals
-- ─────────────────────────────────────────────────────────────────────────────

-- D1: contratos_locacao
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 6: GROUP E — Calendar & Activities
-- ─────────────────────────────────────────────────────────────────────────────

-- E1: eventos
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 7: GROUP F — Documents & Signatures
-- ─────────────────────────────────────────────────────────────────────────────

-- F1: documentos
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

-- F2: document_templates
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

-- F3: assinaturas
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 8: GROUP G — Email & Marketing
-- ─────────────────────────────────────────────────────────────────────────────

-- G1: emails
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

-- G2: email_templates
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

-- G3: campanhas
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

-- G4: envios_email
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 9: GROUP H — WhatsApp
-- ─────────────────────────────────────────────────────────────────────────────

-- H1: whatsapp_messages
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 10: GROUP I — Inspections & Maintenance
-- ─────────────────────────────────────────────────────────────────────────────

-- I1: vistorias
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

-- I2: checkins
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

-- I3: vistorias_rapidas
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

-- I4: ordens_servico
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 11: GROUP J — Insurance
-- ─────────────────────────────────────────────────────────────────────────────

-- J1: seguros
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 12: GROUP K — Credit Analysis
-- ─────────────────────────────────────────────────────────────────────────────

-- K1: analises_credito
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 13: GROUP L — Key Management
-- ─────────────────────────────────────────────────────────────────────────────

-- L1: chaves
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

-- L2: chaves_historico
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 14: GROUP M — Portals & Site
-- ─────────────────────────────────────────────────────────────────────────────

-- M1: portal_acessos
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

-- M2: chamados_portal
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

-- M3: portal_tokens
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

-- M4: site_config
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 15: GROUP N — Portal Support
-- ─────────────────────────────────────────────────────────────────────────────
-- (chamados_portal is already in Section 14)

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 16: GROUP O — Gamification
-- ─────────────────────────────────────────────────────────────────────────────

-- O1: pontuacoes
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

-- O2: conquistas
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 17: GROUP P — Distribution & Branches
-- ─────────────────────────────────────────────────────────────────────────────

-- P1: distribuicao_config
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

-- P2: filiais
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

-- P3: remessas (banking)
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 18: Phase 2 — Notifications
-- ─────────────────────────────────────────────────────────────────────────────

-- N1: notificacoes
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

-- N2: notificacao_preferencias
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 19: Phase 2 — WAHA WhatsApp Config
-- ─────────────────────────────────────────────────────────────────────────────

-- W1: whatsapp_config
CREATE TABLE IF NOT EXISTS erp.whatsapp_config (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL UNIQUE,
  provider text NOT NULL DEFAULT 'meta'
    CHECK (provider IN ('meta','waha')),
  -- Meta Business API settings
  meta_api_token text,
  meta_phone_number_id text,
  meta_api_version text DEFAULT 'v18.0',
  -- WAHA settings
  waha_api_url text,
  waha_api_key text,
  waha_session_name text DEFAULT 'default',
  -- General
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 20: Phase 2 — Meta API (Facebook/Instagram Ads)
-- ─────────────────────────────────────────────────────────────────────────────

-- MA1: meta_config
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

-- MA2: meta_leads
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

-- MA3: meta_campanhas_sync
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

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 21: Add filial_id columns to existing tables
-- ─────────────────────────────────────────────────────────────────────────────

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'erp' AND table_name = 'ativos' AND column_name = 'filial_id'
  ) THEN
    ALTER TABLE erp.ativos ADD COLUMN filial_id uuid;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'erp' AND table_name = 'clientes' AND column_name = 'filial_id'
  ) THEN
    ALTER TABLE erp.clientes ADD COLUMN filial_id uuid;
  END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 22: Indexes
-- ─────────────────────────────────────────────────────────────────────────────

-- Group A indexes
CREATE INDEX IF NOT EXISTS idx_propostas_org ON erp.propostas(org_id);
CREATE INDEX IF NOT EXISTS idx_propostas_cliente ON erp.propostas(cliente_id);
CREATE INDEX IF NOT EXISTS idx_propostas_imovel ON erp.propostas(imovel_id);
CREATE INDEX IF NOT EXISTS idx_propostas_corretor ON erp.propostas(corretor_id);
CREATE INDEX IF NOT EXISTS idx_propostas_status ON erp.propostas(status);

CREATE INDEX IF NOT EXISTS idx_contratos_org ON erp.contratos(org_id);
CREATE INDEX IF NOT EXISTS idx_contratos_cliente ON erp.contratos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_contratos_imovel ON erp.contratos(imovel_id);
CREATE INDEX IF NOT EXISTS idx_contratos_status ON erp.contratos(status);

CREATE INDEX IF NOT EXISTS idx_parcelas_contrato_org ON erp.parcelas_contrato(org_id);
CREATE INDEX IF NOT EXISTS idx_parcelas_contrato_contrato ON erp.parcelas_contrato(contrato_id);
CREATE INDEX IF NOT EXISTS idx_parcelas_contrato_status ON erp.parcelas_contrato(status);

-- Group B indexes
CREATE INDEX IF NOT EXISTS idx_lancamentos_org ON erp.lancamentos(org_id);
CREATE INDEX IF NOT EXISTS idx_lancamentos_tipo ON erp.lancamentos(tipo);
CREATE INDEX IF NOT EXISTS idx_lancamentos_status ON erp.lancamentos(status);
CREATE INDEX IF NOT EXISTS idx_lancamentos_vencimento ON erp.lancamentos(data_vencimento);
CREATE INDEX IF NOT EXISTS idx_lancamentos_cliente ON erp.lancamentos(cliente_id);

CREATE INDEX IF NOT EXISTS idx_impostos_org ON erp.impostos(org_id);
CREATE INDEX IF NOT EXISTS idx_impostos_imovel ON erp.impostos(imovel_id);
CREATE INDEX IF NOT EXISTS idx_impostos_ano ON erp.impostos(ano);
CREATE INDEX IF NOT EXISTS idx_impostos_status ON erp.impostos(status);

CREATE INDEX IF NOT EXISTS idx_extratos_org ON erp.extratos_bancarios(org_id);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_org ON erp.movimentacoes_bancarias(org_id);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_extrato ON erp.movimentacoes_bancarias(extrato_id);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_conciliado ON erp.movimentacoes_bancarias(conciliado);

-- Group C indexes
CREATE INDEX IF NOT EXISTS idx_comissoes_org ON erp.comissoes(org_id);
CREATE INDEX IF NOT EXISTS idx_comissoes_status ON erp.comissoes(status);
CREATE INDEX IF NOT EXISTS idx_comissoes_splits_comissao ON erp.comissoes_splits(comissao_id);
CREATE INDEX IF NOT EXISTS idx_comissoes_splits_corretor ON erp.comissoes_splits(corretor_id);

-- Group D indexes
CREATE INDEX IF NOT EXISTS idx_contratos_locacao_org ON erp.contratos_locacao(org_id);
CREATE INDEX IF NOT EXISTS idx_contratos_locacao_imovel ON erp.contratos_locacao(imovel_id);
CREATE INDEX IF NOT EXISTS idx_contratos_locacao_status ON erp.contratos_locacao(status);
CREATE INDEX IF NOT EXISTS idx_contratos_locacao_locatario ON erp.contratos_locacao(locatario_id);

-- Group E indexes
CREATE INDEX IF NOT EXISTS idx_eventos_org ON erp.eventos(org_id);
CREATE INDEX IF NOT EXISTS idx_eventos_corretor ON erp.eventos(corretor_id);
CREATE INDEX IF NOT EXISTS idx_eventos_data ON erp.eventos(data_inicio);
CREATE INDEX IF NOT EXISTS idx_eventos_status ON erp.eventos(status);
CREATE INDEX IF NOT EXISTS idx_eventos_cliente ON erp.eventos(cliente_id);

-- Group F indexes
CREATE INDEX IF NOT EXISTS idx_documentos_org ON erp.documentos(org_id);
CREATE INDEX IF NOT EXISTS idx_documentos_imovel ON erp.documentos(imovel_id);
CREATE INDEX IF NOT EXISTS idx_documentos_cliente ON erp.documentos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_document_templates_org ON erp.document_templates(org_id);

CREATE INDEX IF NOT EXISTS idx_assinaturas_org ON erp.assinaturas(org_id);
CREATE INDEX IF NOT EXISTS idx_assinaturas_status ON erp.assinaturas(status);
CREATE INDEX IF NOT EXISTS idx_assinaturas_contrato ON erp.assinaturas(contrato_id);

-- Group G indexes
CREATE INDEX IF NOT EXISTS idx_emails_org ON erp.emails(org_id);
CREATE INDEX IF NOT EXISTS idx_emails_cliente ON erp.emails(cliente_id);
CREATE INDEX IF NOT EXISTS idx_emails_status ON erp.emails(status);
CREATE INDEX IF NOT EXISTS idx_email_templates_org ON erp.email_templates(org_id);

CREATE INDEX IF NOT EXISTS idx_campanhas_org ON erp.campanhas(org_id);
CREATE INDEX IF NOT EXISTS idx_campanhas_status ON erp.campanhas(status);
CREATE INDEX IF NOT EXISTS idx_envios_email_campanha ON erp.envios_email(campanha_id);
CREATE INDEX IF NOT EXISTS idx_envios_email_cliente ON erp.envios_email(cliente_id);

-- Group H indexes
CREATE INDEX IF NOT EXISTS idx_whatsapp_org ON erp.whatsapp_messages(org_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_phone ON erp.whatsapp_messages(phone);
CREATE INDEX IF NOT EXISTS idx_whatsapp_cliente ON erp.whatsapp_messages(cliente_id);

-- Group I indexes
CREATE INDEX IF NOT EXISTS idx_vistorias_org ON erp.vistorias(org_id);
CREATE INDEX IF NOT EXISTS idx_vistorias_imovel ON erp.vistorias(imovel_id);
CREATE INDEX IF NOT EXISTS idx_vistorias_status ON erp.vistorias(status);

CREATE INDEX IF NOT EXISTS idx_checkins_org ON erp.checkins(org_id);
CREATE INDEX IF NOT EXISTS idx_checkins_corretor ON erp.checkins(corretor_id);
CREATE INDEX IF NOT EXISTS idx_checkins_imovel ON erp.checkins(imovel_id);

CREATE INDEX IF NOT EXISTS idx_vistorias_rapidas_org ON erp.vistorias_rapidas(org_id);
CREATE INDEX IF NOT EXISTS idx_vistorias_rapidas_imovel ON erp.vistorias_rapidas(imovel_id);

CREATE INDEX IF NOT EXISTS idx_ordens_servico_org ON erp.ordens_servico(org_id);
CREATE INDEX IF NOT EXISTS idx_ordens_servico_imovel ON erp.ordens_servico(imovel_id);
CREATE INDEX IF NOT EXISTS idx_ordens_servico_status ON erp.ordens_servico(status);
CREATE INDEX IF NOT EXISTS idx_ordens_servico_prioridade ON erp.ordens_servico(prioridade);

-- Group J indexes
CREATE INDEX IF NOT EXISTS idx_seguros_org ON erp.seguros(org_id);
CREATE INDEX IF NOT EXISTS idx_seguros_imovel ON erp.seguros(imovel_id);
CREATE INDEX IF NOT EXISTS idx_seguros_status ON erp.seguros(status);
CREATE INDEX IF NOT EXISTS idx_seguros_vencimento ON erp.seguros(data_vencimento);

-- Group K indexes
CREATE INDEX IF NOT EXISTS idx_analises_credito_org ON erp.analises_credito(org_id);
CREATE INDEX IF NOT EXISTS idx_analises_credito_cpf ON erp.analises_credito(cpf);
CREATE INDEX IF NOT EXISTS idx_analises_credito_cliente ON erp.analises_credito(cliente_id);

-- Group L indexes
CREATE INDEX IF NOT EXISTS idx_chaves_org ON erp.chaves(org_id);
CREATE INDEX IF NOT EXISTS idx_chaves_imovel ON erp.chaves(imovel_id);
CREATE INDEX IF NOT EXISTS idx_chaves_status ON erp.chaves(status);
CREATE INDEX IF NOT EXISTS idx_chaves_historico_chave ON erp.chaves_historico(chave_id);

-- Group M indexes
CREATE INDEX IF NOT EXISTS idx_portal_acessos_org ON erp.portal_acessos(org_id);
CREATE INDEX IF NOT EXISTS idx_portal_acessos_cliente ON erp.portal_acessos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_portal_acessos_token ON erp.portal_acessos(token);

CREATE INDEX IF NOT EXISTS idx_chamados_portal_org ON erp.chamados_portal(org_id);
CREATE INDEX IF NOT EXISTS idx_chamados_portal_cliente ON erp.chamados_portal(cliente_id);
CREATE INDEX IF NOT EXISTS idx_chamados_portal_status ON erp.chamados_portal(status);

CREATE INDEX IF NOT EXISTS idx_portal_tokens_org ON erp.portal_tokens(org_id);
CREATE INDEX IF NOT EXISTS idx_portal_tokens_token ON erp.portal_tokens(token);

CREATE INDEX IF NOT EXISTS idx_site_config_slug ON erp.site_config(slug);

-- Group O indexes
CREATE INDEX IF NOT EXISTS idx_pontuacoes_org ON erp.pontuacoes(org_id);
CREATE INDEX IF NOT EXISTS idx_pontuacoes_user ON erp.pontuacoes(user_id);
CREATE INDEX IF NOT EXISTS idx_conquistas_org ON erp.conquistas(org_id);
CREATE INDEX IF NOT EXISTS idx_conquistas_user ON erp.conquistas(user_id);

-- Group P indexes
CREATE INDEX IF NOT EXISTS idx_filiais_org ON erp.filiais(org_id);
CREATE INDEX IF NOT EXISTS idx_filiais_active ON erp.filiais(is_active);
CREATE INDEX IF NOT EXISTS idx_remessas_org ON erp.remessas(org_id);

-- Notification indexes
CREATE INDEX IF NOT EXISTS idx_notificacoes_org ON erp.notificacoes(org_id);
CREATE INDEX IF NOT EXISTS idx_notificacoes_user ON erp.notificacoes(user_id);
CREATE INDEX IF NOT EXISTS idx_notificacoes_read ON erp.notificacoes(is_read);
CREATE INDEX IF NOT EXISTS idx_notificacoes_created ON erp.notificacoes(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notificacao_prefs_user ON erp.notificacao_preferencias(user_id);

-- Meta API indexes
CREATE INDEX IF NOT EXISTS idx_meta_leads_org ON erp.meta_leads(org_id);
CREATE INDEX IF NOT EXISTS idx_meta_leads_lead_id ON erp.meta_leads(lead_id);
CREATE INDEX IF NOT EXISTS idx_meta_leads_importado ON erp.meta_leads(importado);
CREATE INDEX IF NOT EXISTS idx_meta_campanhas_org ON erp.meta_campanhas_sync(org_id);
CREATE INDEX IF NOT EXISTS idx_meta_campanhas_campaign ON erp.meta_campanhas_sync(campaign_id);

-- filial_id on existing tables
CREATE INDEX IF NOT EXISTS idx_ativos_filial ON erp.ativos(filial_id);
CREATE INDEX IF NOT EXISTS idx_clientes_filial ON erp.clientes(filial_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 23: RLS Policies
-- ─────────────────────────────────────────────────────────────────────────────

-- Helper: enable RLS + create org-scoped policies for each table
-- Pattern: authenticated users can CRUD rows where org_id matches their org

DO $$
DECLARE
  tbl text;
BEGIN
  FOR tbl IN SELECT unnest(ARRAY[
    'propostas','contratos','parcelas_contrato',
    'lancamentos','impostos','extratos_bancarios','movimentacoes_bancarias',
    'comissoes','comissoes_splits',
    'contratos_locacao',
    'eventos',
    'documentos','document_templates','assinaturas',
    'emails','email_templates','campanhas','envios_email',
    'whatsapp_messages',
    'vistorias','checkins','vistorias_rapidas','ordens_servico',
    'seguros',
    'analises_credito',
    'chaves','chaves_historico',
    'portal_acessos','chamados_portal','portal_tokens','site_config',
    'pontuacoes','conquistas',
    'distribuicao_config','filiais','remessas',
    'notificacoes','notificacao_preferencias',
    'whatsapp_config','meta_config','meta_leads','meta_campanhas_sync'
  ])
  LOOP
    EXECUTE format('ALTER TABLE erp.%I ENABLE ROW LEVEL SECURITY', tbl);

    -- Select: authenticated users see their org's data
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_select_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR SELECT TO authenticated USING (org_id = (auth.jwt() ->> ''org_id'')::uuid)',
      tbl || '_select_policy', tbl
    );

    -- Insert: authenticated users insert into their org
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_insert_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR INSERT TO authenticated WITH CHECK (org_id = (auth.jwt() ->> ''org_id'')::uuid)',
      tbl || '_insert_policy', tbl
    );

    -- Update: authenticated users update their org's data
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_update_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR UPDATE TO authenticated USING (org_id = (auth.jwt() ->> ''org_id'')::uuid)',
      tbl || '_update_policy', tbl
    );

    -- Delete: authenticated users delete their org's data
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_delete_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR DELETE TO authenticated USING (org_id = (auth.jwt() ->> ''org_id'')::uuid)',
      tbl || '_delete_policy', tbl
    );

    -- Service role: full access (bypasses RLS anyway, but explicit)
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_service_role_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR ALL TO service_role USING (true)',
      tbl || '_service_role_policy', tbl
    );
  END LOOP;
END $$;

-- Special: portal/site public access for anon users (public-facing portals)
DROP POLICY IF EXISTS site_config_anon_read ON erp.site_config;
CREATE POLICY site_config_anon_read ON erp.site_config
  FOR SELECT TO anon USING (is_active = true);

DROP POLICY IF EXISTS portal_tokens_anon_read ON erp.portal_tokens;
CREATE POLICY portal_tokens_anon_read ON erp.portal_tokens
  FOR SELECT TO anon USING (is_active = true AND expires_at > now());

DROP POLICY IF EXISTS portal_acessos_anon_read ON erp.portal_acessos;
CREATE POLICY portal_acessos_anon_read ON erp.portal_acessos
  FOR SELECT TO anon USING (ativo = true);

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 24: Timestamp triggers for tables with updated_at
-- ─────────────────────────────────────────────────────────────────────────────

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
      'CREATE TRIGGER set_timestamps_%I BEFORE INSERT OR UPDATE ON erp.%I FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp()',
      tbl, tbl
    );
  END LOOP;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 25: Final grants on all new objects
-- ─────────────────────────────────────────────────────────────────────────────

GRANT ALL ON ALL TABLES IN SCHEMA erp TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA erp TO authenticated;
GRANT SELECT ON ALL TABLES IN SCHEMA erp TO anon;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA erp TO authenticated, service_role;

COMMIT;
