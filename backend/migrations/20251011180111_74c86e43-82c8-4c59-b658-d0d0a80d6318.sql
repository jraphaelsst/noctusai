-- Adicionar campos carry_in e carry_out às metas
ALTER TABLE public.metas 
ADD COLUMN IF NOT EXISTS carry_in INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS carry_out INTEGER NOT NULL DEFAULT 0;

-- Criar índices para melhor performance
CREATE INDEX IF NOT EXISTS idx_metas_usuario_tipo_data 
ON public.metas(usuario_id, tipo, data_prazo);

CREATE INDEX IF NOT EXISTS idx_metas_usuario_tipo_categoria_data 
ON public.metas(usuario_id, tipo, categoria, data_prazo);

-- Função para obter chave do período
CREATE OR REPLACE FUNCTION public.get_period_key(tipo_meta tipo_meta, data_ref date)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  CASE tipo_meta
    WHEN 'diaria' THEN
      RETURN TO_CHAR(data_ref, 'YYYY-MM-DD');
    WHEN 'semanal' THEN
      RETURN TO_CHAR(data_ref, 'IYYY-IW');
    WHEN 'mensal' THEN
      RETURN TO_CHAR(data_ref, 'YYYY-MM');
    WHEN 'anual' THEN
      RETURN TO_CHAR(data_ref, 'YYYY');
  END CASE;
END;
$$;

-- Função para obter data_prazo correta do período
CREATE OR REPLACE FUNCTION public.period_end_date(tipo_meta tipo_meta, data_ref date)
RETURNS DATE
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  CASE tipo_meta
    WHEN 'diaria' THEN
      RETURN data_ref;
    WHEN 'semanal' THEN
      -- Domingo da semana
      RETURN data_ref + (7 - EXTRACT(ISODOW FROM data_ref)::INTEGER);
    WHEN 'mensal' THEN
      -- Último dia do mês
      RETURN (DATE_TRUNC('month', data_ref) + INTERVAL '1 month - 1 day')::DATE;
    WHEN 'anual' THEN
      -- 31 de dezembro
      RETURN (DATE_TRUNC('year', data_ref) + INTERVAL '1 year - 1 day')::DATE;
  END CASE;
END;
$$;

-- Função para garantir existência de scaffold
CREATE OR REPLACE FUNCTION public.ensure_scaffold_meta(
  p_usuario_id uuid,
  p_tipo tipo_meta,
  p_categoria categoria_meta,
  p_data_ref date
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_data_prazo DATE;
  v_meta_pretendida INTEGER;
  v_meta_id TEXT;
  v_id uuid;
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
  
  -- Obter meta_pretendida da config se for diária
  IF p_tipo = 'diaria' THEN
    SELECT meta_pretendida INTO v_meta_pretendida
    FROM public.metas_config
    WHERE usuario_id = p_usuario_id
      AND tipo = p_tipo
      AND categoria = p_categoria
      AND ativo = true
    LIMIT 1;
    
    v_meta_pretendida := COALESCE(v_meta_pretendida, 1);
  ELSE
    v_meta_pretendida := 0; -- Agregadas são calculadas
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
$$;

-- Função principal de rollup com carry-over
CREATE OR REPLACE FUNCTION public.rollup_metas(
  p_usuario_id uuid,
  p_categoria categoria_meta,
  p_data_ref date
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
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
  v_meta_id uuid;
  v_data_prazo DATE;
  v_prev_data_prazo DATE;
BEGIN
  -- Processar Semanal
  v_data_prazo := period_end_date('semanal', p_data_ref);
  v_periodo_inicio := v_data_prazo - 6; -- Domingo - 6 = Segunda
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
  
  -- Somar diárias da semana
  SELECT 
    COALESCE(SUM(meta_realizada), 0),
    COALESCE(SUM(meta_pretendida), 0)
  INTO v_real_bruta, v_pretendida
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
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
  
  -- Somar diárias do mês
  SELECT 
    COALESCE(SUM(meta_realizada), 0),
    COALESCE(SUM(meta_pretendida), 0)
  INTO v_real_bruta, v_pretendida
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
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
  
  -- Somar diárias do ano
  SELECT 
    COALESCE(SUM(meta_realizada), 0),
    COALESCE(SUM(meta_pretendida), 0)
  INTO v_real_bruta, v_pretendida
  FROM public.metas
  WHERE usuario_id = p_usuario_id
    AND tipo = 'diaria'
    AND categoria = p_categoria
    AND data_prazo >= v_periodo_inicio
    AND data_prazo <= v_periodo_fim;
  
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

-- Trigger para recalcular agregadas quando diária é alterada
CREATE OR REPLACE FUNCTION public.trigger_rollup_on_diaria()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NEW.tipo = 'diaria' THEN
    PERFORM rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo);
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS metas_diaria_on_write ON public.metas;
CREATE TRIGGER metas_diaria_on_write
  AFTER INSERT OR UPDATE ON public.metas
  FOR EACH ROW
  EXECUTE FUNCTION trigger_rollup_on_diaria();

-- Proteção contra edição manual de agregadas
CREATE OR REPLACE FUNCTION public.protect_aggregated_metas()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.tipo IN ('semanal', 'mensal', 'anual') THEN
    -- Apenas service role pode editar via funções
    IF current_setting('request.jwt.claims', true)::jsonb->>'role' != 'service_role' THEN
      -- Bloquear mudanças em campos calculados
      IF OLD.meta_realizada IS DISTINCT FROM NEW.meta_realizada OR
         OLD.meta_pretendida IS DISTINCT FROM NEW.meta_pretendida OR
         OLD.carry_in IS DISTINCT FROM NEW.carry_in OR
         OLD.carry_out IS DISTINCT FROM NEW.carry_out THEN
        RAISE EXCEPTION 'Metas agregadas são read-only. Use as funções apropriadas.';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS protect_aggregated_metas_trigger ON public.metas;
CREATE TRIGGER protect_aggregated_metas_trigger
  BEFORE UPDATE ON public.metas
  FOR EACH ROW
  EXECUTE FUNCTION protect_aggregated_metas();

-- RPC para concluir meta agrupada com segurança
CREATE OR REPLACE FUNCTION public.concluir_meta_agrupada(p_meta_id text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_meta RECORD;
  v_result jsonb;
BEGIN
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
  UPDATE public.metas
  SET 
    status = 'concluida',
    finalizada_em = NOW(),
    finalizada_no_prazo = (CURRENT_DATE <= data_prazo),
    updated_at = NOW()
  WHERE id = p_meta_id;
  
  RETURN jsonb_build_object('success', true, 'message', 'Meta concluída com sucesso');
END;
$$;