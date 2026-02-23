-- Concurrency-safe metas ID generation and uniqueness to prevent duplicates during parallel inserts

-- 1) Create a global sequence for metas IDs (safe for concurrent nextval)
CREATE SEQUENCE IF NOT EXISTS public.metas_id_seq;

-- 2) Initialize the sequence to current max numeric part of existing IDs
-- Next nextval() will return max+1
SELECT setval(
  'public.metas_id_seq',
  COALESCE(
    (
      SELECT MAX(CAST(SUBSTRING(id FROM 3) AS INTEGER))
      FROM public.metas
      WHERE id ~ '^MT[0-9]+$'
    ),
    0
  ),
  true
);

-- 3) Replace generate_meta_id() to use the sequence (eliminates race conditions)
CREATE OR REPLACE FUNCTION public.generate_meta_id()
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    next_number INTEGER;
    next_id TEXT;
BEGIN
    next_number := nextval('public.metas_id_seq')::INTEGER;
    IF next_number <= 9999 THEN
        next_id := 'MT' || LPAD(next_number::TEXT, 4, '0');
    ELSE
        next_id := 'MT' || next_number::TEXT;
    END IF;
    RETURN next_id;
END;
$function$;

-- 4) Enforce domain rule: only one meta per (usuario_id, tipo, categoria, data_prazo)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    WHERE t.relname = 'metas' AND c.conname = 'metas_user_tipo_categoria_prazo_uniq'
  ) THEN
    ALTER TABLE public.metas
    ADD CONSTRAINT metas_user_tipo_categoria_prazo_uniq
    UNIQUE (usuario_id, tipo, categoria, data_prazo);
  END IF;
END$$;

-- 5) Make ensure_scaffold_meta idempotent with ON CONFLICT to avoid 409s under concurrency
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
  -- SECURITY: Validate caller owns the user_id or is admin
  IF p_usuario_id != auth.uid() AND NOT has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: não é possível criar metas para outros usuários';
  END IF;
  
  v_data_prazo := period_end_date(p_tipo, p_data_ref);
  
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

  -- Try insert idempotently using unique constraint; return the existing/new id
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