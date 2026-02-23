-- Corrigir search_path nas funções criadas
CREATE OR REPLACE FUNCTION public.get_period_key(tipo_meta tipo_meta, data_ref date)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
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

CREATE OR REPLACE FUNCTION public.period_end_date(tipo_meta tipo_meta, data_ref date)
RETURNS DATE
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
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

CREATE OR REPLACE FUNCTION public.protect_aggregated_metas()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
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