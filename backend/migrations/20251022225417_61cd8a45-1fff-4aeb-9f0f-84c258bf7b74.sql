-- Updated function to distribute aggregated meta creating multiple derived metas with meta_pretendida=1
CREATE OR REPLACE FUNCTION public.distribuir_meta_descendente()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
  v_quantidade_total INTEGER;
  v_dias_uteis INTEGER;
  v_num_semanas INTEGER;
  v_data_inicio DATE;
  v_data_fim DATE;
  v_data_atual DATE;
  v_dia_semana INTEGER;
  v_dias_disponiveis INTEGER;
  v_metas_por_dia INTEGER;
  v_resto INTEGER;
  v_contador INTEGER;
  v_metas_criadas INTEGER;
  v_domingo_atual DATE;
  v_semanas_disponiveis INTEGER;
  v_metas_por_semana INTEGER;
  v_mes_atual DATE;
  v_meses_disponiveis INTEGER;
  v_metas_por_mes INTEGER;
BEGIN
  -- Only process manually created aggregated metas
  IF NEW.criada_manualmente <> true THEN
    RETURN NEW;
  END IF;
  
  -- Only process semanal, mensal, anual types
  IF NEW.tipo NOT IN ('semanal', 'mensal', 'anual') THEN
    RETURN NEW;
  END IF;

  v_quantidade_total := NEW.meta_pretendida;
  v_data_fim := NEW.data_prazo;
  
  CASE NEW.tipo
    WHEN 'anual' THEN
      -- ANNUAL: distribute to monthly, weekly and daily metas
      v_data_inicio := DATE_TRUNC('year', v_data_fim)::DATE;
      
      -- 1. Create MONTHLY metas (quantity_total / 12 months)
      v_meses_disponiveis := 12;
      v_metas_por_mes := v_quantidade_total / v_meses_disponiveis;
      v_resto := v_quantidade_total % v_meses_disponiveis;
      
      v_contador := 0;
      v_mes_atual := v_data_inicio;
      WHILE v_mes_atual <= v_data_fim LOOP
        -- Distribute remainder among first months
        v_metas_criadas := v_metas_por_mes;
        IF v_contador < v_resto THEN
          v_metas_criadas := v_metas_criadas + 1;
        END IF;
        
        -- Create multiple monthly metas for this month
        FOR i IN 1..v_metas_criadas LOOP
          INSERT INTO public.metas (
            usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
            data_prazo, status, criada_manualmente, carry_in, carry_out
          ) VALUES (
            NEW.usuario_id, 'mensal', NEW.categoria, NEW.categoria_custom,
            1, 0,
            period_end_date('mensal', v_mes_atual), 'no_prazo', false, 0, 0
          );
        END LOOP;
        
        v_contador := v_contador + 1;
        v_mes_atual := v_mes_atual + INTERVAL '1 month';
      END LOOP;
      
      -- 2. Create WEEKLY metas (~52 weeks/year)
      v_semanas_disponiveis := 52;
      v_metas_por_semana := v_quantidade_total / v_semanas_disponiveis;
      v_resto := v_quantidade_total % v_semanas_disponiveis;
      
      -- Find first Sunday of the year
      v_domingo_atual := v_data_inicio;
      v_dia_semana := EXTRACT(ISODOW FROM v_domingo_atual);
      IF v_dia_semana != 7 THEN
        v_domingo_atual := v_domingo_atual + (7 - v_dia_semana);
      END IF;
      
      v_contador := 0;
      WHILE v_domingo_atual <= v_data_fim LOOP
        v_metas_criadas := v_metas_por_semana;
        IF v_contador < v_resto THEN
          v_metas_criadas := v_metas_criadas + 1;
        END IF;
        
        FOR i IN 1..v_metas_criadas LOOP
          INSERT INTO public.metas (
            usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
            data_prazo, status, criada_manualmente, carry_in, carry_out
          ) VALUES (
            NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom,
            1, 0,
            v_domingo_atual, 'no_prazo', false, 0, 0
          );
        END LOOP;
        
        v_contador := v_contador + 1;
        v_domingo_atual := v_domingo_atual + INTERVAL '7 days';
      END LOOP;
      
      -- 3. Create DAILY metas (~250 working days/year)
      -- Count actual working days
      v_dias_disponiveis := 0;
      v_data_atual := v_data_inicio;
      WHILE v_data_atual <= v_data_fim LOOP
        v_dia_semana := EXTRACT(ISODOW FROM v_data_atual);
        IF v_dia_semana BETWEEN 1 AND 5 THEN
          v_dias_disponiveis := v_dias_disponiveis + 1;
        END IF;
        v_data_atual := v_data_atual + 1;
      END LOOP;
      
      v_metas_por_dia := v_quantidade_total / v_dias_disponiveis;
      v_resto := v_quantidade_total % v_dias_disponiveis;
      
      v_contador := 0;
      v_data_atual := v_data_inicio;
      WHILE v_data_atual <= v_data_fim LOOP
        v_dia_semana := EXTRACT(ISODOW FROM v_data_atual);
        IF v_dia_semana BETWEEN 1 AND 5 THEN
          v_metas_criadas := v_metas_por_dia;
          IF v_contador < v_resto THEN
            v_metas_criadas := v_metas_criadas + 1;
          END IF;
          
          FOR i IN 1..v_metas_criadas LOOP
            INSERT INTO public.metas (
              usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
              data_prazo, status, criada_manualmente, carry_in, carry_out
            ) VALUES (
              NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom,
              1, 0,
              v_data_atual, 'no_prazo', false, 0, 0
            );
          END LOOP;
          
          v_contador := v_contador + 1;
        END IF;
        v_data_atual := v_data_atual + 1;
      END LOOP;
      
    WHEN 'mensal' THEN
      -- MONTHLY: distribute to weekly and daily metas
      v_data_inicio := DATE_TRUNC('month', v_data_fim)::DATE;
      
      -- 1. Create WEEKLY metas
      v_num_semanas := CEIL(semanas_mes(v_data_fim))::INTEGER;
      v_metas_por_semana := v_quantidade_total / v_num_semanas;
      v_resto := v_quantidade_total % v_num_semanas;
      
      -- Find first Sunday of the month
      v_domingo_atual := v_data_inicio;
      v_dia_semana := EXTRACT(ISODOW FROM v_domingo_atual);
      IF v_dia_semana != 7 THEN
        v_domingo_atual := v_domingo_atual + (7 - v_dia_semana);
      END IF;
      
      v_contador := 0;
      WHILE v_domingo_atual <= v_data_fim LOOP
        v_metas_criadas := v_metas_por_semana;
        IF v_contador < v_resto THEN
          v_metas_criadas := v_metas_criadas + 1;
        END IF;
        
        FOR i IN 1..v_metas_criadas LOOP
          INSERT INTO public.metas (
            usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
            data_prazo, status, criada_manualmente, carry_in, carry_out
          ) VALUES (
            NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom,
            1, 0,
            v_domingo_atual, 'no_prazo', false, 0, 0
          );
        END LOOP;
        
        v_contador := v_contador + 1;
        v_domingo_atual := v_domingo_atual + INTERVAL '7 days';
      END LOOP;
      
      -- 2. Create DAILY metas
      v_dias_uteis := dias_uteis_mes(v_data_fim);
      v_metas_por_dia := v_quantidade_total / v_dias_uteis;
      v_resto := v_quantidade_total % v_dias_uteis;
      
      v_contador := 0;
      v_data_atual := v_data_inicio;
      WHILE v_data_atual <= v_data_fim LOOP
        v_dia_semana := EXTRACT(ISODOW FROM v_data_atual);
        IF v_dia_semana BETWEEN 1 AND 5 THEN
          v_metas_criadas := v_metas_por_dia;
          IF v_contador < v_resto THEN
            v_metas_criadas := v_metas_criadas + 1;
          END IF;
          
          FOR i IN 1..v_metas_criadas LOOP
            INSERT INTO public.metas (
              usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
              data_prazo, status, criada_manualmente, carry_in, carry_out
            ) VALUES (
              NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom,
              1, 0,
              v_data_atual, 'no_prazo', false, 0, 0
            );
          END LOOP;
          
          v_contador := v_contador + 1;
        END IF;
        v_data_atual := v_data_atual + 1;
      END LOOP;
      
    WHEN 'semanal' THEN
      -- WEEKLY: distribute to daily metas (5 working days)
      v_data_fim := NEW.data_prazo;
      v_data_inicio := v_data_fim - 6; -- 6 days back = Monday
      
      v_dias_disponiveis := 5; -- Mon-Fri
      v_metas_por_dia := v_quantidade_total / v_dias_disponiveis;
      v_resto := v_quantidade_total % v_dias_disponiveis;
      
      v_contador := 0;
      v_data_atual := v_data_inicio;
      WHILE v_data_atual <= v_data_fim LOOP
        v_dia_semana := EXTRACT(ISODOW FROM v_data_atual);
        IF v_dia_semana BETWEEN 1 AND 5 THEN
          v_metas_criadas := v_metas_por_dia;
          IF v_contador < v_resto THEN
            v_metas_criadas := v_metas_criadas + 1;
          END IF;
          
          FOR i IN 1..v_metas_criadas LOOP
            INSERT INTO public.metas (
              usuario_id, tipo, categoria, categoria_custom, meta_pretendida, meta_realizada,
              data_prazo, status, criada_manualmente, carry_in, carry_out
            ) VALUES (
              NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom,
              1, 0,
              v_data_atual, 'no_prazo', false, 0, 0
            );
          END LOOP;
          
          v_contador := v_contador + 1;
        END IF;
        v_data_atual := v_data_atual + 1;
      END LOOP;
  END CASE;

  RETURN NEW;
END;
$$;