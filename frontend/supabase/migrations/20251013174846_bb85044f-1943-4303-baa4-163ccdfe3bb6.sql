
-- Remover trigger que impede atualizações em metas agregadas
-- As RLS policies já fornecem proteção adequada
DROP TRIGGER IF EXISTS protect_aggregated_metas_trigger ON public.metas;
DROP FUNCTION IF EXISTS public.protect_aggregated_metas();
