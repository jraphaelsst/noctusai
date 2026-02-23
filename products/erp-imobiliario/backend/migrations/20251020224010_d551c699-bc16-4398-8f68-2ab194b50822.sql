-- =====================================================
-- TIMEZONE NORMALIZATION SYSTEM
-- Garante que todas as datas sejam salvas em America/Sao_Paulo
-- =====================================================

-- Função para obter timestamp atual em São Paulo
CREATE OR REPLACE FUNCTION public.now_sao_paulo()
RETURNS TIMESTAMP WITH TIME ZONE
LANGUAGE SQL
STABLE
AS $$
  SELECT NOW() AT TIME ZONE 'America/Sao_Paulo';
$$;

-- Função para normalizar qualquer timestamp para São Paulo
CREATE OR REPLACE FUNCTION public.normalize_timestamp_sp(ts TIMESTAMP WITH TIME ZONE)
RETURNS TIMESTAMP WITH TIME ZONE
LANGUAGE SQL
IMMUTABLE
AS $$
  SELECT ts AT TIME ZONE 'America/Sao_Paulo';
$$;

-- Trigger function para garantir timestamps em SP em created_at/updated_at
CREATE OR REPLACE FUNCTION public.set_timestamps_sp()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
BEGIN
  -- Se for INSERT, definir created_at em SP
  IF TG_OP = 'INSERT' THEN
    NEW.created_at := now_sao_paulo();
    IF TG_TABLE_NAME IN ('clientes', 'imoveis', 'profiles', 'negociacoes', 'metas', 'metas_config') THEN
      NEW.updated_at := now_sao_paulo();
    END IF;
  END IF;
  
  -- Se for UPDATE, atualizar apenas updated_at
  IF TG_OP = 'UPDATE' THEN
    IF TG_TABLE_NAME IN ('clientes', 'imoveis', 'profiles', 'negociacoes', 'metas', 'metas_config') THEN
      NEW.updated_at := now_sao_paulo();
    END IF;
  END IF;
  
  RETURN NEW;
END;
$$;

-- Aplicar triggers em todas as tabelas relevantes
-- Remover triggers existentes de updated_at se houver
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.metas;
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.clientes;
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.imoveis;
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.profiles;
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.negociacoes;
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.metas_config;
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.atividades;
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.funil_movimentos;
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.user_actions_log;
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.perfis_permutas;
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.imoveis_perfis_permutas;
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.user_roles;
DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON public.password_request_codes;

-- Criar novos triggers
CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT OR UPDATE ON public.metas
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT OR UPDATE ON public.clientes
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT OR UPDATE ON public.imoveis
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT OR UPDATE ON public.profiles
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT OR UPDATE ON public.negociacoes
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT OR UPDATE ON public.metas_config
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT ON public.atividades
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT ON public.funil_movimentos
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT ON public.user_actions_log
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT OR UPDATE ON public.perfis_permutas
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT ON public.imoveis_perfis_permutas
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT ON public.user_roles
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT ON public.password_request_codes
  FOR EACH ROW
  EXECUTE FUNCTION public.set_timestamps_sp();

-- Trigger específico para normalizar finalizada_em em metas
CREATE OR REPLACE FUNCTION public.normalize_metas_finalizada_em()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
BEGIN
  -- Normalizar finalizada_em se fornecido
  IF NEW.finalizada_em IS NOT NULL THEN
    NEW.finalizada_em := normalize_timestamp_sp(NEW.finalizada_em);
  END IF;
  
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS normalize_metas_finalizada_em_trigger ON public.metas;
CREATE TRIGGER normalize_metas_finalizada_em_trigger
  BEFORE INSERT OR UPDATE ON public.metas
  FOR EACH ROW
  EXECUTE FUNCTION public.normalize_metas_finalizada_em();

-- Trigger específico para normalizar data_execucao em atividades
CREATE OR REPLACE FUNCTION public.normalize_atividades_data_execucao()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
BEGIN
  -- Normalizar data_execucao se fornecido
  IF NEW.data_execucao IS NOT NULL THEN
    NEW.data_execucao := normalize_timestamp_sp(NEW.data_execucao);
  ELSE
    NEW.data_execucao := now_sao_paulo();
  END IF;
  
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS normalize_atividades_data_execucao_trigger ON public.atividades;
CREATE TRIGGER normalize_atividades_data_execucao_trigger
  BEFORE INSERT ON public.atividades
  FOR EACH ROW
  EXECUTE FUNCTION public.normalize_atividades_data_execucao();

-- Trigger específico para normalizar last_activity_at em profiles
CREATE OR REPLACE FUNCTION public.normalize_profiles_last_activity()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
BEGIN
  -- Normalizar last_activity_at
  IF NEW.last_activity_at IS NOT NULL THEN
    NEW.last_activity_at := normalize_timestamp_sp(NEW.last_activity_at);
  ELSE
    NEW.last_activity_at := now_sao_paulo();
  END IF;
  
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS normalize_profiles_last_activity_trigger ON public.profiles;
CREATE TRIGGER normalize_profiles_last_activity_trigger
  BEFORE INSERT OR UPDATE ON public.profiles
  FOR EACH ROW
  EXECUTE FUNCTION public.normalize_profiles_last_activity();

-- Trigger específico para normalizar expires_at em password_request_codes
CREATE OR REPLACE FUNCTION public.normalize_password_codes_expires()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
BEGIN
  -- Normalizar expires_at
  IF NEW.expires_at IS NOT NULL THEN
    NEW.expires_at := normalize_timestamp_sp(NEW.expires_at);
  END IF;
  
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS normalize_password_codes_expires_trigger ON public.password_request_codes;
CREATE TRIGGER normalize_password_codes_expires_trigger
  BEFORE INSERT ON public.password_request_codes
  FOR EACH ROW
  EXECUTE FUNCTION public.normalize_password_codes_expires();

-- Atualizar função de cálculo de dias_restantes para usar data de SP consistentemente
CREATE OR REPLACE FUNCTION public.calcular_dias_restantes(p_data_prazo date)
RETURNS integer
LANGUAGE plpgsql
IMMUTABLE
AS $function$
BEGIN
  -- Usar a data atual de São Paulo para cálculo
  RETURN p_data_prazo - current_date_sao_paulo();
END;
$function$;

-- Comentários para documentação
COMMENT ON FUNCTION public.now_sao_paulo() IS 'Retorna o timestamp atual no timezone America/Sao_Paulo';
COMMENT ON FUNCTION public.normalize_timestamp_sp(TIMESTAMP WITH TIME ZONE) IS 'Normaliza qualquer timestamp para o timezone America/Sao_Paulo';
COMMENT ON FUNCTION public.set_timestamps_sp() IS 'Trigger function que garante que created_at e updated_at sejam salvos em America/Sao_Paulo';
COMMENT ON FUNCTION public.current_date_sao_paulo() IS 'Retorna a data atual (sem hora) no timezone America/Sao_Paulo';