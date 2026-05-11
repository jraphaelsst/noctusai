-- Migration 028: search_path hardening on ERP functions
--
-- Project:   projects/keeper-trio-erp/PROJECT.md
-- Wave:      Wave 1 child B of keeper-trio-platform-triage
-- Surfaced:  2026-05-11 phase-0-triage.md (ERP §REAL_BUG #2)
--
-- Background:
--   Engineer II's `check_function_search_path_pinned` keeper detector (per
--   Supabase advisor 0011) flagged 9 ERP functions authored without an
--   explicit `SET search_path` clause. Two of them are TRIGGER bodies
--   and the rest are STABLE/IMMUTABLE/plpgsql callables; the highest-risk
--   one is `erp.delete_expired_password_codes()` — SECURITY DEFINER
--   without a pinned search_path is the textbook privilege-escalation
--   vector advisor 0011 calls out.
--
--   The other 30+ ERP functions in 003_schema_separation.sql + later
--   migrations already pin `SET search_path = erp, public` (or `''` for
--   pure SQL STABLE/IMMUTABLE bodies). These 9 are the gaps.
--
-- This migration:
--   1. CREATE OR REPLACE FUNCTION for each of the 9 with an explicit
--      `SET search_path` clause. Bodies preserved verbatim from the
--      originating migrations (003 §5a/5b/5c/5d/5e, 004 §1, 005 §0).
--   2. The TRIGGER variant (`erp.set_timestamps_sp`) is recreated last
--      so it remains the version triggers fire — both 004:28 and
--      005:11 left it without `SET search_path`; 005's body is the
--      live version (CREATE OR REPLACE supersedes 004's). Our 028 body
--      mirrors 005's column-existence check.
--   3. Idempotent — CREATE OR REPLACE on every function. Existing
--      triggers continue to reference the function by name and pick
--      up the new body transparently.
--
-- Per `feedback_mcp_migrations_mirror_file`: this file is committed
-- BEFORE being applied via mcp__claude_ai_Supabase__apply_migration.

-- ─────────────────────────────────────────────────────────────────────
-- 1. Pure-SQL date/time helpers (STABLE / IMMUTABLE)
--    Pin search_path = '' per advisor 0011 — bodies are schema-pure.
-- ─────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION erp.current_date_sao_paulo()
RETURNS DATE
LANGUAGE SQL
STABLE
SET search_path = ''
AS $$ SELECT (NOW() AT TIME ZONE 'America/Sao_Paulo')::DATE; $$;

CREATE OR REPLACE FUNCTION erp.now_sao_paulo()
RETURNS TIMESTAMP WITH TIME ZONE
LANGUAGE SQL
STABLE
SET search_path = ''
AS $$ SELECT NOW() AT TIME ZONE 'America/Sao_Paulo'; $$;

CREATE OR REPLACE FUNCTION erp.normalize_timestamp_sp(ts TIMESTAMP WITH TIME ZONE)
RETURNS TIMESTAMP WITH TIME ZONE
LANGUAGE SQL
IMMUTABLE
SET search_path = ''
AS $$ SELECT ts AT TIME ZONE 'America/Sao_Paulo'; $$;

CREATE OR REPLACE FUNCTION erp.get_data_sp()
RETURNS DATE
LANGUAGE SQL
STABLE
SET search_path = ''
AS $$ SELECT (NOW() AT TIME ZONE 'America/Sao_Paulo')::DATE; $$;

-- ─────────────────────────────────────────────────────────────────────
-- 2. plpgsql IMMUTABLE classifier (no body access to ERP tables).
-- ─────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION erp.calcular_nivel_performance(p_realizada INTEGER, p_pretendida INTEGER)
RETURNS erp.nivel_performance_meta
LANGUAGE plpgsql
IMMUTABLE
SET search_path = erp, public
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

-- ─────────────────────────────────────────────────────────────────────
-- 3. SECURITY DEFINER housekeeping — highest-risk fix (advisor 0011).
--    Without pinned search_path, a malicious user search_path could
--    shadow `erp.password_request_codes` with a same-named table they
--    own and trigger the SECURITY DEFINER context against their table.
-- ─────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION erp.delete_expired_password_codes()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = erp, public
AS $$ BEGIN DELETE FROM erp.password_request_codes WHERE expires_at < now(); END; $$;

-- ─────────────────────────────────────────────────────────────────────
-- 4. Meta-distribution TRIGGER body — exercises erp.metas table.
-- ─────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION erp.distribuir_meta_descendente()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = erp, public
AS $$
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
        v_data_atual := DATE_TRUNC('month', NEW.data_inicio + (v_meses || ' months')::INTERVAL)::DATE;
        v_data_fim := (DATE_TRUNC('month', v_data_atual) + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
        SELECT EXISTS (SELECT 1 FROM erp.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'mensal'
          AND data_inicio = v_data_atual AND data_prazo = v_data_fim) INTO v_existe_meta;
        IF NOT v_existe_meta THEN
          INSERT INTO erp.metas (usuario_id, tipo, tipo_meta, meta_pretendida, data_inicio, data_prazo,
            status, criada_manualmente, meta_pai_id)
          VALUES (NEW.usuario_id, 'mensal', NEW.tipo_meta, v_meta_mensal, v_data_atual, v_data_fim,
            'no_prazo', false, NEW.id);
        END IF;
      END LOOP;
    WHEN 'mensal' THEN
      v_data_atual := NEW.data_inicio;
      v_data_fim := NEW.data_prazo;
      v_dias_uteis := 0;
      v_data_temp := v_data_atual;
      WHILE v_data_temp <= v_data_fim LOOP
        v_dia_semana := EXTRACT(DOW FROM v_data_temp);
        IF v_dia_semana NOT IN (0, 6) THEN
          v_dias_uteis := v_dias_uteis + 1;
        END IF;
        v_data_temp := v_data_temp + 1;
      END LOOP;
      IF v_dias_uteis > 0 THEN
        v_meta_diaria := NEW.meta_pretendida / v_dias_uteis;
        v_data_temp := v_data_atual;
        WHILE v_data_temp <= v_data_fim LOOP
          v_dia_semana := EXTRACT(DOW FROM v_data_temp);
          IF v_dia_semana NOT IN (0, 6) THEN
            SELECT EXISTS (SELECT 1 FROM erp.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'diaria'
              AND data_inicio = v_data_temp AND data_prazo = v_data_temp) INTO v_existe_meta;
            IF NOT v_existe_meta THEN
              INSERT INTO erp.metas (usuario_id, tipo, tipo_meta, meta_pretendida, data_inicio, data_prazo,
                status, criada_manualmente, meta_pai_id)
              VALUES (NEW.usuario_id, 'diaria', NEW.tipo_meta, v_meta_diaria, v_data_temp, v_data_temp,
                'no_prazo', false, NEW.id);
            END IF;
          END IF;
          v_data_temp := v_data_temp + 1;
        END LOOP;
      END IF;
    WHEN 'semanal' THEN
      v_meta_diaria := NEW.meta_pretendida / 5;
      v_data_temp := NEW.data_inicio;
      WHILE v_data_temp <= NEW.data_prazo LOOP
        v_dia_semana := EXTRACT(DOW FROM v_data_temp);
        IF v_dia_semana NOT IN (0, 6) THEN
          SELECT EXISTS (SELECT 1 FROM erp.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'diaria'
            AND data_inicio = v_data_temp AND data_prazo = v_data_temp) INTO v_existe_meta;
          IF NOT v_existe_meta THEN
            INSERT INTO erp.metas (usuario_id, tipo, tipo_meta, meta_pretendida, data_inicio, data_prazo,
              status, criada_manualmente, meta_pai_id)
            VALUES (NEW.usuario_id, 'diaria', NEW.tipo_meta, v_meta_diaria, v_data_temp, v_data_temp,
              'no_prazo', false, NEW.id);
          END IF;
        END IF;
        v_data_temp := v_data_temp + 1;
      END LOOP;
    ELSE
      NULL;
  END CASE;
  RETURN NEW;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────
-- 5. Timestamp-stamp TRIGGER — recreated WITH search_path pin.
--    Reads from information_schema; we pin to erp, public so the
--    body's references resolve under a Postgres internal namespace.
-- ─────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION erp.set_timestamps_sp()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = erp, public
AS $$
DECLARE
  has_updated_at boolean;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = TG_TABLE_SCHEMA
      AND table_name = TG_TABLE_NAME
      AND column_name = 'updated_at'
  ) INTO has_updated_at;

  IF TG_OP = 'INSERT' THEN
    NEW.created_at := COALESCE(NEW.created_at, now() AT TIME ZONE 'America/Sao_Paulo');
    IF has_updated_at THEN
      NEW.updated_at := NEW.created_at;
    END IF;
  ELSIF TG_OP = 'UPDATE' THEN
    IF has_updated_at THEN
      NEW.updated_at := now() AT TIME ZONE 'America/Sao_Paulo';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────
-- Commentary anchors so future readers see the why-here.
-- ─────────────────────────────────────────────────────────────────────

COMMENT ON FUNCTION erp.delete_expired_password_codes() IS
  'SECURITY DEFINER housekeeping; search_path pinned in migration 028 '
  '(keeper-trio-erp Phase 2) per Supabase advisor 0011.';

COMMENT ON FUNCTION erp.set_timestamps_sp() IS
  'Generic created_at/updated_at trigger function; search_path pinned in '
  'migration 028 (keeper-trio-erp Phase 2). Body unchanged from migration 005.';
