-- Adicionar coluna dias_restantes na tabela metas
ALTER TABLE public.metas
ADD COLUMN dias_restantes INTEGER;

-- Função para calcular dias restantes
CREATE OR REPLACE FUNCTION public.calcular_dias_restantes(p_data_prazo DATE)
RETURNS INTEGER
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
  RETURN p_data_prazo - CURRENT_DATE;
END;
$$;

-- Trigger para atualizar dias_restantes automaticamente
CREATE OR REPLACE FUNCTION public.atualizar_dias_restantes()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  NEW.dias_restantes := calcular_dias_restantes(NEW.data_prazo);
  RETURN NEW;
END;
$$;

CREATE TRIGGER trigger_atualizar_dias_restantes
BEFORE INSERT OR UPDATE OF data_prazo ON public.metas
FOR EACH ROW
EXECUTE FUNCTION public.atualizar_dias_restantes();

-- Atualizar função atualizar_status_metas para incluir dias_restantes
CREATE OR REPLACE FUNCTION public.atualizar_status_metas()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_metas_atualizadas INTEGER := 0;
  v_temp_count INTEGER;
  v_hoje DATE := CURRENT_DATE;
  v_amanha DATE := CURRENT_DATE + 1;
BEGIN
  -- Atualizar dias_restantes para todas as metas não concluídas
  UPDATE public.metas
  SET 
    dias_restantes = calcular_dias_restantes(data_prazo),
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
$$;

-- Atualizar dias_restantes para metas existentes
UPDATE public.metas
SET dias_restantes = calcular_dias_restantes(data_prazo);