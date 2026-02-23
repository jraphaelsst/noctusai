-- Criar função que atualiza status das metas considerando "vence amanhã"
CREATE OR REPLACE FUNCTION public.atualizar_status_metas()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
DECLARE
  v_metas_atualizadas INTEGER := 0;
  v_temp_count INTEGER;
  v_hoje DATE := CURRENT_DATE;
  v_amanha DATE := CURRENT_DATE + 1;
BEGIN
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

-- Criar trigger para prevenir alterações manuais do status (exceto por admins ou sistema)
CREATE OR REPLACE FUNCTION public.validar_alteracao_status_meta()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
BEGIN
  -- Permitir se for admin
  IF public.has_role(auth.uid(), 'admin') THEN
    RETURN NEW;
  END IF;
  
  -- Permitir alteração para 'concluida' (conclusão manual)
  IF NEW.status = 'concluida' AND OLD.status != 'concluida' THEN
    RETURN NEW;
  END IF;
  
  -- Bloquear alterações de status diferentes de conclusão por não-admins
  IF OLD.status IS DISTINCT FROM NEW.status AND NEW.status != 'concluida' THEN
    RAISE EXCEPTION 'O status da meta é atualizado automaticamente pelo sistema';
  END IF;
  
  RETURN NEW;
END;
$$;

-- Criar trigger na tabela metas
DROP TRIGGER IF EXISTS trigger_validar_status_meta ON public.metas;
CREATE TRIGGER trigger_validar_status_meta
  BEFORE UPDATE ON public.metas
  FOR EACH ROW
  EXECUTE FUNCTION public.validar_alteracao_status_meta();