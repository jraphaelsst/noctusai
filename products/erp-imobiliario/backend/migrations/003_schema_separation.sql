-- =====================================================================
-- 003 — Schema Separation: Move ERP objects from `public` to `erp`
--
-- Run this AFTER 001 + 002 on an existing Supabase project.
-- Moves all ERP-specific enums, sequences, tables, and functions into
-- the `erp` schema, leaving core platform tables in `public`.
--
-- Must be run as a superuser / service_role.
-- =====================================================================

BEGIN;

-- ─────────────────────────────────────────────────────────────────────
-- 1. CREATE SCHEMA + GRANT PERMISSIONS
-- ─────────────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS erp;

GRANT USAGE ON SCHEMA erp TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA erp TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA erp TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA erp TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT USAGE ON SEQUENCES TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA erp TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;

-- ─────────────────────────────────────────────────────────────────────
-- 2. MOVE ENUMS (PostgreSQL tracks by OID — column refs stay valid)
-- ─────────────────────────────────────────────────────────────────────

ALTER TYPE public.tipo_meta SET SCHEMA erp;
ALTER TYPE public.status_meta SET SCHEMA erp;
ALTER TYPE public.app_role SET SCHEMA erp;
ALTER TYPE public.categoria_meta SET SCHEMA erp;
ALTER TYPE public.conclusao_prazo_meta SET SCHEMA erp;
ALTER TYPE public.nivel_performance_meta SET SCHEMA erp;
ALTER TYPE public.etapa_funil SET SCHEMA erp;
ALTER TYPE public.tipo_atividade SET SCHEMA erp;
ALTER TYPE public.finalidade_imovel SET SCHEMA erp;
ALTER TYPE public.tipo_imovel SET SCHEMA erp;
ALTER TYPE public.categoria_permuta SET SCHEMA erp;
ALTER TYPE public.tipo_movel SET SCHEMA erp;
ALTER TYPE public.status_negociacao SET SCHEMA erp;
ALTER TYPE public.tipo_acao SET SCHEMA erp;
ALTER TYPE public.tipo_entidade SET SCHEMA erp;
ALTER TYPE public.status_match SET SCHEMA erp;

-- ─────────────────────────────────────────────────────────────────────
-- 3. MOVE SEQUENCES
-- ─────────────────────────────────────────────────────────────────────

ALTER SEQUENCE public.metas_id_seq SET SCHEMA erp;
ALTER SEQUENCE public.imoveis_id_seq SET SCHEMA erp;
ALTER SEQUENCE public.perfis_permutas_id_seq SET SCHEMA erp;
ALTER SEQUENCE public.negociacoes_id_seq SET SCHEMA erp;

-- ─────────────────────────────────────────────────────────────────────
-- 4. MOVE TABLES (auto-moves owned indexes and constraints)
-- ─────────────────────────────────────────────────────────────────────

ALTER TABLE public.funil_movimentos SET SCHEMA erp;
ALTER TABLE public.atividades SET SCHEMA erp;
ALTER TABLE public.imoveis_perfis_permutas SET SCHEMA erp;
ALTER TABLE public.negociacoes SET SCHEMA erp;
ALTER TABLE public.matches SET SCHEMA erp;
ALTER TABLE public.password_request_codes SET SCHEMA erp;
ALTER TABLE public.user_actions_log SET SCHEMA erp;
ALTER TABLE public.status_pagina SET SCHEMA erp;
ALTER TABLE public.metas SET SCHEMA erp;
ALTER TABLE public.metas_config SET SCHEMA erp;
ALTER TABLE public.clientes SET SCHEMA erp;
ALTER TABLE public.imoveis SET SCHEMA erp;
ALTER TABLE public.perfis_permutas SET SCHEMA erp;
ALTER TABLE public.ativos SET SCHEMA erp;
ALTER TABLE public.condominios SET SCHEMA erp;
ALTER TABLE public.profiles SET SCHEMA erp;
ALTER TABLE public.user_roles SET SCHEMA erp;

-- ─────────────────────────────────────────────────────────────────────
-- 5. RECREATE FUNCTIONS IN `erp` SCHEMA
-- ─────────────────────────────────────────────────────────────────────
-- Strategy: Create new erp.* functions FIRST, then update column
-- defaults to reference them, then drop old public.* functions.
-- This avoids "cannot drop because other objects depend on it" errors.

-- 5a. Utility functions (no dependents — safe to drop-and-recreate)

DROP FUNCTION IF EXISTS public.current_date_sao_paulo();
CREATE OR REPLACE FUNCTION erp.current_date_sao_paulo()
RETURNS DATE LANGUAGE SQL STABLE
AS $$ SELECT (NOW() AT TIME ZONE 'America/Sao_Paulo')::DATE; $$;

DROP FUNCTION IF EXISTS public.now_sao_paulo();
CREATE OR REPLACE FUNCTION erp.now_sao_paulo()
RETURNS TIMESTAMP WITH TIME ZONE LANGUAGE SQL STABLE
AS $$ SELECT NOW() AT TIME ZONE 'America/Sao_Paulo'; $$;

DROP FUNCTION IF EXISTS public.normalize_timestamp_sp(TIMESTAMP WITH TIME ZONE);
CREATE OR REPLACE FUNCTION erp.normalize_timestamp_sp(ts TIMESTAMP WITH TIME ZONE)
RETURNS TIMESTAMP WITH TIME ZONE LANGUAGE SQL IMMUTABLE
AS $$ SELECT ts AT TIME ZONE 'America/Sao_Paulo'; $$;

-- 5b. ID generators — CREATE NEW FIRST, then repoint defaults, then drop old

CREATE OR REPLACE FUNCTION erp.generate_meta_id()
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
DECLARE next_number INTEGER; next_id TEXT;
BEGIN
  next_number := nextval('erp.metas_id_seq')::INTEGER;
  IF next_number <= 9999 THEN next_id := 'MT' || LPAD(next_number::TEXT, 4, '0');
  ELSE next_id := 'MT' || next_number::TEXT; END IF;
  RETURN next_id;
END;
$$;

CREATE OR REPLACE FUNCTION erp.generate_imovel_id()
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
DECLARE next_number INTEGER; next_id TEXT;
BEGIN
  next_number := nextval('erp.imoveis_id_seq')::INTEGER;
  IF next_number <= 9999 THEN next_id := 'IM' || LPAD(next_number::TEXT, 4, '0');
  ELSE next_id := 'IM' || next_number::TEXT; END IF;
  RETURN next_id;
END;
$$;

CREATE OR REPLACE FUNCTION erp.generate_perfil_permuta_id()
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
DECLARE next_number INTEGER; next_id TEXT;
BEGIN
  next_number := nextval('erp.perfis_permutas_id_seq')::INTEGER;
  IF next_number <= 9999 THEN next_id := 'PP' || LPAD(next_number::TEXT, 4, '0');
  ELSE next_id := 'PP' || next_number::TEXT; END IF;
  RETURN next_id;
END;
$$;

CREATE OR REPLACE FUNCTION erp.generate_negociacao_id()
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
DECLARE next_number INTEGER; next_id TEXT;
BEGIN
  next_number := nextval('erp.negociacoes_id_seq')::INTEGER;
  IF next_number <= 9999 THEN next_id := 'NG' || LPAD(next_number::TEXT, 4, '0');
  ELSE next_id := 'NG' || next_number::TEXT; END IF;
  RETURN next_id;
END;
$$;

-- Repoint column defaults from public.* → erp.*
ALTER TABLE erp.metas ALTER COLUMN id SET DEFAULT erp.generate_meta_id();
ALTER TABLE erp.imoveis ALTER COLUMN id SET DEFAULT erp.generate_imovel_id();
ALTER TABLE erp.perfis_permutas ALTER COLUMN id SET DEFAULT erp.generate_perfil_permuta_id();
ALTER TABLE erp.negociacoes ALTER COLUMN id SET DEFAULT erp.generate_negociacao_id();

-- Now safe to drop old ID generators
DROP FUNCTION IF EXISTS public.generate_meta_id();
DROP FUNCTION IF EXISTS public.generate_imovel_id();
DROP FUNCTION IF EXISTS public.generate_perfil_permuta_id();
DROP FUNCTION IF EXISTS public.generate_negociacao_id();

-- 5c. Trigger functions — use CASCADE (drops triggers; we recreate them in step 7)

DROP FUNCTION IF EXISTS public.update_updated_at_column() CASCADE;
CREATE OR REPLACE FUNCTION erp.update_updated_at_column()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

DROP FUNCTION IF EXISTS public.set_timestamps_sp() CASCADE;
CREATE OR REPLACE FUNCTION erp.set_timestamps_sp()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    NEW.created_at := erp.now_sao_paulo();
    IF TG_TABLE_NAME IN ('clientes', 'imoveis', 'profiles', 'negociacoes', 'metas', 'metas_config') THEN
      NEW.updated_at := erp.now_sao_paulo();
    END IF;
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF TG_TABLE_NAME IN ('clientes', 'imoveis', 'profiles', 'negociacoes', 'metas', 'metas_config') THEN
      NEW.updated_at := erp.now_sao_paulo();
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP FUNCTION IF EXISTS public.set_conclusao_prazo() CASCADE;
CREATE OR REPLACE FUNCTION erp.set_conclusao_prazo()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.status = 'concluida' AND (OLD.status IS DISTINCT FROM 'concluida') THEN
      IF NEW.finalizada_em IS NULL THEN NEW.finalizada_em := now(); END IF;
      NEW.finalizada_no_prazo := (NEW.finalizada_em::date <= NEW.data_prazo);
      NEW.conclusao_prazo := CASE WHEN NEW.finalizada_em::date <= NEW.data_prazo THEN 'no_prazo' ELSE 'atrasada' END;
    ELSE
      IF NEW.conclusao_prazo IS DISTINCT FROM OLD.conclusao_prazo THEN
        RAISE EXCEPTION 'conclusao_prazo é gerenciado pelo sistema e não pode ser alterado manualmente';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP FUNCTION IF EXISTS public.atualizar_nivel_performance() CASCADE;
CREATE OR REPLACE FUNCTION erp.atualizar_nivel_performance()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  NEW.nivel_performance := erp.calcular_nivel_performance(COALESCE(NEW.meta_realizada, 0), NEW.meta_pretendida);
  RETURN NEW;
END;
$$;

DROP FUNCTION IF EXISTS public.atualizar_dias_restantes() CASCADE;
CREATE OR REPLACE FUNCTION erp.atualizar_dias_restantes()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$ BEGIN NEW.dias_restantes := NEW.data_prazo - erp.current_date_sao_paulo(); RETURN NEW; END; $$;

DROP FUNCTION IF EXISTS public.validar_alteracao_status_meta() CASCADE;
CREATE OR REPLACE FUNCTION erp.validar_alteracao_status_meta()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  IF public.has_role(auth.uid(), 'admin') THEN RETURN NEW; END IF;
  IF auth.uid() IS NULL THEN RETURN NEW; END IF;
  IF NEW.status = 'concluida' AND OLD.status != 'concluida' THEN RETURN NEW; END IF;
  IF OLD.status IS DISTINCT FROM NEW.status AND NEW.status != 'concluida' THEN
    RAISE EXCEPTION 'O status da meta é atualizado automaticamente pelo sistema';
  END IF;
  RETURN NEW;
END;
$$;

DROP FUNCTION IF EXISTS public.validar_alteracao_nivel_performance() CASCADE;
CREATE OR REPLACE FUNCTION erp.validar_alteracao_nivel_performance()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  IF public.has_role(auth.uid(), 'admin') THEN RETURN NEW; END IF;
  IF auth.uid() IS NULL THEN RETURN NEW; END IF;
  IF OLD.nivel_performance IS DISTINCT FROM NEW.nivel_performance THEN
    IF NEW.nivel_performance != erp.calcular_nivel_performance(COALESCE(NEW.meta_realizada, 0), NEW.meta_pretendida) THEN
      RAISE EXCEPTION 'O nível de performance é calculado automaticamente';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP FUNCTION IF EXISTS public.prevent_date_change_on_daily_metas() CASCADE;
CREATE OR REPLACE FUNCTION erp.prevent_date_change_on_daily_metas()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  IF public.has_role(auth.uid(), 'admin') THEN RETURN NEW; END IF;
  IF OLD.tipo = 'diaria' AND NEW.data_prazo IS DISTINCT FROM OLD.data_prazo THEN
    RAISE EXCEPTION 'Apenas administradores podem alterar a data prazo de metas diárias';
  END IF;
  RETURN NEW;
END;
$$;

DROP FUNCTION IF EXISTS public.recalcular_metas_on_mensal_change() CASCADE;
CREATE OR REPLACE FUNCTION erp.recalcular_metas_on_mensal_change()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  IF NEW.tipo = 'mensal' AND OLD.meta_pretendida IS DISTINCT FROM NEW.meta_pretendida THEN
    PERFORM erp.rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo);
    PERFORM erp.rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo - INTERVAL '1 month');
    PERFORM erp.rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo + INTERVAL '1 month');
  END IF;
  RETURN NEW;
END;
$$;

DROP FUNCTION IF EXISTS public.normalize_metas_finalizada_em() CASCADE;
CREATE OR REPLACE FUNCTION erp.normalize_metas_finalizada_em()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$ BEGIN IF NEW.finalizada_em IS NOT NULL THEN NEW.finalizada_em := erp.normalize_timestamp_sp(NEW.finalizada_em); END IF; RETURN NEW; END; $$;

DROP FUNCTION IF EXISTS public.normalize_atividades_data_execucao() CASCADE;
CREATE OR REPLACE FUNCTION erp.normalize_atividades_data_execucao()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$ BEGIN IF NEW.data_execucao IS NOT NULL THEN NEW.data_execucao := erp.normalize_timestamp_sp(NEW.data_execucao); ELSE NEW.data_execucao := erp.now_sao_paulo(); END IF; RETURN NEW; END; $$;

DROP FUNCTION IF EXISTS public.normalize_profiles_last_activity() CASCADE;
CREATE OR REPLACE FUNCTION erp.normalize_profiles_last_activity()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$ BEGIN IF NEW.last_activity_at IS NOT NULL THEN NEW.last_activity_at := erp.normalize_timestamp_sp(NEW.last_activity_at); ELSE NEW.last_activity_at := erp.now_sao_paulo(); END IF; RETURN NEW; END; $$;

DROP FUNCTION IF EXISTS public.normalize_password_codes_expires() CASCADE;
CREATE OR REPLACE FUNCTION erp.normalize_password_codes_expires()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$ BEGIN IF NEW.expires_at IS NOT NULL THEN NEW.expires_at := erp.normalize_timestamp_sp(NEW.expires_at); END IF; RETURN NEW; END; $$;

DROP FUNCTION IF EXISTS public.distribuir_meta_descendente() CASCADE;
CREATE OR REPLACE FUNCTION erp.distribuir_meta_descendente()
RETURNS TRIGGER AS $$
DECLARE
  v_meta_diaria DECIMAL; v_meta_semanal DECIMAL; v_meta_mensal DECIMAL; v_meta_anual DECIMAL;
  v_data_atual DATE; v_data_fim DATE; v_data_temp DATE;
  v_dias_uteis INTEGER; v_semanas INTEGER; v_meses INTEGER; v_dia_semana INTEGER; v_existe_meta BOOLEAN;
BEGIN
  IF NOT NEW.criada_manualmente THEN RETURN NEW; END IF;
  CASE NEW.tipo
    WHEN 'anual' THEN
      v_meta_mensal := NEW.meta_pretendida / 12.0;
      FOR v_meses IN 0..11 LOOP
        v_data_atual := DATE_TRUNC('year', NEW.data_prazo) + (v_meses || ' months')::INTERVAL;
        v_data_fim := (v_data_atual + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
        v_semanas := CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0);
        v_meta_semanal := v_meta_mensal / v_semanas;
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'mensal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_mensal), v_data_fim, false, NEW.nome, NEW.detalhes);
        FOR v_semanas IN 1..CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0) LOOP
          v_data_temp := v_data_atual::DATE + ((v_semanas - 1) * 7);
          v_data_fim := LEAST(v_data_temp + 6, (DATE_TRUNC('month', v_data_temp) + INTERVAL '1 month' - INTERVAL '1 day')::DATE);
          v_dias_uteis := 0; v_data_temp := v_data_temp;
          WHILE v_data_temp <= v_data_fim LOOP
            IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN v_dias_uteis := v_dias_uteis + 1; END IF;
            v_data_temp := v_data_temp + 1;
          END LOOP;
          v_meta_diaria := v_meta_semanal / GREATEST(v_dias_uteis, 1);
          INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
          VALUES (NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_semanal), v_data_fim, false, NEW.nome, NEW.detalhes);
          v_data_temp := v_data_atual::DATE + ((v_semanas - 1) * 7);
          WHILE v_data_temp <= v_data_fim LOOP
            IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN
              INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
              VALUES (NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_diaria), v_data_temp, false, NEW.nome, NEW.detalhes);
            END IF;
            v_data_temp := v_data_temp + 1;
          END LOOP;
        END LOOP;
      END LOOP;
    WHEN 'mensal' THEN
      v_data_atual := DATE_TRUNC('month', NEW.data_prazo)::DATE;
      v_data_fim := (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
      v_semanas := CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0);
      v_meta_semanal := NEW.meta_pretendida / v_semanas;
      v_meta_anual := NEW.meta_pretendida * 12;
      SELECT EXISTS(SELECT 1 FROM erp.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'anual' AND categoria = NEW.categoria AND data_prazo = (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)) INTO v_existe_meta;
      IF NOT v_existe_meta THEN
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'anual', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_anual), (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE, false, NEW.nome, NEW.detalhes);
      END IF;
      FOR v_semanas IN 1..CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0) LOOP
        v_data_temp := v_data_atual + ((v_semanas - 1) * 7);
        v_data_fim := LEAST(v_data_temp + 6, (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE);
        v_dias_uteis := 0; v_data_temp := v_data_temp;
        WHILE v_data_temp <= v_data_fim LOOP IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN v_dias_uteis := v_dias_uteis + 1; END IF; v_data_temp := v_data_temp + 1; END LOOP;
        v_meta_diaria := v_meta_semanal / GREATEST(v_dias_uteis, 1);
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_semanal), v_data_fim, false, NEW.nome, NEW.detalhes);
        v_data_temp := v_data_atual + ((v_semanas - 1) * 7);
        WHILE v_data_temp <= v_data_fim LOOP
          IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN
            INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
            VALUES (NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_diaria), v_data_temp, false, NEW.nome, NEW.detalhes);
          END IF;
          v_data_temp := v_data_temp + 1;
        END LOOP;
      END LOOP;
    WHEN 'semanal' THEN
      v_data_atual := NEW.data_prazo - EXTRACT(DOW FROM NEW.data_prazo)::INTEGER + 1;
      IF EXTRACT(DOW FROM NEW.data_prazo) = 0 THEN v_data_atual := v_data_atual - 7; END IF;
      v_dias_uteis := 0; v_data_temp := v_data_atual;
      FOR i IN 0..6 LOOP IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN v_dias_uteis := v_dias_uteis + 1; END IF; v_data_temp := v_data_temp + 1; END LOOP;
      v_meta_diaria := NEW.meta_pretendida / GREATEST(v_dias_uteis, 1);
      v_meta_mensal := NEW.meta_pretendida * 4;
      SELECT EXISTS(SELECT 1 FROM erp.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'mensal' AND categoria = NEW.categoria AND data_prazo = (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)) INTO v_existe_meta;
      IF NOT v_existe_meta THEN
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'mensal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_mensal), (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE, false, NEW.nome, NEW.detalhes);
      END IF;
      v_meta_anual := v_meta_mensal * 12;
      SELECT EXISTS(SELECT 1 FROM erp.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'anual' AND categoria = NEW.categoria AND data_prazo = (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)) INTO v_existe_meta;
      IF NOT v_existe_meta THEN
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'anual', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_anual), (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE, false, NEW.nome, NEW.detalhes);
      END IF;
      v_data_temp := v_data_atual;
      FOR i IN 0..6 LOOP
        IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN
          INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
          VALUES (NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_diaria), v_data_temp, false, NEW.nome, NEW.detalhes);
        END IF;
        v_data_temp := v_data_temp + 1;
      END LOOP;
    ELSE NULL;
  END CASE;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 5d. Non-trigger business logic functions (no column default deps — safe to drop first)

DROP FUNCTION IF EXISTS public.get_period_key(erp.tipo_meta, date);
CREATE OR REPLACE FUNCTION erp.get_period_key(tipo_meta erp.tipo_meta, data_ref date)
RETURNS TEXT LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  CASE tipo_meta
    WHEN 'diaria' THEN RETURN TO_CHAR(data_ref, 'YYYY-MM-DD');
    WHEN 'semanal' THEN RETURN TO_CHAR(data_ref, 'IYYY-IW');
    WHEN 'mensal' THEN RETURN TO_CHAR(data_ref, 'YYYY-MM');
    WHEN 'anual' THEN RETURN TO_CHAR(data_ref, 'YYYY');
  END CASE;
END;
$$;

DROP FUNCTION IF EXISTS public.period_end_date(erp.tipo_meta, date);
CREATE OR REPLACE FUNCTION erp.period_end_date(tipo_meta erp.tipo_meta, data_ref date)
RETURNS DATE LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  CASE tipo_meta
    WHEN 'diaria' THEN RETURN data_ref;
    WHEN 'semanal' THEN RETURN data_ref + (7 - EXTRACT(ISODOW FROM data_ref)::INTEGER);
    WHEN 'mensal' THEN RETURN (DATE_TRUNC('month', data_ref) + INTERVAL '1 month - 1 day')::DATE;
    WHEN 'anual' THEN RETURN (DATE_TRUNC('year', data_ref) + INTERVAL '1 year - 1 day')::DATE;
  END CASE;
END;
$$;

DROP FUNCTION IF EXISTS public.dias_uteis_mes(date);
CREATE OR REPLACE FUNCTION erp.dias_uteis_mes(p_data_ref date)
RETURNS integer LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = erp, public
AS $$
DECLARE v_primeiro DATE; v_ultimo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_primeiro := DATE_TRUNC('month', p_data_ref)::DATE;
  v_ultimo := (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE;
  v_dia := v_primeiro;
  WHILE v_dia <= v_ultimo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

DROP FUNCTION IF EXISTS public.semanas_mes(date);
CREATE OR REPLACE FUNCTION erp.semanas_mes(p_data_ref date)
RETURNS numeric LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = erp, public
AS $$
DECLARE v_dias INTEGER;
BEGIN
  v_dias := EXTRACT(DAY FROM (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE);
  RETURN ROUND(v_dias::numeric / 7, 2);
END;
$$;

DROP FUNCTION IF EXISTS public.dias_uteis_restantes_semana(DATE);
CREATE OR REPLACE FUNCTION erp.dias_uteis_restantes_semana(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path = erp, public
AS $$
DECLARE v_domingo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_domingo := p_data_ref + (7 - EXTRACT(ISODOW FROM p_data_ref)::INTEGER);
  v_dia := p_data_ref;
  WHILE v_dia <= v_domingo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

DROP FUNCTION IF EXISTS public.dias_uteis_totais_semana(DATE);
CREATE OR REPLACE FUNCTION erp.dias_uteis_totais_semana(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path = erp, public
AS $$
DECLARE v_segunda DATE; v_domingo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_segunda := p_data_ref - (EXTRACT(ISODOW FROM p_data_ref)::INTEGER - 1);
  v_domingo := v_segunda + 6;
  v_dia := v_segunda;
  WHILE v_dia <= v_domingo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

DROP FUNCTION IF EXISTS public.dias_uteis_restantes_mes(DATE);
CREATE OR REPLACE FUNCTION erp.dias_uteis_restantes_mes(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path = erp, public
AS $$
DECLARE v_ultimo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_ultimo := (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE;
  v_dia := p_data_ref;
  WHILE v_dia <= v_ultimo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

DROP FUNCTION IF EXISTS public.dias_uteis_totais_mes(DATE);
CREATE OR REPLACE FUNCTION erp.dias_uteis_totais_mes(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path = erp, public
AS $$ BEGIN RETURN erp.dias_uteis_mes(p_data_ref); END; $$;

DROP FUNCTION IF EXISTS public.dias_uteis_restantes_ano(DATE);
CREATE OR REPLACE FUNCTION erp.dias_uteis_restantes_ano(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path = erp, public
AS $$
DECLARE v_ultimo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_ultimo := (DATE_TRUNC('year', p_data_ref) + INTERVAL '1 year - 1 day')::DATE;
  v_dia := p_data_ref;
  WHILE v_dia <= v_ultimo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

DROP FUNCTION IF EXISTS public.dias_uteis_totais_ano(DATE);
CREATE OR REPLACE FUNCTION erp.dias_uteis_totais_ano(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path = erp, public
AS $$
DECLARE v_primeiro DATE; v_ultimo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_primeiro := DATE_TRUNC('year', p_data_ref)::DATE;
  v_ultimo := (DATE_TRUNC('year', p_data_ref) + INTERVAL '1 year - 1 day')::DATE;
  v_dia := v_primeiro;
  WHILE v_dia <= v_ultimo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

DROP FUNCTION IF EXISTS public.calcular_meta_proporcional(INTEGER, erp.tipo_meta, DATE);
CREATE OR REPLACE FUNCTION erp.calcular_meta_proporcional(p_meta_mensal INTEGER, p_tipo erp.tipo_meta, p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path = erp, public
AS $$
DECLARE v_total INTEGER; v_restantes INTEGER; v_diaria NUMERIC; v_resultado INTEGER;
BEGIN
  CASE p_tipo
    WHEN 'diaria' THEN
      v_total := erp.dias_uteis_totais_mes(p_data_ref);
      v_resultado := CEIL(p_meta_mensal::NUMERIC / GREATEST(v_total, 1));
    WHEN 'semanal' THEN
      v_total := erp.dias_uteis_totais_mes(p_data_ref);
      v_restantes := erp.dias_uteis_restantes_semana(p_data_ref);
      v_diaria := p_meta_mensal::NUMERIC / GREATEST(v_total, 1);
      v_resultado := CEIL(v_diaria * v_restantes);
    WHEN 'mensal' THEN
      v_total := erp.dias_uteis_totais_mes(p_data_ref);
      v_restantes := erp.dias_uteis_restantes_mes(p_data_ref);
      v_resultado := CEIL(p_meta_mensal::NUMERIC * v_restantes::NUMERIC / GREATEST(v_total, 1));
    WHEN 'anual' THEN
      v_total := erp.dias_uteis_totais_ano(p_data_ref);
      v_restantes := erp.dias_uteis_restantes_ano(p_data_ref);
      v_resultado := CEIL((p_meta_mensal * 12)::NUMERIC * v_restantes::NUMERIC / GREATEST(v_total, 1));
  END CASE;
  RETURN GREATEST(v_resultado, 1);
END;
$$;

DROP FUNCTION IF EXISTS public.ensure_scaffold_meta(uuid, erp.tipo_meta, erp.categoria_meta, date);
CREATE OR REPLACE FUNCTION erp.ensure_scaffold_meta(
  p_usuario_id uuid, p_tipo erp.tipo_meta, p_categoria erp.categoria_meta, p_data_ref date
)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
DECLARE v_data_prazo DATE; v_meta_id TEXT;
BEGIN
  IF p_usuario_id != auth.uid() AND NOT public.has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: não é possível acessar metas para outros usuários';
  END IF;
  v_data_prazo := erp.period_end_date(p_tipo, p_data_ref);
  SELECT id INTO v_meta_id FROM erp.metas
  WHERE usuario_id = p_usuario_id AND tipo = p_tipo AND categoria = p_categoria AND data_prazo = v_data_prazo
  ORDER BY created_at DESC LIMIT 1;
  RETURN v_meta_id;
END;
$$;

DROP FUNCTION IF EXISTS public.rollup_metas(uuid, erp.categoria_meta, date);
CREATE OR REPLACE FUNCTION erp.rollup_metas(p_usuario_id uuid, p_categoria erp.categoria_meta, p_data_ref date)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
DECLARE
  v_periodo_inicio DATE; v_periodo_fim DATE;
  v_real_bruta INTEGER; v_pretendida INTEGER; v_carry_in_prev INTEGER;
  v_acumulado INTEGER; v_real_cap INTEGER; v_carry_out_calc INTEGER;
  v_status erp.status_meta; v_meta_id TEXT; v_data_prazo DATE; v_prev_data_prazo DATE;
  v_meta_mensal INTEGER; v_semanas NUMERIC; v_hoje DATE;
BEGIN
  IF p_usuario_id != auth.uid() AND NOT public.has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado';
  END IF;
  v_hoje := erp.current_date_sao_paulo();
  SELECT meta_pretendida INTO v_meta_mensal FROM erp.metas_config
  WHERE usuario_id = p_usuario_id AND tipo = 'mensal' AND categoria = p_categoria AND ativo = true LIMIT 1;
  v_meta_mensal := COALESCE(v_meta_mensal, 0);

  -- Weekly
  v_data_prazo := erp.period_end_date('semanal', p_data_ref);
  v_periodo_inicio := v_data_prazo - 6;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := erp.period_end_date('semanal', v_periodo_inicio - 7);
  SELECT carry_out INTO v_carry_in_prev FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'semanal' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria AND data_prazo >= v_periodo_inicio AND data_prazo <= v_periodo_fim;
  v_semanas := erp.semanas_mes(p_data_ref);
  v_pretendida := CASE WHEN v_semanas > 0 THEN CEIL(v_meta_mensal::numeric / v_semanas) ELSE v_meta_mensal END;
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  v_status := CASE WHEN v_real_cap >= v_pretendida THEN 'concluida' WHEN v_hoje > v_data_prazo THEN 'atrasada' ELSE 'no_prazo' END;
  v_meta_id := erp.ensure_scaffold_meta(p_usuario_id, 'semanal', p_categoria, p_data_ref);
  IF v_meta_id IS NOT NULL THEN
    UPDATE erp.metas SET meta_pretendida = v_pretendida, meta_realizada = v_real_cap, carry_in = v_carry_in_prev, carry_out = v_carry_out_calc, status = v_status, updated_at = NOW() WHERE id = v_meta_id;
  END IF;

  -- Monthly
  v_data_prazo := erp.period_end_date('mensal', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('month', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := erp.period_end_date('mensal', v_periodo_inicio - 1);
  SELECT carry_out INTO v_carry_in_prev FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'mensal' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria AND data_prazo >= v_periodo_inicio AND data_prazo <= v_periodo_fim;
  v_pretendida := v_meta_mensal;
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  v_status := CASE WHEN v_real_cap >= v_pretendida THEN 'concluida' WHEN v_hoje > v_data_prazo THEN 'atrasada' ELSE 'no_prazo' END;
  v_meta_id := erp.ensure_scaffold_meta(p_usuario_id, 'mensal', p_categoria, p_data_ref);
  IF v_meta_id IS NOT NULL THEN
    UPDATE erp.metas SET meta_pretendida = v_pretendida, meta_realizada = v_real_cap, carry_in = v_carry_in_prev, carry_out = v_carry_out_calc, status = v_status, updated_at = NOW() WHERE id = v_meta_id;
  END IF;

  -- Annual
  v_data_prazo := erp.period_end_date('anual', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('year', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := erp.period_end_date('anual', v_periodo_inicio - 1);
  SELECT carry_out INTO v_carry_in_prev FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'anual' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria AND data_prazo >= v_periodo_inicio AND data_prazo <= v_periodo_fim;
  v_pretendida := v_meta_mensal * 12;
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  v_status := CASE WHEN v_real_cap >= v_pretendida THEN 'concluida' WHEN v_hoje > v_data_prazo THEN 'atrasada' ELSE 'no_prazo' END;
  v_meta_id := erp.ensure_scaffold_meta(p_usuario_id, 'anual', p_categoria, p_data_ref);
  IF v_meta_id IS NOT NULL THEN
    UPDATE erp.metas SET meta_pretendida = v_pretendida, meta_realizada = v_real_cap, carry_in = v_carry_in_prev, carry_out = v_carry_out_calc, status = v_status, updated_at = NOW() WHERE id = v_meta_id;
  END IF;
END;
$$;

DROP FUNCTION IF EXISTS public.concluir_meta_agrupada(text);
CREATE OR REPLACE FUNCTION erp.concluir_meta_agrupada(p_meta_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
DECLARE v_meta RECORD; v_no_prazo boolean; v_hoje DATE;
BEGIN
  v_hoje := erp.current_date_sao_paulo();
  SELECT * INTO v_meta FROM erp.metas WHERE id = p_meta_id AND tipo IN ('semanal', 'mensal', 'anual') AND usuario_id = auth.uid();
  IF NOT FOUND THEN RETURN jsonb_build_object('success', false, 'error', 'Meta não encontrada ou sem permissão'); END IF;
  IF v_meta.meta_realizada < v_meta.meta_pretendida THEN
    RETURN jsonb_build_object('success', false, 'error', 'Meta não atingida. Realize: ' || v_meta.meta_realizada || '/' || v_meta.meta_pretendida);
  END IF;
  v_no_prazo := (v_hoje <= v_meta.data_prazo);
  UPDATE erp.metas SET status = 'concluida', finalizada_em = NOW(), finalizada_no_prazo = v_no_prazo,
    conclusao_prazo = CASE WHEN v_no_prazo THEN 'no_prazo' ELSE 'atrasada' END::erp.conclusao_prazo_meta, updated_at = NOW()
  WHERE id = p_meta_id;
  RETURN jsonb_build_object('success', true, 'message', 'Meta concluída com sucesso');
END;
$$;

DROP FUNCTION IF EXISTS public.calcular_nivel_performance(INTEGER, INTEGER);
CREATE OR REPLACE FUNCTION erp.calcular_nivel_performance(p_realizada INTEGER, p_pretendida INTEGER)
RETURNS erp.nivel_performance_meta LANGUAGE plpgsql IMMUTABLE
AS $$
DECLARE v_prog NUMERIC;
BEGIN
  IF p_pretendida = 0 THEN RETURN 'baixo'; END IF;
  v_prog := (p_realizada::NUMERIC / p_pretendida::NUMERIC) * 100;
  IF v_prog >= 100 THEN RETURN 'excelente';
  ELSIF v_prog >= 80 THEN RETURN 'bom';
  ELSIF v_prog >= 50 THEN RETURN 'regular';
  ELSE RETURN 'baixo'; END IF;
END;
$$;

DROP FUNCTION IF EXISTS public.atualizar_status_metas();
CREATE OR REPLACE FUNCTION erp.atualizar_status_metas()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
DECLARE v_count INTEGER := 0; v_tmp INTEGER; v_hoje DATE; v_amanha DATE;
BEGIN
  v_hoje := erp.current_date_sao_paulo();
  v_amanha := v_hoje + 1;
  UPDATE erp.metas SET dias_restantes = data_prazo - v_hoje, updated_at = NOW() WHERE status NOT IN ('concluida');
  UPDATE erp.metas SET status = 'vence_amanha', updated_at = NOW() WHERE data_prazo = v_amanha AND status NOT IN ('concluida') AND status != 'vence_amanha';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  UPDATE erp.metas SET status = 'atrasada', updated_at = NOW() WHERE data_prazo < v_hoje AND status NOT IN ('concluida') AND status != 'atrasada';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  UPDATE erp.metas SET status = 'no_prazo', updated_at = NOW() WHERE data_prazo > v_amanha AND status NOT IN ('concluida') AND status != 'no_prazo';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  UPDATE erp.metas SET status = 'no_prazo', updated_at = NOW() WHERE data_prazo = v_hoje AND status NOT IN ('concluida', 'no_prazo') AND status != 'vence_amanha';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  RETURN jsonb_build_object('success', true, 'metas_atualizadas', v_count, 'timestamp', NOW());
END;
$$;

DROP FUNCTION IF EXISTS public.desativar_metas_usuarios_inativos();
CREATE OR REPLACE FUNCTION erp.desativar_metas_usuarios_inativos()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
DECLARE v_users INTEGER := 0; v_configs INTEGER := 0;
BEGIN
  IF auth.uid() IS NOT NULL AND NOT public.has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: apenas administradores';
  END IF;
  WITH inativos AS (SELECT id FROM erp.profiles WHERE last_activity_at < NOW() - INTERVAL '20 days')
  UPDATE erp.metas_config SET ativo = false, updated_at = NOW()
  WHERE usuario_id IN (SELECT id FROM inativos) AND ativo = true;
  GET DIAGNOSTICS v_configs = ROW_COUNT;
  SELECT COUNT(DISTINCT usuario_id) INTO v_users FROM (SELECT usuario_id FROM erp.metas_config WHERE updated_at >= NOW() - INTERVAL '1 minute' AND ativo = false) t;
  RETURN jsonb_build_object('success', true, 'usuarios_afetados', v_users, 'configs_desativadas', v_configs, 'timestamp', NOW());
END;
$$;

DROP FUNCTION IF EXISTS public.delete_expired_password_codes();
CREATE OR REPLACE FUNCTION erp.delete_expired_password_codes()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
AS $$ BEGIN DELETE FROM erp.password_request_codes WHERE expires_at < now(); END; $$;

-- 5e. get_data_sp (alias used by backend RPC calls)

CREATE OR REPLACE FUNCTION erp.get_data_sp()
RETURNS DATE LANGUAGE SQL STABLE
AS $$ SELECT (NOW() AT TIME ZONE 'America/Sao_Paulo')::DATE; $$;

-- 5f. match_ativos (from 002_ai_matching.sql)

DROP FUNCTION IF EXISTS public.match_ativos(extensions.vector, INT, FLOAT, UUID);
CREATE OR REPLACE FUNCTION erp.match_ativos(
  query_embedding extensions.vector(1536),
  match_count INT DEFAULT 50,
  similarity_threshold FLOAT DEFAULT 0.3,
  exclude_id UUID DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  similarity FLOAT
)
LANGUAGE sql STABLE
SET search_path = erp, public, extensions
AS $$
  SELECT
    a.id,
    1 - (a.embedding OPERATOR(extensions.<=>) query_embedding) AS similarity
  FROM erp.ativos a
  WHERE a.embedding IS NOT NULL
    AND (exclude_id IS NULL OR a.id != exclude_id)
    AND a.status = 'ativo'
    AND 1 - (a.embedding OPERATOR(extensions.<=>) query_embedding) > similarity_threshold
  ORDER BY a.embedding OPERATOR(extensions.<=>) query_embedding
  LIMIT match_count;
$$;

-- ─────────────────────────────────────────────────────────────────────
-- 6. UPDATE AUTH HOOK FUNCTIONS (stay in `public`, reference `erp.*`)
-- ─────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
BEGIN
  INSERT INTO erp.profiles (id, nome, email, telefone)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'nome', NEW.email),
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'telefone', '')
  );
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.assign_default_corretor_role()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO erp.user_roles (user_id, role)
  VALUES (NEW.id, 'corretor')
  ON CONFLICT (user_id, role) DO NOTHING;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.has_role(_user_id UUID, _role erp.app_role)
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT EXISTS (SELECT 1 FROM erp.user_roles WHERE user_id = _user_id AND role = _role); $$;

-- ─────────────────────────────────────────────────────────────────────
-- 7. RECREATE TRIGGERS (pointing to erp schema functions)
-- ─────────────────────────────────────────────────────────────────────
-- The CASCADE drops on trigger functions already removed the triggers.
-- Auth triggers on auth.users are NOT affected (they point to public.*).

-- Timestamp triggers (São Paulo)
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.clientes FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.imoveis FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.profiles FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.negociacoes FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.metas_config FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.atividades FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.funil_movimentos FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.user_actions_log FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.perfis_permutas FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.imoveis_perfis_permutas FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.user_roles FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.password_request_codes FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();

-- Updated_at triggers
CREATE TRIGGER update_perfis_permutas_updated_at BEFORE UPDATE ON erp.perfis_permutas FOR EACH ROW EXECUTE FUNCTION erp.update_updated_at_column();
CREATE TRIGGER update_negociacoes_updated_at BEFORE UPDATE ON erp.negociacoes FOR EACH ROW EXECUTE FUNCTION erp.update_updated_at_column();
CREATE TRIGGER update_metas_config_updated_at BEFORE UPDATE ON erp.metas_config FOR EACH ROW EXECUTE FUNCTION erp.update_updated_at_column();

-- Metas-specific triggers
CREATE TRIGGER trg_set_conclusao_prazo BEFORE UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.set_conclusao_prazo();
CREATE TRIGGER trigger_atualizar_nivel_performance BEFORE INSERT OR UPDATE OF meta_realizada, meta_pretendida ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.atualizar_nivel_performance();
CREATE TRIGGER trigger_validar_nivel_performance BEFORE UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.validar_alteracao_nivel_performance();
CREATE TRIGGER trigger_atualizar_dias_restantes BEFORE INSERT OR UPDATE OF data_prazo ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.atualizar_dias_restantes();
CREATE TRIGGER trigger_validar_status_meta BEFORE UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.validar_alteracao_status_meta();
CREATE TRIGGER prevent_date_change_trigger BEFORE UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.prevent_date_change_on_daily_metas();
CREATE TRIGGER trigger_recalcular_metas_mensal AFTER UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.recalcular_metas_on_mensal_change();

-- Timestamp normalization triggers
CREATE TRIGGER normalize_metas_finalizada_em_trigger BEFORE INSERT OR UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.normalize_metas_finalizada_em();
CREATE TRIGGER normalize_atividades_data_execucao_trigger BEFORE INSERT ON erp.atividades FOR EACH ROW EXECUTE FUNCTION erp.normalize_atividades_data_execucao();
CREATE TRIGGER normalize_profiles_last_activity_trigger BEFORE INSERT OR UPDATE ON erp.profiles FOR EACH ROW EXECUTE FUNCTION erp.normalize_profiles_last_activity();
CREATE TRIGGER normalize_password_codes_expires_trigger BEFORE INSERT ON erp.password_request_codes FOR EACH ROW EXECUTE FUNCTION erp.normalize_password_codes_expires();

-- ─────────────────────────────────────────────────────────────────────
-- 8. GRANT PERMISSIONS ON NEW OBJECTS
-- ─────────────────────────────────────────────────────────────────────

GRANT ALL ON ALL TABLES IN SCHEMA erp TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA erp TO anon, authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA erp TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA erp TO anon, authenticated, service_role;

COMMIT;

-- ─────────────────────────────────────────────────────────────────────
-- VERIFICATION (run after migration)
-- ─────────────────────────────────────────────────────────────────────
-- SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'erp' ORDER BY tablename;
-- SELECT n.nspname, p.proname FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid WHERE n.nspname = 'erp' ORDER BY p.proname;
-- SELECT n.nspname, t.typname FROM pg_type t JOIN pg_namespace n ON t.typnamespace = n.oid WHERE n.nspname = 'erp' AND t.typtype = 'e' ORDER BY t.typname;
