-- Remover política que permite usuários deletarem metas agrupadas sem restrição de status
DROP POLICY IF EXISTS "Users can delete own aggregated metas" ON public.metas;

-- Recriar política para usuários deletarem apenas metas agrupadas NÃO concluídas
CREATE POLICY "Users can delete own aggregated metas"
ON public.metas
FOR DELETE
USING (
  (auth.uid() = usuario_id) 
  AND (tipo = ANY (ARRAY['semanal'::tipo_meta, 'mensal'::tipo_meta, 'anual'::tipo_meta]))
  AND (status <> 'concluida'::status_meta)
);

-- Garantir que existe política para admins deletarem metas concluídas
DROP POLICY IF EXISTS "Admins can delete completed metas" ON public.metas;

CREATE POLICY "Admins can delete completed metas"
ON public.metas
FOR DELETE
USING (
  has_role(auth.uid(), 'admin'::app_role) 
  AND (status = 'concluida'::status_meta)
);