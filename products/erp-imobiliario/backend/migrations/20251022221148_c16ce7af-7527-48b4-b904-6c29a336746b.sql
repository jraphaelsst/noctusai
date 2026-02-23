-- Secure and accumulate-only rollup_metas
CREATE OR REPLACE FUNCTION public.rollup_metas(p_usuario_id uuid, p_categoria categoria_meta, p_data_ref date)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_periodo_inicio DATE;
  v_periodo_fim DATE;
  v_real_bruta INTEGER;
  v_pretendida INTEGER;
  v_carry_in_prev INTEGER;
  v_status status_meta;
  v_meta_id TEXT;
  v_data_prazo DATE;
  v_prev_data_prazo DATE;
  v_hoje DATE;
  v_curr_pretendida INTEGER;
  v_curr_realizada INTEGER;
  v_curr_carry_in INTEGER;
  v_delta_pretendida INTEGER;
  v_delta_realizada INTEGER;
  v_new_pretendida INTEGER;
  v_new_realizada INTEGER;
  v_new_carry_out INTEGER;
BEGIN
  -- SECURITY: Validate caller owns the user_id or is admin
  IF p_usuario_id != auth.uid() AND NOT has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: não é possível processar metas para outros usuários';
  END IF;

  v_hoje := current_date_sao_paulo();

  -- Process Weekly (semanal)
  v_data_prazo := period_end_date('semanal', p_data_ref);
  v_periodo_inicio := v_data_prazo - 6;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := period_end_date('semanal', v_periodo_inicio - 7);

  SELECT carry_out INTO v_carry_in_prev
  FROM public.metas
  WHERE usuario_id = p_usuario_id AND tipo = 'semanal' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);

  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'semanal', p_categoria, p_data_ref);
  IF v_meta_id IS NULL THEN
    INSERT INTO public.metas (
      usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada, data_prazo, status, criada_manualmente, carry_in, carry_out
    ) VALUES (
      p_usuario_id, 'semanal', p_categoria, NULL, 0, 0, v_data_prazo, 'no_prazo', false, 0, 0
    ) RETURNING id INTO v_meta_id;
  END IF;

  SELECT COALESCE(meta_pretendida,0), COALESCE(meta_realizada,0), COALESCE(carry_in,0)
  INTO v_curr_pretendida, v_curr_realizada, v_curr_carry_in
  FROM public.metas WHERE id = v_meta_id;

  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta
  FROM public.metas
  WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria
    AND data_prazo BETWEEN v_periodo_inicio AND v_periodo_fim;

  SELECT COALESCE(SUM(meta_pretendida), 0) INTO v_pretendida
  FROM public.metas
  WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria
    AND data_prazo BETWEEN v_periodo_inicio AND v_periodo_fim;

  v_delta_pretendida := GREATEST(v_pretendida - v_curr_pretendida, 0);
  v_delta_realizada := GREATEST(LEAST(v_real_bruta + v_carry_in_prev, v_pretendida) - v_curr_realizada, 0);

  v_new_pretendida := v_curr_pretendida + v_delta_pretendida;
  v_new_realizada := v_curr_realizada + v_delta_realizada;
  v_new_carry_out := GREATEST(v_carry_in_prev + v_new_realizada - v_new_pretendida, 0);

  IF v_new_realizada >= v_new_pretendida THEN
    v_status := 'concluida';
  ELSIF v_hoje > v_data_prazo THEN
    v_status := 'atrasada';
  ELSE
    v_status := 'no_prazo';
  END IF;

  UPDATE public.metas
  SET meta_pretendida = v_new_pretendida,
      meta_realizada = v_new_realizada,
      carry_in = v_carry_in_prev,
      carry_out = v_new_carry_out,
      status = v_status,
      updated_at = NOW()
  WHERE id = v_meta_id;

  -- Process Monthly (mensal)
  v_data_prazo := period_end_date('mensal', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('month', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := period_end_date('mensal', (v_periodo_inicio - 1));

  SELECT carry_out INTO v_carry_in_prev
  FROM public.metas
  WHERE usuario_id = p_usuario_id AND tipo = 'mensal' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);

  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'mensal', p_categoria, p_data_ref);
  IF v_meta_id IS NULL THEN
    INSERT INTO public.metas (
      usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada, data_prazo, status, criada_manualmente, carry_in, carry_out
    ) VALUES (
      p_usuario_id, 'mensal', p_categoria, NULL, 0, 0, v_data_prazo, 'no_prazo', false, 0, 0
    ) RETURNING id INTO v_meta_id;
  END IF;

  SELECT COALESCE(meta_pretendida,0), COALESCE(meta_realizada,0), COALESCE(carry_in,0)
  INTO v_curr_pretendida, v_curr_realizada, v_curr_carry_in
  FROM public.metas WHERE id = v_meta_id;

  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta
  FROM public.metas
  WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria
    AND data_prazo BETWEEN v_periodo_inicio AND v_periodo_fim;

  SELECT COALESCE(SUM(meta_pretendida), 0) INTO v_pretendida
  FROM public.metas
  WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria
    AND data_prazo BETWEEN v_periodo_inicio AND v_periodo_fim;

  v_delta_pretendida := GREATEST(v_pretendida - v_curr_pretendida, 0);
  v_delta_realizada := GREATEST(LEAST(v_real_bruta + v_carry_in_prev, v_pretendida) - v_curr_realizada, 0);

  v_new_pretendida := v_curr_pretendida + v_delta_pretendida;
  v_new_realizada := v_curr_realizada + v_delta_realizada;
  v_new_carry_out := GREATEST(v_carry_in_prev + v_new_realizada - v_new_pretendida, 0);

  IF v_new_realizada >= v_new_pretendida THEN
    v_status := 'concluida';
  ELSIF v_hoje > v_data_prazo THEN
    v_status := 'atrasada';
  ELSE
    v_status := 'no_prazo';
  END IF;

  UPDATE public.metas
  SET meta_pretendida = v_new_pretendida,
      meta_realizada = v_new_realizada,
      carry_in = v_carry_in_prev,
      carry_out = v_new_carry_out,
      status = v_status,
      updated_at = NOW()
  WHERE id = v_meta_id;

  -- Process Annual (anual)
  v_data_prazo := period_end_date('anual', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('year', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := period_end_date('anual', (v_periodo_inicio - 1));

  SELECT carry_out INTO v_carry_in_prev
  FROM public.metas
  WHERE usuario_id = p_usuario_id AND tipo = 'anual' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);

  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'anual', p_categoria, p_data_ref);
  IF v_meta_id IS NULL THEN
    INSERT INTO public.metas (
      usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada, data_prazo, status, criada_manualmente, carry_in, carry_out
    ) VALUES (
      p_usuario_id, 'anual', p_categoria, NULL, 0, 0, v_data_prazo, 'no_prazo', false, 0, 0
    ) RETURNING id INTO v_meta_id;
  END IF;

  SELECT COALESCE(meta_pretendida,0), COALESCE(meta_realizada,0), COALESCE(carry_in,0)
  INTO v_curr_pretendida, v_curr_realizada, v_curr_carry_in
  FROM public.metas WHERE id = v_meta_id;

  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta
  FROM public.metas
  WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria
    AND data_prazo BETWEEN v_periodo_inicio AND v_periodo_fim;

  SELECT COALESCE(SUM(meta_pretendida), 0) INTO v_pretendida
  FROM public.metas
  WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria
    AND data_prazo BETWEEN v_periodo_inicio AND v_periodo_fim;

  v_delta_pretendida := GREATEST(v_pretendida - v_curr_pretendida, 0);
  v_delta_realizada := GREATEST(LEAST(v_real_bruta + v_carry_in_prev, v_pretendida) - v_curr_realizada, 0);

  v_new_pretendida := v_curr_pretendida + v_delta_pretendida;
  v_new_realizada := v_curr_realizada + v_delta_realizada;
  v_new_carry_out := GREATEST(v_carry_in_prev + v_new_realizada - v_new_pretendida, 0);

  IF v_new_realizada >= v_new_pretendida THEN
    v_status := 'concluida';
  ELSIF v_hoje > v_data_prazo THEN
    v_status := 'atrasada';
  ELSE
    v_status := 'no_prazo';
  END IF;

  UPDATE public.metas
  SET meta_pretendida = v_new_pretendida,
      meta_realizada = v_new_realizada,
      carry_in = v_carry_in_prev,
      carry_out = v_new_carry_out,
      status = v_status,
      updated_at = NOW()
  WHERE id = v_meta_id;
END;
$$;