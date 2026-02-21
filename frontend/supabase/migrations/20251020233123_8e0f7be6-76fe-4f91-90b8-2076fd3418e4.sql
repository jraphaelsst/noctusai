-- Adicionar colunas para detalhes e discriminar metas criadas manualmente vs automaticamente
ALTER TABLE public.metas 
ADD COLUMN detalhes text,
ADD COLUMN criada_manualmente boolean NOT NULL DEFAULT false;

-- Comentários para documentação
COMMENT ON COLUMN public.metas.detalhes IS 'Descrição detalhada da meta (opcional, principalmente para metas criadas manualmente)';
COMMENT ON COLUMN public.metas.criada_manualmente IS 'Indica se a meta foi criada manualmente pelo usuário (true) ou automaticamente pelo sistema (false)';