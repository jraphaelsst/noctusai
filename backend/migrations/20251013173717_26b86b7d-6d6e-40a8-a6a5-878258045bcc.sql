
-- Corrigir tipo de retorno da função ensure_scaffold_meta
DROP FUNCTION IF EXISTS public.ensure_scaffold_meta(uuid, tipo_meta, categoria_meta, date);

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
  v_meta_pretendida INTEGER;
  v_meta_id TEXT;
  v_id TEXT;
BEGIN
  v_data_prazo := period_end_date(p_tipo, p_data_ref);
  
  -- Verificar se já existe
  SELECT id INTO v_id
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = p_tipo
    AND categoria = p_categoria
    AND data_prazo = v_data_prazo;
    
  IF v_id IS NOT NULL THEN
    RETURN v_id;
  END IF;
  
  -- Obter meta_pretendida da config se for diária
  IF p_tipo = 'diaria' THEN
    SELECT meta_pretendida INTO v_meta_pretendida
    FROM public.metas_config
    WHERE usuario_id = p_usuario_id
      AND tipo = p_tipo
      AND categoria = p_categoria
      AND ativo = true
    LIMIT 1;
    
    v_meta_pretendida := COALESCE(v_meta_pretendida, 1);
  ELSE
    v_meta_pretendida := 0; -- Agregadas são calculadas
  END IF;
  
  -- Criar nova meta
  v_meta_id := generate_meta_id();
  
  INSERT INTO public.metas (
    id, usuario_id, tipo, categoria, 
    meta_pretendida, meta_realizada,
    data_prazo, status
  ) VALUES (
    v_meta_id, p_usuario_id, p_tipo, p_categoria,
    v_meta_pretendida, 0,
    v_data_prazo, 'aberta'
  )
  RETURNING id INTO v_id;
  
  RETURN v_id;
END;
$$;
