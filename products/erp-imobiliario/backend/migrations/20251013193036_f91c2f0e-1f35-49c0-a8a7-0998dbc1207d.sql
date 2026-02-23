-- Update rollup_metas to derive targets from monthly config instead of summing daily targets
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
  v_meta_mensal INTEGER;
  v_semanas NUMERIC;
BEGIN
  -- Buscar meta mensal de referência nas configurações
  SELECT meta_pretendida INTO v_meta_mensal
  FROM public.metas_config
  WHERE usuario_id = p_usuario_id
    AND tipo = 'mensal'
    AND categoria = p_categoria
    AND ativo = true
  LIMIT 1;

  v_meta_mensal := COALESCE(v_meta_mensal, 0);

  -- Processar Semanal
  v_data_prazo := period_end_date('semanal', p_data_ref);
  v_periodo_inicio := v_data_prazo - 6;
  v_periodo_fim := v_data_prazo;
  
  -- Buscar carry_in da semana anterior
  v_prev_data_prazo := v_periodo_inicio - 7;
  v_prev_data_prazo := period_end_date('semanal', v_prev_data_prazo);
  
  SELECT carry_out INTO v_carry_in_prev
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'semanal'
    AND categoria = p_categoria
    AND data_prazo = v_prev_data_prazo;
    
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  
  -- Somar realizadas das diárias da semana
  SELECT 
    COALESCE(SUM(meta_realizada), 0)
  INTO v_real_bruta
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
  -- Calcular meta semanal a partir da mensal
  v_semanas := semanas_mes(p_data_ref);
  IF v_semanas > 0 THEN
    v_pretendida := CEIL(v_meta_mensal::numeric / v_semanas);
  ELSE
    v_pretendida := v_meta_mensal;
  END IF;
  
  -- Calcular cap e carry
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  
  -- Determinar status
  IF v_real_cap >= v_pretendida THEN
    v_status := 'concluida';
  ELSIF CURRENT_DATE > v_data_prazo THEN
    v_status := 'atrasada';
  ELSE
    v_status := 'no_prazo';
  END IF;
  
  -- Garantir scaffold e atualizar
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'semanal', p_categoria, p_data_ref);
  
  UPDATE public.metas
  SET 
    meta_pretendida = v_pretendida,
    meta_realizada = v_real_cap,
    carry_in = v_carry_in_prev,
    carry_out = v_carry_out_calc,
    status = v_status,
    updated_at = NOW()
  WHERE id = v_meta_id;
  
  -- Processar Mensal
  v_data_prazo := period_end_date('mensal', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('month', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  
  -- Buscar carry_in do mês anterior
  v_prev_data_prazo := v_periodo_inicio - 1;
  v_prev_data_prazo := period_end_date('mensal', v_prev_data_prazo);
  
  SELECT carry_out INTO v_carry_in_prev
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'mensal'
    AND categoria = p_categoria
    AND data_prazo = v_prev_data_prazo;
    
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  
  -- Somar realizadas das diárias do mês
  SELECT 
    COALESCE(SUM(meta_realizada), 0)
  INTO v_real_bruta
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
  -- Meta mensal diretamente da configuração
  v_pretendida := v_meta_mensal;
  
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  
  IF v_real_cap >= v_pretendida THEN
    v_status := 'concluida';
  ELSIF CURRENT_DATE > v_data_prazo THEN
    v_status := 'atrasada';
  ELSE
    v_status := 'no_prazo';
  END IF;
  
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'mensal', p_categoria, p_data_ref);
  
  UPDATE public.metas
  SET 
    meta_pretendida = v_pretendida,
    meta_realizada = v_real_cap,
    carry_in = v_carry_in_prev,
    carry_out = v_carry_out_calc,
    status = v_status,
    updated_at = NOW()
  WHERE id = v_meta_id;
  
  -- Processar Anual
  v_data_prazo := period_end_date('anual', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('year', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  
  -- Buscar carry_in do ano anterior
  v_prev_data_prazo := v_periodo_inicio - 1;
  v_prev_data_prazo := period_end_date('anual', v_prev_data_prazo);
  
  SELECT carry_out INTO v_carry_in_prev
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'anual'
    AND categoria = p_categoria
    AND data_prazo = v_prev_data_prazo;
    
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  
  -- Somar realizadas das diárias do ano
  SELECT 
    COALESCE(SUM(meta_realizada), 0)
  INTO v_real_bruta
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
  -- Meta anual = mensal * 12
  v_pretendida := v_meta_mensal * 12;
  
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  
  IF v_real_cap >= v_pretendida THEN
    v_status := 'concluida';
  ELSIF CURRENT_DATE > v_data_prazo THEN
    v_status := 'atrasada';
  ELSE
    v_status := 'no_prazo';
  END IF;
  
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'anual', p_categoria, p_data_ref);
  
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