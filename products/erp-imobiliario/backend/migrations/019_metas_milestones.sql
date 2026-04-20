-- 019_metas_milestones.sql
-- Milestone tracking for VGV meta achievement — prevents duplicate notifications
-- when an agent crosses 50 / 80 / 100 % of their (or their team's) VGV goal.
--
-- The tracker is append-only:
--   (org_id, corretor_id, periodo_id, categoria, milestone)
-- A trigger on `meta_eventos` checks after each insert whether a new milestone
-- was crossed; if so it inserts a row here AND a notification.

SET search_path = erp, public;

CREATE TABLE IF NOT EXISTS erp.meta_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    corretor_id UUID NOT NULL,
    periodo_id UUID NOT NULL REFERENCES erp.meta_periodos(id) ON DELETE CASCADE,
    categoria TEXT NOT NULL DEFAULT 'vgv',
    milestone SMALLINT NOT NULL CHECK (milestone IN (50, 80, 100)),
    notified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, corretor_id, periodo_id, categoria, milestone)
);

CREATE INDEX IF NOT EXISTS idx_meta_milestones_corretor
    ON erp.meta_milestones (corretor_id, periodo_id);

ALTER TABLE erp.meta_milestones ENABLE ROW LEVEL SECURITY;

-- Read: the agent sees their own milestones; admins see their whole org.
-- Writes are service-role only (the trigger inserts bypass RLS).
DROP POLICY IF EXISTS "agent reads own milestones" ON erp.meta_milestones;
CREATE POLICY "agent reads own milestones"
    ON erp.meta_milestones FOR SELECT TO authenticated
    USING (corretor_id = (SELECT auth.uid()));

DROP POLICY IF EXISTS "admin reads org milestones" ON erp.meta_milestones;
CREATE POLICY "admin reads org milestones"
    ON erp.meta_milestones FOR SELECT TO authenticated
    USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));


-- ── Helper: current realized VGV + target for an (agent, period) ─────

CREATE OR REPLACE FUNCTION erp.fn_meta_progresso(
    p_corretor_id UUID,
    p_periodo_id UUID,
    p_categoria TEXT DEFAULT 'vgv'
) RETURNS TABLE (
    realizado NUMERIC,
    meta NUMERIC,
    pct NUMERIC
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = erp, public
AS $$
DECLARE
    v_realizado NUMERIC;
    v_meta NUMERIC;
    v_periodo RECORD;
BEGIN
    SELECT * INTO v_periodo FROM erp.meta_periodos WHERE id = p_periodo_id;
    IF v_periodo IS NULL THEN
        RETURN;
    END IF;

    -- Realized VGV: sum of meta_eventos.valor_vgv for this agent in the
    -- period window. For non-VGV categorias we sum pontos as the realized
    -- count (used for agent-level point goals).
    IF p_categoria = 'vgv' THEN
        SELECT COALESCE(SUM(valor_vgv), 0) INTO v_realizado
        FROM erp.meta_eventos
        WHERE corretor_id = p_corretor_id
          AND created_at >= v_periodo.data_inicio
          AND created_at <  (v_periodo.data_fim::date + INTERVAL '1 day');
    ELSE
        SELECT COALESCE(SUM(pontos), 0) INTO v_realizado
        FROM erp.meta_eventos
        WHERE corretor_id = p_corretor_id
          AND created_at >= v_periodo.data_inicio
          AND created_at <  (v_periodo.data_fim::date + INTERVAL '1 day');
    END IF;

    -- Target: agent-level meta first, team-level second (distributed equally
    -- if the agent has no personal VGV goal but belongs to a team with one).
    SELECT meta_vgv INTO v_meta
    FROM erp.metas
    WHERE corretor_id = p_corretor_id
      AND periodo_id = p_periodo_id
      AND categoria = p_categoria::erp.categoria_meta
    LIMIT 1;

    -- No personal meta → try team allocation divided by team size.
    IF v_meta IS NULL OR v_meta = 0 THEN
        SELECT (me.valor_meta / NULLIF(cnt.members, 0)) INTO v_meta
        FROM erp.equipe_membros em
        JOIN erp.metas_equipe me ON me.equipe_id = em.equipe_id
            AND me.periodo_id = p_periodo_id
            AND me.categoria = p_categoria
        JOIN LATERAL (
            SELECT COUNT(*)::NUMERIC AS members
            FROM erp.equipe_membros
            WHERE equipe_id = em.equipe_id AND left_at IS NULL
        ) cnt ON TRUE
        WHERE em.user_id = p_corretor_id AND em.left_at IS NULL
        LIMIT 1;
    END IF;

    IF v_meta IS NULL OR v_meta = 0 THEN
        RETURN;
    END IF;

    realizado := v_realizado;
    meta := v_meta;
    pct := ROUND((v_realizado / v_meta) * 100, 2);
    RETURN NEXT;
END;
$$;


-- ── Trigger: on meta_eventos insert, check milestones ─────────────────

CREATE OR REPLACE FUNCTION erp.fn_check_milestone()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = erp, public
AS $$
DECLARE
    v_periodo_id UUID;
    v_progresso RECORD;
    v_ms SMALLINT;
    v_already_notified BOOLEAN;
    v_titulo TEXT;
    v_mensagem TEXT;
BEGIN
    -- Find the currently-open periodo for this org. Milestones are computed
    -- against the open period; closed periods don't re-fire.
    SELECT id INTO v_periodo_id
    FROM erp.meta_periodos
    WHERE org_id = NEW.org_id
      AND tipo = 'quinzenal'
      AND status = 'aberto'
      AND NEW.created_at >= data_inicio
      AND NEW.created_at <  (data_fim::date + INTERVAL '1 day')
    LIMIT 1;

    IF v_periodo_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT * INTO v_progresso
    FROM erp.fn_meta_progresso(NEW.corretor_id, v_periodo_id, 'vgv');

    IF v_progresso IS NULL OR v_progresso.pct IS NULL THEN
        RETURN NEW;
    END IF;

    -- Determine which milestone (if any) has just been crossed.
    FOREACH v_ms IN ARRAY ARRAY[100, 80, 50]::SMALLINT[]
    LOOP
        IF v_progresso.pct >= v_ms THEN
            SELECT EXISTS(
                SELECT 1 FROM erp.meta_milestones
                WHERE org_id = NEW.org_id
                  AND corretor_id = NEW.corretor_id
                  AND periodo_id = v_periodo_id
                  AND categoria = 'vgv'
                  AND milestone = v_ms
            ) INTO v_already_notified;

            IF NOT v_already_notified THEN
                INSERT INTO erp.meta_milestones (
                    org_id, corretor_id, periodo_id, categoria, milestone
                ) VALUES (
                    NEW.org_id, NEW.corretor_id, v_periodo_id, 'vgv', v_ms
                );

                -- Build the notification copy per milestone.
                v_titulo := CASE v_ms
                    WHEN 100 THEN 'Meta VGV batida! 🎯'
                    WHEN  80 THEN '80% da meta VGV — quase lá!'
                    WHEN  50 THEN 'Metade da meta VGV — bom ritmo!'
                END;
                v_mensagem := 'Você atingiu ' || v_ms::TEXT || '% da sua meta VGV (R$ ' ||
                    TO_CHAR(v_progresso.realizado, 'FM999G999G999') || ' de R$ ' ||
                    TO_CHAR(v_progresso.meta, 'FM999G999G999') || ').';

                -- Dispatch the notification via the public notificacoes table —
                -- the product's notification pipeline picks it up from there.
                INSERT INTO public.notificacoes (
                    org_id, user_id, tipo, titulo, mensagem, link
                ) VALUES (
                    NEW.org_id, NEW.corretor_id, 'meta_atingida',
                    v_titulo, v_mensagem, '/metas/dashboard'
                );
            END IF;

            -- Only the *highest* newly-crossed milestone fires; lower ones
            -- are backfilled in the same insert so the user doesn't see
            -- three notifications at once when they leap from 40 → 100.
            EXIT WHEN v_already_notified;
        END IF;
    END LOOP;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_meta_milestone ON erp.meta_eventos;
CREATE TRIGGER trg_meta_milestone
    AFTER INSERT ON erp.meta_eventos
    FOR EACH ROW
    EXECUTE FUNCTION erp.fn_check_milestone();
