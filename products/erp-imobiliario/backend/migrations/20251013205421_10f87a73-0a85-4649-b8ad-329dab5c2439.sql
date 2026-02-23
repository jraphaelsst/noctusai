-- Adicionar campo de última atividade na tabela profiles
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Criar índice para melhorar performance das consultas
CREATE INDEX IF NOT EXISTS idx_profiles_last_activity 
ON public.profiles(last_activity_at);

-- Criar função para desativar metas de usuários inativos
CREATE OR REPLACE FUNCTION public.desativar_metas_usuarios_inativos()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
  v_usuarios_afetados INTEGER := 0;
  v_configs_desativadas INTEGER := 0;
BEGIN
  -- Desativar configs de usuários inativos por 20+ dias
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
  
  -- Contar usuários únicos afetados
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
$function$;