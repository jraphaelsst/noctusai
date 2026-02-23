-- Adicionar coluna nome na tabela metas
ALTER TABLE public.metas
ADD COLUMN nome TEXT;

-- Criar índice para busca por nome
CREATE INDEX idx_metas_nome ON public.metas(nome);

COMMENT ON COLUMN public.metas.nome IS 'Nome customizado da meta. Pode ser definido na criação manual ou editado posteriormente.';