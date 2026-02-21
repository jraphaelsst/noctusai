-- Renomear coluna corretor_id para usuario_id na tabela metas
ALTER TABLE public.metas 
RENAME COLUMN corretor_id TO usuario_id;

-- Atualizar comentários se existirem
COMMENT ON COLUMN public.metas.usuario_id IS 'ID do usuário responsável pela meta';