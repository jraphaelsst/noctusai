-- Drop existing UPDATE policies for metas
DROP POLICY IF EXISTS "Users can update their own metas" ON public.metas;
DROP POLICY IF EXISTS "Admins can update all metas" ON public.metas;

-- Create new restrictive UPDATE policies
-- Users can only update DAILY metas that are NOT completed
CREATE POLICY "Users can update own daily incomplete metas"
ON public.metas
FOR UPDATE
TO authenticated
USING (
  auth.uid() = usuario_id 
  AND tipo = 'diaria'
  AND status != 'concluida'
)
WITH CHECK (
  auth.uid() = usuario_id 
  AND tipo = 'diaria'
  AND status != 'concluida'
);

-- Admins can update MONTHLY metas only (not weekly or annual aggregated)
CREATE POLICY "Admins can update monthly metas"
ON public.metas
FOR UPDATE
TO authenticated
USING (
  has_role(auth.uid(), 'admin')
  AND tipo = 'mensal'
)
WITH CHECK (
  has_role(auth.uid(), 'admin')
  AND tipo = 'mensal'
);

-- Admins can update daily metas
CREATE POLICY "Admins can update daily metas"
ON public.metas
FOR UPDATE
TO authenticated
USING (
  has_role(auth.uid(), 'admin')
  AND tipo = 'diaria'
)
WITH CHECK (
  has_role(auth.uid(), 'admin')
  AND tipo = 'diaria'
);

-- Create function to recalculate all metas when monthly meta is changed
CREATE OR REPLACE FUNCTION public.recalcular_metas_on_mensal_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  -- Only trigger if it's a monthly meta and meta_pretendida changed
  IF NEW.tipo = 'mensal' AND OLD.meta_pretendida IS DISTINCT FROM NEW.meta_pretendida THEN
    -- Recalculate all metas for this user and category
    PERFORM rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo);
    
    -- Also recalculate previous and next months to update carry values
    PERFORM rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo - INTERVAL '1 month');
    PERFORM rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo + INTERVAL '1 month');
  END IF;
  
  RETURN NEW;
END;
$$;

-- Create trigger for monthly meta changes
DROP TRIGGER IF EXISTS trigger_recalcular_metas_mensal ON public.metas;
CREATE TRIGGER trigger_recalcular_metas_mensal
AFTER UPDATE ON public.metas
FOR EACH ROW
EXECUTE FUNCTION public.recalcular_metas_on_mensal_change();

-- Add comment to explain the policy
COMMENT ON POLICY "Users can update own daily incomplete metas" ON public.metas IS 
'Usuários podem atualizar apenas suas próprias metas diárias não concluídas';

COMMENT ON POLICY "Admins can update monthly metas" ON public.metas IS 
'Administradores podem atualizar metas mensais, o que dispara recálculo automático';

COMMENT ON POLICY "Admins can update daily metas" ON public.metas IS 
'Administradores podem atualizar metas diárias de qualquer usuário';