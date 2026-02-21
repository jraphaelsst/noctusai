-- Drop existing trigger if exists (to recreate)
DROP TRIGGER IF EXISTS trigger_atualizar_nivel_performance ON public.metas;

-- Recreate the trigger function to ensure it's up to date
CREATE OR REPLACE FUNCTION public.atualizar_nivel_performance()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  -- Calcular e definir o nível de performance automaticamente sempre que meta_realizada ou meta_pretendida mudar
  NEW.nivel_performance := calcular_nivel_performance(
    COALESCE(NEW.meta_realizada, 0),
    NEW.meta_pretendida
  );
  
  RETURN NEW;
END;
$$;

-- Create the trigger to execute BEFORE INSERT OR UPDATE
CREATE TRIGGER trigger_atualizar_nivel_performance
  BEFORE INSERT OR UPDATE OF meta_realizada, meta_pretendida
  ON public.metas
  FOR EACH ROW
  EXECUTE FUNCTION public.atualizar_nivel_performance();

-- Also ensure the validation trigger exists to prevent manual changes
DROP TRIGGER IF EXISTS trigger_validar_nivel_performance ON public.metas;

CREATE TRIGGER trigger_validar_nivel_performance
  BEFORE UPDATE OF nivel_performance
  ON public.metas
  FOR EACH ROW
  EXECUTE FUNCTION public.validar_alteracao_nivel_performance();