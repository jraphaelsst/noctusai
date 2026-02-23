-- Configurar timezone do banco para America/Sao_Paulo
SET timezone = 'America/Sao_Paulo';

-- Criar função helper para obter data atual em São Paulo
CREATE OR REPLACE FUNCTION public.current_date_sao_paulo()
RETURNS DATE
LANGUAGE SQL
STABLE
AS $$
  SELECT (NOW() AT TIME ZONE 'America/Sao_Paulo')::DATE;
$$;

-- Atualizar função atualizar_status_metas para usar timezone de São Paulo
CREATE OR REPLACE FUNCTION public.atualizar_status_metas()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
  v_metas_atualizadas INTEGER := 0;
  v_temp_count INTEGER;
  v_hoje DATE;
  v_amanha DATE;
BEGIN
  -- Usar data de São Paulo
  v_hoje := current_date_sao_paulo();
  v_amanha := v_hoje + 1;
  
  -- Atualizar dias_restantes para todas as metas não concluídas
  UPDATE public.metas
  SET 
    dias_restantes = data_prazo - v_hoje,
    updated_at = NOW()
  WHERE status NOT IN ('concluida');
  
  -- Atualizar metas que vencem amanhã (não concluídas)
  UPDATE public.metas
  SET 
    status = 'vence_amanha',
    updated_at = NOW()
  WHERE 
    data_prazo = v_amanha
    AND status NOT IN ('concluida')
    AND status != 'vence_amanha';
  
  GET DIAGNOSTICS v_temp_count = ROW_COUNT;
  v_metas_atualizadas := v_metas_atualizadas + v_temp_count;
  
  -- Atualizar metas atrasadas (prazo passou e não estão concluídas)
  UPDATE public.metas
  SET 
    status = 'atrasada',
    updated_at = NOW()
  WHERE 
    data_prazo < v_hoje
    AND status NOT IN ('concluida')
    AND status != 'atrasada';
  
  GET DIAGNOSTICS v_temp_count = ROW_COUNT;
  v_metas_atualizadas := v_metas_atualizadas + v_temp_count;
  
  -- Atualizar metas no prazo (prazo futuro além de amanhã e não concluídas)
  UPDATE public.metas
  SET 
    status = 'no_prazo',
    updated_at = NOW()
  WHERE 
    data_prazo > v_amanha
    AND status NOT IN ('concluida')
    AND status != 'no_prazo';
  
  GET DIAGNOSTICS v_temp_count = ROW_COUNT;
  v_metas_atualizadas := v_metas_atualizadas + v_temp_count;
  
  -- Atualizar metas de hoje que ainda não estão marcadas corretamente
  UPDATE public.metas
  SET 
    status = 'no_prazo',
    updated_at = NOW()
  WHERE 
    data_prazo = v_hoje
    AND status NOT IN ('concluida', 'no_prazo')
    AND status != 'vence_amanha';
  
  GET DIAGNOSTICS v_temp_count = ROW_COUNT;
  v_metas_atualizadas := v_metas_atualizadas + v_temp_count;
  
  RETURN jsonb_build_object(
    'success', true,
    'metas_atualizadas', v_metas_atualizadas,
    'timestamp', NOW()
  );
END;
$function$;

-- Atualizar função rollup_metas para usar timezone correto
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
  v_hoje DATE;
BEGIN
  -- SECURITY: Validate caller owns the user_id or is admin
  IF p_usuario_id != auth.uid() AND NOT has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: não é possível processar metas para outros usuários';
  END IF;

  -- Usar data atual de São Paulo
  v_hoje := current_date_sao_paulo();

  -- Fetch monthly meta reference from config
  SELECT meta_pretendida INTO v_meta_mensal
  FROM public.metas_config
  WHERE usuario_id = p_usuario_id
    AND tipo = 'mensal'
    AND categoria = p_categoria
    AND ativo = true
  LIMIT 1;

  v_meta_mensal := COALESCE(v_meta_mensal, 0);

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
  
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
  v_semanas := semanas_mes(p_data_ref);
  IF v_semanas > 0 THEN
    v_pretendida := CEIL(v_meta_mensal::numeric / v_semanas);
  ELSE
    v_pretendida := v_meta_mensal;
  END IF;
  
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  
  IF v_real_cap >= v_pretendida THEN
    v_status := 'concluida';
  ELSIF v_hoje > v_data_prazo THEN
    v_status := 'atrasada';
  ELSE
    v_status := 'no_prazo';
  END IF;
  
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
  
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
  v_pretendida := v_meta_mensal;
  
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  
  IF v_real_cap >= v_pretendida THEN
    v_status := 'concluida';
  ELSIF v_hoje > v_data_prazo THEN
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
  
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
  v_pretendida := v_meta_mensal * 12;
  
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  
  IF v_real_cap >= v_pretendida THEN
    v_status := 'concluida';
  ELSIF v_hoje > v_data_prazo THEN
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

-- Atualizar função concluir_meta_agrupada para usar timezone correto
CREATE OR REPLACE FUNCTION public.concluir_meta_agrupada(p_meta_id text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
  v_meta RECORD;
  v_result jsonb;
  v_no_prazo boolean;
  v_hoje DATE;
BEGIN
  -- Usar data de São Paulo
  v_hoje := current_date_sao_paulo();
  
  -- Buscar a meta
  SELECT * INTO v_meta
  FROM public.metas
  WHERE id = p_meta_id
    AND tipo IN ('semanal', 'mensal', 'anual')
    AND usuario_id = auth.uid();
    
  IF NOT FOUND THEN
    RETURN jsonb_build_object('success', false, 'error', 'Meta não encontrada ou sem permissão');
  END IF;
  
  -- Verificar elegibilidade
  IF v_meta.meta_realizada < v_meta.meta_pretendida THEN
    RETURN jsonb_build_object('success', false, 'error', 'Meta não atingida. Realize: ' || v_meta.meta_realizada || '/' || v_meta.meta_pretendida);
  END IF;
  
  -- Concluir
  v_no_prazo := (v_hoje <= v_meta.data_prazo);
  
  UPDATE public.metas
  SET 
    status = 'concluida',
    finalizada_em = NOW(),
    finalizada_no_prazo = v_no_prazo,
    conclusao_prazo = CASE WHEN v_no_prazo THEN 'no_prazo' ELSE 'atrasada' END::public.conclusao_prazo_meta,
    updated_at = NOW()
  WHERE id = p_meta_id;
  
  RETURN jsonb_build_object('success', true, 'message', 'Meta concluída com sucesso');
END;
$function$;