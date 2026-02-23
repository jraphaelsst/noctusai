-- Fix search_path for new functions
ALTER FUNCTION dias_uteis_restantes_semana(DATE) SET search_path TO 'public';
ALTER FUNCTION dias_uteis_totais_semana(DATE) SET search_path TO 'public';
ALTER FUNCTION dias_uteis_restantes_mes(DATE) SET search_path TO 'public';
ALTER FUNCTION dias_uteis_totais_mes(DATE) SET search_path TO 'public';
ALTER FUNCTION dias_uteis_restantes_ano(DATE) SET search_path TO 'public';
ALTER FUNCTION dias_uteis_totais_ano(DATE) SET search_path TO 'public';
ALTER FUNCTION calcular_meta_proporcional(INTEGER, tipo_meta, DATE) SET search_path TO 'public';