-- Criar tabela de log de ações dos usuários

-- Tipos de ação possíveis
CREATE TYPE public.tipo_acao AS ENUM (
  'criar',
  'editar',
  'excluir',
  'concluir',
  'arquivar',
  'desarquivar',
  'mover',
  'login',
  'logout'
);

-- Tipos de entidade
CREATE TYPE public.tipo_entidade AS ENUM (
  'meta',
  'cliente',
  'usuario',
  'atividade',
  'config_meta',
  'auth'
);

-- Tabela de logs de ações
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

-- Criar índices para melhor performance nas queries
CREATE INDEX idx_user_actions_log_usuario_id ON public.user_actions_log(usuario_id);
CREATE INDEX idx_user_actions_log_created_at ON public.user_actions_log(created_at DESC);
CREATE INDEX idx_user_actions_log_tipo_acao ON public.user_actions_log(tipo_acao);
CREATE INDEX idx_user_actions_log_tipo_entidade ON public.user_actions_log(tipo_entidade);

-- Enable RLS
ALTER TABLE public.user_actions_log ENABLE ROW LEVEL SECURITY;

-- Políticas RLS
-- Admins podem ver todos os logs
CREATE POLICY "Admins podem ver todos os logs de ações"
ON public.user_actions_log
FOR SELECT
USING (has_role(auth.uid(), 'admin'));

-- Usuários podem ver apenas seus próprios logs
CREATE POLICY "Usuários podem ver seus próprios logs"
ON public.user_actions_log
FOR SELECT
USING (auth.uid() = usuario_id);

-- Todos usuários autenticados podem inserir logs
CREATE POLICY "Usuários podem inserir logs"
ON public.user_actions_log
FOR INSERT
WITH CHECK (auth.uid() = usuario_id);