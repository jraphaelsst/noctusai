-- ============================================================================
-- IgIg — user-editable pipelines: Comercial (sales funnel) + Esteira
-- (roadmap `project-history/roadmaps/cardhub-igig-crm-2026-09.md`, wave B)
--
--   pipeline_stages     — per-org stage ROWS for both boards. Same shape as
--                         erp-imobiliario 042 / social-wiring, because the
--                         code that reads it is the SAME seed module
--                         (`noctusai_lib.domain.pipeline`).
--   pipeline_movimentos — ONE stage-transition history for both boards,
--                         written by the seed `move_card` on every change.
--
-- tarefa moves off its hardcoded 8-value `etapa` CHECK onto `etapa_id` (a
-- stage ROW): the esteira becomes editable (roadmap R3), and a rename is one
-- UPDATE of one label. The 8 old values become the esteira's default stages,
-- with the SAME slugs, so the backfill below is a slug match. `etapa` is then
-- DROPPED: every reader moved to `etapa_id` + the stage's `papel` in the same
-- change, and a text column nobody writes would silently go stale.
--
-- Column names `etapa_id` / `kanban_pos` are the seed's (`move_card` writes
-- exactly those) — naming them otherwise would need a fork of the seed.
--
-- `papel` CHECK carries IgIg's roles: 'fechado' (comercial — closing requires
-- an orçamento), 'aprovacao_cliente' + 'agendado' (esteira). The API validates
-- against `PipelineConfig.stage_roles` (app/pipelines.py); this CHECK is the
-- database half of the same closed set.
--
-- Also here, because they belong to the same esteira rework:
--   * igig.incrementar_refacoes() — the ATOMIC refação increment (smoke
--     finding 4: the read-then-write lost increments under concurrency).
--   * apontamento.profissional_id — the timer resolves the caller's
--     profissional (smoke finding 8: tarefa.responsavel_id is a profissional,
--     apontamento.usuario_id an auth user; the two never met).
--   * aprovacao.emitido_por — who minted the link, so the agency can be
--     notified when the client decides (smoke finding 4).
--
-- SQLite mirror: migrations/sqlite/017_pipeline.sql (parity-tested).
-- ============================================================================
SET search_path = igig, public;

-- ----------------------------------------------------------------------------
-- 1. pipeline_stages
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS igig.pipeline_stages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    pipeline    TEXT NOT NULL CHECK (pipeline IN ('comercial', 'esteira')),
    -- Stable machine key; immutable after creation. `label` is what users edit.
    slug        TEXT NOT NULL CHECK (slug ~ '^[a-z0-9_]+$'),
    label       TEXT NOT NULL CHECK (length(trim(label)) > 0),
    -- Design-system token, never a class string (see erp 042's header).
    cor         TEXT NOT NULL DEFAULT 'secondary'
                CHECK (cor IN ('primary', 'secondary', 'success', 'warning', 'destructive', 'muted')),
    posicao     INTEGER NOT NULL DEFAULT 0,
    papel       TEXT CHECK (papel IN ('fechado', 'aprovacao_cliente', 'agendado')),
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ,
    UNIQUE (org_id, pipeline, slug)
);

-- At most one stage per role per board, or "the Fechado stage" is ambiguous.
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_pipeline_stages_papel
    ON igig.pipeline_stages (org_id, pipeline, papel)
    WHERE papel IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_igig_pipeline_stages_board
    ON igig.pipeline_stages (org_id, pipeline, posicao);

-- ----------------------------------------------------------------------------
-- 2. pipeline_movimentos
-- ----------------------------------------------------------------------------
-- `entidade_id` is deliberately NOT an FK: one column cannot reference both
-- negocio and tarefa, and history outliving a hard-deleted card is the point of
-- an audit trail. The stage FKs are ON DELETE SET NULL: the seed's
-- `delete_stage` hard-deletes an emptied stage, and a RESTRICT here would turn
-- "delete a column that ever had a card" into an opaque 23503.
-- `responsavel_id` is nullable: the public approval portal moves a tarefa on
-- behalf of the agency's CLIENT, who has no noc user.
CREATE TABLE IF NOT EXISTS igig.pipeline_movimentos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    pipeline       TEXT NOT NULL CHECK (pipeline IN ('comercial', 'esteira')),
    entidade_id    UUID NOT NULL,
    cliente_id     UUID REFERENCES igig.cliente (id) ON DELETE SET NULL,
    de_etapa_id    UUID REFERENCES igig.pipeline_stages (id) ON DELETE SET NULL,
    para_etapa_id  UUID REFERENCES igig.pipeline_stages (id) ON DELETE SET NULL,
    responsavel_id UUID,
    motivo         TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_igig_pipeline_movimentos_entidade
    ON igig.pipeline_movimentos (org_id, pipeline, entidade_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_igig_pipeline_movimentos_cliente
    ON igig.pipeline_movimentos (org_id, cliente_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 3. Esteira defaults for every org that already has tarefas
-- ----------------------------------------------------------------------------
-- Needed BEFORE the backfill below: a tarefa can only point at a stage row
-- that exists. Orgs with no tarefas get their defaults lazily on first read
-- (`app/pipelines.py::garantir_etapas_padrao`). This VALUES list and
-- `ESTEIRA_PADRAO` there are pinned identical by `tests/test_pipelines.py`.
INSERT INTO igig.pipeline_stages (org_id, pipeline, slug, label, cor, posicao, papel)
SELECT o.org_id, 'esteira', v.slug, v.label, v.cor, v.posicao, v.papel
  FROM (SELECT DISTINCT org_id FROM igig.tarefa) AS o
 CROSS JOIN (VALUES
    ('aguardando_roteiro',      'Aguardando roteiro',      'secondary', 0, NULL),
    ('roteiro_em_producao',     'Roteiro em produção',     'primary',   1, NULL),
    ('aguardando_design',       'Aguardando design',       'secondary', 2, NULL),
    ('design_em_producao',      'Design em produção',      'primary',   3, NULL),
    ('revisao_interna',         'Revisão interna',         'warning',   4, NULL),
    ('aprovacao_cliente',       'Aprovação do cliente',    'warning',   5, 'aprovacao_cliente'),
    ('pronto_para_agendamento', 'Pronto para agendamento', 'success',   6, NULL),
    ('agendado',                'Agendado',                'success',   7, 'agendado')
 ) AS v (slug, label, cor, posicao, papel)
ON CONFLICT (org_id, pipeline, slug) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 4. tarefa → stage rows
-- ----------------------------------------------------------------------------
ALTER TABLE igig.tarefa ADD COLUMN IF NOT EXISTS etapa_id UUID
    REFERENCES igig.pipeline_stages (id);
-- NUMERIC, not integer: fractional positions make a drag ONE write (seed
-- `noctusai_lib.domain.pipeline.ordering`).
ALTER TABLE igig.tarefa ADD COLUMN IF NOT EXISTS kanban_pos NUMERIC NOT NULL DEFAULT 0;
-- Denormalised from pauta.cliente_id: the esteira filters by cliente (roadmap
-- R9) and the transition history records it without a join.
ALTER TABLE igig.tarefa ADD COLUMN IF NOT EXISTS cliente_id UUID
    REFERENCES igig.cliente (id) ON DELETE CASCADE;

UPDATE igig.tarefa AS t
   SET etapa_id = s.id
  FROM igig.pipeline_stages AS s
 WHERE s.org_id = t.org_id
   AND s.pipeline = 'esteira'
   AND s.slug = t.etapa
   AND t.etapa_id IS NULL;

UPDATE igig.tarefa AS t
   SET cliente_id = p.cliente_id
  FROM igig.pauta AS p
 WHERE p.id = t.pauta_id
   AND t.cliente_id IS NULL;

-- Verify LOUDLY before dropping the old column: a NULL etapa_id is a tarefa
-- that silently vanishes from the board.
DO $$
DECLARE v_orfas INTEGER;
BEGIN
    SELECT count(*) INTO v_orfas FROM igig.tarefa WHERE etapa_id IS NULL;
    IF v_orfas > 0 THEN
        RAISE EXCEPTION
            'tarefa.etapa_id backfill incompleto: % tarefa(s) sem etapa. '
            'Nenhuma coluna foi removida; corrija e re-execute.', v_orfas;
    END IF;
END $$;

ALTER TABLE igig.tarefa ALTER COLUMN etapa_id SET NOT NULL;
DROP INDEX IF EXISTS igig.idx_igig_tarefa_etapa;
ALTER TABLE igig.tarefa DROP COLUMN IF EXISTS etapa;

CREATE INDEX IF NOT EXISTS idx_igig_tarefa_board
    ON igig.tarefa (org_id, etapa_id, kanban_pos);
CREATE INDEX IF NOT EXISTS idx_igig_tarefa_cliente
    ON igig.tarefa (org_id, cliente_id);

-- ----------------------------------------------------------------------------
-- 5. Atomic refação increment (smoke finding 4)
-- ----------------------------------------------------------------------------
-- INVOKER, not DEFINER: an authenticated caller may only bump a tarefa RLS
-- already lets it update; the service-role portal passes org_id explicitly.
CREATE OR REPLACE FUNCTION igig.incrementar_refacoes(p_tarefa_id UUID, p_org_id UUID)
  RETURNS INTEGER
  LANGUAGE sql
  SECURITY INVOKER
  SET search_path = igig, public
AS $$
    UPDATE igig.tarefa
       SET refacoes = refacoes + 1
     WHERE id = p_tarefa_id
       AND org_id = p_org_id
    RETURNING refacoes;
$$;

REVOKE ALL ON FUNCTION igig.incrementar_refacoes(UUID, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION igig.incrementar_refacoes(UUID, UUID) TO authenticated, service_role;

-- ----------------------------------------------------------------------------
-- 6. Timer ↔ profissional, approval link ↔ who minted it
-- ----------------------------------------------------------------------------
ALTER TABLE igig.apontamento ADD COLUMN IF NOT EXISTS profissional_id UUID
    REFERENCES igig.profissional (id) ON DELETE SET NULL;
ALTER TABLE igig.aprovacao ADD COLUMN IF NOT EXISTS emitido_por UUID;

-- ----------------------------------------------------------------------------
-- 7. RLS + updated_at
-- ----------------------------------------------------------------------------
-- Org isolation for every member. Stage WRITES are additionally gated to org
-- admins at the API (`app/pipelines.py::exigir_admin_da_org`); the policy is
-- the tenant boundary, not the role check.
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['pipeline_stages', 'pipeline_movimentos']
    LOOP
        EXECUTE format('ALTER TABLE igig.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON igig.%I', t || '_org_isolation', t);
        EXECUTE format(
            'CREATE POLICY %I ON igig.%I FOR ALL TO authenticated '
            'USING (org_id = (SELECT public.current_org_id())) '
            'WITH CHECK (org_id = (SELECT public.current_org_id()))',
            t || '_org_isolation', t
        );
    END LOOP;
END $$;

DROP TRIGGER IF EXISTS trg_pipeline_stages_updated_at ON igig.pipeline_stages;
CREATE TRIGGER trg_pipeline_stages_updated_at
    BEFORE UPDATE ON igig.pipeline_stages
    FOR EACH ROW EXECUTE FUNCTION igig.set_updated_at();

NOTIFY pgrst, 'reload schema';
