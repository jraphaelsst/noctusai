-- Modificar rollup_metas para SOMAR valores incrementalmente ao invés de substituir
CREATE OR REPLACE FUNCTION public.rollup_metas(p_usuario_id uuid, p_categoria categoria_meta, p_data_ref date)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
  v_record RECORD;
  v_periodo_inicio DATE;
  v_periodo_fim DATE;
  v_real_bruta INTEGER;
  v_pretendida INTEGER;
  v_carry_in_prev INTEGER;
  v_acumulado INTEGER;
  v_real_cap INTEGER;
  v_carry_out_calc INTEGER;
  v_status status_meta;
  v_meta_id TEXT;
  v_data_prazo DATE;
  v_prev_data_prazo DATE;
  v_hoje DATE;
  v_meta_realizada_atual INTEGER;
BEGIN
  -- SECURITY: Validate caller owns the user_id or is admin
  IF p_usuario_id != auth.uid() AND NOT has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: não é possível processar metas para outros usuários';
  END IF;

  -- Usar data atual de São Paulo
  v_hoje := current_date_sao_paulo();

  -- Process Weekly
  v_data_prazo := period_end_date('semanal', p_data_ref);
  v_periodo_inicio := v_data_prazo - 6;
  v_periodo_fim := v_data_prazo;
  
  v_prev_data_prazo := v_periodo_inicio - 7;
  v_prev_data_prazo := period_end_date('semanal', v_prev_data_prazo);
  
  SELECT carry_out INTO v_carry_in_prev
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'semanal'
    AND categoria = p_categoria
    AND data_prazo = v_prev_data_prazo;
    
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  
  -- Buscar meta_realizada atual da meta semanal
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'semanal', p_categoria, p_data_ref);
  
  SELECT COALESCE(meta_realizada, 0) INTO v_meta_realizada_atual
  FROM public.metas
  WHERE id = v_meta_id;
  
  -- Somar meta_realizada das metas diárias
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
  -- Somar meta_pretendida das metas diárias
  SELECT COALESCE(SUM(meta_pretendida), 0) INTO v_pretendida
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
  -- SOMAR com valor pré-existente
  v_acumulado := v_real_bruta + v_meta_realizada_atual + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  
  IF v_real_cap >= v_pretendida THEN
    v_status := 'concluida';
  ELSIF v_hoje > v_data_prazo THEN
    v_status := 'atrasada';
  ELSE
    v_status := 'no_prazo';
  END IF;
  
  UPDATE public.metas
  SET 
    meta_pretendida = v_pretendida,
    meta_realizada = v_real_cap,
    carry_in = v_carry_in_prev,
    carry_out = v_carry_out_calc,
    status = v_status,
    updated_at = NOW()
  WHERE id = v_meta_id;
  
  -- Process Monthly
  v_data_prazo := period_end_date('mensal', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('month', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  
  v_prev_data_prazo := v_periodo_inicio - 1;
  v_prev_data_prazo := period_end_date('mensal', v_prev_data_prazo);
  
  SELECT carry_out INTO v_carry_in_prev
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'mensal'
    AND categoria = p_categoria
    AND data_prazo = v_prev_data_prazo;
    
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  
  -- Buscar meta_realizada atual da meta mensal
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'mensal', p_categoria, p_data_ref);
  
  SELECT COALESCE(meta_realizada, 0) INTO v_meta_realizada_atual
  FROM public.metas
  WHERE id = v_meta_id;
  
  -- Somar meta_realizada das metas diárias
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
  -- Somar meta_pretendida das metas diárias
  SELECT COALESCE(SUM(meta_pretendida), 0) INTO v_pretendida
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
  -- SOMAR com valor pré-existente
  v_acumulado := v_real_bruta + v_meta_realizada_atual + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  
  IF v_real_cap >= v_pretendida THEN
    v_status := 'concluida';
  ELSIF v_hoje > v_data_prazo THEN
    v_status := 'atrasada';
  ELSE
    v_status := 'no_prazo';
  END IF;
  
  UPDATE public.metas
  SET 
    meta_pretendida = v_pretendida,
    meta_realizada = v_real_cap,
    carry_in = v_carry_in_prev,
    carry_out = v_carry_out_calc,
    status = v_status,
    updated_at = NOW()
  WHERE id = v_meta_id;
  
  -- Process Annual
  v_data_prazo := period_end_date('anual', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('year', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  
  v_prev_data_prazo := v_periodo_inicio - 1;
  v_prev_data_prazo := period_end_date('anual', v_prev_data_prazo);
  
  SELECT carry_out INTO v_carry_in_prev
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'anual'
    AND categoria = p_categoria
    AND data_prazo = v_prev_data_prazo;
    
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  
  -- Buscar meta_realizada atual da meta anual
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'anual', p_categoria, p_data_ref);
  
  SELECT COALESCE(meta_realizada, 0) INTO v_meta_realizada_atual
  FROM public.metas
  WHERE id = v_meta_id;
  
  -- Somar meta_realizada das metas diárias
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
  -- Somar meta_pretendida das metas diárias
  SELECT COALESCE(SUM(meta_pretendida), 0) INTO v_pretendida
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
  -- SOMAR com valor pré-existente
  v_acumulado := v_real_bruta + v_meta_realizada_atual + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  
  IF v_real_cap >= v_pretendida THEN
    v_status := 'concluida';
  ELSIF v_hoje > v_data_prazo THEN
    v_status := 'atrasada';
  ELSE
    v_status := 'no_prazo';
  END IF;
  
  UPDATE public.metas
  SET 
    meta_pretendida = v_pretendida,
    meta_realizada = v_real_cap,
    carry_in = v_carry_in_prev,
    carry_out = v_carry_out_calc,
    status = v_status,
    updated_at = NOW()
  WHERE id = v_meta_id;
END;
$function$;