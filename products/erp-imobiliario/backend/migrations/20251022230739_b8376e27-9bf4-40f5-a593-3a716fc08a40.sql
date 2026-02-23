-- Corrigir função distribuir_meta_descendente removendo ON CONFLICT
CREATE OR REPLACE FUNCTION public.distribuir_meta_descendente()
RETURNS TRIGGER AS $$
DECLARE
  v_meta_diaria DECIMAL;
  v_meta_semanal DECIMAL;
  v_meta_mensal DECIMAL;
  v_meta_anual DECIMAL;
  v_data_atual DATE;
  v_data_fim DATE;
  v_data_temp DATE;
  v_dias_uteis INTEGER;
  v_semanas INTEGER;
  v_meses INTEGER;
  v_dia_semana INTEGER;
  v_existe_meta BOOLEAN;
BEGIN
  -- Só processa se a meta foi criada manualmente
  IF NOT NEW.criada_manualmente THEN
    RETURN NEW;
  END IF;

  CASE NEW.tipo
    -- META ANUAL: Distribuir para meses → semanas → dias
    WHEN 'anual' THEN
      v_meta_mensal := NEW.meta_pretendida / 12.0;
      
      -- Criar 12 metas mensais
      FOR v_meses IN 0..11 LOOP
        v_data_atual := DATE_TRUNC('year', NEW.data_prazo) + (v_meses || ' months')::INTERVAL;
        v_data_fim := (v_data_atual + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
        
        -- Contar semanas no mês
        v_semanas := CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0);
        v_meta_semanal := v_meta_mensal / v_semanas;
        
        -- Inserir meta mensal
        INSERT INTO public.metas (
          usuario_id, tipo, categoria, categoria_custom,
          meta_pretendida, data_prazo, criada_manualmente, nome, detalhes
        ) VALUES (
          NEW.usuario_id, 'mensal', NEW.categoria, NEW.categoria_custom,
          ROUND(v_meta_mensal), v_data_fim, false,
          NEW.nome, NEW.detalhes
        );
        
        -- Criar metas semanais para este mês
        FOR v_semanas IN 1..CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0) LOOP
          v_data_temp := v_data_atual::DATE + ((v_semanas - 1) * 7);
          v_data_fim := LEAST(
            v_data_temp + 6,
            (DATE_TRUNC('month', v_data_temp) + INTERVAL '1 month' - INTERVAL '1 day')::DATE
          );
          
          -- Contar dias úteis da semana
          v_dias_uteis := 0;
          v_data_temp := v_data_temp;
          WHILE v_data_temp <= v_data_fim LOOP
            v_dia_semana := EXTRACT(DOW FROM v_data_temp);
            IF v_dia_semana BETWEEN 1 AND 5 THEN
              v_dias_uteis := v_dias_uteis + 1;
            END IF;
            v_data_temp := v_data_temp + 1;
          END LOOP;
          
          v_meta_diaria := v_meta_semanal / GREATEST(v_dias_uteis, 1);
          
          -- Inserir meta semanal
          INSERT INTO public.metas (
            usuario_id, tipo, categoria, categoria_custom,
            meta_pretendida, data_prazo, criada_manualmente, nome, detalhes
          ) VALUES (
            NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom,
            ROUND(v_meta_semanal), v_data_fim, false,
            NEW.nome, NEW.detalhes
          );
          
          -- Criar metas diárias para esta semana
          v_data_temp := v_data_atual::DATE + ((v_semanas - 1) * 7);
          WHILE v_data_temp <= v_data_fim LOOP
            v_dia_semana := EXTRACT(DOW FROM v_data_temp);
            IF v_dia_semana BETWEEN 1 AND 5 THEN
              INSERT INTO public.metas (
                usuario_id, tipo, categoria, categoria_custom,
                meta_pretendida, data_prazo, criada_manualmente, nome, detalhes
              ) VALUES (
                NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom,
                ROUND(v_meta_diaria), v_data_temp, false,
                NEW.nome, NEW.detalhes
              );
            END IF;
            v_data_temp := v_data_temp + 1;
          END LOOP;
        END LOOP;
      END LOOP;

    -- META MENSAL: Distribuir para semanas → dias, Projetar para ano
    WHEN 'mensal' THEN
      -- Calcular semanas no mês
      v_data_atual := DATE_TRUNC('month', NEW.data_prazo)::DATE;
      v_data_fim := (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
      v_semanas := CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0);
      v_meta_semanal := NEW.meta_pretendida / v_semanas;
      
      -- Projetar meta anual (verificar se já existe)
      v_meta_anual := NEW.meta_pretendida * 12;
      SELECT EXISTS(
        SELECT 1 FROM public.metas
        WHERE usuario_id = NEW.usuario_id
          AND tipo = 'anual'
          AND categoria = NEW.categoria
          AND data_prazo = (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE
          AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)
      ) INTO v_existe_meta;
      
      IF NOT v_existe_meta THEN
        INSERT INTO public.metas (
          usuario_id, tipo, categoria, categoria_custom,
          meta_pretendida, data_prazo, criada_manualmente, nome, detalhes
        ) VALUES (
          NEW.usuario_id, 'anual', NEW.categoria, NEW.categoria_custom,
          ROUND(v_meta_anual), (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE,
          false, NEW.nome, NEW.detalhes
        );
      END IF;
      
      -- Criar metas semanais
      FOR v_semanas IN 1..CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0) LOOP
        v_data_temp := v_data_atual + ((v_semanas - 1) * 7);
        v_data_fim := LEAST(
          v_data_temp + 6,
          (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE
        );
        
        -- Contar dias úteis
        v_dias_uteis := 0;
        v_data_temp := v_data_temp;
        WHILE v_data_temp <= v_data_fim LOOP
          v_dia_semana := EXTRACT(DOW FROM v_data_temp);
          IF v_dia_semana BETWEEN 1 AND 5 THEN
            v_dias_uteis := v_dias_uteis + 1;
          END IF;
          v_data_temp := v_data_temp + 1;
        END LOOP;
        
        v_meta_diaria := v_meta_semanal / GREATEST(v_dias_uteis, 1);
        
        -- Inserir meta semanal
        INSERT INTO public.metas (
          usuario_id, tipo, categoria, categoria_custom,
          meta_pretendida, data_prazo, criada_manualmente, nome, detalhes
        ) VALUES (
          NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom,
          ROUND(v_meta_semanal), v_data_fim, false,
          NEW.nome, NEW.detalhes
        );
        
        -- Criar metas diárias
        v_data_temp := v_data_atual + ((v_semanas - 1) * 7);
        WHILE v_data_temp <= v_data_fim LOOP
          v_dia_semana := EXTRACT(DOW FROM v_data_temp);
          IF v_dia_semana BETWEEN 1 AND 5 THEN
            INSERT INTO public.metas (
              usuario_id, tipo, categoria, categoria_custom,
              meta_pretendida, data_prazo, criada_manualmente, nome, detalhes
            ) VALUES (
              NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom,
              ROUND(v_meta_diaria), v_data_temp, false,
              NEW.nome, NEW.detalhes
            );
          END IF;
          v_data_temp := v_data_temp + 1;
        END LOOP;
      END LOOP;

    -- META SEMANAL: Distribuir para dias, Projetar para mês → ano
    WHEN 'semanal' THEN
      -- Encontrar início da semana (segunda-feira)
      v_data_atual := NEW.data_prazo - EXTRACT(DOW FROM NEW.data_prazo)::INTEGER + 1;
      IF EXTRACT(DOW FROM NEW.data_prazo) = 0 THEN
        v_data_atual := v_data_atual - 7;
      END IF;
      
      -- Contar dias úteis (segunda a sexta)
      v_dias_uteis := 0;
      v_data_temp := v_data_atual;
      FOR i IN 0..6 LOOP
        v_dia_semana := EXTRACT(DOW FROM v_data_temp);
        IF v_dia_semana BETWEEN 1 AND 5 THEN
          v_dias_uteis := v_dias_uteis + 1;
        END IF;
        v_data_temp := v_data_temp + 1;
      END LOOP;
      
      v_meta_diaria := NEW.meta_pretendida / GREATEST(v_dias_uteis, 1);
      
      -- Projetar meta mensal (verificar se já existe)
      v_meta_mensal := NEW.meta_pretendida * 4;
      SELECT EXISTS(
        SELECT 1 FROM public.metas
        WHERE usuario_id = NEW.usuario_id
          AND tipo = 'mensal'
          AND categoria = NEW.categoria
          AND data_prazo = (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE
          AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)
      ) INTO v_existe_meta;
      
      IF NOT v_existe_meta THEN
        INSERT INTO public.metas (
          usuario_id, tipo, categoria, categoria_custom,
          meta_pretendida, data_prazo, criada_manualmente, nome, detalhes
        ) VALUES (
          NEW.usuario_id, 'mensal', NEW.categoria, NEW.categoria_custom,
          ROUND(v_meta_mensal), (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE,
          false, NEW.nome, NEW.detalhes
        );
      END IF;
      
      -- Projetar meta anual (verificar se já existe)
      v_meta_anual := v_meta_mensal * 12;
      SELECT EXISTS(
        SELECT 1 FROM public.metas
        WHERE usuario_id = NEW.usuario_id
          AND tipo = 'anual'
          AND categoria = NEW.categoria
          AND data_prazo = (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE
          AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)
      ) INTO v_existe_meta;
      
      IF NOT v_existe_meta THEN
        INSERT INTO public.metas (
          usuario_id, tipo, categoria, categoria_custom,
          meta_pretendida, data_prazo, criada_manualmente, nome, detalhes
        ) VALUES (
          NEW.usuario_id, 'anual', NEW.categoria, NEW.categoria_custom,
          ROUND(v_meta_anual), (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE,
          false, NEW.nome, NEW.detalhes
        );
      END IF;
      
      -- Criar metas diárias (segunda a sexta)
      v_data_temp := v_data_atual;
      FOR i IN 0..6 LOOP
        v_dia_semana := EXTRACT(DOW FROM v_data_temp);
        IF v_dia_semana BETWEEN 1 AND 5 THEN
          INSERT INTO public.metas (
            usuario_id, tipo, categoria, categoria_custom,
            meta_pretendida, data_prazo, criada_manualmente, nome, detalhes
          ) VALUES (
            NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom,
            ROUND(v_meta_diaria), v_data_temp, false,
            NEW.nome, NEW.detalhes
          );
        END IF;
        v_data_temp := v_data_temp + 1;
      END LOOP;

    ELSE
      -- Meta diária: não precisa distribuir
      NULL;
  END CASE;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;