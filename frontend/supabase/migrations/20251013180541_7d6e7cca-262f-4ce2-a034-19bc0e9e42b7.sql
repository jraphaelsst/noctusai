-- Funções auxiliares para cálculo de valores proporcionais baseados em config mensal

-- Função para calcular número de dias úteis no mês (seg-sex)
CREATE OR REPLACE FUNCTION public.dias_uteis_mes(p_data_ref date)
RETURNS integer
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
  v_primeiro_dia DATE;
  v_ultimo_dia DATE;
  v_dia_atual DATE;
  v_contador INTEGER := 0;
BEGIN
  v_primeiro_dia := DATE_TRUNC('month', p_data_ref)::DATE;
  v_ultimo_dia := (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE;
  
  v_dia_atual := v_primeiro_dia;
  
  WHILE v_dia_atual <= v_ultimo_dia LOOP
    -- Contar apenas seg-sex (1-5)
    IF EXTRACT(ISODOW FROM v_dia_atual) BETWEEN 1 AND 5 THEN
      v_contador := v_contador + 1;
    END IF;
    v_dia_atual := v_dia_atual + 1;
  END LOOP;
  
  RETURN v_contador;
END;
$function$;

-- Função para calcular número de semanas completas no mês
CREATE OR REPLACE FUNCTION public.semanas_mes(p_data_ref date)
RETURNS numeric
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
  v_dias_mes INTEGER;
BEGIN
  v_dias_mes := EXTRACT(DAY FROM (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE);
  -- Aproximação: dividir dias do mês por 7
  RETURN ROUND(v_dias_mes::numeric / 7, 2);
END;
$function$;

-- Atualizar ensure_scaffold_meta para calcular meta_pretendida baseada em config mensal
CREATE OR REPLACE FUNCTION public.ensure_scaffold_meta(p_usuario_id uuid, p_tipo tipo_meta, p_categoria categoria_meta, p_data_ref date)
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
  
  -- Obter meta_pretendida da config MENSAL
  SELECT meta_pretendida INTO v_meta_mensal
  FROM public.metas_config
  WHERE usuario_id = p_usuario_id
    AND tipo = 'mensal'
    AND categoria = p_categoria
    AND ativo = true
  LIMIT 1;
  
  v_meta_mensal := COALESCE(v_meta_mensal, 0);
  
  -- Calcular meta_pretendida baseado no tipo
  IF p_tipo = 'diaria' THEN
    -- Meta diária = meta mensal / dias úteis do mês
    v_dias_uteis := dias_uteis_mes(p_data_ref);
    IF v_dias_uteis > 0 THEN
      v_meta_pretendida := CEIL(v_meta_mensal::numeric / v_dias_uteis);
    ELSE
      v_meta_pretendida := v_meta_mensal;
    END IF;
  ELSIF p_tipo = 'semanal' THEN
    -- Meta semanal = meta mensal / número de semanas no mês
    v_semanas := semanas_mes(p_data_ref);
    IF v_semanas > 0 THEN
      v_meta_pretendida := CEIL(v_meta_mensal::numeric / v_semanas);
    ELSE
      v_meta_pretendida := v_meta_mensal;
    END IF;
  ELSIF p_tipo = 'mensal' THEN
    v_meta_pretendida := v_meta_mensal;
  ELSIF p_tipo = 'anual' THEN
    -- Meta anual = meta mensal * 12
    v_meta_pretendida := v_meta_mensal * 12;
  ELSE
    v_meta_pretendida := 0;
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
$function$;