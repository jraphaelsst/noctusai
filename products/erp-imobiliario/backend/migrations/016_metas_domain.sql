-- ─────────────────────────────────────────────────────────────────────────────
-- 016_metas_domain.sql
--
-- Phase 1 foundation for the Metas domain.
-- See products/erp-imobiliario/METAS-PLAN.md for full context.
--
-- Creates:
--   - Teams (equipes) + membership (equipe_membros) with history
--   - Periods (meta_periodos) with parent-child hierarchy
--   - Cascade goals at company + team level (metas_empresa, metas_equipe)
--     (individual goals extend existing erp.metas via new columns)
--   - Point rules (regras_pontuacao) — owner-tunable scoring
--   - Org-wide scoring config (metas_configuracao) — VGV→pontos weight
--   - Event fact table (meta_eventos) — one row per scoring event
--   - Closing snapshots (meta_fechamentos) — immutable period history
--
-- Extends:
--   - erp.categoria_meta enum with 'vgv'
--   - erp.tipo_meta enum with 'quinzenal', 'trimestral'
--   - erp.metas with periodo_id, equipe_id, meta_vgv, meta_vgv_realizado
--
-- Seeds:
--   - Platform-default point rules (org_id NULL) derived from the spreadsheet
--
-- RLS:
--   - admin (ERP platform admin) → full access
--   - coordenador (team leader) → read own team + members; CRUD team metas of members
--   - corretor (agent) → read own rows; CRUD own individual goals
-- ─────────────────────────────────────────────────────────────────────────────

BEGIN;

-- ─── Enum extensions ─────────────────────────────────────────────────────────
-- Values are NOT referenced within this migration (no INSERT uses them).
-- They become visible to subsequent transactions after COMMIT.

ALTER TYPE erp.categoria_meta ADD VALUE IF NOT EXISTS 'vgv';
ALTER TYPE erp.tipo_meta ADD VALUE IF NOT EXISTS 'quinzenal';
ALTER TYPE erp.tipo_meta ADD VALUE IF NOT EXISTS 'trimestral';

-- ─── New enums (Metas domain only) ───────────────────────────────────────────

CREATE TYPE erp.modalidade_evento AS ENUM ('padrao', 'compartilhada', 'exclusividade');
CREATE TYPE erp.tipo_evento_meta AS ENUM ('captacao', 'visita', 'venda', 'locacao', 'reuniao');
CREATE TYPE erp.papel_equipe AS ENUM ('lider', 'corretor');
CREATE TYPE erp.status_periodo AS ENUM ('aberto', 'em_avaliacao', 'fechado');

-- ─── Teams ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.equipes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    cor TEXT,                       -- hex color for UI (owner-configurable)
    icone TEXT,                     -- lucide icon name or emoji, owner-configurable
    lider_id UUID REFERENCES erp.profiles(id) ON DELETE SET NULL,
    ativo BOOLEAN NOT NULL DEFAULT true,
    disbanded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, nome)
);
CREATE INDEX IF NOT EXISTS ix_equipes_org ON erp.equipes(org_id) WHERE ativo = true;

COMMENT ON TABLE erp.equipes IS 'Teams (equipes) — managed by the org owner. Each has a leader (coordenador) and members.';
COMMENT ON COLUMN erp.equipes.cor IS 'Hex color used for UI badges / team branding.';
COMMENT ON COLUMN erp.equipes.icone IS 'Icon identifier (lucide or emoji) for the team.';

-- ─── Team membership (history-enabled) ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.equipe_membros (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    equipe_id UUID NOT NULL REFERENCES erp.equipes(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES erp.profiles(id) ON DELETE CASCADE,
    papel erp.papel_equipe NOT NULL DEFAULT 'corretor',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Only one active membership per (team, user). Past memberships preserved.
CREATE UNIQUE INDEX IF NOT EXISTS ux_equipe_membros_ativos
    ON erp.equipe_membros(equipe_id, user_id)
    WHERE left_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_equipe_membros_user ON erp.equipe_membros(user_id);

COMMENT ON TABLE erp.equipe_membros IS 'Team membership with history. left_at preserves historical membership.';

-- ─── Periods ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.meta_periodos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    tipo erp.tipo_meta NOT NULL,    -- quinzenal | mensal | trimestral | anual
    data_inicio DATE NOT NULL,
    data_fim DATE NOT NULL,
    parent_periodo_id UUID REFERENCES erp.meta_periodos(id) ON DELETE SET NULL,
    status erp.status_periodo NOT NULL DEFAULT 'aberto',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (data_fim >= data_inicio)
);
CREATE INDEX IF NOT EXISTS ix_meta_periodos_org_intervalo ON erp.meta_periodos(org_id, data_inicio, data_fim);
CREATE INDEX IF NOT EXISTS ix_meta_periodos_parent ON erp.meta_periodos(parent_periodo_id);

COMMENT ON TABLE erp.meta_periodos IS 'Meta evaluation periods. Quinzenal rolls up into mensal, mensal into trimestral, etc.';

-- ─── Company meta (owner-set VGV goal per period) ────────────────────────────

CREATE TABLE IF NOT EXISTS erp.metas_empresa (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id UUID NOT NULL REFERENCES erp.meta_periodos(id) ON DELETE CASCADE,
    categoria TEXT NOT NULL DEFAULT 'vgv',    -- 'vgv' in Phase 1; future categories possible
    valor_meta NUMERIC NOT NULL CHECK (valor_meta >= 0),
    definida_por UUID REFERENCES erp.profiles(id) ON DELETE SET NULL,
    definida_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    observacoes TEXT,
    UNIQUE (periodo_id, categoria)
);

COMMENT ON TABLE erp.metas_empresa IS 'Company-level meta set by the org owner. Cascades into metas_equipe.';

-- ─── Team meta (leader quota distributed by owner) ───────────────────────────

CREATE TABLE IF NOT EXISTS erp.metas_equipe (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id UUID NOT NULL REFERENCES erp.meta_periodos(id) ON DELETE CASCADE,
    equipe_id UUID NOT NULL REFERENCES erp.equipes(id) ON DELETE CASCADE,
    categoria TEXT NOT NULL DEFAULT 'vgv',
    valor_meta NUMERIC NOT NULL CHECK (valor_meta >= 0),
    definida_por UUID REFERENCES erp.profiles(id) ON DELETE SET NULL,
    definida_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (periodo_id, equipe_id, categoria)
);

COMMENT ON TABLE erp.metas_equipe IS 'Team-level meta. Sum of agent quotas within a team should not exceed this.';

-- ─── Scoring configuration (org-wide) ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.metas_configuracao (
    org_id UUID PRIMARY KEY,
    vgv_por_ponto NUMERIC NOT NULL DEFAULT 10000,   -- R$ per 1 bonus point (100K = 10 pts)
    peso_pontos NUMERIC NOT NULL DEFAULT 1.0,       -- weight in unified score
    peso_vgv NUMERIC NOT NULL DEFAULT 1.0,
    metrica_ranking_padrao TEXT NOT NULL DEFAULT 'unificado' CHECK (metrica_ranking_padrao IN ('pontos', 'vgv', 'unificado')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE erp.metas_configuracao IS 'Per-org scoring configuration: VGV→points conversion, unified score weights, default ranking metric.';

-- ─── Point rules (per event type × modality, optionally per period) ──────────

CREATE TABLE IF NOT EXISTS erp.regras_pontuacao (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID,                                    -- NULL = platform default (copied to tenant on provisioning)
    vigencia_periodo_id UUID REFERENCES erp.meta_periodos(id) ON DELETE CASCADE,
    evento_tipo erp.tipo_evento_meta NOT NULL,
    modalidade erp.modalidade_evento NOT NULL DEFAULT 'padrao',
    pontos NUMERIC NOT NULL,
    descricao TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- NULLS NOT DISTINCT lets us enforce uniqueness even when org_id or vigencia_periodo_id are NULL.
CREATE UNIQUE INDEX IF NOT EXISTS ux_regras_pontuacao_scope
    ON erp.regras_pontuacao(
        COALESCE(org_id::text, '∅'),
        COALESCE(vigencia_periodo_id::text, '∅'),
        evento_tipo,
        modalidade
    );
CREATE INDEX IF NOT EXISTS ix_regras_pontuacao_org ON erp.regras_pontuacao(org_id);

COMMENT ON TABLE erp.regras_pontuacao IS 'Point rules per event type × modality. org_id NULL = platform default. vigencia_periodo_id set = override for a specific period.';

-- ─── Event fact table (one row per scoring event) ────────────────────────────

CREATE TABLE IF NOT EXISTS erp.meta_eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    periodo_id UUID REFERENCES erp.meta_periodos(id) ON DELETE SET NULL,
    corretor_id UUID NOT NULL REFERENCES erp.profiles(id) ON DELETE CASCADE,
    equipe_id_snapshot UUID REFERENCES erp.equipes(id) ON DELETE SET NULL,
    evento_tipo erp.tipo_evento_meta NOT NULL,
    modalidade erp.modalidade_evento NOT NULL DEFAULT 'padrao',
    data_evento DATE NOT NULL,
    valor_vgv NUMERIC,                              -- only for venda/locacao
    pontos NUMERIC NOT NULL DEFAULT 0,
    fracao NUMERIC NOT NULL DEFAULT 1.0 CHECK (fracao > 0 AND fracao <= 1.0),
    referencia_tipo TEXT,                           -- 'comissoes_split' | 'evento' | 'ativo' | 'manual'
    referencia_id UUID,
    observacoes TEXT,
    ajuste_manual BOOLEAN NOT NULL DEFAULT false,
    ajustado_por UUID REFERENCES erp.profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_meta_eventos_corretor_data ON erp.meta_eventos(corretor_id, data_evento DESC);
CREATE INDEX IF NOT EXISTS ix_meta_eventos_periodo ON erp.meta_eventos(periodo_id);
CREATE INDEX IF NOT EXISTS ix_meta_eventos_equipe ON erp.meta_eventos(equipe_id_snapshot, data_evento DESC);
CREATE INDEX IF NOT EXISTS ix_meta_eventos_referencia ON erp.meta_eventos(referencia_tipo, referencia_id);

COMMENT ON TABLE erp.meta_eventos IS 'Scoring event fact table. Auto-populated by triggers on existing ERP entities (Phase 5). Manual adjustments via ajuste_manual flag.';

-- ─── Closings (immutable snapshots per period + agent) ───────────────────────

CREATE TABLE IF NOT EXISTS erp.meta_fechamentos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    periodo_id UUID NOT NULL REFERENCES erp.meta_periodos(id) ON DELETE CASCADE,
    corretor_id UUID NOT NULL REFERENCES erp.profiles(id) ON DELETE CASCADE,
    equipe_id_snapshot UUID REFERENCES erp.equipes(id) ON DELETE SET NULL,
    vgv_realizado NUMERIC NOT NULL DEFAULT 0,
    vgv_meta NUMERIC NOT NULL DEFAULT 0,
    pontos_atividade NUMERIC NOT NULL DEFAULT 0,
    pontos_vgv NUMERIC NOT NULL DEFAULT 0,
    score_unificado NUMERIC NOT NULL DEFAULT 0,
    captacoes_count INTEGER NOT NULL DEFAULT 0,
    visitas_count INTEGER NOT NULL DEFAULT 0,
    vendas_count INTEGER NOT NULL DEFAULT 0,
    locacoes_count INTEGER NOT NULL DEFAULT 0,
    reunioes_count INTEGER NOT NULL DEFAULT 0,
    snapshot_json JSONB,
    fechado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    fechado_por UUID REFERENCES erp.profiles(id) ON DELETE SET NULL,
    UNIQUE (periodo_id, corretor_id)
);
CREATE INDEX IF NOT EXISTS ix_meta_fechamentos_periodo ON erp.meta_fechamentos(periodo_id);

COMMENT ON TABLE erp.meta_fechamentos IS 'Immutable per-period per-agent closing snapshots. Populated when a periodo.status transitions to fechado.';

-- ─── Extend existing erp.metas for individual VGV + cascade link ─────────────

ALTER TABLE erp.metas
    ADD COLUMN IF NOT EXISTS periodo_id UUID REFERENCES erp.meta_periodos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS equipe_id UUID REFERENCES erp.equipes(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS meta_vgv NUMERIC,                 -- for VGV metas (R$ amount)
    ADD COLUMN IF NOT EXISTS meta_vgv_realizado NUMERIC;       -- running VGV total vs meta

CREATE INDEX IF NOT EXISTS ix_metas_periodo ON erp.metas(periodo_id);
CREATE INDEX IF NOT EXISTS ix_metas_equipe ON erp.metas(equipe_id);

COMMENT ON COLUMN erp.metas.meta_vgv IS 'VGV target amount (R$) when categoria = vgv. Integer meta_pretendida is for count-based categories.';

-- ─── Trigger: set_timestamps_sp on new tables ────────────────────────────────

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'equipes', 'meta_periodos', 'metas_empresa', 'metas_equipe',
        'metas_configuracao', 'regras_pontuacao', 'meta_eventos'
    ]
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_set_timestamps ON erp.%I;
             CREATE TRIGGER trg_set_timestamps BEFORE INSERT OR UPDATE ON erp.%I
             FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();',
            t, t
        );
    END LOOP;
END $$;

-- ─── RLS ─────────────────────────────────────────────────────────────────────

ALTER TABLE erp.equipes            ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.equipe_membros     ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.meta_periodos      ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.metas_empresa      ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.metas_equipe       ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.metas_configuracao ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.regras_pontuacao   ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.meta_eventos       ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.meta_fechamentos   ENABLE ROW LEVEL SECURITY;

-- Admin (ERP org owner/admin) full access on everything
CREATE POLICY admin_full_equipes            ON erp.equipes            FOR ALL USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)) WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
CREATE POLICY admin_full_equipe_membros     ON erp.equipe_membros     FOR ALL USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)) WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
CREATE POLICY admin_full_meta_periodos      ON erp.meta_periodos      FOR ALL USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)) WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
CREATE POLICY admin_full_metas_empresa      ON erp.metas_empresa      FOR ALL USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)) WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
CREATE POLICY admin_full_metas_equipe       ON erp.metas_equipe       FOR ALL USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)) WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
CREATE POLICY admin_full_metas_configuracao ON erp.metas_configuracao FOR ALL USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)) WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
CREATE POLICY admin_full_regras_pontuacao   ON erp.regras_pontuacao   FOR ALL USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)) WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
CREATE POLICY admin_full_meta_eventos       ON erp.meta_eventos       FOR ALL USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)) WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
CREATE POLICY admin_full_meta_fechamentos   ON erp.meta_fechamentos   FOR ALL USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)) WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));

-- Corretor: SELECT own team (equipes where member + active)
CREATE POLICY corretor_select_equipes ON erp.equipes
    FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM erp.equipe_membros m
        WHERE m.equipe_id = erp.equipes.id
          AND m.user_id = (SELECT auth.uid())
          AND m.left_at IS NULL
    ));

-- Corretor: SELECT memberships of own team
CREATE POLICY corretor_select_equipe_membros ON erp.equipe_membros
    FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM erp.equipe_membros self
        WHERE self.equipe_id = erp.equipe_membros.equipe_id
          AND self.user_id = (SELECT auth.uid())
          AND self.left_at IS NULL
    ));

-- Corretor: SELECT meta_periodos + metas_empresa + metas_equipe (read-only transparency)
CREATE POLICY corretor_select_meta_periodos ON erp.meta_periodos FOR SELECT USING (true);
CREATE POLICY corretor_select_metas_empresa ON erp.metas_empresa FOR SELECT USING (true);
CREATE POLICY corretor_select_metas_equipe  ON erp.metas_equipe  FOR SELECT USING (
    EXISTS (
        SELECT 1 FROM erp.equipe_membros m
        WHERE m.equipe_id = erp.metas_equipe.equipe_id
          AND m.user_id = (SELECT auth.uid())
          AND m.left_at IS NULL
    )
);

-- Corretor: read point rules (so UIs can show formulas)
CREATE POLICY corretor_select_regras_pontuacao ON erp.regras_pontuacao FOR SELECT USING (true);
CREATE POLICY corretor_select_metas_configuracao ON erp.metas_configuracao FOR SELECT USING (true);

-- Corretor: SELECT own events + team events (for leader visibility)
CREATE POLICY corretor_select_meta_eventos ON erp.meta_eventos
    FOR SELECT
    USING (
        corretor_id = (SELECT auth.uid())
        OR EXISTS (
            SELECT 1 FROM erp.equipe_membros lider
            WHERE lider.user_id = (SELECT auth.uid())
              AND lider.papel = 'lider'
              AND lider.left_at IS NULL
              AND lider.equipe_id = erp.meta_eventos.equipe_id_snapshot
        )
    );

-- Leader (via equipe_membros.papel='lider'): CRUD meta_eventos for team members
CREATE POLICY lider_manage_meta_eventos ON erp.meta_eventos
    FOR UPDATE
    USING (EXISTS (
        SELECT 1 FROM erp.equipe_membros lider
        WHERE lider.user_id = (SELECT auth.uid())
          AND lider.papel = 'lider'
          AND lider.left_at IS NULL
          AND lider.equipe_id = erp.meta_eventos.equipe_id_snapshot
    ));

-- Corretor: SELECT own closings + team closings (if leader)
CREATE POLICY corretor_select_meta_fechamentos ON erp.meta_fechamentos
    FOR SELECT
    USING (
        corretor_id = (SELECT auth.uid())
        OR EXISTS (
            SELECT 1 FROM erp.equipe_membros lider
            WHERE lider.user_id = (SELECT auth.uid())
              AND lider.papel = 'lider'
              AND lider.left_at IS NULL
              AND lider.equipe_id = erp.meta_fechamentos.equipe_id_snapshot
        )
    );

-- ─── Seed platform-default point rules (idempotent) ──────────────────────────

DO $seed$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM erp.regras_pontuacao WHERE org_id IS NULL AND vigencia_periodo_id IS NULL) THEN
        INSERT INTO erp.regras_pontuacao (org_id, evento_tipo, modalidade, pontos, descricao) VALUES
            (NULL, 'captacao', 'padrao',         1.0,   'Captação individual'),
            (NULL, 'captacao', 'compartilhada',  0.5,   'Captação compartilhada (corretor recebe metade)'),
            (NULL, 'captacao', 'exclusividade',  2.0,   'Captação com exclusividade'),
            (NULL, 'visita',   'padrao',         1.0,   'Visita realizada (cada participante recebe 1 ponto)'),
            (NULL, 'visita',   'compartilhada',  1.0,   'Visita com múltiplos corretores — cada um recebe 1 ponto'),
            (NULL, 'venda',    'padrao',         50.0,  'Venda individual'),
            (NULL, 'venda',    'compartilhada',  25.0,  'Venda compartilhada (por corretor)'),
            (NULL, 'venda',    'exclusividade', 125.0,  'Venda com exclusividade'),
            (NULL, 'locacao',  'padrao',         5.0,   'Locação (por locação)'),
            (NULL, 'locacao',  'compartilhada',  2.5,   'Locação compartilhada (por corretor)'),
            (NULL, 'reuniao',  'padrao',         1.0,   'Reunião — presença');
    END IF;
END
$seed$;

COMMIT;
