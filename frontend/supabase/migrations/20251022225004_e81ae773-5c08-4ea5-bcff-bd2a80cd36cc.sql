-- Function to distribute aggregated meta to derived (lower-level) metas
CREATE OR REPLACE FUNCTION public.distribuir_meta_descendente()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
  v_dias_uteis INTEGER;
  v_num_semanas NUMERIC;
  v_meta_diaria INTEGER;
  v_meta_semanal INTEGER;
  v_meta_mensal INTEGER;
  v_data_inicio DATE;
  v_data_fim DATE;
  v_data_atual DATE;
  v_dia_semana INTEGER;
  v_primeiro_domingo DATE;
  v_domingo_atual DATE;
  v_primeiro_dia_mes DATE;
  v_mes_atual DATE;
BEGIN
  -- Only process manually created aggregated metas
  IF NEW.criada_manualmente <> true THEN
    RETURN NEW;
  END IF;
  
  -- Only process semanal, mensal, anual types
  IF NEW.tipo NOT IN ('semanal', 'mensal', 'anual') THEN
    RETURN NEW;
  END IF;

  -- Get period boundaries
  v_data_fim := NEW.data_prazo;
  
  CASE NEW.tipo
    WHEN 'anual' THEN
      -- Annual: create monthly, weekly and daily metas for the whole year
      v_data_inicio := DATE_TRUNC('year', v_data_fim)::DATE;
      
      -- Calculate monthly meta (annual / 12)
      v_meta_mensal := CEIL(NEW.meta_pretendida::NUMERIC / 12);
      
      -- Create monthly metas
      v_mes_atual := v_data_inicio;
      WHILE v_mes_atual <= v_data_fim LOOP
        v_primeiro_dia_mes := DATE_TRUNC('month', v_mes_atual)::DATE;
        
        INSERT INTO public.metas (
          usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
          data_prazo, status, criada_manualmente, carry_in, carry_out
        ) VALUES (
          NEW.usuario_id, 'mensal', NEW.categoria, NEW.categoria_custom,
          v_meta_mensal, 0,
          period_end_date('mensal', v_primeiro_dia_mes), 'no_prazo', false, 0, 0
        )
        ON CONFLICT DO NOTHING;
        
        v_mes_atual := v_mes_atual + INTERVAL '1 month';
      END LOOP;
      
      -- For annual, also create weekly and daily for the entire year
      -- Calculate weekly meta (annual / ~52 weeks)
      v_meta_semanal := CEIL(NEW.meta_pretendida::NUMERIC / 52);
      
      -- Find first Sunday of the year
      v_domingo_atual := v_data_inicio;
      v_dia_semana := EXTRACT(ISODOW FROM v_domingo_atual);
      IF v_dia_semana != 7 THEN
        v_domingo_atual := v_domingo_atual + (7 - v_dia_semana);
      END IF;
      
      -- Create weekly metas
      WHILE v_domingo_atual <= v_data_fim LOOP
        INSERT INTO public.metas (
          usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
          data_prazo, status, criada_manualmente, carry_in, carry_out
        ) VALUES (
          NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom,
          v_meta_semanal, 0,
          v_domingo_atual, 'no_prazo', false, 0, 0
        )
        ON CONFLICT DO NOTHING;
        
        v_domingo_atual := v_domingo_atual + INTERVAL '7 days';
      END LOOP;
      
      -- Calculate daily meta (annual / working days in year ~250)
      v_meta_diaria := CEIL(NEW.meta_pretendida::NUMERIC / 250);
      
      -- Create daily metas for all weekdays
      v_data_atual := v_data_inicio;
      WHILE v_data_atual <= v_data_fim LOOP
        v_dia_semana := EXTRACT(ISODOW FROM v_data_atual);
        IF v_dia_semana BETWEEN 1 AND 5 THEN -- Monday to Friday
          INSERT INTO public.metas (
            usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
            data_prazo, status, criada_manualmente, carry_in, carry_out
          ) VALUES (
            NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom,
            v_meta_diaria, 0,
            v_data_atual, 'no_prazo', false, 0, 0
          )
          ON CONFLICT DO NOTHING;
        END IF;
        v_data_atual := v_data_atual + 1;
      END LOOP;
      
    WHEN 'mensal' THEN
      -- Monthly: create weekly and daily metas for the month
      v_data_inicio := DATE_TRUNC('month', v_data_fim)::DATE;
      
      -- Calculate number of weeks and working days
      v_num_semanas := semanas_mes(v_data_fim);
      v_dias_uteis := dias_uteis_mes(v_data_fim);
      
      -- Calculate weekly meta (monthly / weeks in month)
      v_meta_semanal := CEIL(NEW.meta_pretendida::NUMERIC / v_num_semanas);
      
      -- Find first Sunday of the month
      v_domingo_atual := v_data_inicio;
      v_dia_semana := EXTRACT(ISODOW FROM v_domingo_atual);
      IF v_dia_semana != 7 THEN
        v_domingo_atual := v_domingo_atual + (7 - v_dia_semana);
      END IF;
      
      -- Create weekly metas
      WHILE v_domingo_atual <= v_data_fim LOOP
        INSERT INTO public.metas (
          usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
          data_prazo, status, criada_manualmente, carry_in, carry_out
        ) VALUES (
          NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom,
          v_meta_semanal, 0,
          v_domingo_atual, 'no_prazo', false, 0, 0
        )
        ON CONFLICT DO NOTHING;
        
        v_domingo_atual := v_domingo_atual + INTERVAL '7 days';
      END LOOP;
      
      -- Calculate daily meta (monthly / working days)
      v_meta_diaria := CEIL(NEW.meta_pretendida::NUMERIC / v_dias_uteis);
      
      -- Create daily metas for all weekdays in the month
      v_data_atual := v_data_inicio;
      WHILE v_data_atual <= v_data_fim LOOP
        v_dia_semana := EXTRACT(ISODOW FROM v_data_atual);
        IF v_dia_semana BETWEEN 1 AND 5 THEN -- Monday to Friday
          INSERT INTO public.metas (
            usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
            data_prazo, status, criada_manualmente, carry_in, carry_out
          ) VALUES (
            NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom,
            v_meta_diaria, 0,
            v_data_atual, 'no_prazo', false, 0, 0
          )
          ON CONFLICT DO NOTHING;
        END IF;
        v_data_atual := v_data_atual + 1;
      END LOOP;
      
    WHEN 'semanal' THEN
      -- Weekly: create daily metas for the week (Mon-Fri)
      -- Week ends on Sunday (data_prazo), starts on Monday
      v_data_fim := NEW.data_prazo;
      v_data_inicio := v_data_fim - 6; -- 6 days back = Monday
      
      -- Calculate daily meta (weekly / 5 working days)
      v_meta_diaria := CEIL(NEW.meta_pretendida::NUMERIC / 5);
      
      -- Create daily metas for weekdays
      v_data_atual := v_data_inicio;
      WHILE v_data_atual <= v_data_fim LOOP
        v_dia_semana := EXTRACT(ISODOW FROM v_data_atual);
        IF v_dia_semana BETWEEN 1 AND 5 THEN -- Monday to Friday
          INSERT INTO public.metas (
            usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
            data_prazo, status, criada_manualmente, carry_in, carry_out
          ) VALUES (
            NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom,
            v_meta_diaria, 0,
            v_data_atual, 'no_prazo', false, 0, 0
          )
          ON CONFLICT DO NOTHING;
        END IF;
        v_data_atual := v_data_atual + 1;
      END LOOP;
  END CASE;

  RETURN NEW;
END;
$$;

-- Create trigger to execute distribution when aggregated meta is inserted
DROP TRIGGER IF EXISTS trigger_distribuir_descendente ON public.metas;
CREATE TRIGGER trigger_distribuir_descendente
  AFTER INSERT ON public.metas
  FOR EACH ROW
  EXECUTE FUNCTION public.distribuir_meta_descendente();