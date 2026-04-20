-- ─────────────────────────────────────────────────────────────────────────────
-- 017_metas_event_pipeline.sql
--
-- Phase 5 of METAS-PLAN.md — auto-populate `erp.meta_eventos` from existing
-- ERP entities via triggers.
--
-- Scope of THIS migration:
--   - Add `captador_id` to erp.ativos (nullable UUID → erp.profiles)
--   - Relax `erp.meta_eventos.org_id` to NULLABLE (some source tables don't carry org_id directly)
--   - SQL helpers: erp.fn_resolve_pontos(), erp.fn_current_equipe()
--   - Trigger fn_meta_eventos_from_ativo  (captação)
--   - Trigger fn_meta_eventos_from_evento (visita + reunião)
--   - Trigger fn_meta_eventos_from_split  (venda via comissoes_splits)
--
-- Deferred to micro-phase 5b (needs owner sign-off — see METAS-PLAN §7):
--   - exclusividade flag on ativos + contratos
--   - evento_participantes bridge table for multi-agent visits
--   - explicit locação detection (needs a contrato→comissoes link, currently absent)
--   - one-time backfill of historical meta_eventos
--
-- All trigger functions are SECURITY DEFINER + SET search_path — they run
-- under the table owner so RLS on meta_eventos doesn't block auto-inserts.
-- ─────────────────────────────────────────────────────────────────────────────

BEGIN;

-- ─── 1. Schema additions ────────────────────────────────────────────

ALTER TABLE erp.ativos
    ADD COLUMN IF NOT EXISTS captador_id UUID REFERENCES erp.profiles(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_ativos_captador ON erp.ativos(captador_id) WHERE captador_id IS NOT NULL;

COMMENT ON COLUMN erp.ativos.captador_id IS 'Captador corretor. Nullable for legacy rows (see erp.ativos.corretor TEXT fallback).';

-- Relax the NOT NULL on meta_eventos.org_id so triggers can insert rows where
-- the source (e.g. ativos + auth.users metadata lookup) can't always resolve org.
ALTER TABLE erp.meta_eventos ALTER COLUMN org_id DROP NOT NULL;

-- ─── 2. Helpers ─────────────────────────────────────────────────────

-- Winning rule pontos for (org, period, event, modalidade). Mirrors Python resolve_rule.
CREATE OR REPLACE FUNCTION erp.fn_resolve_pontos(
    p_org_id UUID,
    p_periodo_id UUID,
    p_evento_tipo erp.tipo_evento_meta,
    p_modalidade erp.modalidade_evento
) RETURNS NUMERIC
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, erp
AS $$
DECLARE v_pontos NUMERIC;
BEGIN
    IF p_org_id IS NOT NULL AND p_periodo_id IS NOT NULL THEN
        SELECT pontos INTO v_pontos FROM erp.regras_pontuacao
        WHERE org_id = p_org_id AND vigencia_periodo_id = p_periodo_id
          AND evento_tipo = p_evento_tipo AND modalidade = p_modalidade
        LIMIT 1;
        IF FOUND THEN RETURN v_pontos; END IF;
    END IF;

    IF p_periodo_id IS NOT NULL THEN
        SELECT pontos INTO v_pontos FROM erp.regras_pontuacao
        WHERE org_id IS NULL AND vigencia_periodo_id = p_periodo_id
          AND evento_tipo = p_evento_tipo AND modalidade = p_modalidade
        LIMIT 1;
        IF FOUND THEN RETURN v_pontos; END IF;
    END IF;

    IF p_org_id IS NOT NULL THEN
        SELECT pontos INTO v_pontos FROM erp.regras_pontuacao
        WHERE org_id = p_org_id AND vigencia_periodo_id IS NULL
          AND evento_tipo = p_evento_tipo AND modalidade = p_modalidade
        LIMIT 1;
        IF FOUND THEN RETURN v_pontos; END IF;
    END IF;

    SELECT pontos INTO v_pontos FROM erp.regras_pontuacao
    WHERE org_id IS NULL AND vigencia_periodo_id IS NULL
      AND evento_tipo = p_evento_tipo AND modalidade = p_modalidade
    LIMIT 1;
    RETURN COALESCE(v_pontos, 0);
END;
$$;

COMMENT ON FUNCTION erp.fn_resolve_pontos IS 'Four-tier precedence rule lookup (see Python regras_pontuacao_service.resolve_rule).';

-- Current active team for a corretor.
CREATE OR REPLACE FUNCTION erp.fn_current_equipe(p_user_id UUID)
RETURNS UUID
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, erp
AS $$
    SELECT equipe_id FROM erp.equipe_membros
    WHERE user_id = p_user_id AND left_at IS NULL
    ORDER BY joined_at DESC
    LIMIT 1;
$$;

COMMENT ON FUNCTION erp.fn_current_equipe IS 'Active team (papel any) for the corretor at call time.';

-- Resolve org_id from a user — reads auth.users.raw_user_meta_data.
CREATE OR REPLACE FUNCTION erp.fn_org_for_user(p_user_id UUID)
RETURNS UUID
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, auth
AS $$
    SELECT (raw_user_meta_data->>'org_id')::uuid
    FROM auth.users
    WHERE id = p_user_id;
$$;

-- ─── 3. Trigger: captação from ativos INSERT ───────────────────────

CREATE OR REPLACE FUNCTION erp.fn_meta_eventos_from_ativo()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, erp
AS $$
DECLARE
    v_org_id UUID;
    v_equipe_id UUID;
    v_pontos NUMERIC;
BEGIN
    IF NEW.captador_id IS NULL THEN RETURN NEW; END IF;

    v_org_id    := erp.fn_org_for_user(NEW.captador_id);
    v_equipe_id := erp.fn_current_equipe(NEW.captador_id);
    v_pontos    := erp.fn_resolve_pontos(v_org_id, NULL, 'captacao', 'padrao');

    INSERT INTO erp.meta_eventos (
        org_id, corretor_id, equipe_id_snapshot,
        evento_tipo, modalidade, data_evento, pontos,
        referencia_tipo, referencia_id
    ) VALUES (
        v_org_id, NEW.captador_id, v_equipe_id,
        'captacao', 'padrao', NEW.created_at::date, v_pontos,
        'ativo', NEW.id
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_meta_eventos_captacao ON erp.ativos;
CREATE TRIGGER trg_meta_eventos_captacao
    AFTER INSERT ON erp.ativos
    FOR EACH ROW WHEN (NEW.captador_id IS NOT NULL)
    EXECUTE FUNCTION erp.fn_meta_eventos_from_ativo();

-- ─── 4. Trigger: visita + reunião from eventos INSERT ──────────────

CREATE OR REPLACE FUNCTION erp.fn_meta_eventos_from_evento()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, erp
AS $$
DECLARE
    v_tipo erp.tipo_evento_meta;
    v_equipe_id UUID;
    v_pontos NUMERIC;
BEGIN
    IF NEW.tipo = 'visita' THEN
        v_tipo := 'visita';
    ELSIF NEW.tipo = 'reuniao' THEN
        v_tipo := 'reuniao';
    ELSE
        RETURN NEW;
    END IF;

    v_equipe_id := erp.fn_current_equipe(NEW.corretor_id);
    v_pontos    := erp.fn_resolve_pontos(NEW.org_id, NULL, v_tipo, 'padrao');

    INSERT INTO erp.meta_eventos (
        org_id, corretor_id, equipe_id_snapshot,
        evento_tipo, modalidade, data_evento, pontos,
        referencia_tipo, referencia_id
    ) VALUES (
        NEW.org_id, NEW.corretor_id, v_equipe_id,
        v_tipo, 'padrao', NEW.data_inicio::date, v_pontos,
        'evento', NEW.id
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_meta_eventos_evento ON erp.eventos;
CREATE TRIGGER trg_meta_eventos_evento
    AFTER INSERT ON erp.eventos
    FOR EACH ROW WHEN (NEW.tipo IN ('visita', 'reuniao'))
    EXECUTE FUNCTION erp.fn_meta_eventos_from_evento();

-- ─── 5. Trigger: venda from comissoes_splits INSERT ────────────────
-- NOTE: treats all splits as 'venda' events (the current schema has no
-- venda/locação distinction on comissoes). Locação handling will land in
-- micro-phase 5b once the contrato→comissao link is clarified.

CREATE OR REPLACE FUNCTION erp.fn_meta_eventos_from_split()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, erp
AS $$
DECLARE
    v_com RECORD;
    v_modalidade erp.modalidade_evento;
    v_splits_count INT;
    v_vgv NUMERIC;
    v_fracao NUMERIC;
    v_equipe_id UUID;
    v_pontos NUMERIC;
    v_data DATE;
BEGIN
    SELECT id, valor_venda, valor_comissao, data_venda, created_at
      INTO v_com
      FROM erp.comissoes
      WHERE id = NEW.comissao_id;
    IF NOT FOUND THEN RETURN NEW; END IF;

    SELECT COUNT(*) INTO v_splits_count
      FROM erp.comissoes_splits
      WHERE comissao_id = NEW.comissao_id;

    v_modalidade := CASE WHEN v_splits_count > 1
                         THEN 'compartilhada'::erp.modalidade_evento
                         ELSE 'padrao'::erp.modalidade_evento END;

    v_fracao := CASE WHEN v_com.valor_comissao > 0
                     THEN LEAST(1.0, NEW.valor / v_com.valor_comissao)
                     ELSE 1.0 END;
    v_vgv    := v_com.valor_venda * v_fracao;

    v_equipe_id := erp.fn_current_equipe(NEW.corretor_id);
    v_pontos    := erp.fn_resolve_pontos(NEW.org_id, NULL, 'venda', v_modalidade);
    v_data      := COALESCE(v_com.data_venda, v_com.created_at::date);

    INSERT INTO erp.meta_eventos (
        org_id, corretor_id, equipe_id_snapshot,
        evento_tipo, modalidade, data_evento,
        valor_vgv, pontos, fracao,
        referencia_tipo, referencia_id
    ) VALUES (
        NEW.org_id, NEW.corretor_id, v_equipe_id,
        'venda', v_modalidade, v_data,
        v_vgv, v_pontos, v_fracao,
        'comissoes_split', NEW.id
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_meta_eventos_split ON erp.comissoes_splits;
CREATE TRIGGER trg_meta_eventos_split
    AFTER INSERT ON erp.comissoes_splits
    FOR EACH ROW
    EXECUTE FUNCTION erp.fn_meta_eventos_from_split();

COMMIT;
