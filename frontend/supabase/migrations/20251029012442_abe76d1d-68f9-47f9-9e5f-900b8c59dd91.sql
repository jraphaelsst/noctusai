-- Criar funções para calcular dias úteis restantes em cada período

-- Função para calcular dias úteis restantes na semana (considerando seg-sex)
CREATE OR REPLACE FUNCTION dias_uteis_restantes_semana(p_data_ref DATE)
RETURNS INTEGER
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_domingo DATE;
  v_dia_atual DATE;
  v_contador INTEGER := 0;
  v_dia_semana INTEGER;
BEGIN
  -- Encontrar o domingo da semana (fim da semana)
  v_domingo := p_data_ref + (7 - EXTRACT(ISODOW FROM p_data_ref)::INTEGER);
  
  -- Contar dias úteis de hoje até o domingo (inclusive hoje se for dia útil)
  v_dia_atual := p_data_ref;
  WHILE v_dia_atual <= v_domingo LOOP
    v_dia_semana := EXTRACT(ISODOW FROM v_dia_atual);
    IF v_dia_semana BETWEEN 1 AND 5 THEN -- Seg-Sex
      v_contador := v_contador + 1;
    END IF;
    v_dia_atual := v_dia_atual + 1;
  END LOOP;
  
  RETURN v_contador;
END;
$$;

-- Função para calcular dias úteis totais na semana completa
CREATE OR REPLACE FUNCTION dias_uteis_totais_semana(p_data_ref DATE)
RETURNS INTEGER
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_segunda DATE;
  v_domingo DATE;
  v_dia_atual DATE;
  v_contador INTEGER := 0;
  v_dia_semana INTEGER;
BEGIN
  -- Encontrar a segunda-feira da semana (início da semana)
  v_segunda := p_data_ref - (EXTRACT(ISODOW FROM p_data_ref)::INTEGER - 1);
  
  -- Encontrar o domingo da semana (fim da semana)
  v_domingo := v_segunda + 6;
  
  -- Contar dias úteis da semana
  v_dia_atual := v_segunda;
  WHILE v_dia_atual <= v_domingo LOOP
    v_dia_semana := EXTRACT(ISODOW FROM v_dia_atual);
    IF v_dia_semana BETWEEN 1 AND 5 THEN -- Seg-Sex
      v_contador := v_contador + 1;
    END IF;
    v_dia_atual := v_dia_atual + 1;
  END LOOP;
  
  RETURN v_contador;
END;
$$;

-- Função para calcular dias úteis restantes no mês (considerando seg-sex)
CREATE OR REPLACE FUNCTION dias_uteis_restantes_mes(p_data_ref DATE)
RETURNS INTEGER
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_ultimo_dia DATE;
  v_dia_atual DATE;
  v_contador INTEGER := 0;
  v_dia_semana INTEGER;
BEGIN
  -- Último dia do mês
  v_ultimo_dia := (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE;
  
  -- Contar dias úteis de hoje até o fim do mês (inclusive hoje se for dia útil)
  v_dia_atual := p_data_ref;
  WHILE v_dia_atual <= v_ultimo_dia LOOP
    v_dia_semana := EXTRACT(ISODOW FROM v_dia_atual);
    IF v_dia_semana BETWEEN 1 AND 5 THEN -- Seg-Sex
      v_contador := v_contador + 1;
    END IF;
    v_dia_atual := v_dia_atual + 1;
  END LOOP;
  
  RETURN v_contador;
END;
$$;

-- Função para calcular dias úteis totais no mês completo
CREATE OR REPLACE FUNCTION dias_uteis_totais_mes(p_data_ref DATE)
RETURNS INTEGER
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  -- Usar função já existente
  RETURN dias_uteis_mes(p_data_ref);
END;
$$;

-- Função para calcular dias úteis restantes no ano (considerando seg-sex)
CREATE OR REPLACE FUNCTION dias_uteis_restantes_ano(p_data_ref DATE)
RETURNS INTEGER
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_ultimo_dia DATE;
  v_dia_atual DATE;
  v_contador INTEGER := 0;
  v_dia_semana INTEGER;
BEGIN
  -- Último dia do ano (31 de dezembro)
  v_ultimo_dia := (DATE_TRUNC('year', p_data_ref) + INTERVAL '1 year - 1 day')::DATE;
  
  -- Contar dias úteis de hoje até o fim do ano (inclusive hoje se for dia útil)
  v_dia_atual := p_data_ref;
  WHILE v_dia_atual <= v_ultimo_dia LOOP
    v_dia_semana := EXTRACT(ISODOW FROM v_dia_atual);
    IF v_dia_semana BETWEEN 1 AND 5 THEN -- Seg-Sex
      v_contador := v_contador + 1;
    END IF;
    v_dia_atual := v_dia_atual + 1;
  END LOOP;
  
  RETURN v_contador;
END;
$$;

-- Função para calcular dias úteis totais no ano completo
CREATE OR REPLACE FUNCTION dias_uteis_totais_ano(p_data_ref DATE)
RETURNS INTEGER
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_primeiro_dia DATE;
  v_ultimo_dia DATE;
  v_dia_atual DATE;
  v_contador INTEGER := 0;
  v_dia_semana INTEGER;
BEGIN
  -- Primeiro dia do ano
  v_primeiro_dia := DATE_TRUNC('year', p_data_ref)::DATE;
  
  -- Último dia do ano
  v_ultimo_dia := (DATE_TRUNC('year', p_data_ref) + INTERVAL '1 year - 1 day')::DATE;
  
  -- Contar dias úteis do ano
  v_dia_atual := v_primeiro_dia;
  WHILE v_dia_atual <= v_ultimo_dia LOOP
    v_dia_semana := EXTRACT(ISODOW FROM v_dia_atual);
    IF v_dia_semana BETWEEN 1 AND 5 THEN -- Seg-Sex
      v_contador := v_contador + 1;
    END IF;
    v_dia_atual := v_dia_atual + 1;
  END LOOP;
  
  RETURN v_contador;
END;
$$;

-- Função para calcular meta proporcional baseada em dias restantes
CREATE OR REPLACE FUNCTION calcular_meta_proporcional(
  p_meta_mensal INTEGER,
  p_tipo tipo_meta,
  p_data_ref DATE
)
RETURNS INTEGER
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_dias_uteis_totais INTEGER;
  v_dias_uteis_restantes INTEGER;
  v_meta_diaria NUMERIC;
  v_resultado INTEGER;
BEGIN
  CASE p_tipo
    WHEN 'diaria' THEN
      -- Meta diária: meta mensal / dias úteis totais do mês
      v_dias_uteis_totais := dias_uteis_totais_mes(p_data_ref);
      v_resultado := CEIL(p_meta_mensal::NUMERIC / GREATEST(v_dias_uteis_totais, 1));
      
    WHEN 'semanal' THEN
      -- Meta semanal: proporcional aos dias úteis restantes na semana
      v_dias_uteis_totais := dias_uteis_totais_mes(p_data_ref);
      v_dias_uteis_restantes := dias_uteis_restantes_semana(p_data_ref);
      v_meta_diaria := p_meta_mensal::NUMERIC / GREATEST(v_dias_uteis_totais, 1);
      v_resultado := CEIL(v_meta_diaria * v_dias_uteis_restantes);
      
    WHEN 'mensal' THEN
      -- Meta mensal: proporcional aos dias úteis restantes no mês
      v_dias_uteis_totais := dias_uteis_totais_mes(p_data_ref);
      v_dias_uteis_restantes := dias_uteis_restantes_mes(p_data_ref);
      v_resultado := CEIL(p_meta_mensal::NUMERIC * v_dias_uteis_restantes::NUMERIC / GREATEST(v_dias_uteis_totais, 1));
      
    WHEN 'anual' THEN
      -- Meta anual: proporcional aos dias úteis restantes no ano
      v_dias_uteis_totais := dias_uteis_totais_ano(p_data_ref);
      v_dias_uteis_restantes := dias_uteis_restantes_ano(p_data_ref);
      -- Meta anual base = meta mensal * 12
      v_resultado := CEIL((p_meta_mensal * 12)::NUMERIC * v_dias_uteis_restantes::NUMERIC / GREATEST(v_dias_uteis_totais, 1));
  END CASE;
  
  RETURN GREATEST(v_resultado, 1); -- Garantir mínimo de 1
END;
$$;