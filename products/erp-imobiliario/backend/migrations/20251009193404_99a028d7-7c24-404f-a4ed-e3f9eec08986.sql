-- Criar tabela de configurações de metas
CREATE TABLE IF NOT EXISTS public.metas_config (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  usuario_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tipo tipo_meta NOT NULL,
  categoria categoria_meta NOT NULL,
  meta_pretendida integer NOT NULL DEFAULT 0,
  ativo boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  UNIQUE(usuario_id, tipo, categoria)
);

-- Habilitar RLS
ALTER TABLE public.metas_config ENABLE ROW LEVEL SECURITY;

-- Políticas RLS
CREATE POLICY "Usuários podem ver suas próprias configs"
  ON public.metas_config
  FOR SELECT
  USING (auth.uid() = usuario_id);

CREATE POLICY "Usuários podem inserir suas próprias configs"
  ON public.metas_config
  FOR INSERT
  WITH CHECK (auth.uid() = usuario_id);

CREATE POLICY "Usuários podem atualizar suas próprias configs"
  ON public.metas_config
  FOR UPDATE
  USING (auth.uid() = usuario_id);

CREATE POLICY "Usuários podem deletar suas próprias configs"
  ON public.metas_config
  FOR DELETE
  USING (auth.uid() = usuario_id);

CREATE POLICY "Admins podem ver todas as configs"
  ON public.metas_config
  FOR SELECT
  USING (has_role(auth.uid(), 'admin'::app_role));

-- Trigger para updated_at
CREATE TRIGGER update_metas_config_updated_at
  BEFORE UPDATE ON public.metas_config
  FOR EACH ROW
  EXECUTE FUNCTION public.update_updated_at_column();

-- Habilitar extensões necessárias para cron jobs
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;