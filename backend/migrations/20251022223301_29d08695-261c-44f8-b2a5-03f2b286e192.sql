-- Update trigger function to avoid summing initial targets when aggregated metas already have a preset target
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
  v_data_prazo DATE;
  v_prev_data_prazo DATE;
  v_carry_in_prev INTEGER;
  v_real_bruta INTEGER;
  v_pretendida INTEGER;
  v_new_pretendida INTEGER;
  v_new_realizada INTEGER;
  v_new_carry_out INTEGER;
  v_status status_meta;
BEGIN
  IF NEW.tipo <> 'diaria' THEN
    RETURN NEW;
  END IF;

  -- Calcular deltas (INSERT/UPDATE)
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

  -- Atualizar metas agregadas de forma incremental: semanal, mensal e anual
  FOREACH v_tipo_agg IN ARRAY ARRAY['semanal'::tipo_meta, 'mensal'::tipo_meta, 'anual'::tipo_meta]
  LOOP
    -- Garantir existência da meta agregada do período (buscar; se não houver, criar zerada)
    v_agg_id := ensure_scaffold_meta(NEW.usuario_id, v_tipo_agg, NEW.categoria, v_data_ref);

    IF v_agg_id IS NULL THEN
      INSERT INTO public.metas (
        usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
        data_prazo, status, criada_manualmente, carry_in, carry_out
      ) VALUES (
        NEW.usuario_id, v_tipo_agg, NEW.categoria, NEW.categoria_custom,
        0, 0,
        period_end_date(v_tipo_agg, v_data_ref), 'no_prazo'::status_meta, false, 0, 0
      ) RETURNING id INTO v_agg_id;
    END IF;

    -- Ler estado atual da meta agregada
    SELECT COALESCE(meta_pretendida,0), COALESCE(meta_realizada,0), COALESCE(carry_in,0)
      INTO v_curr_pretendida, v_curr_realizada, v_curr_carry_in
    FROM public.metas WHERE id = v_agg_id;

    -- Regra: NÃO somar delta de meta_pretendida se a meta agregada já possui um alvo inicial (>0)
    -- Isso evita inflar a meta agregada quando ela foi criada previamente com um valor planejado (ex.: via configuração mensal)
    IF v_curr_pretendida > 0 THEN
      v_new_pretendida := v_curr_pretendida; -- preservar alvo existente
    ELSE
      v_new_pretendida := v_curr_pretendida + v_delta_pretendida; -- construir alvo a partir das diárias apenas se estava zerado
    END IF;

    -- Sempre somar progresso realizado incrementalmente a partir das diárias
    v_new_realizada := v_curr_realizada + v_delta_realizada;

    -- Recalcular carry_out com base nos novos valores e carry_in atual
    v_new_carry_out := GREATEST(COALESCE(v_curr_carry_in,0) + v_new_realizada - v_new_pretendida, 0);

    -- Status com base nos novos totais e prazo
    SELECT period_end_date(v_tipo_agg, v_data_ref) INTO v_data_prazo;
    IF v_new_realizada >= v_new_pretendida THEN
      v_status := 'concluida';
    ELSIF v_hoje > v_data_prazo THEN
      v_status := 'atrasada';
    ELSE
      v_status := 'no_prazo';
    END IF;

    UPDATE public.metas
    SET 
      meta_pretendida = v_new_pretendida,
      meta_realizada = v_new_realizada,
      carry_out = v_new_carry_out,
      updated_at = NOW(),
      status = v_status
    WHERE id = v_agg_id;
  END LOOP;

  RETURN NEW;
END;
$$;