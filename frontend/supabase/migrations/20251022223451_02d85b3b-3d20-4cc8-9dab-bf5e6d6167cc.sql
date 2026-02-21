-- Disable rollup behavior: make trigger function a no-op so aggregated metas are not updated from daily metas
CREATE OR REPLACE FUNCTION public.trigger_rollup_on_diaria()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
BEGIN
  -- Trigger intentionally disabled per request: do nothing
  RETURN NEW;
END;
$$;