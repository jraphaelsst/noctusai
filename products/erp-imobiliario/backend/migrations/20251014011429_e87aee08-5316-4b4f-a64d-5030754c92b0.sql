-- Permitir que corretores excluam suas próprias metas agregadas (semanal, mensal, anual)

-- Remover política restritiva antiga se existir
DROP POLICY IF EXISTS "Users can delete own aggregated metas" ON public.metas;

-- Criar nova política permitindo corretores deletarem suas próprias metas agregadas
CREATE POLICY "Users can delete own aggregated metas"
ON public.metas
FOR DELETE
USING (
  (auth.uid() = usuario_id) 
  AND (tipo IN ('semanal', 'mensal', 'anual'))
);