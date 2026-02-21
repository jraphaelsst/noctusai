-- Atualizar trigger_rollup_on_diaria para usar cálculo proporcional
CREATE OR REPLACE FUNCTION public.trigger_rollup_on_diaria()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
  v_delta_pretendida INTEGER := 0;
  v_delta_realizada INTEGER := 0;
  v_data_ref DATE;
  v_hoje DATE := current_date_sao_paulo();
  v_agg_id TEXT;
  v_tipo_agg tipo_meta;
  v_curr_pretendida INTEGER;
  v_curr_realizada INTEGER;
  v_curr_carry_in INTEGER;
  v_new_pretendida INTEGER;
  v_new_realizada INTEGER;
  v_new_carry_out INTEGER;
  v_status status_meta;
  v_data_prazo DATE;
  v_config_mensal INTEGER;
  v_initial_pretendida INTEGER;
BEGIN
  -- Only process daily metas
  IF NEW.tipo <> 'diaria' THEN
    RETURN NEW;
  END IF;

  -- Calculate deltas (INSERT/UPDATE)
  IF TG_OP = 'INSERT' THEN
    v_delta_pretendida := COALESCE(NEW.meta_pretendida, 0);
    v_delta_realizada := COALESCE(NEW.meta_realizada, 0);
    v_data_ref := NEW.data_prazo::date;
  ELSIF TG_OP = 'UPDATE' THEN
    v_delta_pretendida := COALESCE(NEW.meta_pretendida, 0) - COALESCE(OLD.meta_pretendida, 0);
    v_delta_realizada := COALESCE(NEW.meta_realizada, 0) - COALESCE(OLD.meta_realizada, 0);
    v_data_ref := NEW.data_prazo::date;
  END IF;

  IF v_delta_pretendida = 0 AND v_delta_realizada = 0 THEN
    RETURN NEW;
  END IF;

  -- Get monthly config for this user and category
  SELECT meta_pretendida INTO v_config_mensal
  FROM metas_config
  WHERE usuario_id = NEW.usuario_id
    AND categoria = NEW.categoria
    AND tipo = 'mensal'
    AND ativo = true
  LIMIT 1;

  -- If no config found, use 0 as fallback
  v_config_mensal := COALESCE(v_config_mensal, 0);

  -- Update aggregated metas incrementally: weekly, monthly and annual
  FOREACH v_tipo_agg IN ARRAY ARRAY['semanal'::tipo_meta, 'mensal'::tipo_meta, 'anual'::tipo_meta]
  LOOP
    -- Ensure aggregated meta exists for the period
    v_agg_id := ensure_scaffold_meta(NEW.usuario_id, v_tipo_agg, NEW.categoria, v_data_ref);

    IF v_agg_id IS NULL THEN
      -- Calculate initial meta_pretendida PROPORCIONAL aos dias restantes
      v_initial_pretendida := calcular_meta_proporcional(v_config_mensal, v_tipo_agg, v_data_ref);

      -- Create aggregated meta with proper meta_pretendida
      INSERT INTO public.metas (
        usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
        data_prazo, status, criada_manualmente, carry_in, carry_out
      ) VALUES (
        NEW.usuario_id, v_tipo_agg, NEW.categoria, NEW.categoria_custom,
        v_initial_pretendida, 0,
        period_end_date(v_tipo_agg, v_data_ref), 'no_prazo'::status_meta, false, 0, 0
      ) RETURNING id INTO v_agg_id;
    END IF;

    -- Read current state of aggregated meta
    SELECT COALESCE(meta_pretendida,0), COALESCE(meta_realizada,0), COALESCE(carry_in,0)
      INTO v_curr_pretendida, v_curr_realizada, v_curr_carry_in
    FROM public.metas WHERE id = v_agg_id;

    -- For INSERT: only update meta_realizada (meta_pretendida already set correctly)
    -- For UPDATE: sum both deltas
    IF TG_OP = 'INSERT' THEN
      v_new_pretendida := v_curr_pretendida; -- Keep existing pretendida
      v_new_realizada := v_curr_realizada + v_delta_realizada;
    ELSE
      v_new_pretendida := v_curr_pretendida + v_delta_pretendida;
      v_new_realizada := v_curr_realizada + v_delta_realizada;
    END IF;

    -- Recalculate carry_out
    v_new_carry_out := GREATEST(COALESCE(v_curr_carry_in,0) + v_new_realizada - v_new_pretendida, 0);

    -- Calculate status based on new totals and deadline
    SELECT period_end_date(v_tipo_agg, v_data_ref) INTO v_data_prazo;
    IF v_new_realizada >= v_new_pretendida THEN
      v_status := 'concluida';
    ELSIF v_hoje > v_data_prazo THEN
      v_status := 'atrasada';
    ELSE
      v_status := 'no_prazo';
    END IF;

    -- Update aggregated meta
    UPDATE public.metas
    SET 
      meta_pretendida = v_new_pretendida,
      meta_realizada = v_new_realizada,
      carry_out = v_new_carry_out,
      status = v_status,
      updated_at = NOW()
    WHERE id = v_agg_id;
  END LOOP;

  RETURN NEW;
END;
$$;