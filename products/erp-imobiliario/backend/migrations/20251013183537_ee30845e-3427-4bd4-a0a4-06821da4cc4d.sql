-- Adicionar novos valores ao enum categoria_meta
ALTER TYPE public.categoria_meta ADD VALUE IF NOT EXISTS 'captacao_imoveis';
ALTER TYPE public.categoria_meta ADD VALUE IF NOT EXISTS 'captacao_compradores';
ALTER TYPE public.categoria_meta ADD VALUE IF NOT EXISTS 'atualizacao_imoveis';
ALTER TYPE public.categoria_meta ADD VALUE IF NOT EXISTS 'outro';

-- Adicionar coluna categoria_custom para suportar categorias personalizadas
ALTER TABLE public.metas ADD COLUMN IF NOT EXISTS categoria_custom TEXT;
ALTER TABLE public.metas_config ADD COLUMN IF NOT EXISTS categoria_custom TEXT;

-- Criar índices para melhor performance
CREATE INDEX IF NOT EXISTS idx_metas_categoria_custom ON public.metas(categoria_custom);
CREATE INDEX IF NOT EXISTS idx_metas_config_categoria_custom ON public.metas_config(categoria_custom);