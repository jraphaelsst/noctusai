-- Trigger para impedir alteração de data_prazo em metas diárias por não-admins
CREATE OR REPLACE FUNCTION public.prevent_date_change_on_daily_metas()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
BEGIN
  -- Permitir se for admin
  IF public.has_role(auth.uid(), 'admin') THEN
    RETURN NEW;
  END IF;
  
  -- Se for meta diária e a data_prazo mudou, bloquear
  IF OLD.tipo = 'diaria' AND NEW.data_prazo IS DISTINCT FROM OLD.data_prazo THEN
    RAISE EXCEPTION 'Apenas administradores podem alterar a data prazo de metas diárias';
  END IF;
  
  RETURN NEW;
END;
$function$;

-- Criar trigger
DROP TRIGGER IF EXISTS prevent_date_change_trigger ON public.metas;
CREATE TRIGGER prevent_date_change_trigger
  BEFORE UPDATE ON public.metas
  FOR EACH ROW
  EXECUTE FUNCTION public.prevent_date_change_on_daily_metas();