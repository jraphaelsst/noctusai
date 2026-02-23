-- Remover políticas de deleção existentes
DROP POLICY IF EXISTS "Users can delete their own metas" ON public.metas;
DROP POLICY IF EXISTS "Admins can delete all metas" ON public.metas;

-- Criar novas políticas de deleção mais restritivas

-- 1. Usuários podem deletar apenas suas próprias metas diárias não concluídas
CREATE POLICY "Users can delete own daily incomplete metas"
ON public.metas
FOR DELETE
USING (
  auth.uid() = usuario_id 
  AND tipo = 'diaria' 
  AND status != 'concluida'
);

-- 2. Apenas admins podem deletar metas concluídas
CREATE POLICY "Admins can delete completed metas"
ON public.metas
FOR DELETE
USING (
  has_role(auth.uid(), 'admin')
  AND status = 'concluida'
);

-- 3. Apenas admins podem deletar metas agregadas (semanal, mensal, anual)
CREATE POLICY "Admins can delete aggregated metas"
ON public.metas
FOR DELETE
USING (
  has_role(auth.uid(), 'admin')
  AND tipo IN ('semanal', 'mensal', 'anual')
);

-- 4. Admins podem deletar qualquer meta diária não concluída
CREATE POLICY "Admins can delete any daily incomplete meta"
ON public.metas
FOR DELETE
USING (
  has_role(auth.uid(), 'admin')
  AND tipo = 'diaria'
  AND status != 'concluida'
);