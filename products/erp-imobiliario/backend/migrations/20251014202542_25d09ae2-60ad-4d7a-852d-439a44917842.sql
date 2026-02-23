-- Fix ensure_scaffold_meta to only reuse meta for the SAME period (same data_prazo)
-- instead of reusing any open meta from previous days.
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
AS $function$
DECLARE
  v_data_prazo DATE;
  v_meta_pretendida INTEGER;
  v_meta_id TEXT;
  v_id TEXT;
  v_meta_mensal INTEGER;
  v_dias_uteis INTEGER;
  v_semanas NUMERIC;
  v_meta_existente TEXT;
BEGIN
  -- SECURITY: Validate caller owns the user_id or is admin
  IF p_usuario_id != auth.uid() AND NOT has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: não é possível criar metas para outros usuários';
  END IF;

  -- Compute target due date for the given period from the reference date
  v_data_prazo := period_end_date(p_tipo, p_data_ref);

  -- Reuse meta only if there is already one for the SAME data_prazo (same period)
  SELECT id INTO v_meta_existente
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = p_tipo
    AND categoria = p_categoria
    AND data_prazo = v_data_prazo
  LIMIT 1;

  IF v_meta_existente IS NOT NULL THEN
    RETURN v_meta_existente;
  END IF;

  -- Calculate meta_pretendida from monthly config
  SELECT meta_pretendida INTO v_meta_mensal
  FROM public.metas_config
  WHERE usuario_id = p_usuario_id
    AND tipo = 'mensal'
    AND categoria = p_categoria
    AND ativo = true
  LIMIT 1;

  v_meta_mensal := COALESCE(v_meta_mensal, 0);

  -- Calculate meta_pretendida based on type
  IF p_tipo = 'diaria' THEN
    v_dias_uteis := dias_uteis_mes(p_data_ref);
    IF v_dias_uteis > 0 THEN
      v_meta_pretendida := CEIL(v_meta_mensal::numeric / v_dias_uteis);
    ELSE
      v_meta_pretendida := v_meta_mensal;
    END IF;
  ELSIF p_tipo = 'semanal' THEN
    v_semanas := semanas_mes(p_data_ref);
    IF v_semanas > 0 THEN
      v_meta_pretendida := CEIL(v_meta_mensal::numeric / v_semanas);
    ELSE
      v_meta_pretendida := v_meta_mensal;
    END IF;
  ELSIF p_tipo = 'mensal' THEN
    v_meta_pretendida := v_meta_mensal;
  ELSIF p_tipo = 'anual' THEN
    v_meta_pretendida := v_meta_mensal * 12;
  ELSE
    v_meta_pretendida := 0;
  END IF;

  -- Insert idempotently using unique constraint (user, tipo, categoria, data_prazo)
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
  ON CONFLICT ON CONSTRAINT metas_user_tipo_categoria_prazo_uniq
  DO UPDATE SET updated_at = NOW()
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$function$;