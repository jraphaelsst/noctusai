-- ─────────────────────────────────────────────────────────────────────────────
-- 018_metas_phase5b.sql — Phase 5b refinements to the event pipeline.
--
-- Changes:
--   - ativos.exclusividade BOOLEAN (drives 'exclusividade' modalidade)
--   - contratos.exclusividade BOOLEAN (drives modalidade for vendas/locações)
--   - comissoes.contrato_id UUID → contratos (lets the split trigger distinguish venda vs locação)
--   - evento_participantes (bridge table) for multi-agent visitas/reuniões
--   - updated fn_meta_eventos_from_ativo (honors exclusividade)
--   - updated fn_meta_eventos_from_split (venda vs locação via contrato.tipo; exclusividade)
--   - new fn_meta_eventos_from_participante (mirrors primary evento for each participant)
--   - erp.fn_backfill_meta_eventos(org_id) one-time helper
-- ─────────────────────────────────────────────────────────────────────────────

BEGIN;

-- 1. Schema additions
ALTER TABLE erp.ativos     ADD COLUMN IF NOT EXISTS exclusividade BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE erp.contratos  ADD COLUMN IF NOT EXISTS exclusividade BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE erp.comissoes  ADD COLUMN IF NOT EXISTS contrato_id UUID REFERENCES erp.contratos(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_comissoes_contrato ON erp.comissoes(contrato_id);

-- 2. evento_participantes bridge
CREATE TABLE IF NOT EXISTS erp.evento_participantes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evento_id UUID NOT NULL REFERENCES erp.eventos(id) ON DELETE CASCADE,
    corretor_id UUID NOT NULL REFERENCES erp.profiles(id) ON DELETE CASCADE,
    papel TEXT NOT NULL DEFAULT 'adicional' CHECK (papel IN ('principal','adicional')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_evento_participantes ON erp.evento_participantes(evento_id, corretor_id);
ALTER TABLE erp.evento_participantes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS admin_full_evento_participantes ON erp.evento_participantes;
CREATE POLICY admin_full_evento_participantes ON erp.evento_participantes
    FOR ALL USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role))
    WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
DROP POLICY IF EXISTS corretor_select_evento_participantes ON erp.evento_participantes;
CREATE POLICY corretor_select_evento_participantes ON erp.evento_participantes
    FOR SELECT USING (
        corretor_id = (SELECT auth.uid())
        OR EXISTS (SELECT 1 FROM erp.eventos e WHERE e.id = erp.evento_participantes.evento_id AND e.corretor_id = (SELECT auth.uid()))
    );

-- 3. Updated captação trigger (honors exclusividade)
CREATE OR REPLACE FUNCTION erp.fn_meta_eventos_from_ativo()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, erp
AS $$
DECLARE
    v_org_id UUID; v_equipe_id UUID;
    v_modalidade erp.modalidade_evento; v_pontos NUMERIC;
BEGIN
    IF NEW.captador_id IS NULL THEN RETURN NEW; END IF;
    v_org_id := erp.fn_org_for_user(NEW.captador_id);
    v_equipe_id := erp.fn_current_equipe(NEW.captador_id);
    v_modalidade := CASE WHEN NEW.exclusividade THEN 'exclusividade'::erp.modalidade_evento ELSE 'padrao'::erp.modalidade_evento END;
    v_pontos := erp.fn_resolve_pontos(v_org_id, NULL, 'captacao', v_modalidade);
    INSERT INTO erp.meta_eventos (
        org_id, corretor_id, equipe_id_snapshot,
        evento_tipo, modalidade, data_evento, pontos,
        referencia_tipo, referencia_id
    ) VALUES (
        v_org_id, NEW.captador_id, v_equipe_id,
        'captacao', v_modalidade, NEW.created_at::date, v_pontos,
        'ativo', NEW.id
    );
    RETURN NEW;
END;
$$;

-- 4. Updated split trigger (venda vs locação + exclusividade)
CREATE OR REPLACE FUNCTION erp.fn_meta_eventos_from_split()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, erp
AS $$
DECLARE
    v_com RECORD; v_contrato RECORD;
    v_tipo erp.tipo_evento_meta; v_modalidade erp.modalidade_evento;
    v_splits_count INT; v_vgv NUMERIC; v_fracao NUMERIC;
    v_equipe_id UUID; v_pontos NUMERIC; v_data DATE;
    v_exclusividade BOOLEAN := false;
BEGIN
    SELECT id, valor_venda, valor_comissao, data_venda, created_at, contrato_id
      INTO v_com FROM erp.comissoes WHERE id = NEW.comissao_id;
    IF NOT FOUND THEN RETURN NEW; END IF;

    -- Default to venda; refine via contrato when linked
    v_tipo := 'venda';
    IF v_com.contrato_id IS NOT NULL THEN
        SELECT tipo, exclusividade INTO v_contrato FROM erp.contratos WHERE id = v_com.contrato_id;
        IF FOUND THEN
            IF v_contrato.tipo = 'locacao' THEN v_tipo := 'locacao'; END IF;
            v_exclusividade := COALESCE(v_contrato.exclusividade, false);
        END IF;
    END IF;

    SELECT COUNT(*) INTO v_splits_count
      FROM erp.comissoes_splits WHERE comissao_id = NEW.comissao_id;

    v_modalidade := CASE
        WHEN v_exclusividade THEN 'exclusividade'::erp.modalidade_evento
        WHEN v_splits_count > 1 THEN 'compartilhada'::erp.modalidade_evento
        ELSE 'padrao'::erp.modalidade_evento
    END;

    v_fracao := CASE WHEN v_com.valor_comissao > 0 THEN LEAST(1.0, NEW.valor / v_com.valor_comissao) ELSE 1.0 END;
    v_vgv := v_com.valor_venda * v_fracao;

    v_equipe_id := erp.fn_current_equipe(NEW.corretor_id);
    v_pontos := erp.fn_resolve_pontos(NEW.org_id, NULL, v_tipo, v_modalidade);
    v_data := COALESCE(v_com.data_venda, v_com.created_at::date);

    INSERT INTO erp.meta_eventos (
        org_id, corretor_id, equipe_id_snapshot,
        evento_tipo, modalidade, data_evento,
        valor_vgv, pontos, fracao,
        referencia_tipo, referencia_id
    ) VALUES (
        NEW.org_id, NEW.corretor_id, v_equipe_id,
        v_tipo, v_modalidade, v_data,
        v_vgv, v_pontos, v_fracao,
        'comissoes_split', NEW.id
    );
    RETURN NEW;
END;
$$;

-- 5. New trigger: participant → mirror meta_evento for the co-agent
CREATE OR REPLACE FUNCTION erp.fn_meta_eventos_from_participante()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, erp
AS $$
DECLARE
    v_ev RECORD; v_tipo erp.tipo_evento_meta;
    v_equipe_id UUID; v_pontos NUMERIC;
BEGIN
    -- 'principal' role is already handled by fn_meta_eventos_from_evento on INSERT;
    -- only mirror for 'adicional' participants.
    IF NEW.papel = 'principal' THEN RETURN NEW; END IF;

    SELECT id, org_id, tipo, data_inicio INTO v_ev FROM erp.eventos WHERE id = NEW.evento_id;
    IF NOT FOUND THEN RETURN NEW; END IF;

    IF v_ev.tipo = 'visita' THEN v_tipo := 'visita';
    ELSIF v_ev.tipo = 'reuniao' THEN v_tipo := 'reuniao';
    ELSE RETURN NEW;
    END IF;

    v_equipe_id := erp.fn_current_equipe(NEW.corretor_id);
    v_pontos := erp.fn_resolve_pontos(v_ev.org_id, NULL, v_tipo, 'padrao');

    INSERT INTO erp.meta_eventos (
        org_id, corretor_id, equipe_id_snapshot,
        evento_tipo, modalidade, data_evento, pontos,
        referencia_tipo, referencia_id
    ) VALUES (
        v_ev.org_id, NEW.corretor_id, v_equipe_id,
        v_tipo, 'padrao', v_ev.data_inicio::date, v_pontos,
        'evento_participante', NEW.id
    );
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_meta_eventos_participante ON erp.evento_participantes;
CREATE TRIGGER trg_meta_eventos_participante
    AFTER INSERT ON erp.evento_participantes
    FOR EACH ROW EXECUTE FUNCTION erp.fn_meta_eventos_from_participante();

-- 6. Backfill helper — processes historical rows into meta_eventos.
-- Call manually: SELECT erp.fn_backfill_meta_eventos(NULL);   -- all orgs
-- Or: SELECT erp.fn_backfill_meta_eventos('<org_uuid>');       -- one tenant
CREATE OR REPLACE FUNCTION erp.fn_backfill_meta_eventos(p_org_id UUID DEFAULT NULL)
RETURNS TABLE (captacoes INT, visitas INT, vendas INT)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, erp
AS $$
DECLARE
    v_capt INT := 0; v_visit INT := 0; v_vendas INT := 0;
BEGIN
    -- Captações: only ativos with captador_id set, not already referenced
    INSERT INTO erp.meta_eventos (
        org_id, corretor_id, equipe_id_snapshot,
        evento_tipo, modalidade, data_evento, pontos,
        referencia_tipo, referencia_id
    )
    SELECT erp.fn_org_for_user(a.captador_id), a.captador_id, erp.fn_current_equipe(a.captador_id),
           'captacao',
           CASE WHEN a.exclusividade THEN 'exclusividade'::erp.modalidade_evento ELSE 'padrao'::erp.modalidade_evento END,
           a.created_at::date,
           erp.fn_resolve_pontos(erp.fn_org_for_user(a.captador_id), NULL, 'captacao',
                                 CASE WHEN a.exclusividade THEN 'exclusividade'::erp.modalidade_evento ELSE 'padrao'::erp.modalidade_evento END),
           'ativo', a.id
    FROM erp.ativos a
    WHERE a.captador_id IS NOT NULL
      AND (p_org_id IS NULL OR erp.fn_org_for_user(a.captador_id) = p_org_id)
      AND NOT EXISTS (SELECT 1 FROM erp.meta_eventos me
                      WHERE me.referencia_tipo = 'ativo' AND me.referencia_id = a.id);
    GET DIAGNOSTICS v_capt = ROW_COUNT;

    -- Visitas + reuniões (primary corretor only; participants handled via their own trigger)
    INSERT INTO erp.meta_eventos (
        org_id, corretor_id, equipe_id_snapshot,
        evento_tipo, modalidade, data_evento, pontos,
        referencia_tipo, referencia_id
    )
    SELECT e.org_id, e.corretor_id, erp.fn_current_equipe(e.corretor_id),
           e.tipo::erp.tipo_evento_meta,
           'padrao', e.data_inicio::date,
           erp.fn_resolve_pontos(e.org_id, NULL, e.tipo::erp.tipo_evento_meta, 'padrao'),
           'evento', e.id
    FROM erp.eventos e
    WHERE e.tipo IN ('visita','reuniao')
      AND (p_org_id IS NULL OR e.org_id = p_org_id)
      AND NOT EXISTS (SELECT 1 FROM erp.meta_eventos me
                      WHERE me.referencia_tipo = 'evento' AND me.referencia_id = e.id);
    GET DIAGNOSTICS v_visit = ROW_COUNT;

    -- Vendas via comissoes_splits
    INSERT INTO erp.meta_eventos (
        org_id, corretor_id, equipe_id_snapshot,
        evento_tipo, modalidade, data_evento,
        valor_vgv, pontos, fracao,
        referencia_tipo, referencia_id
    )
    SELECT cs.org_id, cs.corretor_id, erp.fn_current_equipe(cs.corretor_id),
           COALESCE((SELECT CASE WHEN c.tipo='locacao' THEN 'locacao' ELSE 'venda' END
                     FROM erp.contratos c WHERE c.id = com.contrato_id), 'venda')::erp.tipo_evento_meta,
           CASE WHEN (SELECT exclusividade FROM erp.contratos c WHERE c.id = com.contrato_id) THEN 'exclusividade'::erp.modalidade_evento
                WHEN (SELECT COUNT(*) FROM erp.comissoes_splits s2 WHERE s2.comissao_id = cs.comissao_id) > 1 THEN 'compartilhada'::erp.modalidade_evento
                ELSE 'padrao'::erp.modalidade_evento END,
           COALESCE(com.data_venda, com.created_at::date),
           com.valor_venda * (CASE WHEN com.valor_comissao > 0 THEN LEAST(1.0, cs.valor/com.valor_comissao) ELSE 1.0 END),
           erp.fn_resolve_pontos(cs.org_id, NULL,
               COALESCE((SELECT CASE WHEN c.tipo='locacao' THEN 'locacao' ELSE 'venda' END FROM erp.contratos c WHERE c.id=com.contrato_id), 'venda')::erp.tipo_evento_meta,
               CASE WHEN (SELECT exclusividade FROM erp.contratos c WHERE c.id=com.contrato_id) THEN 'exclusividade'::erp.modalidade_evento
                    WHEN (SELECT COUNT(*) FROM erp.comissoes_splits s2 WHERE s2.comissao_id=cs.comissao_id) > 1 THEN 'compartilhada'::erp.modalidade_evento
                    ELSE 'padrao'::erp.modalidade_evento END),
           CASE WHEN com.valor_comissao > 0 THEN LEAST(1.0, cs.valor/com.valor_comissao) ELSE 1.0 END,
           'comissoes_split', cs.id
    FROM erp.comissoes_splits cs
    JOIN erp.comissoes com ON com.id = cs.comissao_id
    WHERE (p_org_id IS NULL OR cs.org_id = p_org_id)
      AND NOT EXISTS (SELECT 1 FROM erp.meta_eventos me
                      WHERE me.referencia_tipo = 'comissoes_split' AND me.referencia_id = cs.id);
    GET DIAGNOSTICS v_vendas = ROW_COUNT;

    RETURN QUERY SELECT v_capt, v_visit, v_vendas;
END;
$$;

COMMIT;
