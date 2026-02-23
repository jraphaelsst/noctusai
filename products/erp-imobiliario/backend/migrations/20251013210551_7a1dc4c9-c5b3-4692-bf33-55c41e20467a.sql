-- =====================================================
-- CRITICAL SECURITY FIXES
-- =====================================================

-- 1. Fix nullable usuario_id in metas table
-- First update any existing NULL values (shouldn't exist but safety first)
UPDATE metas 
SET usuario_id = (SELECT id FROM profiles LIMIT 1) 
WHERE usuario_id IS NULL;

-- Make column NOT NULL
ALTER TABLE metas ALTER COLUMN usuario_id SET NOT NULL;

-- 2. Add input validation to ensure_scaffold_meta function
CREATE OR REPLACE FUNCTION public.ensure_scaffold_meta(
  p_usuario_id uuid, 
  p_tipo tipo_meta, 
  p_categoria categoria_meta, 
  p_data_ref date
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
DECLARE
  v_data_prazo DATE;
  v_meta_pretendida INTEGER;
  v_meta_id TEXT;
  v_id TEXT;
  v_meta_mensal INTEGER;
  v_dias_uteis INTEGER;
  v_semanas NUMERIC;
BEGIN
  -- SECURITY: Validate caller owns the user_id or is admin
  IF p_usuario_id != auth.uid() AND NOT has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: não é possível criar metas para outros usuários';
  END IF;
  
  v_data_prazo := period_end_date(p_tipo, p_data_ref);
  
  -- Check if meta already exists
  SELECT id INTO v_id
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = p_tipo
    AND categoria = p_categoria
    AND data_prazo = v_data_prazo;
    
  IF v_id IS NOT NULL THEN
    RETURN v_id;
  END IF;
  
  -- Get meta_pretendida from MENSAL config
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
  
  -- Create new meta
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

-- 3. Add input validation to rollup_metas function
CREATE OR REPLACE FUNCTION public.rollup_metas(
  p_usuario_id uuid, 
  p_categoria categoria_meta, 
  p_data_ref date
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
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
  -- SECURITY: Validate caller owns the user_id or is admin
  IF p_usuario_id != auth.uid() AND NOT has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: não é possível processar metas para outros usuários';
  END IF;

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
  ELSIF CURRENT_DATE > v_data_prazo THEN
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
$$;

-- 4. Remove corretor SELECT policy on password_request_codes
DROP POLICY IF EXISTS "Only intended corretor can view their codes" ON password_request_codes;

-- Create admin-only SELECT policy
CREATE POLICY "Only admins can view password codes"
ON password_request_codes FOR SELECT
TO authenticated
USING (has_role(auth.uid(), 'admin'));

-- 5. Add admin-only check to desativar_metas_usuarios_inativos
CREATE OR REPLACE FUNCTION public.desativar_metas_usuarios_inativos()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
DECLARE
  v_usuarios_afetados INTEGER := 0;
  v_configs_desativadas INTEGER := 0;
BEGIN
  -- SECURITY: Only admins or service role can execute
  IF auth.uid() IS NOT NULL AND NOT has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: apenas administradores podem executar esta função';
  END IF;

  -- Disable configs for inactive users (20+ days)
  WITH usuarios_inativos AS (
    SELECT id
    FROM public.profiles
    WHERE last_activity_at < NOW() - INTERVAL '20 days'
  )
  UPDATE public.metas_config
  SET 
    ativo = false,
    updated_at = NOW()
  WHERE usuario_id IN (SELECT id FROM usuarios_inativos)
    AND ativo = true
  RETURNING usuario_id;
  
  GET DIAGNOSTICS v_configs_desativadas = ROW_COUNT;
  
  -- Count unique affected users
  SELECT COUNT(DISTINCT usuario_id) INTO v_usuarios_afetados
  FROM (
    SELECT usuario_id 
    FROM public.metas_config 
    WHERE updated_at >= NOW() - INTERVAL '1 minute'
      AND ativo = false
  ) AS recent_updates;
  
  RETURN jsonb_build_object(
    'success', true,
    'usuarios_afetados', v_usuarios_afetados,
    'configs_desativadas', v_configs_desativadas,
    'timestamp', NOW()
  );
END;
$$;