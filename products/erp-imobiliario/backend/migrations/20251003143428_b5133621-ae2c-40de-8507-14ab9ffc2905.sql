-- Criar enum para categorias de meta
CREATE TYPE categoria_meta AS ENUM ('captacao', 'visitas', 'contatos', 'propostas', 'fechamento');

-- Adicionar coluna categoria à tabela metas
ALTER TABLE public.metas 
ADD COLUMN categoria categoria_meta NOT NULL DEFAULT 'captacao';

-- Criar índice para melhor performance nas consultas por categoria
CREATE INDEX idx_metas_categoria ON public.metas(categoria);