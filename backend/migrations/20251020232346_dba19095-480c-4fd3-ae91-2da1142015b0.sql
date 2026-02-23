-- Remover constraint de unicidade para permitir múltiplas metas da mesma categoria/tipo/período
ALTER TABLE public.metas DROP CONSTRAINT IF EXISTS metas_user_tipo_categoria_prazo_uniq;

-- Atualizar função ensure_scaffold_meta para APENAS buscar meta existente, não criar nem atualizar
-- Usada apenas pelo sistema de automação - NÃO cria nova meta, NÃO atualiza meta existente
CREATE OR REPLACE FUNCTION public.ensure_scaffold_meta(
  p_usuario_id uuid, 
  p_tipo tipo_meta, 
  p_categoria categoria_meta, 
  p_data_ref date
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
  v_data_prazo DATE;
  v_meta_id TEXT;
BEGIN
  -- SECURITY: Validate caller owns the user_id or is admin
  IF p_usuario_id != auth.uid() AND NOT has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: não é possível acessar metas para outros usuários';
  END IF;

  -- Compute target due date for the given period from the reference date
  v_data_prazo := period_end_date(p_tipo, p_data_ref);

  -- IMPORTANTE: Apenas buscar meta existente, NÃO criar nova nem atualizar
  -- Se não existir, retorna NULL
  SELECT id INTO v_meta_id
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = p_tipo
    AND categoria = p_categoria
    AND data_prazo = v_data_prazo
  ORDER BY created_at DESC
  LIMIT 1;

  RETURN v_meta_id;
END;
$$;