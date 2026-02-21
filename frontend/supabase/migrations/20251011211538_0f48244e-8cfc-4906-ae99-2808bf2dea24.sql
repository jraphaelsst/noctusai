-- Criar enum para etapas do funil
CREATE TYPE etapa_funil AS ENUM ('qualificacao', 'visitas', 'proposta', 'negociacao', 'fechado');

-- Criar enum para tipos de atividade
CREATE TYPE tipo_atividade AS ENUM ('ligacao', 'email', 'reuniao', 'whatsapp', 'visita', 'proposta', 'negociacao', 'outro');

-- Tabela de clientes
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

-- Tabela de movimentos no funil
CREATE TABLE public.funil_movimentos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id UUID NOT NULL REFERENCES public.clientes(id) ON DELETE CASCADE,
  de_etapa etapa_funil,
  para_etapa etapa_funil NOT NULL,
  responsavel_id UUID NOT NULL REFERENCES public.profiles(id),
  motivo TEXT,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Tabela de atividades
CREATE TABLE public.atividades (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id UUID NOT NULL REFERENCES public.clientes(id) ON DELETE CASCADE,
  usuario_id UUID NOT NULL REFERENCES public.profiles(id),
  tipo tipo_atividade NOT NULL DEFAULT 'outro',
  descricao TEXT NOT NULL,
  data_execucao TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Índices para performance
CREATE INDEX idx_clientes_etapa_pos ON public.clientes(etapa_atual, kanban_pos);
CREATE INDEX idx_clientes_owner ON public.clientes(usuario_id, arquivado);
CREATE INDEX idx_clientes_busca ON public.clientes USING gin(to_tsvector('portuguese', nome || ' ' || COALESCE(email, '') || ' ' || COALESCE(telefone, '')));
CREATE INDEX idx_funil_movimentos_cliente ON public.funil_movimentos(cliente_id, created_at DESC);
CREATE INDEX idx_atividades_cliente ON public.atividades(cliente_id, created_at DESC);

-- Trigger para updated_at em clientes
CREATE TRIGGER update_clientes_updated_at
BEFORE UPDATE ON public.clientes
FOR EACH ROW
EXECUTE FUNCTION public.update_updated_at_column();

-- Habilitar RLS
ALTER TABLE public.clientes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.funil_movimentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atividades ENABLE ROW LEVEL SECURITY;

-- Políticas RLS para clientes
CREATE POLICY "Usuários podem ver seus próprios clientes"
ON public.clientes
FOR SELECT
TO authenticated
USING (auth.uid() = usuario_id);

CREATE POLICY "Admins podem ver todos os clientes"
ON public.clientes
FOR SELECT
TO authenticated
USING (public.has_role(auth.uid(), 'admin'));

CREATE POLICY "Usuários podem criar seus próprios clientes"
ON public.clientes
FOR INSERT
TO authenticated
WITH CHECK (auth.uid() = usuario_id);

CREATE POLICY "Usuários podem atualizar seus próprios clientes"
ON public.clientes
FOR UPDATE
TO authenticated
USING (auth.uid() = usuario_id);

CREATE POLICY "Admins podem atualizar todos os clientes"
ON public.clientes
FOR UPDATE
TO authenticated
USING (public.has_role(auth.uid(), 'admin'));

CREATE POLICY "Usuários podem deletar seus próprios clientes"
ON public.clientes
FOR DELETE
TO authenticated
USING (auth.uid() = usuario_id);

CREATE POLICY "Admins podem deletar todos os clientes"
ON public.clientes
FOR DELETE
TO authenticated
USING (public.has_role(auth.uid(), 'admin'));

-- Políticas RLS para funil_movimentos
CREATE POLICY "Usuários podem ver movimentos de seus clientes"
ON public.funil_movimentos
FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.clientes
    WHERE clientes.id = funil_movimentos.cliente_id
    AND clientes.usuario_id = auth.uid()
  )
);

CREATE POLICY "Admins podem ver todos os movimentos"
ON public.funil_movimentos
FOR SELECT
TO authenticated
USING (public.has_role(auth.uid(), 'admin'));

CREATE POLICY "Usuários podem criar movimentos para seus clientes"
ON public.funil_movimentos
FOR INSERT
TO authenticated
WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.clientes
    WHERE clientes.id = funil_movimentos.cliente_id
    AND clientes.usuario_id = auth.uid()
  )
  AND responsavel_id = auth.uid()
);

-- Políticas RLS para atividades
CREATE POLICY "Usuários podem ver atividades de seus clientes"
ON public.atividades
FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.clientes
    WHERE clientes.id = atividades.cliente_id
    AND clientes.usuario_id = auth.uid()
  )
);

CREATE POLICY "Admins podem ver todas as atividades"
ON public.atividades
FOR SELECT
TO authenticated
USING (public.has_role(auth.uid(), 'admin'));

CREATE POLICY "Usuários podem criar atividades para seus clientes"
ON public.atividades
FOR INSERT
TO authenticated
WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.clientes
    WHERE clientes.id = atividades.cliente_id
    AND clientes.usuario_id = auth.uid()
  )
  AND usuario_id = auth.uid()
);